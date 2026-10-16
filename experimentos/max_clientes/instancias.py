"""Definiciones de instancias donde NO es factible atender a todos los clientes.

Geometría en línea recta (RedHaversine): 0.01 grados de longitud ~ 1.11 km; con
factor_vial 1.3 y consumo 0.156 kWh/km, un salto de 0.01 grados cuesta ~0.225 kWh.
Jugamos con batería pequeña, distancias, cargadores escasos/incompatibles y nº de
vehículos para forzar que algunos clientes queden fuera.

Cada builder devuelve (nombre, filas, bateria, reserva, n_veh, n_esperado_pista).
`n_esperado_pista` es una expectativa humana (no autoridad): la verdad la da el oráculo
en instancias pequeñas y la formulación completa en las grandes.
"""
from __future__ import annotations

from .harness import _nodo


def _clientes_linea(n, lon0=0.02, paso=0.01, lat=0.0, prefijo="V"):
    return [_nodo(f"{prefijo}{i+1}", "visit", lat, lon0 + i * paso) for i in range(n)]


# ------------------------------------------------------------------- PEQUEÑAS (<=8)
def peq_bateria_corta():
    """6 clientes en línea hacia el este; la batería alcanza solo a los cercanos; un
    cargador compatible cercano extiende el alcance, pero 1 vehículo no cubre todos."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _clientes_linea(6, lon0=0.03, paso=0.03)   # 0.03..0.18 grados
    filas.append(_nodo("C1", "charger", 0, 0.05, "CHAdeMO", "2", "50"))
    return ("peq_bateria_corta", filas, 3.2, 0.4, 1, "0<N*<6")


def peq_incompatibles():
    """5 clientes; dos cargadores pero ambos de conector incompatible (CCS/NACS) con el
    vehículo (CHAdeMO/J1772). Sin recarga útil, solo alcanzan los más cercanos."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _clientes_linea(5, lon0=0.025, paso=0.03)
    filas.append(_nodo("C1", "charger", 0, 0.05, "CCS", "2", "50"))
    filas.append(_nodo("C2", "charger", 0, 0.08, "NACS", "2", "50"))
    return ("peq_incompatibles", filas, 5.0, 0.4, 1, "0<N*<5 (cargadores inútiles)")


def peq_lejano_aislado():
    """6 clientes agrupados cerca + 2 muy lejanos sin cargador que los alcance. Con 1
    vehículo y batería media se atienden los cercanos; los lejanos quedan fuera."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _clientes_linea(6, lon0=0.02, paso=0.015)       # cercanos
    filas += [_nodo("V7", "visit", 0, 0.9), _nodo("V8", "visit", 0, 1.0)]  # lejanos ~100 km
    filas.append(_nodo("C1", "charger", 0, 0.05, "CHAdeMO", "2", "50"))
    return ("peq_lejano_aislado", filas, 3.0, 0.3, 1, "~6")


def peq_cadena_F_F():
    """1 cliente alcanzable SOLO encadenando dos cargadores (C1->C2->V). La formulación
    compacta (un cargador por arco) no lo cubre; el respaldo (completa) debe activarse.
    Más 3 clientes cercanos normales."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _clientes_linea(3, lon0=0.02, paso=0.02)
    filas.append(_nodo("C1", "charger", 0, 0.08, "CHAdeMO", "2", "50"))
    filas.append(_nodo("C2", "charger", 0, 0.21, "CHAdeMO", "2", "50"))
    filas.append(_nodo("V4", "visit", 0, 0.28))
    return ("peq_cadena_F_F", filas, 4.0, 0.3, 1, "4 (requiere F->F)")


