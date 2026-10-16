import { applyDataProvenance, DATA_SOURCE, SOURCE_DETAILS, SCENARIO, NODES, VEHICLES, ROUTES, RUN_INFO, nodeById, routeById, routesForNode, visitLabel, number, visitIdsForRoute, deliveryCount, chargeCount } from './shared/data.js';
import { createMap } from './map.js';
import { icon, carDrawing } from './shared/icons.js';
import { detailSurface } from './shared/motion.js';
import { readPlanContext, savePlanContext } from './state.js';
import { escapeHtml as esc } from './shared/html.js';
import { stopFacts } from './shared/solver-output.js';
import { chargerDetails, chargerList, chargerOccurrences, chargerChargeText } from './shared/charger-details.js';

applyDataProvenance();

const $ = id => document.getElementById(id);
const chargerStyles = document.createElement('link');
chargerStyles.rel = 'stylesheet';
chargerStyles.href = new URL('./charger-details.css', import.meta.url);
document.head.append(chargerStyles);
const chargerTab = document.createElement('button');
chargerTab.id = 'chargers-tab';
chargerTab.type = 'button';
chargerTab.setAttribute('role', 'tab');
chargerTab.setAttribute('aria-controls', 'sidebar-content');
chargerTab.innerHTML = `Cargadores <span>${NODES.filter(node => node.type === 'charger').length}</span>`;
$('stops-tab').after(chargerTab);
const tabs = ['fleet', 'stops', 'chargers'];
const pending = DATA_SOURCE === 'pending';
const noSolution = RUN_INFO?.hasSolution === false;
const detail = detailSurface($('selection'));
let selected = null, tab = 'fleet', selectedStop = null, selectedCharger = null, map, returnFocus;
let detailOpen = false;
const mobile = matchMedia('(max-width:760px)');
const vehicleById = id => VEHICLES.find(v => v.id === id);
const served = new Set(ROUTES.flatMap(route => [...visitIdsForRoute(route)]));
const unserved = noSolution ? [] : NODES.filter(node => node.type === 'visit' && !served.has(node.id));
const stopTitle = (node, index, route) => node.type !== 'base' ? node.label
  : index === 0 ? 'Salida de base' : index === route.stops.length - 1 ? 'Regreso a base' : 'Paso por base';
const servedAt = (state, node) => RUN_INFO ? state?.deliveredVisitIds?.includes(node.id) : node.type === 'visit' && !!state;
const batteryStyle = (value, property) => Number.isFinite(value) && value >= 0 && value <= 100
  ? `style="${property}:${value}%"` : 'hidden';
const saved = readPlanContext();
const previous = saved?.scenario === SCENARIO.id ? saved : {};
const params = new URLSearchParams(location.search);
const explicit = (!RUN_INFO || params.get('run') === RUN_INFO.runId)
  && ['vehicle', 'tab', 'stop', 'chargers', 'charger'].some(key => params.has(key));
const initial = explicit ? {
  vehicle: params.get('vehicle'),
  tab: params.get('tab') || (params.has('vehicle') ? 'stops' : params.get('chargers') === '1' ? 'chargers' : 'fleet'),
  stop: params.has('stop') ? { vehicleId: params.get('vehicle'), index: Number(params.get('stop')) } : null,
  charger: params.get('charger'),
  chargers: params.get('chargers') === '1'
} : previous;
selected = routeById(initial.vehicle) ? initial.vehicle : null;
tab = tabs.includes(initial.tab) ? initial.tab : 'fleet';
const initialStop = initial.stop && initial.stop.vehicleId === selected &&
  Number.isInteger(initial.stop.index) && routeById(selected)?.stops[initial.stop.index] ? initial.stop : null;
const initialView = (!explicit || params.has('tab')) && previous.vehicle === selected &&
  previous.tab === tab && previous.stop?.vehicleId === initialStop?.vehicleId &&
  previous.stop?.index === initialStop?.index &&
  (previous.charger ?? null) === (initial.charger ?? null) &&
  previous.viewportWidth === innerWidth ? previous.view : null;

