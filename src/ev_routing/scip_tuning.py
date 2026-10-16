"""Catálogo de búsqueda de SCIP instalado, acotado por el algoritmo que lo usa."""

from __future__ import annotations

from functools import lru_cache

from pyscipopt import SCIP_PARAMSETTING, Model

LP_SEARCH = {
    "lp/initalgorithm", "lp/resolvealgorithm", "lp/pricing", "lp/scaling",
    "lp/presolving", "lp/colagelimit", "lp/rowagelimit", "lp/cleanupcols",
    "lp/cleanupcolsroot", "lp/cleanuprows", "lp/cleanuprowsroot",
    "lp/lexdualalgo", "lp/lexdualrootonly", "lp/lexdualmaxrounds",
    "lp/lexdualbasic", "lp/lexdualstalling", "lp/solutionpolishing",
    "lp/refactorinterval", "lp/resolveiterfac", "lp/resolveitermin",
}
SETTINGS = {
    "default": SCIP_PARAMSETTING.DEFAULT, "fast": SCIP_PARAMSETTING.FAST,
    "aggressive": SCIP_PARAMSETTING.AGGRESSIVE, "off": SCIP_PARAMSETTING.OFF,
}


@lru_cache(maxsize=2)
def parameter_catalog(single_tour: bool = False) -> dict:
    model = Model()
    model.hideOutput()
    native = model.getParams()
    prefixes = ("branching/", "heuristics/", "nodeselection/")
    if single_tour:
        prefixes += ("presolving/", "separating/", "propagating/", "conflict/")
    parameters = {
        name: value for name, value in native.items()
        if (name.startswith(prefixes) or name in LP_SEARCH)
        and not any(token in name.lower() for token in (
            "/seed", "/randomseed", "/threads", "/nthreads", "/time", "/memory",
            "filename", "/file", "/write", "/read",
        ))
    }
    result = {
        "scip_version": f"{model.getMajorVersion()}.{model.getMinorVersion()}.{model.getTechVersion()}",
        "algorithm": "directed_tour" if single_tour else "branch_price",
        "native_parameter_count": len(native), "available_parameter_count": len(parameters),
        "parameters_and_defaults": parameters,
        "locked": [
            "Global time, nodes, gaps, threads, seeds and memory remain user-controlled.",
            "Numerical tolerances, feasibility checks and certification cannot be changed.",
            *([] if single_tour else [
                "Native presolve/separation and root reduced-cost strengthening remain off: "
                "the custom pricer must maintain all future-column coefficients.",
                "Use route_cuts/max_subset_rows for implemented column-compatible cuts.",
            ]),
        ],
    }
    model.freeProb()
    return result


def validate_parameters(parameters: dict, single_tour: bool = False) -> dict:
    """Validar nombres, tipos y rangos con la MISMA biblioteca de SCIP instalada."""
    allowed = parameter_catalog(single_tour)["parameters_and_defaults"]
    model = Model()
    model.hideOutput()
    try:
        for name, value in parameters.items():
            if name not in allowed:
                raise ValueError(f"Parámetro no permitido para este algoritmo: {name}")
            original = allowed[name]
            if isinstance(original, bool):
                valid = type(value) is bool
            elif isinstance(original, int):
                valid = type(value) is int
            elif isinstance(original, float):
                valid = type(value) in (float, int)
            else:
                valid = isinstance(value, str)
            if not valid:
                raise ValueError(f"Tipo incorrecto para {name}: {type(value).__name__}")
            try:
                model.setParam(name, value)
            except (ValueError, TypeError, KeyError, LookupError) as error:
                raise ValueError(f"Valor fuera del dominio de SCIP para {name}: {value}") from error
        return {name: model.getParam(name) for name in parameters}
    finally:
        model.freeProb()


def apply_parameters(model, policy, *, single_tour: bool) -> dict:
    """Devolver cambios nativos reales, incluidos los efectos de presets."""
    before = model.getParams()
    model.setHeuristics(SETTINGS[policy.heuristics])
    if single_tour:
        model.setPresolve(SETTINGS[policy.presolve])
        model.setSeparating(SETTINGS[policy.separation])
    model.setIntParam(f"branching/{policy.branching}/priority", 1000000)
    for name, value in policy.scip_parameters.items():
        model.setParam(name, value)
    after = model.getParams()
    return {
        name: {"before": value, "after": after[name]}
        for name, value in before.items() if value != after[name]
    }
