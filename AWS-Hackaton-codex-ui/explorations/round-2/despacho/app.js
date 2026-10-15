import { SCENARIO, VEHICLES, ROUTES, NODES } from '../shared/data.js';
import { createMap } from '../shared/map.js';
import { carDrawing } from '../shared/icons.js';

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const number = (value) => typeof value === 'number' && Number.isFinite(value) ? value : null;
const format = (value, digits = 1) => number(value) === null ? '—' : new Intl.NumberFormat('es-CL', { maximumFractionDigits: digits }).format(value);
const socText = (value) => number(value) === null ? '—' : `${format(value)} %`;
const visits = NODES.filter((node) => node.type === 'visit');
const chargers = NODES.filter((node) => node.type === 'charger');
const nodeById = new Map(NODES.map((node) => [String(node.id), node]));
const vehicleById = new Map(VEHICLES.map((vehicle) => [vehicle.id, vehicle]));
const state = {
  tab: 'deliveries', filter: 'all', selectedId: null, plan: 'unplanned', chargersVisible: false,
  soc: Object.fromEntries(VEHICLES.map((vehicle) => [vehicle.id, vehicle.initialSoc])),
};
let map;
const appliedMapState = { plan: null, vehicle: undefined, chargers: null };

const paths = {
  battery: '<rect x="2" y="7" width="18" height="10" rx="2"/><path d="M22 11v2M5 10v4m4-4v4"/>',
  bolt: '<path d="m13 2-8 12h6l-1 8 9-12h-7l1-8Z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  base: '<path d="m3 10 9-7 9 7v11H3V10Zm5 11v-8h8v8"/>',
};
const icon = (name, css = '') => `<svg viewBox="0 0 24 24" class="${css}" aria-hidden="true">${paths[name] || paths.info}</svg>`;
const routeFor = (vehicleId) => ROUTES.find((route) => route.vehicleId === vehicleId);
const routeForNode = (id) => ROUTES.find((route) => route.stopIds.some((stopId) => String(stopId) === String(id)));
const stopForNode = (route, id) => route?.stops?.find((stop) => String(stop.nodeId) === String(id));
const hasPlan = () => state.plan === 'example';
const assignmentFor = (node) => hasPlan() ? routeForNode(node.id) : null;
const colorFor = (vehicle) => /^#[0-9a-f]{3,8}$/i.test(vehicle?.color || '') ? vehicle.color : '#527445';
const announce = (text) => { $('#announcement').textContent = text; };
const demoValue = (value) => hasPlan() ? format(value) : '—';

function setMapState() {
  if (!map) return;
  const plan = hasPlan();
  const vehicle = plan && state.filter.startsWith('auto-') ? state.filter : null;
  const chargersShown = state.chargersVisible || state.filter === 'chargers';
  if (appliedMapState.plan !== plan) map.setPlanVisible?.(plan);
  if (appliedMapState.vehicle !== vehicle) map.selectVehicle(vehicle);
  if (appliedMapState.chargers !== chargersShown) map.toggleChargers(chargersShown);
  Object.assign(appliedMapState, { plan, vehicle, chargers: chargersShown });
}

function setTab(tab, focus = false) {
  state.tab = tab;
  if (tab === 'fleet' && state.filter === 'chargers') state.filter = 'all';
  render();
  if (focus) $(`#tab-${tab}`).focus();
}

function setFilter(filter) {
  state.filter = filter;
  state.tab = 'deliveries';
  if (filter === 'chargers') state.chargersVisible = true;
  render();
}

function selectNode(id, fromMap = false, retainFocus = false) {
  const node = nodeById.get(String(id));
  if (!node) return;
  const wasSelected = state.selectedId === String(id);
  state.selectedId = String(id);
  if (fromMap && node.type === 'charger') state.filter = 'chargers';
  if (fromMap && node.type === 'visit' && (state.filter === 'chargers' || (state.filter.startsWith('auto-') && assignmentFor(node)?.vehicleId !== state.filter))) state.filter = 'all';
  render();
  if (fromMap) map?.selectNode(node.id, false);
  else if (!wasSelected) map?.selectNode(node.id);
  const rowButton = [...document.querySelectorAll('.row-select')].find((button) => button.dataset.node === String(id));
  rowButton?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
  if (retainFocus) rowButton?.focus({ preventScroll: true });
}