function remember() {
  if (document.body.dataset.leavingDemo === 'true') return;
  const context = {
    scenario: SCENARIO.id, vehicle: selected, tab,
    stop: detailOpen ? selectedStop : null,
    charger: detailOpen && !selectedStop ? selectedCharger : null,
    chargers: $('chargers').getAttribute('aria-pressed') === 'true',
    view: map?.getView(), viewportWidth: innerWidth
  };
  savePlanContext(context);
  const query = new URLSearchParams({ tab });
  if (RUN_INFO) query.set('run', RUN_INFO.runId);
  if (selected) query.set('vehicle', selected);
  if (context.stop) query.set('stop', context.stop.index);
  if (context.charger) query.set('charger', context.charger);
  if (context.chargers) query.set('chargers', '1');
  try {
    history.replaceState(null, '', `${location.pathname}?${query}`);
  } catch {
    // Navigation and selection also work in restricted browser contexts.
  }
}
addEventListener('pagehide', remember);
addEventListener('pageshow', () => { delete document.body.dataset.leavingDemo; });
$('scenario-location').textContent = SCENARIO.name;
$('fleet-tab').querySelector('span').textContent = VEHICLES.length;
$('stops-tab').querySelector('span').textContent = NODES.filter(n => n.type === 'visit').length;
$('plan-deliveries').textContent = pending ? '—' : RUN_INFO ? number(RUN_INFO.kpis.served_deliveries, 0) : served.size;
$('plan-demand').textContent = pending ? '/ —' : `/ ${NODES.filter(n => n.type === 'visit').length}`;
$('plan-energy').textContent = number(RUN_INFO ? RUN_INFO.totalEnergyKwh
  : ROUTES.length && ROUTES.every(r => Number.isFinite(r.energyKwh)) ? ROUTES.reduce((sum, r) => sum + r.energyKwh, 0) : null);
const charges = ROUTES.map(chargeCount);
$('plan-charges').textContent = pending || noSolution ? '—' : number(RUN_INFO ? RUN_INFO.kpis.charging_stops
  : charges.every(Number.isFinite) ? charges.reduce((sum, value) => sum + value, 0) : null, 0);
if (RUN_INFO || pending) {
  $('plan-deliveries').closest('p').querySelector('small').textContent = 'entregas del modelo';
  $('plan-energy').closest('p').querySelector('small').textContent = RUN_INFO?.totalEnergyKwh == null ? 'consumo no disponible' : 'energía informada';
  document.querySelector('.sidebar-foot p').textContent = pending ? 'Carga una instancia y calcula el plan para ver sus recorridos.'
    : RUN_INFO.feasible === true ? 'Comprobado por el proveedor. Consulta el alcance de validación de esta ejecución.'
    : RUN_INFO.feasible === false ? 'La validación detectó problemas. Revisa el estado de la ejecución.'
    : 'Validación de factibilidad no disponible para esta ejecución.';
}

for (const [id, name, size] of [
  ['about', 'info', 18], ['fit', 'target', 20], ['foot-icon', 'info', 16],
  ['delivery-icon', 'box', 21], ['energy-icon', 'battery', 21], ['charge-icon', 'plug', 21]
]) $(id).innerHTML = icon(name, size);
$('chargers').innerHTML = icon('plug', 17) + 'Cargadores';
$('base-legend').innerHTML = icon('base', 13) + 'Base';
for (const vehicle of VEHICLES) {
  const label = document.createElement('span');
  const dot = document.createElement('i');
  dot.className = 'dot';
  dot.style.backgroundColor = vehicle.color;
  label.append(dot, document.createTextNode(vehicle.name));
  $('base-legend').before(label);
}

