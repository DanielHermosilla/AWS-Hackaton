"""Configuración pequeña: escenario físico y recursos del solver separados."""

from pathlib import Path

from pydantic import Field

from ev_routing.contracts import Contract, ModelParameters, SolverConfig


class ProjectConfig(Contract):
    """No contiene configuración LLM: esta rama nunca invoca AWS."""

    model: ModelParameters = Field(default_factory=ModelParameters)
    solver: SolverConfig = Field(default_factory=SolverConfig)


def load_config(path: str | Path | None = None) -> ProjectConfig:
    """Leer JSON estricto; los parámetros no presentes usan defaults explícitos."""
    if path is None:
        return ProjectConfig()
    return ProjectConfig.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))
