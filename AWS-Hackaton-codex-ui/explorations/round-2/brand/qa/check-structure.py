"""Check the delivered SVG assets and make a local optical proof."""

from pathlib import Path
import json
import xml.etree.ElementTree as ET
import html

ROOT = Path(__file__).resolve().parent.parent
items = json.loads((ROOT / "manifest.json").read_text())
checks = []
for item in items:
    for kind in ["light", "dark", "symbol"]:
        asset = ROOT / item[kind]
        source = asset.read_text()
        svg = ET.fromstring(source)
        forbidden = []
        for element in svg.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in ["image", "script", "foreignObject", "text", "use"]:
                forbidden.append(tag)
            for key, value in element.attrib.items():
                if key.endswith("href") or "url(" in value:
                    forbidden.append(f"{key}={value}")
        checks.append({
            "path": item[kind], "viewBox": svg.get("viewBox"),
            "pure_vector": not forbidden, "forbidden": forbidden,
            "accessible_name": svg.get("aria-label"),
        })
result = {
    "scope": "36 delivered SVGs; custom lettering, no embedded or external images, fonts, scripts or references",
    "concept_count": len(items), "family_counts": {family: sum(x["family"] == family for x in items) for family in ["typographic", "monogram", "symbol"]},
    "recommended_count": sum(x["recommended"] for x in items),
    "passed": len(checks) == 36 and all(x["pure_vector"] and x["accessible_name"] for x in checks),
    "assets": checks,
}
(ROOT / "qa" / "structure.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
cards = []
for item in items:
    symbol = (ROOT / item["symbol"]).read_text()
    rows = []
    for theme in ["light", "dark"]:
        examples = "".join(f'<div><span>{size} px</span><figure style="width:{size}px;height:{size}px">{symbol}</figure></div>' for size in [20, 32, 80])
        rows.append(f'<section class="{theme}">{examples}</section>')
    cards.append(f'<article><h2>{html.escape(item["name"])}</h2>{"".join(rows)}</article>')
proof = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZMD — Ronda 02, prueba óptica</title><style>
*{box-sizing:border-box}body{margin:0;padding:28px;background:#eaf0f6;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#151d26}
h1{font-size:26px;margin:0 0 8px}body>p{margin:0 0 24px;color:#526170}main{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}
article{border:1px solid #cbd6e2;border-radius:8px;overflow:hidden;background:white}h2{font-size:13px;margin:0;padding:14px}
section{display:flex;gap:28px;align-items:center;justify-content:space-around;padding:14px 18px;height:126px}
section>div{display:flex;align-items:center;flex-direction:column;justify-content:flex-start;gap:11px;height:104px}
span{font-size:9px;opacity:.7}figure{padding:0;margin:0;display:block;flex:none}svg{width:100%;height:100%;display:block}
.light{background:white;color:#151d26}.dark{background:#151e29;color:#f5f8fc}
@media(max-width:900px){main{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><h1>Ronda 02 — símbolos a 20, 32 y 80 px</h1><p>El tamaño pequeño verifica usos compactos; la comparación principal muestra los logos completos y grandes.</p><main>""" + "".join(cards) + "</main></html>"
(ROOT / "qa" / "small-sizes.html").write_text(proof)
print(json.dumps({k: v for k, v in result.items() if k != "assets"}, ensure_ascii=False, indent=2))