function render() {
  for (const key of tabs) {
    $(key + '-tab').setAttribute('aria-selected', String(tab === key));
    $(key + '-tab').tabIndex = key === tab ? 0 : -1;
  }
  $('sidebar-content').classList.toggle('stops', tab !== 'fleet');
  $('sidebar-content').setAttribute('aria-labelledby', tab + '-tab');
  if (tab === 'chargers') {
    $('sidebar-content').innerHTML = pending
      ? '<p class="plan-empty">Carga y calcula una instancia para consultar sus estaciones.</p>'
      : chargerList(NODES, ROUTES, { noSolution, selectedId: detailOpen ? selectedCharger : null });
    return;
  }
  if (tab === 'fleet') {
    if (!VEHICLES.length) {
      $('sidebar-content').innerHTML = `<p class="plan-empty">${pending ? 'Aún no hay un resultado de flota.' : 'Esta ejecución no contiene vehículos.'}</p>`;
      return;
    }
    $('sidebar-content').innerHTML = VEHICLES.map(v => {
      const r = routeById(v.id);
      const hasSteps = !!r?.stops.length;
      const inactive = r?.active === false;
      return `<article class="vehicle-card ${selected === v.id ? 'active' : ''}" style="--route:${v.color}">
        <div class="vehicle-heading"><div>
          <div class="vehicle-name"><i class="vehicle-dot"></i>${esc(v.name)}</div>
          <p class="vehicle-model">${esc(v.model || 'Modelo sin indicar')}</p>
        </div>${carDrawing(v.color)}</div>
        <div class="soc-row"><span>Salida <strong>${number(v.initialSoc)} %</strong></span><span>Regreso <strong>${number(r?.finalSoc)} %</strong></span></div>
        <div class="battery-track" aria-hidden="true"><span ${batteryStyle(r?.finalSoc, 'width')}></span><i ${batteryStyle(v.initialSoc, 'left')}></i></div>
        <div class="vehicle-stats">
          <span><strong>${r ? deliveryCount(r) : '—'}</strong> entregas</span>
          <span><strong>${number(r?.energyKwh)}</strong> kWh</span>
          ${RUN_INFO ? `<span><strong>${number(r?.durationSeconds, 0)}</strong> segundos</span>`
            : `<span><strong>${r ? number(chargeCount(r), 0) : '—'}</strong> recargas</span>`}
        </div>
        ${inactive && hasSteps ? '<p class="vehicle-inactive">Sin desplazamiento · en base</p>' : ''}
        <button class="route-button" data-vehicle="${esc(v.id)}" ${hasSteps ? '' : 'disabled'} aria-label="${hasSteps ? inactive ? 'Ver estado en base de' : 'Explorar recorrido de' : 'Sin recorrido de'} ${esc(v.name)}">${hasSteps ? `${inactive ? 'Ver estado en base' : 'Explorar recorrido'} ${icon('arrow', 16)}` : 'Sin recorrido'}</button>
      </article>`;
    }).join('');
    return;
  }
  const routes = selected ? [routeById(selected)] : ROUTES;
  $('sidebar-content').innerHTML =
    (selected ? `<button class="all-routes" id="all-routes">${icon('back', 14)} Toda la flota</button>` : '') +
    routes.map(r => {
      const v = vehicleById(r.vehicleId);
      return `<section class="route-group" style="--route:${v.color}"><div class="route-head"><i class="vehicle-dot"></i>${esc(v.name)}<small>${deliveryCount(r)} entregas · ${number(r.distanceKm)} km${RUN_INFO ? '' : ' de ejemplo'}${r.active === false ? ' · Sin desplazamiento' : ''}</small></div>` +
        (r.stops.length ? '' : '<p class="plan-empty">El motor no informa paradas para este vehículo.</p>') +
        r.stops.map((s, i) => {
          const n = nodeById(s.nodeId);
          const active = selectedStop?.vehicleId === v.id && selectedStop.index === i;
          const secondary = n.type === 'charger'
            ? s.chargeKwh > 0 ? `Recarga · +${number(s.chargeKwh)} kWh` : s.chargeKwh === null ? 'Recarga no informada' : 'Paso sin recarga'
            : RUN_INFO && n.type === 'visit' ? `${n.id} · ${servedAt(s, n) ? 'Entrega del modelo' : 'Paso sin entrega'}` : n.id;
          return `<button class="stop-row ${active ? 'active' : ''}" data-stop="${esc(n.id)}" data-route="${esc(v.id)}" data-index="${i}" aria-pressed="${active}">
            <span class="stop-number">${n.type === 'base' ? icon('base', 16) : n.type === 'charger' ? icon('plug', 16) : n.type === 'junction' ? '·' : visitLabel(n.id)}</span>
            <span class="stop-name">${esc(stopTitle(n, i, r))}<small>${esc(secondary)}</small></span>
            <strong>${number(s.arrivalSoc)} %</strong>
          </button>`;
        }).join('') + '</section>';
    }).join('') +
    (!selected && unserved.length ? `<section class="route-group unserved-group"><div class="route-head">Pendientes <small>${unserved.length} locales sin servicio en el plan</small></div>${unserved.map(node =>
      `<button class="stop-row" data-unserved="${esc(node.id)}"><span class="stop-number">${visitLabel(node.id)}</span><span class="stop-name">${esc(node.label)}<small>${esc(node.id)}</small></span></button>`).join('')}</section>` : '') +
    (!routes.length && !unserved.length ? `<p class="plan-empty">${pending ? 'Aún no hay un resultado de paradas.' : noSolution ? 'El motor no dispone de una solución con recorridos.' : NODES.some(node => node.type === 'visit') ? 'Esta ejecución no contiene recorridos.' : 'Esta ejecución no contiene destinos de entrega.'}</p>` : '');
}

