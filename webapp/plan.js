import { applyDataProvenance, SOURCE_DETAILS, SCENARIO, NODES, VEHICLES, ROUTES, nodeById, routeById, routesForNode, visitLabel, number, visitIdsForRoute, deliveryCount, chargeCount } from './shared/data.js';
import { createMap } from './map.js';
import { icon, carDrawing } from './shared/icons.js';
import { detailSurface } from './shared/motion.js';
import { readPlanContext, savePlanContext } from './state.js';
import { escapeHtml as esc } from './shared/html.js';

applyDataProvenance();

const $ = id => document.getElementById(id);
const detail = detailSurface($('selection'));
let selected = null, tab = 'fleet', selectedStop = null, map, returnFocus;
let detailOpen = false;
const mobile = matchMedia('(max-width:760px)');
const vehicleById = id => VEHICLES.find(v => v.id === id);
const batteryStyle = (value, property) => Number.isFinite(value) && value >= 0 && value <= 100
  ? `style="${property}:${value}%"` : 'hidden';
const saved = readPlanContext();
const previous = saved?.scenario === SCENARIO.id ? saved : {};
const params = new URLSearchParams(location.search);
const explicit = ['vehicle', 'tab', 'stop', 'chargers'].some(key => params.has(key));
const initial = explicit ? {
  vehicle: params.get('vehicle'),
  tab: params.get('tab') || (params.has('vehicle') ? 'stops' : 'fleet'),
  stop: params.has('stop') ? { vehicleId: params.get('vehicle'), index: Number(params.get('stop')) } : null,
  chargers: params.get('chargers') === '1'
} : previous;
selected = routeById(initial.vehicle) ? initial.vehicle : null;
tab = initial.tab === 'stops' ? 'stops' : 'fleet';
const initialStop = initial.stop && initial.stop.vehicleId === selected &&
  Number.isInteger(initial.stop.index) && routeById(selected)?.stops[initial.stop.index] ? initial.stop : null;
const initialView = (!explicit || params.has('tab')) && previous.vehicle === selected &&
  previous.tab === tab && previous.stop?.vehicleId === initialStop?.vehicleId &&
  previous.stop?.index === initialStop?.index &&
  previous.viewportWidth === innerWidth ? previous.view : null;

