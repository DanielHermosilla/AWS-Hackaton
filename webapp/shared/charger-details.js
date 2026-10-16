import { escapeHtml as esc } from './html.js';

const reportedText = value => typeof value === 'string' && value.trim() ? value.trim() : 'Sin informar';
const reportedNumber = (value, unit = '') => Number.isFinite(value)
  ? `${value.toLocaleString('es-CL', { maximumFractionDigits: 6 })}${unit}` : 'Sin informar';
const hasCoordinates = node => Number.isFinite(node.lat) && Number.isFinite(node.lng);

// Station metadata is independent of any vehicle or occurrence in a route.
export function chargerDetails(node) {
  const powerKw = node.powerKw === undefined ? node.maxPowerKw : node.powerKw;
  const facts = [
    ['Dirección', reportedText(node.address)],
    ['Red declarada', reportedText(node.network)],
    ['Conectores declarados', reportedText(node.connectors)],
    ['Potencia máxima reportada', reportedNumber(powerKw, ' kW')],
    ['Puertos totales', reportedNumber(node.totalPorts)],
    ['Puertos DC', reportedNumber(node.dcFastPorts)],
    ['Puertos nivel 2', reportedNumber(node.level2Ports)],
    ['Ubicación', hasCoordinates(node)
      ? `Latitud ${reportedNumber(node.lat)} · longitud ${reportedNumber(node.lng)}`
      : 'Sin coordenadas; disponible en esta lista'],
    ['Disponibilidad', 'No verificada']
  ];
  return `<section class="charger-metadata" aria-label="Datos de la estación">
    <h4>Datos de la estación</h4>
    <dl>${facts.map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>
    <p class="charger-caveat">La potencia reportada corresponde a la estación; no indica potencia por conector, potencia aceptada por el vehículo ni tiempo de carga. Los conectores declarados no verifican compatibilidad real.</p>
  </section>`;
}

export function chargerOccurrences(nodeId, routes) {
  return routes.flatMap(route => route.stops.flatMap((state, index) =>
    state.nodeId === nodeId ? [{ vehicleId: route.vehicleId, index, state }] : []));
}

export function chargerChargeText(chargeKwh, example = false) {
  if (!Number.isFinite(chargeKwh)) return 'Recarga no informada';
  if (chargeKwh === 0) return 'Paso sin recarga · 0 kWh';
  return `${example ? 'Recarga de ejemplo' : 'Incorporada a batería'}: ${reportedNumber(chargeKwh, ' kWh')}`;
}

export function chargerList(nodes, routes, { noSolution = false, selectedId = null } = {}) {
  const chargers = nodes.filter(node => node.type === 'charger');
  if (!chargers.length) return '<p class="plan-empty">Esta instancia no contiene estaciones de carga.</p>';
  const used = new Set(routes.flatMap(route => route.stops.map(state => state.nodeId)));
  return `<div class="charger-list">
    <p class="charger-list-note">Todas las estaciones de la instancia. Disponibilidad sin verificar.</p>
    ${chargers.map(node => {
      const usage = noSolution ? 'Sin recorrido calculado' : used.has(node.id) ? 'En el recorrido' : 'Fuera del recorrido';
      const active = node.id === selectedId;
      return `<button type="button" class="charger-row${active ? ' active' : ''}" data-charger="${esc(node.id)}" aria-pressed="${active}" aria-controls="selection">
        <span class="charger-row-title">${esc(node.label)}</span>
        <span class="charger-row-id">${esc(node.id)}</span>
        <span class="charger-row-status">${usage}${hasCoordinates(node) ? '' : ' · Sin coordenadas'}</span>
      </button>`;
    }).join('')}
  </div>`;
}
