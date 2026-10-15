"""Evaluación de la ingesta por modelo sobre el corpus sintético.

Métricas por modelo:
- precisión / recall de pedidos (emparejando por dirección contra la verdad)
- exactitud de campos (cantidad, ventana presente)
- error de geocodificación en metros vs verdad de terreno
- % geocodificado
- latencia y tokens (suma del corpus)

Uso (requiere credenciales; perfil 'hackathon'):
    $env:AWS_PROFILE='hackathon'
    uv run python -m experimentos.ia_ingesta.evaluar --modelos haiku sonnet
    uv run python -m experimentos.ia_ingesta.evaluar --imagenes   # casos como PNG

Sin --no-geo usa un geocodificador OFFLINE basado en la verdad de terreno (no
llama a red): mide el emparejamiento dirección->coord del propio corpus, aislando
la calidad de extracción del LLM del proveedor de geocodificación.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from evrp.ia import ClienteBedrock
from evrp.ia.ingesta import extraer, geocodificar_pedidos
from evrp.ia.ingesta.geocodificador import Geocodificador, ResultadoGeocodificacion

from .corpus import CORPUS, VERDAD_DIRECCIONES, CasoIngesta, total_pedidos

MODELOS = {
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "sonnet": "us.anthropic.claude-sonnet-4-6",
}


def _norm_dir(d: str) -> str:
    """Normaliza una dirección para emparejar: minúsculas, sin puntuación, abreviaturas."""
    t = (d or "").lower().strip()
    t = re.sub(r"[.,;]", " ", t)
    reemplazos = {
        "road": "rd", "avenue": "ave", "street": "st", "drive": "dr",
        "highway": "hwy", "trail": "trl", "circle": "cir",
    }
    palabras = [reemplazos.get(w, w) for w in t.split()]
    return " ".join(palabras)


def _parecido(a: str, b: str) -> float:
    """Similitud de direcciones robusta a sufijos (ciudad/estado) añadidos.

    Devuelve 1.0 si una dirección normalizada contiene a la otra (p. ej. el modelo
    añadió ", Ann Arbor, Michigan"); si no, usa ratio de SequenceMatcher.
    """
    na, nb = _norm_dir(a), _norm_dir(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 1.0
    # Comparación por el "núcleo" (número + calle) ignorando lo que sigue a la coma.
    ca = _norm_dir(a.split(",")[0])
    cb = _norm_dir(b.split(",")[0])
    if ca and (ca in nb or ca == cb):
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


class GeoVerdad(Geocodificador):
    """Geocodificador OFFLINE: resuelve usando la verdad de terreno del corpus.

    Empareja la dirección extraída con la clave más parecida (umbral 0.6). Sirve
    para medir extracción sin depender de un proveedor externo.
    """

    nombre = "verdad_corpus"

    def geocodificar(self, direccion, *, contexto=None):
        mejor, score = None, 0.0
        for clave, (lat, lon) in VERDAD_DIRECCIONES.items():
            s = _parecido(direccion, clave)
            if s > score:
                mejor, score = (lat, lon), s
        if mejor and score >= 0.6:
            return ResultadoGeocodificacion(lat=mejor[0], lon=mejor[1],
                                            etiqueta=direccion, confianza=score,
                                            fuente=self.nombre)
        return None


@dataclass
class MetricasModelo:
    modelo: str
    casos: int = 0
    esperados: int = 0
    extraidos: int = 0
    verdaderos_pos: int = 0
    campo_cantidad_ok: int = 0
    campo_cantidad_total: int = 0
    campo_ventana_ok: int = 0
    campo_ventana_total: int = 0
    geocodificados: int = 0
    errores_geo_m: list = None
    tokens_in: int = 0
    tokens_out: int = 0
    latencias: list = None

    def __post_init__(self):
        self.errores_geo_m = []
        self.latencias = []

    def resumen(self) -> dict:
        prec = self.verdaderos_pos / self.extraidos if self.extraidos else 0.0
        rec = self.verdaderos_pos / self.esperados if self.esperados else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        geo = sorted(self.errores_geo_m)
        lat = sorted(self.latencias)
        def pct(xs, p):
            return round(xs[min(len(xs) - 1, int(p * len(xs)))], 2) if xs else None
        return {
            "modelo": self.modelo,
            "casos": self.casos,
            "pedidos_esperados": self.esperados,
            "pedidos_extraidos": self.extraidos,
            "precision": round(prec, 3),
            "recall": round(rec, 3),
            "f1": round(f1, 3),
            "exactitud_cantidad": round(self.campo_cantidad_ok / self.campo_cantidad_total, 3)
                if self.campo_cantidad_total else None,
            "exactitud_ventana": round(self.campo_ventana_ok / self.campo_ventana_total, 3)
                if self.campo_ventana_total else None,
            "pct_geocodificado": round(self.geocodificados / self.verdaderos_pos, 3)
                if self.verdaderos_pos else 0.0,
            "error_geo_mediana_m": pct(geo, 0.5),
            "error_geo_p90_m": pct(geo, 0.9),
            "error_geo_max_m": round(geo[-1], 2) if geo else None,
            "latencia_p50_s": pct(lat, 0.5),
            "latencia_p95_s": pct(lat, 0.95),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_in + self.tokens_out,
        }


def _emparejar(extraidos: list, esperados: list) -> list:
    """Empareja pedidos extraídos con esperados por similitud de dirección (greedy)."""
    pares = []
    usados = set()
    for e in esperados:
        mejor_j, mejor_s = None, 0.0
        for j, x in enumerate(extraidos):
            if j in usados:
                continue
            s = _parecido(x.get("direccion", ""), e.direccion)
            if s > mejor_s:
                mejor_j, mejor_s = j, s
        if mejor_j is not None and mejor_s >= 0.6:
            usados.add(mejor_j)
            pares.append((extraidos[mejor_j], e))
        else:
            pares.append((None, e))
    return pares


def evaluar_modelo(modelo_id: str, cliente: ClienteBedrock, *, usar_imagen: bool,
                   geo: Geocodificador, verbose: bool = False) -> MetricasModelo:
    from experimentos.bedrock.png_texto import png_con_texto

    m = MetricasModelo(modelo=modelo_id)
    for caso in CORPUS:
        m.casos += 1
        m.esperados += len(caso.esperados)
        if usar_imagen:
            lineas = [ln for ln in caso.texto.splitlines() if ln.strip()][:12]
            img = png_con_texto(lineas or [caso.texto[:40]])
            out = extraer(imagen=img, contexto="ciudad: Ann Arbor, Michigan",
                          cliente=cliente, modelo=modelo_id)
        else:
            out = extraer(texto=caso.texto, contexto="ciudad: Ann Arbor, Michigan",
                          cliente=cliente, modelo=modelo_id)
        extraidos = out["pedidos"]
        m.extraidos += len(extraidos)
        m.tokens_in += out["uso"]["tokens_in"]
        m.tokens_out += out["uso"]["tokens_out"]
        if out["uso"]["latencia_s"]:
            m.latencias.append(out["uso"]["latencia_s"])

        geores = geocodificar_pedidos(extraidos, geo, contexto="Ann Arbor, Michigan")
        extraidos = geores["pedidos"]

        for ext, esp in _emparejar(extraidos, caso.esperados):
            if ext is None:
                continue
            m.verdaderos_pos += 1
            # Exactitud de campos.
            if esp.cantidad is not None:
                m.campo_cantidad_total += 1
                if ext.get("cantidad") == esp.cantidad:
                    m.campo_cantidad_ok += 1
            if esp.ventana is not None:
                m.campo_ventana_total += 1
                if ext.get("ventana"):
                    m.campo_ventana_ok += 1
            # Geocodificación vs verdad.
            vc = esp.verdad_coord()
            if ext.get("lat") is not None and ext.get("lon") is not None:
                m.geocodificados += 1
                if vc:
                    m.errores_geo_m.append(_haversine_m(ext["lat"], ext["lon"], vc[0], vc[1]))
        if verbose:
            print(f"  {caso.id}: extraidos={len(extraidos)} esperados={len(caso.esperados)}")
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evalúa la ingesta por modelo.")
    ap.add_argument("--modelos", nargs="+", default=["haiku", "sonnet"],
                    help="alias (haiku, sonnet) o IDs completos")
    ap.add_argument("--perfil", default="hackathon")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--imagenes", action="store_true", help="evalúa con PNG en vez de texto")
    ap.add_argument("--salida", default="experimentos/ia_ingesta/resultados.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    geo = GeoVerdad()
    resultados = []
    for alias in args.modelos:
        modelo_id = MODELOS.get(alias, alias)
        print(f"== {alias} ({modelo_id}) {'[imagen]' if args.imagenes else '[texto]'} ==",
              file=sys.stderr)
        try:
            cliente = ClienteBedrock(region=args.region, modelo=modelo_id, perfil=args.perfil)
        except Exception as exc:  # noqa: BLE001
            print(f"  no disponible: {exc}", file=sys.stderr)
            continue
        t0 = time.perf_counter()
        m = evaluar_modelo(modelo_id, cliente, usar_imagen=args.imagenes, geo=geo,
                           verbose=args.verbose)
        res = m.resumen()
        res["modalidad"] = "imagen" if args.imagenes else "texto"
        res["segundos_totales"] = round(time.perf_counter() - t0, 1)
        resultados.append(res)
        print(json.dumps(res, ensure_ascii=False, indent=2), file=sys.stderr)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    datos = {"corpus_casos": len(CORPUS), "corpus_pedidos": total_pedidos(),
             "resultados": resultados}
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEscrito {salida}")


if __name__ == "__main__":
    main()
