"""Corpus sintético de ingesta de pedidos (>= 20 casos).

Cada caso trae un mensaje de entrada (correo / WhatsApp / lista / tabla, con ruido
y errores humanos) y la verdad de terreno: los pedidos esperados con dirección y
coordenadas conocidas. Las direcciones y coordenadas provienen de la columna
`address` de los cargadores reales en data/competition_routing_nodes.csv (Ann Arbor),
usadas aquí como destinos de entrega para medir precisión/recall y error de
geocodificación en metros.

Se usa en experimentos/ia_ingesta/evaluar.py (métricas) y lo reutilizan los tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Verdad de terreno: dirección -> (lat, lon) tomadas de los cargadores reales.
VERDAD_DIRECCIONES = {
    "100 Briarwood Circle": (42.240836, -83.74301),
    "2000 Waters Rd": (42.2436, -83.7682),
    "3145 Ann Arbor-Saline Rd": (42.240517, -83.766005),
    "4550 Jackson Rd": (42.286564, -83.820142),
    "3480 Jackson Avenue": (42.285478, -83.796116),
    "301 E Huron St": (42.282111, -83.745025),
    "4833 E Huron River Dr": (42.266924, -83.664001),
    "4001 Jackson Rd": (42.284497, -83.809509),
    "3400 Nixon Rd": (42.32176, -83.707423),
    "4975 Washtenaw Ave": (42.250736, -83.66149),
    "4125 Washtenaw Avenue": (42.254264382883, -83.677904300936),
    "1919 S Industrial Hwy": (42.259794, -83.736692),
    "3200 Boardwalk Dr": (42.241166, -83.735175),
    "3792 Pontiac Trail": (42.328435, -83.733198),
    "5940 Jackson Rd": (42.290414, -83.847077),
    "3310 Washtenaw Ave": (42.255841, -83.694824),
    "1143 Highland Dr": (42.227372, -83.722697),
    "106 Packard St": (42.27626, -83.74849),
    "950 Greene Street": (42.269958, -83.747931),
    "701 Miller Ave": (42.2844531, -83.7560763),
    "808 E Kingsley": (42.28483, -83.739392),
    "3021 Miller Rd": (42.298939, -83.790382),
    "1320 Baldwin Ave": (42.265165, -83.72695),
    "2945 East Ellsworth Road": (42.230886, -83.702452),
}


@dataclass
class PedidoEsperado:
    direccion: str                     # clave de VERDAD_DIRECCIONES (o "" si libre)
    nombre: str | None = None
    cantidad: float | None = None
    ventana: str | None = None
    lat: float | None = None           # si el caso trae coordenadas explícitas
    lon: float | None = None

    def verdad_coord(self) -> tuple[float, float] | None:
        if self.lat is not None and self.lon is not None:
            return (self.lat, self.lon)
        return VERDAD_DIRECCIONES.get(self.direccion)


@dataclass
class CasoIngesta:
    id: str
    tipo: str                          # correo | whatsapp | lista | tabla | coords
    texto: str
    esperados: list[PedidoEsperado] = field(default_factory=list)


def _c(dir_, **kw):
    return PedidoEsperado(direccion=dir_, **kw)


CORPUS: list[CasoIngesta] = [
    CasoIngesta("c01", "correo",
        "Hola equipo,\n\nMañana necesito que entreguen en 100 Briarwood Circle (cliente "
        "Mariana, 3 cajas) y también en 2000 Waters Rd para el Sr. Ortega, 1 bulto.\n\n"
        "Gracias!\nLaura",
        [_c("100 Briarwood Circle", nombre="Mariana", cantidad=3),
         _c("2000 Waters Rd", nombre="Ortega", cantidad=1)]),

    CasoIngesta("c02", "whatsapp",
        "oye pasa x 301 E Huron St a las 9, son 2 paquetes 🙏 y dsps a 950 Greene Street",
        [_c("301 E Huron St", cantidad=2, ventana="9"),
         _c("950 Greene Street")]),

    CasoIngesta("c03", "lista",
        "Entregas de hoy:\n- 4550 Jackson Rd\n- 3480 Jackson Avenue\n- 4001 Jackson Rd",
        [_c("4550 Jackson Rd"), _c("3480 Jackson Avenue"), _c("4001 Jackson Rd")]),

    CasoIngesta("c04", "tabla",
        "Cliente | Direccion | Cant\n"
        "Perez | 3400 Nixon Rd | 5\n"
        "Gomez | 4975 Washtenaw Ave | 2",
        [_c("3400 Nixon Rd", nombre="Perez", cantidad=5),
         _c("4975 Washtenaw Ave", nombre="Gomez", cantidad=2)]),

    CasoIngesta("c05", "correo",
        "Buenas, confirmo pedido único: 4833 E Huron River Dr, franja de 14 a 16 h, "
        "dejar en recepción.",
        [_c("4833 E Huron River Dr", ventana="14-16")]),

    CasoIngesta("c06", "whatsapp",
        "entregar en 3200 boardwalk dr (ojo es boardwalk no broadway) 1 caja",
        [_c("3200 Boardwalk Dr", cantidad=1)]),

    CasoIngesta("c07", "lista",
        "PEDIDOS:\n1) 106 Packard St - 4u\n2) 701 Miller Ave - 2u\n3) 808 E Kingsley - 1u",
        [_c("106 Packard St", cantidad=4), _c("701 Miller Ave", cantidad=2),
         _c("808 E Kingsley", cantidad=1)]),

    CasoIngesta("c08", "coords",
        "Entrega especial en lat 42.298939, lon -83.790382 (3021 Miller Rd), 2 bultos",
        [_c("3021 Miller Rd", cantidad=2, lat=42.298939, lon=-83.790382)]),

    CasoIngesta("c09", "correo",
        "Hola, repito el de ayer: 1320 Baldwin Ave para Ana. Nada más por hoy.",
        [_c("1320 Baldwin Ave", nombre="Ana")]),

    CasoIngesta("c10", "whatsapp",
        "3 entregas: 2945 East Ellsworth Road, 1143 Highland Dr y 3310 Washtenaw Ave. "
        "las dos primeras urgentes!!",
        [_c("2945 East Ellsworth Road"), _c("1143 Highland Dr"),
         _c("3310 Washtenaw Ave")]),

    CasoIngesta("c11", "tabla",
        "destino;ventana\n5940 Jackson Rd;9-12\n3792 Pontiac Trail;12-15",
        [_c("5940 Jackson Rd", ventana="9-12"),
         _c("3792 Pontiac Trail", ventana="12-15")]),

    CasoIngesta("c12", "correo",
        "Estimados: por favor coordinen entrega en 3145 Ann Arbor-Saline Rd. "
        "El cliente (Farmacia Centro) pidió 10 unidades. Saludos cordiales, Depto. Compras.",
        [_c("3145 Ann Arbor-Saline Rd", nombre="Farmacia Centro", cantidad=10)]),

    CasoIngesta("c13", "whatsapp",
        "una sola: 4125 Washtenaw Avenue, dejar con el conserje",
        [_c("4125 Washtenaw Avenue")]),

    CasoIngesta("c14", "lista",
        "entregas manana\n* 1919 S Industrial Hwy (3 cajas)\n* 100 Briarwood Circle",
        [_c("1919 S Industrial Hwy", cantidad=3), _c("100 Briarwood Circle")]),

    CasoIngesta("c15", "correo",
        "Hola!! disculpa el desorden, necesito q lleven a 2000 waters road (sí, waters) "
        "unas 4 cajitas antes del mediodia porfa",
        [_c("2000 Waters Rd", cantidad=4, ventana="antes del mediodia")]),

    CasoIngesta("c16", "tabla",
        "N | cliente | direccion | u | horario\n"
        "1 | Luis | 950 Greene Street | 1 | 10-11\n"
        "2 | Sofia | 301 E Huron St | 2 | 11-12\n"
        "3 | Pablo | 701 Miller Ave | 3 | 15-16",
        [_c("950 Greene Street", nombre="Luis", cantidad=1, ventana="10-11"),
         _c("301 E Huron St", nombre="Sofia", cantidad=2, ventana="11-12"),
         _c("701 Miller Ave", nombre="Pablo", cantidad=3, ventana="15-16")]),

    CasoIngesta("c17", "whatsapp",
        "jajaja ok entonces manda a 4001 jackson rd y a 4550 jackson rd (no confundas los numeros)",
        [_c("4001 Jackson Rd"), _c("4550 Jackson Rd")]),

    CasoIngesta("c18", "correo",
        "Confirmación de ruta — Cliente VIP en 3400 Nixon Rd, 2 bultos, llamar al llegar. "
        "Firma: J. Pérez (no es una dirección).",
        [_c("3400 Nixon Rd", nombre="VIP", cantidad=2)]),

    CasoIngesta("c19", "lista",
        "- 3480 Jackson Avenue\n- (pendiente de confirmar)\n- 1320 Baldwin Ave",
        [_c("3480 Jackson Avenue"), _c("1320 Baldwin Ave")]),

    CasoIngesta("c20", "coords",
        "GPS: 42.227372,-83.722697 => 1143 Highland Dr, 1 caja",
        [_c("1143 Highland Dr", cantidad=1, lat=42.227372, lon=-83.722697)]),

    CasoIngesta("c21", "whatsapp",
        "necesito 2: 4975 washtenaw ave (5u) y 4833 e huron river dr (ventana 8-10)",
        [_c("4975 Washtenaw Ave", cantidad=5),
         _c("4833 E Huron River Dr", ventana="8-10")]),

    CasoIngesta("c22", "correo",
        "Buen día. Hoy no hay entregas. Mañana les paso la lista. Gracias.",
        []),  # caso negativo: no hay pedidos

    CasoIngesta("c23", "tabla",
        "direccion,cantidad\n808 E Kingsley,2\n2945 East Ellsworth Road,1\n106 Packard St,4",
        [_c("808 E Kingsley", cantidad=2),
         _c("2945 East Ellsworth Road", cantidad=1),
         _c("106 Packard St", cantidad=4)]),
]


def total_pedidos() -> int:
    return sum(len(c.esperados) for c in CORPUS)