function vehicle(id, focus = false, refit = true, nextTab = 'stops') {
  if (!routeById(id)) return;
  selected = id;
  selectedStop = null;
  selectedCharger = null;
  tab = nextTab;
  detailOpen = false;
  detail.hide();
  render();
  map?.selectVehicle(id, refit);
  if (focus) $('all-routes')?.focus({ preventScroll: true });
  remember();
}

function stop(node, routeId, index, trigger, { move = true, overview = false } = {}) {
  let route = overview ? null : routeById(routeId || selected);
  if (!overview && !route?.stopIds.includes(node.id)) {
    route = routesForNode(node.id)[0];
  }
  const sameOccurrence = route && selectedStop?.vehicleId === route.vehicleId &&
    route.stops[selectedStop.index]?.nodeId === node.id;
  const stopIndex = index ?? (sameOccurrence ? selectedStop.index : route?.stops.findIndex(s => s.nodeId === node.id));
  const state = route?.stops[stopIndex];
  const previousFocus = document.activeElement;
  if (route && selected !== route.vehicleId) vehicle(route.vehicleId, false, move, tab === 'chargers' ? 'chargers' : 'stops');
  selectedStop = state ? { vehicleId: route.vehicleId, index: stopIndex } : null;
  selectedCharger = node.type === 'charger' ? node.id : null;
  if (selectedCharger) showChargers();
  // Avoid replacing the list (and its focused button) on each stop selection.
  for (const el of document.querySelectorAll('[data-stop]')) {
    const active = el.dataset.route === selectedStop?.vehicleId && Number(el.dataset.index) === selectedStop?.index;
    el.classList.toggle('active', active);
    el.setAttribute('aria-pressed', String(active));
  }
  for (const el of document.querySelectorAll('[data-charger]')) {
    const active = el.dataset.charger === selectedCharger;
    el.classList.toggle('active', active);
    el.setAttribute('aria-pressed', String(active));
  }
  const currentRow = [...document.querySelectorAll('[data-stop]')].find(el =>
    el.dataset.route === selectedStop?.vehicleId && Number(el.dataset.index) === selectedStop?.index);
  const previousControl = previousFocus?.isConnected && previousFocus !== document.body ? previousFocus : null;
  const stationRow = [...document.querySelectorAll('[data-charger]')].find(el => el.dataset.charger === node.id);
  const fromDetail = $('selection').contains(previousFocus);
  returnFocus = trigger?.isConnected && !$('selection').contains(trigger) ? trigger
    : (!fromDetail && previousControl) || currentRow || stationRow || $(tab + '-tab');
  const title = state ? stopTitle(node, stopIndex, route) : node.label;
  const serviceDescription = node.type === 'charger' ? SOURCE_DETAILS.charger
    : node.type === 'base' ? 'Centro de distribución'
    : node.type === 'junction' ? 'Intersección de la red · paso sin servicio'
    : state ? servedAt(state, node) ? RUN_INFO ? 'Entrega prevista por el modelo' : 'Entrega prevista' : 'Paso por el local sin entrega'
    : noSolution ? 'Sin resultado de servicio para este destino'
    : RUN_INFO ? 'Pendiente de servicio en este plan' : 'Sin asignar en este plan';
  const occurrences = node.type === 'charger' ? chargerOccurrences(node.id, ROUTES) : [];
  $('selection').classList.toggle('charger-selection', node.type === 'charger');
  $('selection').setAttribute('role', 'region');
  $('selection').setAttribute('aria-labelledby', 'selection-title');
  $('selection').innerHTML = `<button class="close" id="close-selection" aria-label="Cerrar detalle">${icon('close', 16)}</button>
    <p class="detail-eyebrow">${route ? esc(vehicleById(route.vehicleId).name) + ' · ' : ''}${esc(node.id)}</p>
    <h3 id="selection-title">${esc(title)}</h3>
    <p>${esc(serviceDescription)}</p>
    ${state ? `<div class="stop-battery"><span>Batería al llegar<strong>${number(state.arrivalSoc)} <small>%</small></strong></span><span>Al salir<strong>${number(state.departureSoc)} <small>%</small></strong></span></div>${node.type === 'charger' || state.chargeKwh ? `<p class="charge-note${state.chargeKwh > 0 ? '' : ' charge-note-neutral'}">${icon('plug', 14)} ${esc(chargerChargeText(state.chargeKwh, !RUN_INFO))}</p>` : ''}${RUN_INFO ? `<p class="stop-occurrence">Paso ${state.position} · ${route.stops.length} posiciones</p>` : ''}` : ''}
    ${node.type === 'charger' ? chargerDetails(node) : ''}
    ${occurrences.length ? `<section class="charger-occurrences" aria-label="Pasos por esta estación"><h4>Pasos por esta estación</h4>${occurrences.map(occurrence =>
      `<button type="button" data-charger-route="${esc(occurrence.vehicleId)}" data-charger-index="${occurrence.index}" aria-pressed="${selectedStop?.vehicleId === occurrence.vehicleId && selectedStop?.index === occurrence.index}">
        <span>${esc(vehicleById(occurrence.vehicleId).name)} · Paso ${occurrence.state.position ?? occurrence.index}</span><small>${esc(chargerChargeText(occurrence.state.chargeKwh, !RUN_INFO))}</small>
      </button>`).join('')}</section>` : node.type === 'charger' ? `<p class="charger-usage">${noSolution ? 'Sin recorrido calculado para esta ejecución.' : 'Esta estación no forma parte de los recorridos del plan.'}</p>` : ''}
    ${RUN_INFO && state ? `${node.type === 'charger' ? '<details class="charger-step-facts"><summary>Datos de este paso</summary>' : ''}<dl class="stop-facts">${stopFacts(state).map(fact => `<dt>${esc(fact.label)}</dt><dd>${esc(fact.value)}</dd>`).join('')}</dl>${node.type === 'charger' ? '</details>' : ''}` : ''}`;
  $('selection-status').textContent = state
    ? `${vehicleById(route.vehicleId).name}. ${title}. ${serviceDescription}. Batería ${RUN_INFO ? 'informada' : 'de ejemplo'}: llegada ${number(state.arrivalSoc)} %, salida ${number(state.departureSoc)} %.`
    : `${title}. ${node.type === 'charger' ? 'Disponibilidad no verificada.' : node.type === 'visit' ? 'Sin asignar en este plan.' : ''}`;
  detail.show();
  detailOpen = true;
  $('selection').scrollTop = 0;
  if (!Number.isFinite(node.lat) || !Number.isFinite(node.lng)) map?.selectVehicle(selected, false);
  map?.selectNode(node.id, move);
  if (fromDetail || (trigger && (mobile.matches || node.type === 'charger'))) {
    $('close-selection').focus({preventScroll:true});
    if (mobile.matches) document.querySelector('.map-region').scrollIntoView({block:'start',behavior:'auto'});
  }
  remember();
}

