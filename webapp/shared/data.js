// One data source per page: explicit example or a specific server-side execution.
// Normalization validates presentation structure, never the energy model.
import { validateFixture } from './validate-fixture.js';
import { getSavedRun, readExecution } from './solver-client.js';

const execution = readExecution();
let fixture, source, raw = null;
if (execution?.runId) {
  raw = await getSavedRun(execution.runId);
  const { adaptSolverResponse } = await import('./solver-adapter.js');
  fixture = adaptSolverResponse(raw);
  source = 'solver';
} else if (execution) {
  source = 'pending';
  fixture = {SCENARIO: {id: 'pending', name: 'Sin resultado', location: 'Carga y calcula una instancia',
    initialSoc: null, demonstration: false}, VEHICLES: [], NODES: [], ROUTES: []};
} else {
  let response = await fetch(new URL('../data/fixture.local.json', import.meta.url));
  source = response.status === 404 ? 'synthetic' : 'local';
  if (source === 'synthetic') response = await fetch(new URL('../data/demo.synthetic.json', import.meta.url));
  if (!response.ok) throw new Error(`No se pudo cargar el escenario (${response.status}).`);
  fixture = validateFixture(await response.json());
  if (source === 'synthetic' && fixture.SCENARIO.synthetic !== true)
    throw new Error('El ejemplo de respaldo debe identificarse como sintético.');
}
export const DATA_SOURCE = source;
export const RAW_RESPONSE = raw;
export const RUN_INFO = fixture.RUN_INFO || null;
export const { SCENARIO, VEHICLES, NODES, ROUTES } = fixture;
export const SOURCE_DETAILS = source === 'solver' ? {
  title: 'Resultado del motor', file: 'Motor', context: 'Resultado del motor',
  description: 'Plan calculado por el motor ev_routing de Daniel para esta instancia nativa y configuración. Las entregas son planificadas, no completadas en terreno.',
  geometry: RUN_INFO.network?.vial
    ? 'La instancia nativa declara una red vial. Solo se dibujan las geometrías guardadas; los tramos sin geometría permanecen en la lista.'
    : 'La red de esta ejecución no es vial. Sus distancias y trazados son aproximaciones; no acreditan conectividad por calles.',
  stations: 'Estaciones incluidas en la instancia; disponibilidad en terreno sin verificar.',
  summary: RUN_INFO.validationScope,
  route: RUN_INFO.network?.vial ? 'Geometría vial declarada' : 'Aproximación no vial',
  charger: 'Estación de la instancia',
} : source === 'pending' ? {
  title: 'Sin resultado', file: 'Pendiente', context: 'Instancia sin calcular',
  description: 'Carga una instancia y ejecútala para consultar sus rutas.',
  geometry: 'No hay geometría de resultados disponible.',
  stations: 'Sin resultado del motor.', summary: 'No se ha completado una ejecución.', route: 'Sin recorrido calculado', charger: 'Estación',
} : DATA_SOURCE === 'synthetic' ? {
  title: 'Ejemplo sintético',
  file: 'Ejemplo',
  context: 'Ejemplo sintético',
  description: 'Ubicaciones y recorridos inventados para probar la interfaz. No representan el escenario de CASE. ZMD Mobility es la consultora que desarrolla esta experiencia.',
  geometry: 'Los trazados son líneas ilustrativas entre puntos, no rutas viales. Consumo, recarga y batería también son inventados; no son resultados del motor ni una validación energética.',
  stations: 'Estaciones ficticias del ejemplo sintético; no representan infraestructura real.',
  summary: 'Datos sintéticos para diseño. Ubicaciones, recorridos y valores inventados; sin validación del motor.',
  route: 'Trazado sintético, no vial',
  charger: 'Estación ficticia · ejemplo',
} : {
  title: 'Escenario público',
  file: 'CSV',
  context: 'Escenario público',
  description: 'Las ubicaciones pertenecen al escenario público de CASE. ZMD Mobility es la consultora que desarrolla esta experiencia.',
  geometry: 'Los recorridos siguen calles de OpenStreetMap mediante OSRM, con un orden de visitas preparado para el diseño. Consumo, recarga y batería son ilustrativos: el motor aún no los ha calculado ni validado.',
  stations: 'Estaciones registradas en el escenario público de CASE; disponibilidad sin verificar.',
  summary: 'Datos del escenario público de CASE. Recorridos y batería de ejemplo; disponibilidad de estaciones sin verificar.',
  route: 'Trazado vial de ejemplo',
  charger: 'Estación registrada',
};
export function applyDataProvenance(root = document) {
  for (const element of root.querySelectorAll('[data-source-text]')) {
    const text = SOURCE_DETAILS[element.dataset.sourceText];
    if (text) element.textContent = text;
  }
  document.body.dataset.demoSource = DATA_SOURCE;
  const badge = root.querySelector('#data-badge');
  if (badge && (source === 'solver' || source === 'pending')) {
    const label = source === 'solver' ? 'Resultado del motor' : 'Sin resultado';
    badge.setAttribute('aria-label', label);
    badge.querySelector('.data-badge__full').textContent = label;
    badge.querySelector('.data-badge__short').textContent = source === 'solver' ? 'Motor' : 'Pendiente';
    root.querySelector('#about-heading').textContent = label;
    root.querySelector('.about-caveat').textContent = source === 'solver'
      ? 'La comprobación se limita al modelo y a los datos del proveedor. Esta beta no acredita consumos reales, disponibilidad, optimalidad global ni entregas realizadas en terreno.'
      : 'No se sustituye una ejecución fallida por datos de ejemplo. Puedes reintentar o elegir el ejemplo de diseño de forma explícita.';
  }
}
export const nodeById = id => NODES.find(node => node.id === id);
export const routeById = id => ROUTES.find(route => route.vehicleId === id);
export const routesForNode = id => ROUTES.filter(route => route.stops.some(stop => stop.nodeId === id));
// Compact location labels shared by pins and rows; not IDs or itinerary positions.
const visitLabels = new Map(NODES.filter(node => node.type === 'visit')
  .map((node, index) => [node.id, String(index + 1)]));
export const visitLabel = id => visitLabels.get(id) || '';
export const number = (n, digits = 1) => Number.isFinite(n) ? n.toLocaleString('es-CL', {maximumFractionDigits: digits}) : '—';
// Real results count explicit service; examples retain their illustrative assignments.
export const visitIdsForRoute = route => source === 'solver' ? new Set(route?.servedVisitIds || [])
  : new Set((route?.stops || []).map(stop => stop.nodeId).filter(id => nodeById(id)?.type === 'visit'));
export const deliveryCount = route => visitIdsForRoute(route).size;
export const chargeCount = route => (route?.stops || []).some(stop => stop.chargeKwh === null)
  ? null : (route?.stops || []).filter(stop => stop.chargeKwh > 0).length;
