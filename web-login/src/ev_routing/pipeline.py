from typing import Optional

from .contracts import ProblemInstance, RunResult, SolverConfig
from .solve import run_pipeline


def run(instance: ProblemInstance, solver_config: Optional[SolverConfig] = None, run_id: Optional[str] = None) -> RunResult:
    return run_pipeline(instance, solver_config, run_id)