function remember() {
  if (document.body.dataset.leavingDemo === 'true') return;
  const context = {
    scenario: SCENARIO.id, vehicle: selected, tab,
    stop: detailOpen ? selectedStop : null,
    chargers: $('chargers').getAttribute('aria-pressed') === 'true',
    view: map?.getView(), viewportWidth: innerWidth
  };
  savePlanContext(context);
  const query = new URLSearchParams({ tab });
  if (selected) query.set('vehicle', selected);
  if (context.stop) query.set('stop', context.stop.index);
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
$('plan-deliveries').textContent = new Set(ROUTES.flatMap(r => [...visitIdsForRoute(r)])).size;
$('plan-demand').textContent = `/ ${NODES.filter(n => n.type === 'visit').length}`;
$('plan-energy').textContent = number(ROUTES.every(r => Number.isFinite(r.energyKwh)) ? ROUTES.reduce((sum, r) => sum + r.energyKwh, 0) : NaN);
$('plan-charges').textContent = ROUTES.reduce((sum, r) => sum + chargeCount(r), 0);

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
  for (const key of ['fleet', 'stops']) {
    $(key + '-tab').setAttribute('aria-selected', String(tab === key));
    $(key + '-tab').tabIndex = key === tab ? 0 : -1;
  }
  $('sidebar-content').classList.toggle('stops', tab === 'stops');
  $('sidebar-content').setAttribute('aria-labelledby', tab + '-tab');
  if (tab === 'fleet') {
    $('sidebar-content').innerHTML = VEHICLES.map(v => {
      const r = routeById(v.id);
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
          <span><strong>${r ? chargeCount(r) : '—'}</strong> recargas</span>
        </div>
        <button class="route-button" data-vehicle="${esc(v.id)}" ${r ? '' : 'disabled'} aria-label="${r ? 'Explorar recorrido de' : 'Sin recorrido asignado a'} ${esc(v.name)}">${r ? `Explorar recorrido ${icon('arrow', 16)}` : 'Sin recorrido asignado'}</button>
      </article>`;
    }).join('');
    return;
  }
  const routes = selected ? [routeById(selected)] : ROUTES;
  $('sidebar-content').innerHTML =
    (selected ? `<button class="all-routes" id="all-routes">${icon('back', 14)} Toda la flota</button>` : '') +
    routes.map(r => {
      const v = vehicleById(r.vehicleId);
      return `<section class="route-group" style="--route:${v.color}"><div class="route-head"><i class="vehicle-dot"></i>${esc(v.name)}<small>${deliveryCount(r)} entregas · ${number(r.distanceKm)} km de ejemplo</small></div>` +
        r.stops.map((s, i) => {
          const n = nodeById(s.nodeId);
          const active = selectedStop?.vehicleId === v.id && selectedStop.index === i;
          return `<button class="stop-row ${active ? 'active' : ''}" data-stop="${esc(n.id)}" data-route="${esc(v.id)}" data-index="${i}" aria-pressed="${active}">
            <span class="stop-number">${n.type === 'base' ? icon('base', 16) : n.type === 'charger' ? icon('plug', 16) : visitLabel(n.id)}</span>
            <span class="stop-name">${n.type === 'base' ? (i === 0 ? 'Salida de base' : 'Regreso a base') : esc(n.label)}<small>${n.type === 'charger' ? `Recarga · +${number(s.chargeKwh)} kWh` : esc(n.id)}</small></span>
            <strong>${number(s.arrivalSoc)} %</strong>
          </button>`;
        }).join('') + '</section>';
    }).join('');
}

function vehicle(id, focus = false, refit = true) {
  if (!routeById(id)) return;
  selected = id;
  selectedStop = null;
  tab = 'stops';
  detailOpen = false;
  detail.hide();
  render();
  map?.selectVehicle(id, refit);
  if (focus) $('all-routes')?.focus({ preventScroll: true });
  remember();
}

function stop(node, routeId, index, trigger, move = true) {
  let route = routeById(routeId || selected);
  if (!route?.stopIds.includes(node.id)) {
    route = routesForNode(node.id)[0];
  }
  const sameOccurrence = route && selectedStop?.vehicleId === route.vehicleId &&
    route.stops[selectedStop.index]?.nodeId === node.id;
  const stopIndex = index ?? (sameOccurrence ? selectedStop.index : route?.stops.findIndex(s => s.nodeId === node.id));
  const state = route?.stops[stopIndex];
  const previousFocus = document.activeElement;
  if (route && selected !== route.vehicleId) vehicle(route.vehicleId, false, move);
  selectedStop = state ? { vehicleId: route.vehicleId, index: stopIndex } : null;
  // Avoid replacing the list (and its focused button) on each stop selection.
  for (const el of document.querySelectorAll('[data-stop]')) {
    const active = el.dataset.route === selectedStop?.vehicleId && Number(el.dataset.index) === selectedStop?.index;
    el.classList.toggle('active', active);
    el.setAttribute('aria-pressed', String(active));
  }
  const currentRow = [...document.querySelectorAll('[data-stop]')].find(el =>
    el.dataset.route === selectedStop?.vehicleId && Number(el.dataset.index) === selectedStop?.index);
  const previousControl = previousFocus?.isConnected && previousFocus !== document.body ? previousFocus : null;
  returnFocus = trigger?.isConnected ? trigger : (trigger ? currentRow : previousControl) || currentRow || $('stops-tab');
  const title = node.type === 'base' && state ? (stopIndex === 0 ? 'Salida de base' : 'Regreso a base') : node.label;
  $('selection').innerHTML = `<button class="close" id="close-selection" aria-label="Cerrar detalle">${icon('close', 16)}</button>
    <p class="detail-eyebrow">${route ? esc(vehicleById(route.vehicleId).name) + ' · ' : ''}${esc(node.id)}</p>
    <h3>${esc(title)}</h3>
    <p>${node.type === 'charger' ? SOURCE_DETAILS.charger : node.type === 'base' ? 'Centro de distribución' : state ? 'Entrega prevista' : 'Sin asignar en este plan'}</p>
    ${state ? `<div class="stop-battery"><span>Batería al llegar<strong>${number(state.arrivalSoc)} <small>%</small></strong></span><span>Al salir<strong>${number(state.departureSoc)} <small>%</small></strong></span></div>${state.chargeKwh ? `<p class="charge-note">${icon('plug', 14)} Recarga de ejemplo: +${number(state.chargeKwh)} kWh</p>` : ''}`
      : node.type === 'charger' ? `<p>${esc(node.connectors || 'Conectores sin información')}</p><p>Disponibilidad no verificada.</p>` : ''}`;
  $('selection-status').textContent = state
    ? `${vehicleById(route.vehicleId).name}. ${title}. Batería de ejemplo: llegada ${number(state.arrivalSoc)} %, salida ${number(state.departureSoc)} %.`
    : `${title}. ${node.type === 'charger' ? 'Disponibilidad no verificada.' : node.type === 'visit' ? 'Sin asignar en este plan.' : ''}`;
  detail.show();
  detailOpen = true;
  map?.selectNode(node.id, move);
  if (trigger && mobile.matches) {
    $('close-selection').focus({preventScroll:true});
    document.querySelector('.map-region').scrollIntoView({block:'start',behavior:'auto'});
  }
  remember();
}

$('sidebar-content').addEventListener('click', e => {
  const v = e.target.closest('[data-vehicle]');
  if (v) vehicle(v.dataset.vehicle, e.detail === 0);
  const s = e.target.closest('[data-stop]');
  if (s) stop(nodeById(s.dataset.stop), s.dataset.route, Number(s.dataset.index), s);
  if (e.target.closest('#all-routes')) {
    selected = null;
    selectedStop = null;
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
  remember();
}
$('selection').addEventListener('click', e => { if (e.target.closest('#close-selection')) closeDetail(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('selection').hidden && !document.querySelector('dialog[open]')) closeDetail();
});
for (const key of ['fleet', 'stops']) {
  $(key + '-tab').onclick = () => { tab = key; render(); remember(); };
  $(key + '-tab').onkeydown = e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    tab = e.key === 'Home' ? 'fleet' : e.key === 'End' ? 'stops' : tab === 'fleet' ? 'stops' : 'fleet';
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
  onSelect: n => stop(n, undefined, undefined, undefined, false),
  onVehicleSelect: id => vehicle(id),
  onReady: () => {
    const restored = initialView && map.restoreView(initialView);
    if (!restored && detailOpen && selectedStop) {
      map.selectNode(routeById(selectedStop.vehicleId).stops[selectedStop.index].nodeId);
    }
  },
  focusPoint,
  padding: () => mobile.matches ? { top: 155, right: 35, bottom: 135, left: 35 } : { top: 160, right: 70, bottom: 105, left: 70 }
});
if (selected) map.selectVehicle(selected, false);
if (initial.chargers) {
  $('chargers').setAttribute('aria-pressed', 'true');
  map.toggleChargers(true);
}
if (initialStop) {
  const state = routeById(selected).stops[initialStop.index];
  stop(nodeById(state.nodeId), selected, initialStop.index, undefined, false);
}
