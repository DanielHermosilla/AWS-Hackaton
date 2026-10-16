"""Estado de una conversacion: datos, configuracion y ultimo plan.

La sesion separa tres cosas:

- **Datos**: de donde salen los nodos. O bien una ``ProblemInstance`` nativa
  (modo libreria/CLI, se resuelve con ``pipeline.run_instance``), o bien un
  ``resolutor`` inyectado por quien expone el chat (el backend web lo usa para
  correr /prepare + /solve con la red vial del servidor).
- **Configuracion**: ``config_base`` (inmutable, para volver atras) mas los
  overrides validados por la lista blanca. Las claves son las de
  ``tools.PARAMETROS``.
- **Conversacion**: historial Converse y pedidos pendientes, para que un
  backend sin estado pueda recrear el ``Asistente`` en cada request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .tools import PARAMETROS, validar_parametro, valores_estandar

Resolutor = Callable[[dict[str, Any]], dict]


class ErrorSesion(RuntimeError):
    """Fallo al aplicar un cambio o al resolver desde la sesion."""


class NecesitaDatos(ErrorSesion):
    """No hay datos cargados: hay que pedir el archivo de nodos."""


@dataclass
class CambioAplicado:
    clave: str
    valor: Any
    seccion: str
    destino: str | None


def config_desde_instancia(instancia: Any) -> dict[str, Any]:
    """Lee de una ProblemInstance los parametros que la lista blanca conoce."""
    params = getattr(instancia, "parameters", None)
    if params is None:
        return {}
    salida = {}
    for clave, spec in PARAMETROS.items():
        if spec.seccion == "parametros" and hasattr(params, spec.destino):
            salida[clave] = getattr(params, spec.destino)
    return salida


def describir_config(cfg: dict[str, Any]) -> str:
    """Texto breve y legible de una configuracion efectiva."""
    red = "calles del servidor" if cfg.get("red") == "road" else "red geodesica"
    busqueda = {"adaptive": "GPT", "standard": "estandar", "deterministic": "determinista"}
    return (
        f"{cfg['vehiculos']} vehiculo(s), SoC {round(cfg['soc_inicial'] * 100)} %, "
        f"bateria {cfg['capacidad_kwh']:g} kWh, reserva {cfg['reserva_kwh']:g} kWh, "
        f"consumo {cfg['consumo_kwh_km']:g} kWh/km, {red}, "
        f"{cfg['tiempo_limite_s']:g} s de calculo, busqueda {busqueda.get(cfg['busqueda'], cfg['busqueda'])}"
    )


@dataclass
class Sesion:
    instancia_base: Any = None
    config_base: dict[str, Any] | None = None
    resolutor: Resolutor | None = None
    descripcion_datos: str | None = None
    no_aplicables: frozenset[str] = frozenset()
    _overrides: dict[str, Any] = field(default_factory=dict)
    historial: list[CambioAplicado] = field(default_factory=list)
    ultimo_resultado: dict | None = None
    # Cambio importante esperando confirmacion (modo libreria).
    confirmacion_pendiente: tuple[str, Any] | None = None
    # El usuario pidio calcular pero faltaban datos: retomar al recibirlos.
    pendiente_calcular: bool = False
    # Historial Converse; vive aqui para sobrevivir entre requests.
    mensajes: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        base = valores_estandar()
        if self.instancia_base is not None:
            base.update(config_desde_instancia(self.instancia_base))
            if self.resolutor is None and not self.no_aplicables:
                # Una instancia nativa ya trae su red: consumo y red no aplican.
                self.no_aplicables = frozenset(
                    k for k, s in PARAMETROS.items() if s.seccion == "preparacion"
                )
        if isinstance(self.config_base, dict):
            base.update(self.config_base)
        self.config_base = base

    # --- datos -------------------------------------------------------------
    @property
    def tiene_datos(self) -> bool:
        return self.resolutor is not None or self.instancia_base is not None

    def cargar_datos(
        self,
        resolutor: Resolutor,
        *,
        descripcion: str,
        config: dict[str, Any] | None = None,
        no_aplicables: frozenset[str] = frozenset(),
    ) -> None:
        """Reemplaza la fuente de datos. Conserva los ajustes ya conversados."""
        self.resolutor = resolutor
        self.instancia_base = None
        self.descripcion_datos = descripcion
        self.no_aplicables = no_aplicables
        base = valores_estandar()
        base.update(config or {})
        self.config_base = base
        self.ultimo_resultado = None

    # --- configuracion -----------------------------------------------------
    def config_efectiva(self) -> dict[str, Any]:
        return {**self.config_base, **self._overrides}

    @property
    def overrides(self) -> dict[str, Any]:
        return dict(self._overrides)

    def resumen_config(self) -> dict:
        return {
            "inicial": dict(self.config_base),
            "vigente": self.config_efectiva(),
            "cambios_aplicados": dict(self._overrides),
            "flota_maxima": int(PARAMETROS["vehiculos"].maximo),
            "datos": self.descripcion_datos,
        }

    def aplicar(self, clave: str, valor: Any) -> CambioAplicado:
        """Valida y registra un override. Lanza ``ErrorParametro`` si es invalido."""
        spec, tipado = validar_parametro(clave, valor)
        if clave in self.no_aplicables:
            raise ErrorSesion(
                f"'{clave}' solo se usa al preparar desde nodos; estos datos ya traen su red."
            )
        self._overrides[clave] = tipado
        cambio = CambioAplicado(clave, tipado, spec.seccion, spec.destino)
        self.historial.append(cambio)
        return cambio

    def deshacer(self) -> CambioAplicado | None:
        if not self.historial:
            return None
        ultimo = self.historial.pop()
        previo = next(
            (c.valor for c in reversed(self.historial) if c.clave == ultimo.clave), None
        )
        if previo is None:
            self._overrides.pop(ultimo.clave, None)
        else:
            self._overrides[ultimo.clave] = previo
        return ultimo

    def reiniciar(self) -> None:
        self._overrides.clear()
        self.historial.clear()
        self.confirmacion_pendiente = None

    # --- resolver ----------------------------------------------------------
    def resolver(self) -> dict:
        """Calcula el plan con el motor. Unica via por la que existen rutas."""
        if self.resolutor is not None:
            resultado = self.resolutor(self.config_efectiva())
        elif self.instancia_base is not None:
            from ev_routing.pipeline import run_instance

            instancia, config = self._instancia_config_efectivas()
            resultado = run_instance(instancia, config)
        else:
            raise NecesitaDatos("No hay datos cargados: falta el archivo de nodos.")
        self.ultimo_resultado = resultado
        self.pendiente_calcular = False
        return resultado

    def _instancia_config_efectivas(self) -> tuple[Any, Any]:
        """Modo nativo: aplica overrides sobre la instancia y SolverConfig."""
        if self.instancia_base is None:
            raise NecesitaDatos("No hay instancia nativa cargada.")
        from ev_routing.contracts import SolverConfig

        cfg = self.config_efectiva()
        instancia = self.instancia_base
        cambios = {
            spec.destino: self._overrides[clave]
            for clave, spec in PARAMETROS.items()
            if spec.seccion == "parametros" and clave in self._overrides
        }
        if cambios:
            datos = instancia.model_dump(mode="json")
            datos["parameters"] = {**datos["parameters"], **cambios}
            try:
                instancia = type(instancia).model_validate(datos)
            except ValueError as exc:
                raise ErrorSesion(f"La configuracion no es valida para estos datos: {exc}") from exc
        config = SolverConfig(time_limit_seconds=cfg["tiempo_limite_s"])
        return instancia, config