$('sidebar-content').addEventListener('click', e => {
  const v = e.target.closest('[data-vehicle]');
  if (v) vehicle(v.dataset.vehicle, e.detail === 0);
  const s = e.target.closest('[data-stop]');
  if (s) stop(nodeById(s.dataset.stop), s.dataset.route, Number(s.dataset.index), s);
  const u = e.target.closest('[data-unserved]');
  if (u) stop(nodeById(u.dataset.unserved), undefined, undefined, u);
  const c = e.target.closest('[data-charger]');
  if (c) stop(nodeById(c.dataset.charger), undefined, undefined, c, { overview: true });
  if (e.target.closest('#all-routes')) {
    selected = null;
    selectedStop = null;
    selectedCharger = null;
    detailOpen = false;
    detail.hide();
    render();
    map?.selectVehicle(null);
    if (e.detail === 0) $('stops-tab').focus({ preventScroll: true });
    remember();
  }
});
function closeDetail() {
  if ($('selection').contains(document.activeElement)) {
    returnFocus?.focus({preventScroll:!mobile.matches});
  }
  detail.hide();
  detailOpen = false;
  for (const row of document.querySelectorAll('[data-charger]')) {
    row.classList.remove('active');
    row.setAttribute('aria-pressed', 'false');
  }
  remember();
}
$('selection').addEventListener('click', e => {
  if (e.target.closest('#close-selection')) closeDetail();
  const occurrence = e.target.closest('[data-charger-route]');
  if (occurrence) {
    const routeId = occurrence.dataset.chargerRoute;
    const index = Number(occurrence.dataset.chargerIndex);
    stop(nodeById(routeById(routeId).stops[index].nodeId), routeId, index, occurrence);
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('selection').hidden && !document.querySelector('dialog[open]')) closeDetail();
});
function showChargers() {
  $('chargers').setAttribute('aria-pressed', 'true');
  map?.toggleChargers(true);
}
for (const key of tabs) {
  $(key + '-tab').onclick = () => { tab = key; if (tab === 'chargers') showChargers(); render(); remember(); };
  $(key + '-tab').onkeydown = e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    tab = e.key === 'Home' ? tabs[0] : e.key === 'End' ? tabs.at(-1)
      : tabs[(tabs.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    if (tab === 'chargers') showChargers();
    render();
    $(tab + '-tab').focus();
    remember();
  };
}
$('fit').onclick = () => map?.fit();
$('chargers').onclick = () => {
  const on = $('chargers').getAttribute('aria-pressed') !== 'true';
  $('chargers').setAttribute('aria-pressed', String(on));
  map?.toggleChargers(on);
  if (on) { tab = 'chargers'; render(); }
  remember();
};
render();

// Place selected markers in free map space, accounting for the actual overlays.
function focusPoint(desired) {
  const bounds = $('map').getBoundingClientRect();
  const margin = 30;
  const obstacles = [...document.querySelectorAll(
    '.map-summary,.map-tools,.legend,.selection:not([hidden]),.maplibregl-ctrl-bottom-right,.maplibregl-ctrl-attrib'
  )].filter(el => el.getClientRects().length).map(el => {
    const r = el.getBoundingClientRect();
    return {left:r.left - bounds.left - margin,right:r.right - bounds.left + margin,
      top:r.top - bounds.top - margin,bottom:r.bottom - bounds.top + margin};
  });
  const xs = [desired.x, margin, bounds.width - margin, ...obstacles.flatMap(r => [r.left, r.right])];
  const ys = [desired.y, margin, bounds.height - margin, ...obstacles.flatMap(r => [r.top, r.bottom])];
  const candidates = xs.flatMap(x => ys.map(y => ({x,y}))).filter(p =>
    p.x >= margin && p.x <= bounds.width - margin && p.y >= margin && p.y <= bounds.height - margin &&
    !obstacles.some(r => p.x > r.left && p.x < r.right && p.y > r.top && p.y < r.bottom)
  );
  return candidates.sort((a,b) =>
    Math.hypot(a.x - desired.x,a.y - desired.y) - Math.hypot(b.x - desired.x,b.y - desired.y)
  )[0] || desired;
}

map = await createMap('map', {
  onSelect: n => stop(n, undefined, undefined, undefined, { move: false }),
  onVehicleSelect: id => vehicle(id),
  onReady: () => {
    const restored = initialView && map.restoreView(initialView);
    if (!restored && detailOpen && selectedStop) {
      map.selectNode(routeById(selectedStop.vehicleId).stops[selectedStop.index].nodeId);
    } else if (!restored && detailOpen && selectedCharger) {
      map.selectNode(selectedCharger);
    }
  },
  focusPoint,
  padding: () => mobile.matches ? { top: 155, right: 35, bottom: 135, left: 35 } : { top: 160, right: 70, bottom: 105, left: 70 }
});
if (selected) map.selectVehicle(selected, false);
if (initial.chargers || tab === 'chargers') showChargers();
if (initialStop) {
  const state = routeById(selected).stops[initialStop.index];
  stop(nodeById(state.nodeId), selected, initialStop.index, undefined, { move: false });
} else if (nodeById(initial.charger)?.type === 'charger') {
  stop(nodeById(initial.charger), undefined, undefined, undefined, { move: false, overview: true });
}
