"""Regenerate the original, editable round-two SVG drawings. Python stdlib only."""

from pathlib import Path
import html
import json
import math

ROOT = Path(__file__).resolve().parent
INK = "var(--logo-ink, {ink})"
ACCENT = "var(--logo-accent, {accent})"
Z = "M0 0H40V8L11 40H40V48H0V40L29 8H0Z"
M = "M0 48V0H9L24 24L39 0H48V48H39V14L24 37L9 14V48Z"
D = "M0 0H19C35 0 44 8 44 24S35 48 19 48H0Z M9 8V40H18C29 40 35 35 35 24S29 8 18 8Z"
ELECTRIC_Z = "M0 0H42V8L25 23H34L11 40H42V48H0V40L18 23H9L30 8H0Z"
MOBILITY = (
    "M0 12V0L5.5 7L11 0V12 "
    "M22.5 0C15.5 0 15.5 12 22.5 12S29.5 0 22.5 0Z "
    "M35 12V0H39.5C46 0 46 6 39.5 6H35 M39.5 6C46 6 46 12 39.5 12H35 "
    "M53 0V12 M64 0V12H74 M80 0V12 M91 0H103 M97 0V12 "
    "M110 0L116 6L122 0 M116 6V12"
)


def path(d, paint="accent", extra=""):
    return f'<path d="{d}" fill="{{{paint}}}" {extra}/>'


def line(d, width=4, paint="accent"):
    return f'<path d="{d}" fill="none" stroke="{{{paint}}}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def rect(x, y, width, height, radius=0, paint="accent"):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{{{paint}}}"/>'


def group(content, transform):
    return f'<g transform="{transform}">{content}</g>'


def lettering(z=Z, z_paint="ink", gap=0):
    return (
        path(z, z_paint, 'fill-rule="evenodd"')
        + group(path(M, "ink"), f"translate({49 + gap} 0)")
        + group(path(D, "ink", 'fill-rule="evenodd"'), f"translate({107 + gap} 0)")
    )


def mobility(x, y):
    return group(line(MOBILITY, 1.7, "ink"), f"translate({x} {y})")


def road_z():
    holes = "M7 3H14V5H7Z M24 3H31V5H24Z M9 43H16V45H9Z M26 43H33V45H26Z "
    ux, uy = -29 / math.hypot(29, 32), 32 / math.hypot(29, 32)
    for cx, cy in [(26, 17), (17, 27), (8.5, 37)]:
        points = [(cx + ux*a - uy*b, cy + uy*a + ux*b) for a, b in [(-3, -1.1), (3, -1.1), (3, 1.1), (-3, 1.1)]]
        holes += "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in points) + "Z "
    return Z + " " + holes


ROAD_Z = road_z()

# Typographic identities: the primary drawing is the full custom ZMD lettering.
t01 = (
    group(path(Z, "ink") + group(path(M, "ink"), "translate(49 0)")
          + group(path(D, "accent", 'fill-rule="evenodd"'), "translate(107 0)")
          + rect(144, 12, 24, 7, 2) + rect(144, 29, 24, 7, 2)
          + line("M107 38V52Q107 62 97 62H19Q9 62 9 52V48", 4), "translate(73 20)")
    + mobility(88, 112)
)
t02 = (
    group('<rect x="0" y="0" width="184" height="72" rx="10" fill="none" stroke="{accent}" stroke-width="4"/>'
          + rect(184, 23, 8, 26, 2)
          + group(lettering(), "translate(16 12)"), "translate(61 22)")
    + mobility(92, 112)
)
t03 = group(lettering(ROAD_Z, "accent"), "translate(84 29)") + mobility(98, 97)
t04 = group(lettering(ELECTRIC_Z, "accent", 3), "translate(82 29)") + mobility(98, 97)

t01_symbol = (
    group(path(Z), "translate(11 8) scale(.88 .75)")
    + line("M45 44V49Q45 54 40 54H29", 4)
    + rect(17, 47, 13, 13, 3)
    + rect(10, 49, 9, 4, 1) + rect(10, 56, 9, 4, 1)
)
t02_symbol = (
    '<rect x="5" y="14" width="49" height="36" rx="6" fill="none" stroke="{accent}" stroke-width="4"/>'
    + rect(54, 25, 6, 14, 1.5)
    + group(path(Z), "translate(17 21) scale(.65 .46)")
)
t03_symbol = group(path(ROAD_Z, extra='fill-rule="evenodd"'), "translate(12 8)")
t04_symbol = group(path(ELECTRIC_Z), "translate(11 8)")

