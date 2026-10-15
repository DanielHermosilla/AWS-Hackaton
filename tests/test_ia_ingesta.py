"""Pruebas de la ingesta de pedidos (texto/imagen -> pedidos -> nodos).

Sin red por defecto: se inyectan dobles del cliente Bedrock (`FakeConverse`) y de
los geocodificadores (fakes y `transporte` para Nominatim). Un único test marcado
`@pytest.mark.bedrock` hace una llamada real y se salta si no hay credenciales.
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path

import pytest

from evrp.ia import ClienteBedrock
from evrp.ia.ingesta import (
    AmazonLocation,
    GeocodificadorNulo,
    Nominatim,
    ResultadoGeocodificacion,
    a_nodos,
    en_area,
    escribir_csv,
    extraer,
    geocodificar_pedidos,
)

DATA = Path(__file__).resolve().parents[1] / "data"
CSV_BASE = DATA / "competition_routing_nodes.csv"


# ------------------------------------------------------------- dobles Bedrock
class FakeConverse:
    """Imita bedrock-runtime.converse devolviendo un bloque toolUse programado."""

    def __init__(self, pedidos, advertencias=None, in_tok=100, out_tok=50):
        self._entrada = {"pedidos": pedidos, "advertencias": advertencias or []}
        self._in, self._out = in_tok, out_tok
        self.ultima_llamada = None

    def converse(self, **kwargs):
        self.ultima_llamada = kwargs
        return {
            "output": {"message": {"content": [
                {"toolUse": {"toolUseId": "t1", "name": "registrar_pedidos",
                             "input": self._entrada}},
            ]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": self._in, "outputTokens": self._out},
        }


class GeoFake(GeocodificadorNulo):
    """Geocodificador doble: mapea direcciones conocidas a coordenadas fijas."""

    nombre = "fake"

    def __init__(self, mapa):
        self._mapa = mapa

    def geocodificar(self, direccion, *, contexto=None):
        if direccion in self._mapa:
            lat, lon = self._mapa[direccion]
            return ResultadoGeocodificacion(lat=lat, lon=lon, etiqueta=direccion,
                                            confianza=0.9, fuente=self.nombre)
        return None


# ------------------------------------------------------------- extraer (texto)
def test_extraer_con_cliente_fake_devuelve_contrato():
    fake = FakeConverse(
        pedidos=[{"id_sugerido": "P1", "direccion": "100 Briarwood Circle",
                  "nombre": "Mariana", "cantidad": 3, "confianza": 0.9}],
        advertencias=["ok"])
    c = ClienteBedrock(cliente=fake)
    out = extraer(texto="entregar en 100 Briarwood Circle, 3 cajas, Mariana", cliente=c)
    assert set(out) == {"pedidos", "advertencias", "uso"}
    assert len(out["pedidos"]) == 1
    p = out["pedidos"][0]
    assert set(p) == {"id_sugerido", "nombre", "direccion", "lat", "lon",
                      "cantidad", "ventana", "notas", "confianza"}
    assert p["direccion"] == "100 Briarwood Circle"
    assert p["cantidad"] == 3.0
    assert out["uso"]["tokens_in"] == 100 and out["uso"]["tokens_out"] == 50
    # Se forzó la herramienta correcta.
    assert fake.ultima_llamada["toolConfig"]["toolChoice"] == {"tool": {"name": "registrar_pedidos"}}


def test_extraer_normaliza_confianza_fuera_de_rango():
    fake = FakeConverse(pedidos=[{"direccion": "X", "confianza": 5}])
    c = ClienteBedrock(cliente=fake)
    out = extraer(texto="x", cliente=c)
    assert out["pedidos"][0]["confianza"] == 1.0


def test_extraer_heuristico_sin_cliente_detecta_coords():
    out = extraer(texto="42.240836, -83.74301 entrega A\notra linea")
    assert out["uso"]["modelo"] == "heuristico"
    assert out["pedidos"][0]["lat"] == 42.240836
    assert out["pedidos"][0]["lon"] == -83.74301
    assert out["pedidos"][1]["lat"] is None


def test_extraer_imagen_sin_cliente_advierte():
    out = extraer(imagen=b"\x89PNG", texto=None)
    assert out["pedidos"] == []
    assert any("Imagen" in a for a in out["advertencias"])


def test_extraer_imagen_con_cliente_envia_bytes():
    fake = FakeConverse(pedidos=[{"direccion": "301 E Huron St"}])
    c = ClienteBedrock(cliente=fake)
    out = extraer(imagen=b"\x89PNG123", cliente=c)
    contenido = fake.ultima_llamada["messages"][0]["content"]
    assert any("image" in b for b in contenido)
    assert len(out["pedidos"]) == 1


# ------------------------------------------------------------- geocodificar
def test_geocodificar_rellena_coordenadas():
    geo = GeoFake({"100 Briarwood Circle": (42.240836, -83.74301)})
    pedidos = [{"id_sugerido": "P1", "direccion": "100 Briarwood Circle",
                "lat": None, "lon": None}]
    r = geocodificar_pedidos(pedidos, geo)
    assert r["geocodificados"] == 1
    assert r["pedidos"][0]["lat"] == 42.240836


def test_geocodificar_mantiene_coords_existentes():
    geo = GeoFake({})
    pedidos = [{"id_sugerido": "P1", "direccion": "x", "lat": 42.28, "lon": -83.74}]
    r = geocodificar_pedidos(pedidos, geo)
    assert r["geocodificados"] == 0
    assert r["pedidos"][0]["lat"] == 42.28


def test_geocodificar_rechaza_fuera_de_area():
    geo = GeoFake({})
    pedidos = [{"id_sugerido": "P1", "direccion": "x", "lat": 10.0, "lon": 10.0}]
    r = geocodificar_pedidos(pedidos, geo)
    assert r["pedidos"][0]["lat"] is None
    assert any("fuera del área" in a for a in r["advertencias"])


def test_geocodificar_nulo_no_resuelve():
    pedidos = [{"id_sugerido": "P1", "direccion": "100 Briarwood Circle", "lat": None, "lon": None}]
    r = geocodificar_pedidos(pedidos, GeocodificadorNulo())
    assert r["geocodificados"] == 0
    assert any("no se pudo geocodificar" in a for a in r["advertencias"])


# ------------------------------------------------------------- a_nodos
def test_a_nodos_genera_filas_visit_validas():
    # Coordenada libre dentro del área (no coincide con base/cargadores existentes).
    pedidos = [
        {"id_sugerido": "P1", "direccion": "100 Briarwood Circle",
         "lat": 42.248000, "lon": -83.743500},
        {"id_sugerido": "P2", "direccion": "sin coords", "lat": None, "lon": None},
    ]
    r = a_nodos(pedidos, CSV_BASE)
    assert len(r["filas_nuevas"]) == 1
    nueva = r["filas_nuevas"][0]
    assert nueva["node_type"] == "visit"
    assert nueva["node_id"].startswith("V")
    assert abs(float(nueva["latitude"]) - 42.248000) < 1e-6
    # El sin-coords fue rechazado.
    assert any(x["id_sugerido"] == "P2" and x["motivo"] == "sin coordenadas"
               for x in r["rechazados"])


def test_a_nodos_rechaza_duplicados_entre_pedidos():
    pedidos = [
        {"id_sugerido": "P1", "direccion": "a", "lat": 42.2900, "lon": -83.7400},
        {"id_sugerido": "P2", "direccion": "b", "lat": 42.2900, "lon": -83.7400},
    ]
    r = a_nodos(pedidos, CSV_BASE)
    assert len(r["filas_nuevas"]) == 1
    assert any(x["id_sugerido"] == "P2" and x["motivo"] == "duplicado" for x in r["rechazados"])


def test_a_nodos_rechaza_fuera_de_area():
    pedidos = [{"id_sugerido": "P1", "direccion": "a", "lat": 0.0, "lon": 0.0}]
    r = a_nodos(pedidos, CSV_BASE)
    assert r["filas_nuevas"] == []
    assert r["rechazados"][0]["motivo"] == "fuera del área"


def test_a_nodos_ids_no_colisionan_con_existentes():
    # El CSV base tiene V1..Vn; los nuevos deben continuar la numeración.
    with open(CSV_BASE, encoding="utf-8-sig", newline="") as f:
        ids = [r["node_id"] for r in csv.DictReader(f)]
    maxv = max(int(x[1:]) for x in ids if x.startswith("V") and x[1:].isdigit())
    pedidos = [{"id_sugerido": "P1", "direccion": "a", "lat": 42.2905, "lon": -83.7405}]
    r = a_nodos(pedidos, CSV_BASE)
    assert r["filas_nuevas"][0]["node_id"] == f"V{maxv + 1}"


def test_escribir_csv_es_resoluble(tmp_path):
    pedidos = [{"id_sugerido": "P1", "direccion": "100 Briarwood Circle",
                "lat": 42.248000, "lon": -83.743500}]
    r = a_nodos(pedidos, CSV_BASE)
    ruta = escribir_csv(r, tmp_path / "nodos.csv")
    assert ruta.exists()
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    # Formato oficial cargable por evrp.datos.
    from evrp.datos import cargar_nodos
    nodos = cargar_nodos(ruta)
    assert any(n.id == r["filas_nuevas"][0]["node_id"] for n in nodos)
    assert sum(1 for n in nodos if n.tipo == "base") == 1


# ------------------------------------------------------------- Nominatim doble
def test_nominatim_con_transporte_fake():
    llamadas = {}

    def transporte(url, params, headers):
        llamadas["params"] = params
        llamadas["headers"] = headers
        return [{"lat": "42.282111", "lon": "-83.745025",
                 "display_name": "301 E Huron St", "importance": 0.6}]

    geo = Nominatim(transporte=transporte, intervalo_s=0.0)
    res = geo.geocodificar("301 E Huron St")
    assert res is not None
    assert abs(res.lat - 42.282111) < 1e-6
    assert "evrp-lab" in llamadas["headers"]["User-Agent"]
    assert llamadas["params"]["bounded"] == 1  # sesgo al área


def test_nominatim_sin_resultados_devuelve_none():
    geo = Nominatim(transporte=lambda u, p, h: [], intervalo_s=0.0)
    assert geo.geocodificar("x") is None


def test_nominatim_error_red_degrada():
    def transporte(url, params, headers):
        raise OSError("sin red")

    geo = Nominatim(transporte=transporte, intervalo_s=0.0)
    assert geo.geocodificar("x") is None


# ------------------------------------------------------------- AmazonLocation doble
class _LocFake:
    def __init__(self, resultados=None, excepcion=None):
        self._r = resultados
        self._exc = excepcion
        self.ultima = None

    def search_place_index_for_text(self, **kwargs):
        self.ultima = kwargs
        if self._exc:
            raise self._exc
        return {"Results": self._r or []}


def test_amazon_location_parsea_punto():
    loc = _LocFake(resultados=[{"Place": {"Label": "301 E Huron St",
                                          "Geometry": {"Point": [-83.745025, 42.282111]}},
                                "Relevance": 0.95}])
    geo = AmazonLocation(indice="idx", cliente=loc)
    res = geo.geocodificar("301 E Huron St")
    assert abs(res.lat - 42.282111) < 1e-6 and abs(res.lon + 83.745025) < 1e-6
    assert res.confianza == 0.95
    assert loc.ultima["IndexName"] == "idx"


def test_amazon_location_error_degrada():
    geo = AmazonLocation(indice="idx", cliente=_LocFake(excepcion=RuntimeError("x")))
    assert geo.geocodificar("x") is None


def test_en_area():
    assert en_area(42.28, -83.74)
    assert not en_area(0.0, 0.0)


# ------------------------------------------------------------- real (opt-in)
@pytest.mark.bedrock
def test_bedrock_real_extrae_pedido():
    """Llamada real a Bedrock: extrae un pedido de texto informal."""
    perfil = os.environ.get("AWS_PROFILE") or "hackathon"
    modelo = os.environ.get("EVRP_BEDROCK_MODELO", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    try:
        c = ClienteBedrock(region="us-east-1", modelo=modelo, perfil=perfil)
        out = extraer(
            texto="hola, entrega mañana en 301 E Huron St, 2 cajas para Sofía",
            contexto="ciudad: Ann Arbor, Michigan", cliente=c)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Bedrock no disponible ({type(exc).__name__}): {exc}")
    assert out["pedidos"], "debe extraer al menos un pedido"
    assert any("huron" in (p["direccion"] or "").lower() for p in out["pedidos"])
    assert out["uso"]["tokens_in"] > 0
