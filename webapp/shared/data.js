// Design examples only. This module neither solves nor validates an energy model.
import { validateFixture } from './validate-fixture.js';

let response = await fetch(new URL('../data/fixture.local.json', import.meta.url));
export const DATA_SOURCE = response.status === 404 ? 'synthetic' : 'local';
if (DATA_SOURCE === 'synthetic') {
  response = await fetch(new URL('../data/demo.synthetic.json', import.meta.url));
}
if (!response.ok) throw new Error(`No se pudo cargar el escenario (${response.status}).`);
const fixture = validateFixture(await response.json());
if (DATA_SOURCE === 'synthetic' && fixture.SCENARIO.synthetic !== true) {
  throw new Error('El ejemplo de respaldo debe identificarse como sintético.');
}
export const { SCENARIO, VEHICLES, NODES, ROUTES } = fixture;
export const SOURCE_DETAILS = DATA_SOURCE === 'synthetic' ? {
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
}
export const nodeById = id => NODES.find(node => node.id === id);
export const routeById = id => ROUTES.find(route => route.vehicleId === id);
export const routesForNode = id => ROUTES.filter(route => route.stops.some(stop => stop.nodeId === id));
// Compact location labels shared by pins and rows; not IDs or itinerary positions.
const visitLabels = new Map(NODES.filter(node => node.type === 'visit')
  .map((node, index) => [node.id, String(index + 1)]));
export const visitLabel = id => visitLabels.get(id) || '';
export const number = (n, digits = 1) => Number.isFinite(n) ? n.toLocaleString('es-CL', {maximumFractionDigits: digits}) : '—';
// These design fixtures describe assigned visits, not completed deliveries.
// The motor's eventual served-delivery contract must replace this interpretation.
export const visitIdsForRoute = route => new Set((route?.stops || [])
  .map(stop => stop.nodeId).filter(id => nodeById(id)?.type === 'visit'));
export const deliveryCount = route => visitIdsForRoute(route).size;
export const chargeCount = route => (route?.stops || []).filter(stop => stop.chargeKwh > 0).length;