function renderVehicleStrip() {
  $('#vehicle-strip').innerHTML = VEHICLES.map((vehicle) => {
    const route = routeFor(vehicle.id);
    const percent = state.soc[vehicle.id];
    const assignedCount = hasPlan() ? route?.stopIds.filter((id) => nodeById.get(String(id))?.type === 'visit').length ?? 0 : null;
    return `<button type="button" class="vehicle-summary" data-vehicle="${esc(vehicle.id)}" aria-label="Revisar ${esc(vehicle.name)}, batería inicial ${esc(percent)} por ciento">
      <span class="vehicle-summary-header"><span class="vehicle-name"><span class="route-dot" style="background:${colorFor(vehicle)}"></span>${esc(vehicle.name)}</span>${carDrawing(colorFor(vehicle))}</span>
      <span class="vehicle-model">${esc(vehicle.model || 'Nissan Leaf 2013')}</span>
      <span class="vehicle-battery-line"><span><span class="soc-pair"><b>${format(percent)}</b><span>%</span></span><span class="soc-description">Batería inicial</span></span><span class="return-soc"><b>${hasPlan() ? socText(route?.finalSoc) : '—'}</b><span>Al volver · ejemplo</span></span></span>
      <span class="battery-meter" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, percent))}%"></span></span>
      <span class="vehicle-mini-detail"><span>${assignedCount === null ? 'Sin asignación' : `${assignedCount} entregas · ejemplo`}</span><span>Recarga ${demoValue(route?.chargeKwh)} kWh</span></span>
    </button>`;
  }).join('');
}

function renderNote() {
  const note = $('#plan-note');
  note.classList.toggle('is-stale', state.plan === 'stale');
  if (state.plan === 'stale') {
    note.innerHTML = `${icon('info')}<div><strong>El ejemplo ya no corresponde a esta batería inicial.</strong> Asignaciones, rutas y energía retiradas.<button type="button" class="restore-button" data-restore>Restaurar demostración al 60 %</button></div>`;
  } else if (hasPlan()) {
    note.innerHTML = `${icon('bolt')}<div><strong>Plan de ejemplo visible.</strong> Asignaciones, consumo y recargas ilustrativos; sin optimización ni validación energética.</div>`;
  } else {
    note.innerHTML = `${icon('info')}<div><strong>Escenario cargado, sin plan del motor.</strong> Abre el ejemplo para revisar entregas, recargas y batería de regreso.</div>`;
  }
  $('#show-example').disabled = state.plan === 'stale';
}

function filteredNodes() {
  if (state.filter === 'chargers') return chargers;
  if (state.filter.startsWith('auto-')) return visits.filter((node) => assignmentFor(node)?.vehicleId === state.filter);
  return visits;
}

function chargerPower(node) {
  return number(node.maxPowerKw) ?? number(node.powerKw) ?? number(node.power_kw) ?? number(node.chargingPowerKw);
}

function renderRows() {
  const nodes = filteredNodes();
  const isChargerList = state.filter === 'chargers';
  $('#table-caption').textContent = isChargerList ? 'Cargadores registrados del escenario' : 'Entregas del escenario';
  $('#table-head').innerHTML = isChargerList ? '<tr><th scope="col">Estación</th><th scope="col">Registro</th><th scope="col">Potencia</th></tr>' : '<tr><th scope="col">Local</th><th scope="col">Asignación</th><th scope="col">Batería al llegar</th></tr>';
  $('#filtered-count').textContent = `${nodes.length} ${isChargerList ? 'estaciones' : 'entregas'}`;
  $('#node-rows').innerHTML = nodes.map((node) => {
    const route = assignmentFor(node);
    const vehicle = route ? vehicleById.get(route.vehicleId) : null;
    const stop = stopForNode(route, node.id);
    const visitOrder = route ? route.stopIds.filter((id) => nodeById.get(String(id))?.type === 'visit').findIndex((id) => String(id) === String(node.id)) + 1 : null;
    const ordinal = visits.findIndex((item) => String(item.id) === String(node.id)) + 1;
    const label = node.label || `${isChargerList ? 'Estación' : 'Local'} ${isChargerList ? node.id : ordinal}`;
    return `<tr data-node="${esc(node.id)}" data-selected="${String(node.id) === state.selectedId}">
      <td><button type="button" class="row-select" data-node="${esc(node.id)}" aria-pressed="${String(node.id) === state.selectedId}"><span class="node-number">${isChargerList ? icon('bolt') : String(ordinal).padStart(2, '0')}</span><span class="row-text"><span class="node-name">${esc(label)}</span><span class="node-code">${esc(node.id)}</span></span></button></td>
      <td>${isChargerList ? '<span class="charger-note">Registrado<br>Disponibilidad desconocida</span>' : `<span class="assignment ${vehicle ? 'has-assignment' : ''}">${vehicle ? `<span class="route-dot" style="background:${colorFor(vehicle)}"></span>${esc(vehicle.name)} · ${visitOrder}` : 'Por asignar'}</span>`}</td>
      <td>${isChargerList ? `<span class="arrival-soc">${format(chargerPower(node))}${chargerPower(node) === null ? '' : ' kW'}</span>` : `<span class="arrival-soc ${number(stop?.arrivalSoc) === null ? 'missing-value' : ''}">${hasPlan() ? socText(stop?.arrivalSoc) : '—'}</span>`}</td>
    </tr>`;
  }).join('');
  $('#empty-list').hidden = nodes.length > 0;
  $('#empty-list').textContent = hasPlan() ? 'Este vehículo no tiene entregas en el ejemplo.' : 'Aún no hay asignaciones. Abre el plan de ejemplo o vuelve a Todos para revisar los locales.';
}

