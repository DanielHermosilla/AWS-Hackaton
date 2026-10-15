"""Escritura de resultados: JSONL crudo + reporte Markdown + CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path

COLUMNAS = ["motor", "solver", "instancia", "vehiculos", "entregas", "clientes",
            "energia_validada_kwh", "km", "tiempo_total_s", "tiempo_solver_s",
            "gap", "estado", "factible_neutral", "mem_pico_mb"]


def escribir_jsonl(filas: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _fila_tabla(r: dict) -> dict:
    return {
        "motor": r.get("motor"),
        "solver": r.get("solver"),
        "instancia": r.get("instancia"),
        "vehiculos": r.get("vehiculos"),
        "entregas": r.get("entregas"),
        "clientes": r.get("clientes"),
        "energia_validada_kwh": r.get("energia_validada_kwh"),
        "km": r.get("km"),
        "tiempo_total_s": r.get("tiempo_total_s"),
        "tiempo_solver_s": r.get("tiempo_solver_s"),
        "gap": r.get("gap"),
        "estado": r.get("estado"),
        "factible_neutral": r.get("factible_neutral"),
        "mem_pico_mb": r.get("mem_pico_mb"),
    }


def escribir_csv(filas: list[dict], ruta: Path) -> None:
    from evrp.datos import celda_csv_segura

    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for r in filas:
            w.writerow({k: celda_csv_segura(v) for k, v in _fila_tabla(r).items()})


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, bool):
        return "si" if v else "no"
    return str(v)


def escribir_markdown(nombre: str, filas_motor: list[dict], filas_solver: list[dict],
                      ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# Arena: {nombre}", ""]
    L.append("No se declara ganador: se presenta la evidencia medida.")
    L.append("")
    L.append("## Motores")
    L.append("")
    cab = ["motor", "instancia", "veh", "entregas/clientes", "energia_val_kwh", "km",
           "t_total_s", "t_solver_s", "gap", "estado", "factible_neutral"]
    L.append("| " + " | ".join(cab) + " |")
    L.append("|" + "|".join(["---"] * len(cab)) + "|")
    for r in filas_motor:
        ec = f"{_fmt(r.get('entregas'))}/{_fmt(r.get('clientes'))}"
        L.append("| " + " | ".join([
            _fmt(r.get("motor")), _fmt(r.get("instancia")), _fmt(r.get("vehiculos")), ec,
            _fmt(r.get("energia_validada_kwh")), _fmt(r.get("km")),
            _fmt(r.get("tiempo_total_s")), _fmt(r.get("tiempo_solver_s")),
            _fmt(r.get("gap")), _fmt(r.get("estado")), _fmt(r.get("factible_neutral")),
        ]) + " |")
    if filas_solver:
        L.append("")
        L.append("## Competencia de solvers (MILP de evrp exportado a MPS)")
        L.append("")
        cab2 = ["instancia", "fase", "solver", "estado", "objetivo", "cota", "gap", "tiempo_s",
                "columnas", "filas"]
        L.append("| " + " | ".join(cab2) + " |")
        L.append("|" + "|".join(["---"] * len(cab2)) + "|")
        for r in filas_solver:
            L.append("| " + " | ".join([
                _fmt(r.get("instancia")), _fmt(r.get("fase")), _fmt(r.get("solver")),
                _fmt(r.get("estado")), _fmt(r.get("objetivo")), _fmt(r.get("cota")),
                _fmt(r.get("gap")), _fmt(r.get("tiempo_s")), _fmt(r.get("columnas")),
                _fmt(r.get("filas")),
            ]) + " |")
    L.append("")
    ruta.write_text("\n".join(L), encoding="utf-8")
