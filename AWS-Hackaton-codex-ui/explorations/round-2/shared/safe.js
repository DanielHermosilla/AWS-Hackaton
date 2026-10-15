// Validación y escape de datos externos antes de pintarlos en el DOM.
// Todas las vistas leen el escenario a través de data.js, que llama a
// validateScenario: un CSV/JSON con HTML o valores fuera de formato se rechaza
// antes de llegar a cualquier innerHTML. escapeHtml es la segunda barrera.

const ID = /^[A-Za-z0-9_.-]{1,64}$/;
const COLOR = /^#[0-9a-fA-F]{6}$/;
// Texto visible: letras (incluidas tildes), dígitos, espacios y puntuación simple.
// Excluye < > " ' ` & y caracteres de control.
const TEXT = /^[\p{L}\p{N} .,;:()·\/+%°_\-]{0,400}$/u;
const NODE_TYPES = new Set(['base', 'visit', 'charger']);

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"'`]/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;'
  })[c]);
}

export const safeColor = value => COLOR.test(String(value)) ? value : '#576b7e';

function fail(path, why) {
  throw new Error(`Escenario rechazado: ${path} ${why}.`);
}
function id(v, path) { if (typeof v !== 'string' || !ID.test(v)) fail(path, 'no es un identificador válido'); }
function text(v, path) { if (v != null && (typeof v !== 'string' || !TEXT.test(v))) fail(path, 'contiene caracteres no permitidos'); }
function num(v, path, min = -Infinity, max = Infinity) {
  if (v != null && (typeof v !== 'number' || !Number.isFinite(v) || v < min || v > max)) fail(path, 'no es un número válido');
}

export function validateScenario(data) {
  if (!data || typeof data !== 'object') fail('escenario', 'no es un objeto');
  const { SCENARIO = {}, VEHICLES, NODES, ROUTES } = data;
  if (!Array.isArray(VEHICLES) || !Array.isArray(NODES) || !Array.isArray(ROUTES)) fail('escenario', 'incompleto');
  if (NODES.length > 2000 || VEHICLES.length > 50) fail('escenario', 'demasiado grande');
  for (const k of ['id', 'name', 'fileName', 'provenance']) text(SCENARIO[k], `SCENARIO.${k}`);
  VEHICLES.forEach((v, i) => {
    id(v.id, `VEHICLES[${i}].id`); text(v.name, `VEHICLES[${i}].name`); text(v.model, `VEHICLES[${i}].model`);
    if (!COLOR.test(String(v.color))) fail(`VEHICLES[${i}].color`, 'no es #rrggbb');
    num(v.initialSoc, `VEHICLES[${i}].initialSoc`, 0, 100);
  });
  NODES.forEach((n, i) => {
    id(n.id, `NODES[${i}].id`);
    if (!NODE_TYPES.has(n.type)) fail(`NODES[${i}].type`, 'desconocido');
    text(n.label, `NODES[${i}].label`); text(n.connectors, `NODES[${i}].connectors`);
    num(n.lat, `NODES[${i}].lat`, -90, 90); num(n.lng, `NODES[${i}].lng`, -180, 180);
    num(n.maxPowerKw, `NODES[${i}].maxPowerKw`, 0, 1000);
    if (n.vehicleId != null) id(n.vehicleId, `NODES[${i}].vehicleId`);
  });
  const known = new Set(NODES.map(n => n.id));
  ROUTES.forEach((r, i) => {
    id(r.vehicleId, `ROUTES[${i}].vehicleId`);
    for (const k of ['energyKwh', 'chargeKwh', 'distanceKm']) num(r[k], `ROUTES[${i}].${k}`, 0, 1e5);
    num(r.finalSoc, `ROUTES[${i}].finalSoc`, 0, 100);
    if (!Array.isArray(r.stopIds) || r.stopIds.some(s => !known.has(s))) fail(`ROUTES[${i}].stopIds`, 'referencia nodos inexistentes');
    (r.stops || []).forEach((s, j) => {
      if (!known.has(s.nodeId)) fail(`ROUTES[${i}].stops[${j}].nodeId`, 'no existe');
      for (const k of ['arrivalSoc', 'departureSoc', 'chargeKwh']) num(s[k], `ROUTES[${i}].stops[${j}].${k}`, 0, 1e5);
    });
    const coords = r.geometry?.coordinates;
    if (r.geometry?.type !== 'LineString' || !Array.isArray(coords) ||
        coords.some(c => !Array.isArray(c) || c.length < 2 || !c.every(Number.isFinite))) {
      fail(`ROUTES[${i}].geometry`, 'no es un LineString válido');
    }
  });
  return data;
}