function renderFleet() {
  $('#fleet-panel').innerHTML = VEHICLES.map((vehicle) => {
    const route = routeFor(vehicle.id);
    const chargingStops = hasPlan() ? route?.stops?.filter((stop) => number(stop.chargeKwh) !== null && stop.chargeKwh > 0) ?? [] : [];
    const orderCount = route?.stopIds.filter((id) => nodeById.get(String(id))?.type === 'visit').length ?? 0;
    return `<article class="fleet-card">
      <div class="fleet-card-header"><div><h2><span class="route-dot" style="background:${colorFor(vehicle)}"></span> ${esc(vehicle.name)}</h2><p>${esc(vehicle.model || 'Nissan Leaf 2013')} · salida y regreso a la base</p></div>${carDrawing(colorFor(vehicle))}</div>
      <div class="fleet-metrics"><div class="fleet-metric"><span>Batería inicial</span><strong>${format(state.soc[vehicle.id])} <small>%</small></strong></div><div class="fleet-metric"><span>Al volver · ejemplo</span><strong>${demoValue(route?.finalSoc)} <small>${hasPlan() ? '%' : ''}</small></strong></div><div class="fleet-metric"><span>Consumo · ejemplo</span><strong>${demoValue(route?.energyKwh)} <small>${hasPlan() ? 'kWh' : ''}</small></strong></div></div>
      <div class="fleet-route-note">${icon('battery')}<span>${hasPlan() ? `${orderCount} entregas · ${format(route?.distanceKm)} km · recarga ${format(route?.chargeKwh)} kWh. Todas son cifras de demostración.` : 'Sin resultado vigente. El porcentaje inicial es un parámetro; no demuestra autonomía ni regreso.'}</span></div>
      ${chargingStops.map((stop) => `<div class="fleet-charge-stop"><button type="button" data-node="${esc(stop.nodeId)}">${icon('bolt')}${esc(nodeById.get(String(stop.nodeId))?.label || `Estación ${stop.nodeId}`)}</button><span>+${format(stop.chargeKwh)} kWh · ejemplo</span></div>`).join('')}
    </article>`;
  }).join('') + '<p class="fleet-footer">Una estación registrada no acredita compatibilidad ni disponibilidad. Los valores de recarga ilustran el flujo.</p>';
}

