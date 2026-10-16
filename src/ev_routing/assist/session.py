"""Estado de la sesion de chat: instancia base inmutable + overrides validados.

La sesion recuerda SIEMPRE la configuracion inicial (snapshot inmutable), de
modo que el usuario puede volver a ella en cualquier momento ("reiniciar_config"
o "deshace el ultimo cambio"). Los cambios se acumulan como overrides y se
aplican sobre copias, nunca mutando el estado base.

El calculo real de rutas lo hace ``pipeline.run_instance`` (solver determinista
+ validacion independiente). Esta sesion solo prepara entradas validas.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .tools import ParametroSpec, validar_parametro

# Import perezoso del nucleo para no acoplar el import del paquete al solver.
try:  # pragma: no cover - disponible en el repo real
    from ev_routing.contracts import Operations, ProblemInstance, SolverConfig
    from ev_routing.pipeline import run_instance
except Exception:  # pragma: no cover - permite inspeccionar sin entorno
    Operations = ProblemInstance = SolverConfig = Any  # type: ignore
    run_instance = None  # type: ignore


class ErrorSesion(RuntimeError):
    """Fallo al aplicar un cambio o al resolver desde la sesion."""


@dataclass
class CambioAplicado:
    """Registro de un override aplicado (para historial y deshacer)."""

    clave: str
    valor: float | int
    seccion: str
    destino: str


@dataclass
class Sesion:
    """Mantiene instancia/config inicial, los overrides y el ultimo resultado.

    ``instancia_base`` y ``config_base`` son el snapshot inmutable al que se
    puede volver. ``_overrides`` guarda los valores actuales por clave de la
    lista blanca; ``historial`` permite deshacer el ultimo cambio.
    """

    instancia_base: Any
    config_base: Any = None
    _overrides: dict[str, float | int] = field(default_factory=dict)
    historial: list[CambioAplicado] = field(default_factory=list)
    ultimo_resultado: dict | None = None

    def __post_init__(self) -> None:
        if self.config_base is None and SolverConfig is not Any:
            self.config_base = SolverConfig()  # defaults del contrato

    # --- consulta de configuracion ----------------------------------------
    def resumen_config(self) -> dict:
        """Config inicial, cambios aplicados y valores vigentes (para contexto)."""
        return {
            "inicial": self._dump(self.config_base),
            "cambios_aplicados": {k: v for k, v in self._overrides.items()},
            "flota_maxima": 10,
        }

    @staticmethod
    def _dump(obj: Any) -> Any:
        dump = getattr(obj, "model_dump", None)
        return dump(mode="json") if callable(dump) else obj

    # --- aplicar / deshacer -----------------------------------------------
    def aplicar(self, clave: str, valor: Any) -> CambioAplicado:
        """Valida y registra un override. Lanza ``ErrorParametro`` si es invalido."""
        spec, tipado = validar_parametro(clave, valor)
        self._overrides[clave] = tipado
        cambio = CambioAplicado(clave, tipado, spec.seccion, spec.destino)
        self.historial.append(cambio)
        return cambio

    def deshacer(self) -> CambioAplicado | None:
        """Quita el ultimo cambio; recalcula el override efectivo de esa clave."""
        if not self.historial:
            return None
        ultimo = self.historial.pop()
        previo = next(
            (c.valor for c in reversed(self.historial) if c.clave == ultimo.clave),
            None,
        )
        if previo is None:
            self._overrides.pop(ultimo.clave, None)
        else:
            self._overrides[ultimo.clave] = previo
        return ultimo

    def reiniciar(self) -> None:
        """Vuelve al estado inicial: descarta todos los overrides."""
        self._overrides.clear()
        self.historial.clear()

    # --- materializar instancia/config efectivas --------------------------
    def _instancia_config_efectivas(self) -> tuple[Any, Any]:
        """Aplica los overrides sobre copias de la instancia/config base."""
        if ProblemInstance is Any:  # entorno sin contratos (solo inspeccion)
            raise ErrorSesion("Contratos no disponibles en este entorno.")
        instancia = copy.deepcopy(self.instancia_base)
        config = copy.deepcopy(self.config_base)
        ops_updates: dict[str, Any] = {}
        cfg_updates: dict[str, Any] = {}
        for clave, valor in self._overrides.items():
            spec: ParametroSpec = __import__(
                "ev_routing.assist.tools", fromlist=["PARAMETROS"]
            ).PARAMETROS[clave]
            if spec.seccion == "operations":
                ops_updates[spec.destino] = valor
            elif spec.seccion == "solver":
                cfg_updates[spec.destino] = valor
            elif spec.seccion == "instancia":
                instancia = self._aplicar_instancia(instancia, spec.destino, valor)
        if ops_updates:
            nuevas_ops = instancia.operations.model_copy(update=ops_updates)
            instancia = instancia.model_copy(update={"operations": nuevas_ops})
        if cfg_updates:
            config = config.model_copy(update=cfg_updates)
        return instancia, config

    @staticmethod
    def _aplicar_instancia(instancia: Any, destino: str, valor: Any) -> Any:
        """Overrides a nivel de instancia (p. ej. tamano de flota).

        Nota: el nombre real del campo de flota depende del contrato de
        instancia; se resuelve dinamicamente y, si no existe, se informa.
        """
        if hasattr(instancia, destino):
            return instancia.model_copy(update={destino: valor})
        params = getattr(instancia, "parameters", None)
        if params is not None and hasattr(params, destino):
            nuevos = params.model_copy(update={destino: valor})
            return instancia.model_copy(update={"parameters": nuevos})
        raise ErrorSesion(
            f"La instancia no expone '{destino}'; no se pudo aplicar el cambio."
        )

    # --- resolver ----------------------------------------------------------
    def resolver(self) -> dict:
        """Resuelve la instancia efectiva con el solver determinista real."""
        if run_instance is None:
            raise ErrorSesion("pipeline.run_instance no disponible en este entorno.")
        instancia, config = self._instancia_config_efectivas()
        self.ultimo_resultado = run_instance(instancia, config)
        return self.ultimo_resultado
