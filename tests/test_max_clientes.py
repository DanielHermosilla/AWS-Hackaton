"""Pruebas de maximización de clientes cuando no se puede atender a todos.

Verifican, en instancias pequeñas (<= 8 clientes), que el motor (fase 1 del MILP)
alcanza el N* del oráculo independiente y, con N* fijo, la energía mínima del oráculo.
Incluye el caso de cadena de cargadores (F->F) donde la compacta no alcanza y el
respaldo (formulación completa) debe activarse.

Las instancias usan RedHaversine (sin internet) con geometría controlada.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experimentos.max_clientes.harness import construir_inst, correr_motor
from experimentos.max_clientes.oraculo import resolver_oraculo
from experimentos.max_clientes import instancias as I


def _inst_oraculo(builder):
    nombre, filas, bat, res, nveh, _ = builder()
    inst, cfg, _ = construir_inst(filas, bat, res, nveh, "compacta", tiempo=10.0)
    return nombre, inst, cfg, filas, bat, res, nveh


# Instancias rápidas de verificar (sin el caso lento peq_lejano_aislado de 8 clientes).
RAPIDAS = [I.peq_bateria_corta, I.peq_incompatibles, I.peq_cadena_F_F]


@pytest.mark.parametrize("builder", RAPIDAS, ids=lambda b: b.__name__)
def test_motor_iguala_oraculo_n_estrella(builder):
    """La fase 1 del MILP (con respaldo completo) alcanza el N* del oráculo."""
    nombre, inst, cfg, filas, bat, res, nveh = _inst_oraculo(builder)
    orac = resolver_oraculo(inst)
    assert 0 < orac["n_estrella"] <= len(inst.clientes)
    # Motor compacta con respaldo a completa.
    m = correr_motor(inst, cfg, con_fallback=True)
    assert m["n_motor"] == orac["n_estrella"], (nombre, m, orac)


@pytest.mark.parametrize("builder", RAPIDAS, ids=lambda b: b.__name__)
def test_motor_minimiza_energia_con_n_fijo(builder):
    """Con N* fijo, la formulación completa (exacta) iguala la energía del oráculo."""
    nombre, inst, cfg, filas, bat, res, nveh = _inst_oraculo(builder)
    orac = resolver_oraculo(inst)
    inst_f, cfg_f, _ = construir_inst(filas, bat, res, nveh, "completa", tiempo=10.0)
    m = correr_motor(inst_f, cfg_f, con_fallback=False)
    assert m["n_motor"] == orac["n_estrella"]
    assert m["energia"] == pytest.approx(orac["energia"], abs=1e-3), (nombre, m, orac)


def test_no_todos_atendibles():
    """peq_incompatibles: cargadores incompatibles -> N* estrictamente menor que |C|."""
    nombre, inst, cfg, *_ = _inst_oraculo(I.peq_incompatibles)
    orac = resolver_oraculo(inst)
    assert orac["n_estrella"] < len(inst.clientes)


def test_respaldo_completa_para_cadena_F_F():
    """peq_cadena_F_F: la compacta por sí sola NO alcanza el N* (no encadena cargadores);
    el respaldo a la formulación completa sí lo logra."""
    nombre, filas, bat, res, nveh, _ = I.peq_cadena_F_F()
    inst, cfg, _ = construir_inst(filas, bat, res, nveh, "compacta", tiempo=10.0)
    orac = resolver_oraculo(inst)
    # Compacta sola (sin respaldo) se queda corta.
    sin = correr_motor(inst, cfg, con_fallback=False)
    inst2, cfg2, _ = construir_inst(filas, bat, res, nveh, "compacta", tiempo=10.0)
    con = correr_motor(inst2, cfg2, con_fallback=True)
    assert sin["n_motor"] < orac["n_estrella"]
    assert con["n_motor"] == orac["n_estrella"]
    assert con["fallback"] is True