def peq_dos_veh():
    """6 clientes en dos brazos opuestos; batería corta; con 2 vehículos se cubren más
    que con 1, pero el extremo de cada brazo queda fuera (no todos)."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += [_nodo(f"E{i+1}", "visit", 0, 0.03 + i * 0.045) for i in range(3)]   # este
    filas += [_nodo(f"W{i+1}", "visit", 0, -(0.03 + i * 0.045)) for i in range(3)]  # oeste
    filas.append(_nodo("C1", "charger", 0, 0.05, "CHAdeMO", "2", "50"))
    filas.append(_nodo("C2", "charger", 0, -0.05, "CHAdeMO", "2", "50"))
    return ("peq_dos_veh", filas, 3.2, 0.4, 2, "0<N*<6")


# -------------------------------------------------------------------- GRANDES (20)
def _veinte_base(semilla_lon=0.0):
    """20 clientes dispersos en una rejilla; devuelve solo las filas de clientes."""
    filas = []
    k = 0
    # 4 anillos de 5 clientes a distintas distancias/direcciones
    import math
    radios = [0.03, 0.06, 0.12, 0.5]  # el último anillo es lejano
    for r in radios:
        for a in range(5):
            ang = 2 * math.pi * a / 5
            lat = r * math.sin(ang)
            lon = r * math.cos(ang) + semilla_lon
            k += 1
            filas.append(_nodo(f"V{k}", "visit", lat, lon))
    return filas


def g20_bateria_pequena():
    """20 clientes, batería pequeña, 2 vehículos, pocos cargadores compatibles. El anillo
    lejano (~55 km) no es alcanzable: no se puede atender a todos."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _veinte_base()
    filas += [_nodo("C1", "charger", 0, 0.08, "CHAdeMO", "2", "50"),
              _nodo("C2", "charger", 0.08, 0, "CHAdeMO", "2", "50"),
              _nodo("C3", "charger", 0, -0.3, "CCS", "2", "50")]  # incompatible
    return ("g20_bateria_pequena", filas, 4.0, 0.4, 2, "<20 (anillo lejano fuera)")


def g20_un_vehiculo():
    """20 clientes, 2 vehículos, batería media; el anillo lejano (~55 km) sin cargador
    que lo alcance queda fuera: no se puede atender a todos aunque haya 2 vehículos."""
    filas = [_nodo("BASE", "base", 0, 0)]
    filas += _veinte_base()
    filas += [_nodo("C1", "charger", 0, 0.08, "CHAdeMO", "2", "50"),
              _nodo("C2", "charger", 0.08, 0, "CHAdeMO", "2", "50"),
              _nodo("C3", "charger", -0.08, 0, "CHAdeMO", "2", "50")]
    return ("g20_dos_veh_anillo", filas, 5.0, 0.5, 2, "<20 (anillo lejano fuera)")


def g20_cadena_F_F():
    """20 clientes; 3 de ellos (brazo lejano a ~45 km) solo alcanzables encadenando dos
    cargadores en fila (C_a -> C_b -> cliente). La compacta no los cubre; el respaldo
    completo debe activarse y atender más que la compacta."""
    import math
    filas = [_nodo("BASE", "base", 0, 0)]
    # 17 clientes cercanos + 3 lejanos en un brazo al este tras cadena de cargadores
    k = 0
    for r, cnt in [(0.025, 6), (0.05, 6), (0.08, 5)]:
        for a in range(cnt):
            ang = 2 * math.pi * a / cnt
            k += 1
            filas.append(_nodo(f"V{k}", "visit", r * math.sin(ang), r * math.cos(ang)))
    for i in range(3):
        k += 1
        filas.append(_nodo(f"V{k}", "visit", 0, 0.34 + i * 0.02))  # brazo lejano
    filas += [_nodo("C1", "charger", 0, 0.10, "CHAdeMO", "2", "50"),
              _nodo("C2", "charger", 0, 0.22, "CHAdeMO", "2", "50")]
    return ("g20_cadena_F_F", filas, 4.0, 0.3, 2, "<=20 (brazo requiere F->F)")


PEQUENAS = [peq_bateria_corta, peq_incompatibles, peq_lejano_aislado,
            peq_cadena_F_F, peq_dos_veh]
GRANDES = [g20_bateria_pequena, g20_un_vehiculo, g20_cadena_F_F]