# Z monograms: the letter is kept legible, with a literal electrical mechanism.
m05 = (
    path("M8 12H43Q50 12 50 19V29H42L21 45H51V53H8V45L35 22H8Z")
    + rect(36, 7, 15, 25, 4)
    + rect(47, 12, 13, 5, 1.5) + rect(47, 24, 13, 5, 1.5)
)
m06 = (
    path("M20 10H44Q51 10 51 17V53Q51 58 46 58H18Q13 58 13 53V17Q13 10 20 10Z "
         "M20 21H44V26L27 43H44V48H20V43L37 26H20Z", extra='fill-rule="evenodd"')
    + rect(25, 4, 14, 6, 1.5)
)
m07 = (
    '<rect x="11" y="8" width="33" height="46" rx="5" fill="none" stroke="{accent}" stroke-width="4"/>'
    + group(path(Z), "translate(18 16) scale(.48 .56)")
    + line("M44 21C54 21 57 25 57 33V44Q57 49 52 49H50V40", 4)
    + rect(46, 32, 8, 10, 2)
    + rect(47, 27, 2.5, 6, .8) + rect(51, 27, 2.5, 6, .8)
    + line("M8 57H47", 4)
)
m08 = (
    line("M14 14H49L14 49H45", 6)
    + '<circle cx="14" cy="14" r="6" fill="{accent}"/>'
    + path("M44 41H50Q55 41 55 46V51Q55 56 50 56H44Z")
    + rect(54, 43, 8, 4, 1) + rect(54, 50, 8, 4, 1)
)

# Recognizable symbols: vehicle, plug, battery return, and charging location.
s09 = (
    path("M8 31L14 21Q17 16 23 16H37Q41 16 45 21L52 30H56Q60 30 60 35V44H55"
         "C55 35 41 35 41 44H26C26 35 12 35 12 44H7V35Q7 32 8 31Z "
         "M20 22H28V30H15Z M32 22H37L44 30H32Z", "ink", 'fill-rule="evenodd"')
    + '<circle cx="19" cy="44" r="5" fill="{ink}"/><circle cx="48" cy="44" r="5" fill="{ink}"/>'
    + line("M56 31V23", 3.5)
    + rect(50, 12, 12, 13, 3)
    + rect(52, 5, 3.5, 9, 1) + rect(58, 5, 3.5, 9, 1)
)
s10 = (
    path("M23 17H41Q48 17 48 24V35Q48 44 39 44H25Q16 44 16 35V24Q16 17 23 17Z "
         "M23 24H41V28L29 35H41V39H23V35L35 28H23Z", extra='fill-rule="evenodd"')
    + rect(21, 6, 6, 13, 1.5) + rect(37, 6, 6, 13, 1.5)
    + line("M32 44V51Q32 57 38 57H48", 5)
)
s11 = (
    '<rect x="13" y="22" width="37" height="23" rx="4" fill="none" stroke="{accent}" stroke-width="3.5"/>'
    + rect(50, 29, 4, 10, 1)
    + group(path(ELECTRIC_Z), "translate(24 27) scale(.36 .28)")
    + line("M9 20C14 6 36 3 48 13L54 18 M46 18H55V9", 3.5)
    + line("M55 46C50 60 28 63 16 53L10 48 M18 48H9V57", 3.5)
)
s12 = path("M32 5C17 5 10 16 10 28C10 42 32 59 32 59S54 42 54 28C54 16 47 5 32 5Z "
           "M35 15L21 32H31L27 44L43 26H33Z", extra='fill-rule="evenodd"')


def standard_lockup(symbol):
    return group(symbol, "translate(36 35)") + group(lettering(), "translate(125 32)") + mobility(139, 91)