function renderSelection() {
  const node = nodeById.get(state.selectedId);
  if (!node) {
    $('#selection-card').innerHTML = `<div class="selection-title"><div><h2>Entrega, vehículo y batería</h2><p class="selection-type">Lista y mapa vinculados</p></div>${icon('pin')}</div><p class="selection-neutral">Selecciona una fila o un punto para revisar su ubicación y los datos del ejemplo.</p>`;
    return;
  }
  const route = assignmentFor(node);
  const stop = stopForNode(route, node.id);
  const vehicle = route ? vehicleById.get(route.vehicleId) : null;
  const label = node.label || `Punto ${node.id}`;
  let detail;
  if (node.type === 'charger') {
    detail = `<div class="selection-values"><div class="selection-value"><span>Potencia registrada</span><b>${format(chargerPower(node))}${chargerPower(node) === null ? '' : ' kW'}</b></div><div class="selection-value"><span>Recarga · ejemplo</span><b>${hasPlan() && stop ? `${format(stop.chargeKwh)} kWh` : '—'}</b></div></div><p class="selection-neutral">${node.connectors ? `Conectores: ${esc(node.connectors)}. ` : ''}Disponibilidad y compatibilidad no verificadas.</p>`;
  } else if (node.type === 'base') {
    detail = '<p class="selection-neutral">Los dos Leaf salen de esta base y deben regresar. La batería inicial se configura en Flota.</p>';
  } else {
    detail = hasPlan() ? `<div class="selection-values"><div class="selection-value"><span>Asignación · ejemplo</span><b>${esc(vehicle?.name || 'Sin asignación')}</b></div><div class="selection-value"><span>Batería al llegar · ejemplo</span><b>${socText(stop?.arrivalSoc)}</b></div></div>` : '<p class="selection-neutral">Ubicación del local. No hay asignación ni batería de llegada vigentes.</p>';
  }
  $('#selection-card').innerHTML = `<div class="selection-title"><div><h2>${esc(label)}</h2><p class="selection-type">${node.type === 'charger' ? 'Estación registrada' : node.type === 'base' ? 'Centro de distribución' : 'Local de entrega'} · ${esc(node.id)}</p></div>${icon(node.type === 'charger' ? 'bolt' : node.type === 'base' ? 'base' : 'pin')}</div>${detail}`;
}

