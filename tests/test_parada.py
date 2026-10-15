"""Pruebas rápidas de la regla de parada por estancamiento (solver.parada)."""
from __future__ import annotations

from evrp.milp_compacto import _ParadaEstancamiento


class _Out:
    def __init__(self, bound, t):
        self.mip_primal_bound = bound
        self.running_time = t


class _In:
    def __init__(self):
        self.user_interrupt = False


def _tick(parada, bound, t):
    inp = _In()
    parada(0, "", _Out(bound, t), inp, None)
    return inp.user_interrupt


def test_no_interrumpe_antes_de_t_min():
    p = _ParadaEstancamiento(t_min_s=15, sin_mejora_s=8, minimiza=True)
    # mejora en t=1 y luego largo estancamiento, pero aún no se alcanza t_min
    assert _tick(p, 10.0, 1.0) is False
    assert _tick(p, 10.0, 12.0) is False     # t < t_min aunque lleve 11s sin mejora


def test_interrumpe_por_estancamiento_tras_t_min():
    p = _ParadaEstancamiento(t_min_s=15, sin_mejora_s=8, minimiza=True)
    assert _tick(p, 10.0, 1.0) is False
    assert _tick(p, 10.0, 10.0) is False     # 9s sin mejora pero t < t_min
    assert _tick(p, 10.0, 16.0) is True      # t >= 15 y 15s sin mejora >= 8
    assert p.interrumpido is True


def test_una_mejora_reinicia_el_contador():
    p = _ParadaEstancamiento(t_min_s=5, sin_mejora_s=8, minimiza=True)
    assert _tick(p, 10.0, 1.0) is False
    assert _tick(p, 9.0, 12.0) is False      # mejora en t=12 -> reinicia
    assert _tick(p, 9.0, 18.0) is False      # solo 6s sin mejora (<8)
    assert _tick(p, 9.0, 21.0) is True       # 9s sin mejora y t>=t_min


def test_maximizacion_normaliza_signo():
    p = _ParadaEstancamiento(t_min_s=5, sin_mejora_s=4, minimiza=False)
    assert _tick(p, 5.0, 1.0) is False
    assert _tick(p, 7.0, 2.0) is False       # mejora (mayor es mejor)
    assert _tick(p, 6.0, 3.0) is False       # empeora -> no reinicia
    assert _tick(p, 7.0, 8.0) is True        # 6s sin mejorar el 7.0


def test_ignora_cota_infinita():
    p = _ParadaEstancamiento(t_min_s=1, sin_mejora_s=1, minimiza=True)
    assert _tick(p, 1e31, 5.0) is False      # sin incumbente válida -> no corta
    assert p.mejor is None


def test_integracion_apagada_por_defecto():
    """Por defecto la regla está apagada: no debe aparecer en la traza."""
    from evrp import config as cfgmod

    cfg = cfgmod.cargar()
    assert cfg["solver"]["parada"]["activar"] is False
    assert cfg["solver"]["parada"]["t_min_s"] == 15.0
    assert cfg["solver"]["parada"]["sin_mejora_s"] == 8.0