CONCEPTS = [
    ("01-zmd-conectado", "ZMD conectado", "typographic", "La D es un enchufe y el cable une el nombre.",
     "Las clavijas ensanchan la D; el nombre necesita espacio horizontal. El símbolo compacto es una Z conectada derivada, no la D aislada.", t01, t01_symbol, True),
    ("02-zmd-bateria", "ZMD en batería", "typographic", "El nombre completo vive dentro de una batería reconocible.",
     "Es la opción más literal, pero la batería como contenedor es frecuente. El nombre completo no sirve como favicon; se entrega una batería con Z.", t02, t02_symbol, False),
    ("03-zmd-recorrido", "ZMD en ruta", "typographic", "La Z es una calzada con marcas de carril; M y D conservan su lectura.",
     "Las marcas de carril se suavizan a 20 px. Sin ellas, el símbolo se parece a una Z geométrica corriente.", t03, t03_symbol, False),
    ("04-zmd-electrico", "ZMD eléctrico", "typographic", "El centro de la Z adopta el quiebre de un rayo, sin perder el nombre.",
     "El rayo es frecuente en energía y rendimiento. La Z sigue siendo legible en el nombre, pero aislada puede leerse primero como descarga.", t04, t04_symbol, True),
    ("05-z-enchufada", "Z enchufada", "monogram", "La barra superior de la Z termina en dos clavijas de enchufe.",
     "Las clavijas y el remate superior deben conservar su separación al reducir. Puede asociarse a electricidad general antes que a una flota.", standard_lockup(m05), m05, False),
    ("06-z-bateria", "Z en batería", "monogram", "Una Z en negativo identifica una batería vertical de bordes suaves.",
     "La batería es reconocible pero común; la singularidad depende de la proporción de la Z. La masa visual es mayor que en las otras opciones.", standard_lockup(m06), m06, True),
    ("07-z-cargador", "Z en cargador", "monogram", "Un cargador eléctrico con cable conserva una Z clara en el frente.",
     "Cable, base y letra suman detalles. A 20 px se reconoce mejor el cargador que la Z; conviene valorar si esa jerarquía sirve al uso.", standard_lockup(m07), m07, False),
    ("08-z-ruta-carga", "Z de ruta con carga", "monogram", "Un recorrido en Z une un punto de salida con un enchufe de llegada.",
     "La Z abierta pesa menos que la tipografía. El punto inicial puede parecer decorativo si se separa del nombre y del contexto de movilidad.", standard_lockup(m08), m08, False),
    ("09-vehiculo-electrico", "Vehículo conectado", "symbol", "Un vehículo compacto se conecta a un enchufe visible; ZMD firma el conjunto.",
     "La relación con movilidad eléctrica es directa, pero la silueta resulta más pictográfica y menos singular. El enchufe pierde detalle en pequeño.", standard_lockup(s09), s09, False),
    ("10-enchufe-z", "Enchufe con Z", "symbol", "Un enchufe simple lleva la Z en negativo y continúa en un cable.",
     "Sin el nombre puede parecer una marca de energía doméstica. Su ventaja es la lectura inmediata; su riesgo, parecer demasiado genérico.", standard_lockup(s10), s10, False),
    ("11-bateria-retorno", "Batería y retorno", "symbol", "Una batería y dos flechas representan la carga y el regreso del vehículo.",
     "Las flechas pueden sugerir reciclaje o regeneración; aquí representan regreso. El dibujo no describe recuperación real de energía ni una prestación medida.", standard_lockup(s11), s11, False),
    ("12-punto-carga", "Punto de carga", "symbol", "Un pin con descarga eléctrica hace evidente la localización de recargas.",
     "Pin y rayo son signos muy usados en mapas de carga. Es claro y operativo, pero el más difícil de diferenciar como identidad propia.", standard_lockup(s12), s12, False),
]
FAMILIES = {"typographic": "ZMD tipográfico", "monogram": "Monograma Z", "symbol": "Símbolo eléctrico"}


def svg(content, label, dark=False, compact=False):
    ink, accent = ("#F5F8FC", "#78B4FF") if dark else ("#151D26", "#126ADE")
    colored = content.replace("{ink}", INK.format(ink=ink)).replace("{accent}", ACCENT.format(accent=accent))
    if compact:
        colored = content.replace("{ink}", "currentColor").replace("{accent}", "currentColor")
    viewbox = "0 0 64 64" if compact else "0 0 320 144"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" '
            f'aria-label="{html.escape(label, quote=True)}">'
            f'<title>{html.escape(label)}</title>{colored}</svg>\n')


def main():
    manifest, options = [], []
    for cid, name, family, meaning, risk, drawing, symbol, recommended in CONCEPTS:
        folder = ROOT / "assets" / cid
        folder.mkdir(parents=True, exist_ok=True)
        label = f"ZMD Mobility — {name}"
        light_svg, dark_svg, symbol_svg = svg(drawing, label), svg(drawing, label, dark=True), svg(symbol, label, compact=True)
        for filename, source in [("logo-light.svg", light_svg), ("logo-dark.svg", dark_svg), ("symbol.svg", symbol_svg)]:
            (folder / filename).write_text(source)
        entry = {
            "id": cid, "name": name, "family": family, "family_label": FAMILIES[family],
            "meaning": meaning, "risk": risk, "recommended": recommended,
            "light": f"assets/{cid}/logo-light.svg", "dark": f"assets/{cid}/logo-dark.svg",
            "symbol": f"assets/{cid}/symbol.svg", "status": "proposal-round-2",
        }
        manifest.append(entry)
        options.append({**entry, "svg": light_svg, "dark_svg": dark_svg, "symbol_svg": symbol_svg})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "options.js").write_text("window.ZMD_ROUND_2 = " + json.dumps(options, ensure_ascii=False) + ";\n")
    print(f"Built {len(manifest)} proposals / {len(manifest) * 3} SVG files in {ROOT}")


if __name__ == "__main__":
    main()