function render() {
  document.querySelectorAll('[data-tab]').forEach((button) => {
    const active = button.dataset.tab === state.tab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', active);
    button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll('[data-nav]').forEach((button) => {
    const active = button.dataset.nav === (state.tab === 'fleet' ? 'fleet' : state.filter === 'chargers' ? 'chargers' : 'deliveries');
    button.classList.toggle('is-active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
    button.title = { deliveries: 'Entregas', fleet: 'Flota', chargers: 'Cargadores' }[button.dataset.nav];
    button.setAttribute('aria-label', button.title);
  });
  document.querySelectorAll('[data-filter]').forEach((button) => {
    const active = button.dataset.filter === state.filter;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active);
  });
  $('#deliveries-panel').hidden = state.tab !== 'deliveries';
  $('#fleet-panel').hidden = state.tab !== 'fleet';
  $('#vehicle-strip').hidden = state.tab === 'fleet';
  $('#charger-layer').checked = state.chargersVisible || state.filter === 'chargers';
  $('#map-plan-label').hidden = !hasPlan();
  $('#map-subtitle').textContent = hasPlan() ? 'Plan de ejemplo · recorridos y paradas' : 'Ubicaciones · sin plan del motor';
  renderNote();
  renderVehicleStrip();
  renderRows();
  renderFleet();
  renderSelection();
  setMapState();
}

function showExample() {
  if (state.plan === 'stale') return;
  state.plan = 'example';
  render();
  map?.fit();
  announce('Plan de ejemplo visible. No se ejecutó una optimización.');
}

function restoreDemo() {
  state.soc = Object.fromEntries(VEHICLES.map((vehicle) => [vehicle.id, vehicle.initialSoc]));
  state.plan = 'example';
  state.filter = 'all';
  render();
  map?.fit();
  $('#show-example').focus();
  announce('Demostración restaurada. Los dos vehículos salen con su batería inicial original.');
}

function editSoc() {
  $('#soc-fields').innerHTML = VEHICLES.map((vehicle) => `<div class="soc-field"><label for="soc-${esc(vehicle.id)}">${esc(vehicle.name)}<span>${esc(vehicle.model || 'Nissan Leaf 2013')}</span></label><span class="soc-input-wrap"><input id="soc-${esc(vehicle.id)}" name="${esc(vehicle.id)}" type="number" min="0" max="100" step="0.1" required inputmode="decimal" value="${esc(state.soc[vehicle.id])}" aria-describedby="soc-error"><span>%</span></span></div>`).join('');
  $('#soc-error').hidden = true;
  $('#soc-dialog').showModal();
}

$('#soc-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const next = {};
  let invalidInput;
  for (const vehicle of VEHICLES) {
    const input = document.getElementById(`soc-${vehicle.id}`);
    const raw = input.value.trim();
    const value = raw === '' ? null : Number(raw);
    const invalid = value === null || !Number.isFinite(value) || value < 0 || value > 100;
    input.setAttribute('aria-invalid', invalid);
    if (invalid) invalidInput ??= input;
    next[vehicle.id] = value;
  }
  if (invalidInput) {
    $('#soc-error').textContent = 'Completa la batería de cada vehículo con un número entre 0 y 100 %. Un campo vacío no equivale a 0 %.';
    $('#soc-error').hidden = false;
    invalidInput.focus();
    return;
  }
  const changed = VEHICLES.some((vehicle) => next[vehicle.id] !== state.soc[vehicle.id]);
  state.soc = next;
  if (changed) {
    state.plan = 'stale';
    state.filter = 'all';
  }
  $('#soc-dialog').close();
  render();
  announce(changed ? 'Batería inicial guardada. El plan de ejemplo fue retirado; no hay un resultado nuevo.' : 'La batería inicial no cambió.');
});

document.addEventListener('click', (event) => {
  const target = event.target.closest('button, tr[data-node]');
  if (!target) return;
  if (target.dataset.tab) setTab(target.dataset.tab);
  else if (target.dataset.filter) setFilter(target.dataset.filter);
  else if (target.dataset.nav) target.dataset.nav === 'fleet' ? setTab('fleet') : setFilter(target.dataset.nav === 'chargers' ? 'chargers' : 'all');
  else if (target.dataset.vehicle) { state.filter = target.dataset.vehicle; setTab('fleet', true); }
  else if (target.dataset.node) selectNode(target.dataset.node, false, target.classList.contains('row-select'));
  else if (target.hasAttribute('data-edit-soc')) editSoc();
  else if (target.hasAttribute('data-restore')) restoreDemo();
  else if (target.dataset.closeDialog) document.getElementById(target.dataset.closeDialog).close();
});

$('.view-tabs').addEventListener('keydown', (event) => {
  if (!event.target.matches('[data-tab]') || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  setTab(event.key === 'Home' ? 'deliveries' : event.key === 'End' ? 'fleet' : state.tab === 'deliveries' ? 'fleet' : 'deliveries', true);
});
$('#node-rows').addEventListener('keydown', (event) => {
  if (!event.target.matches('.row-select') || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
  const buttons = [...document.querySelectorAll('.row-select')];
  const index = buttons.indexOf(event.target);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
  event.preventDefault();
  buttons[next]?.focus();
});
$('#show-example').addEventListener('click', showExample);
$('#fit-map').addEventListener('click', () => map?.fit());
$('#charger-layer').addEventListener('change', (event) => {
  state.chargersVisible = event.target.checked;
  if (!state.chargersVisible && state.filter === 'chargers') state.filter = 'all';
  render();
});
$('#show-data').addEventListener('click', () => $('#data-dialog').showModal());
window.addEventListener('pagehide', () => map?.destroy(), { once: true });

$('#scenario-summary').textContent = `${visits.length} locales · ${VEHICLES.length} Nissan Leaf · ${chargers.length} estaciones registradas`;
$('#nav-delivery-count').textContent = visits.length;
$('#nav-charger-count').textContent = chargers.length;
$('#delivery-tab-count').textContent = visits.length;
$('#charger-layer-count').textContent = `(${chargers.length})`;
VEHICLES.forEach((vehicle, index) => document.documentElement.style.setProperty(`--route-${index + 1}`, colorFor(vehicle)));
$('#scenario-data').innerHTML = `<div class="data-summary"><div><strong>${visits.length}</strong><span>Locales</span></div><div><strong>${VEHICLES.length}</strong><span>Leaf 2013</span></div><div><strong>${chargers.length}</strong><span>Estaciones</span></div></div><p>Ubicaciones del escenario de Ann Arbor. ${esc(SCENARIO.source || 'Instancia pública del desafío CASE.')}</p><p>Las asignaciones, rutas y cifras de batería pertenecen a una demostración. No acreditan factibilidad, autonomía ni disponibilidad de cargadores.</p>`;
render();
try {
  map = await createMap('map', { showRoutes: false, onSelect: (node) => selectNode(node.id, true) });
  setMapState();
} catch {
  $('#map').innerHTML = '<p class="map-error">No se pudo cargar la cartografía. Las entregas y la configuración de flota siguen disponibles en la lista.</p>';
  announce('La cartografía no pudo cargarse. La lista sigue disponible.');
}
