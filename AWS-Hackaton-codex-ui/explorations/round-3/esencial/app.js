import { VEHICLES, ROUTES, nodeById, number } from '../shared/data.js';
import { createMap } from '../shared/map.js';
import { icon, carDrawing } from '../shared/icons.js';
import { detailSurface } from '../shared/motion.js';

const $ = id => document.getElementById(id);
const detail = detailSurface($('selection'));
let selected = null, tab = 'fleet', selectedStop = null, map, returnFocus;
const routeById = id => ROUTES.find(r => r.vehicleId === id);
const vehicleById = id => VEHICLES.find(v => v.id === id);
const deliveryCount = r => r.stops.filter(s => nodeById(s.nodeId).type === 'visit').length;
const chargeCount = r => r.stops.filter(s => s.chargeKwh > 0).length;

for (const [id, name, size] of [
  ['about', 'info', 18], ['fit', 'target', 20], ['foot-icon', 'info', 16],
  ['delivery-icon', 'box', 21], ['energy-icon', 'battery', 21], ['charge-icon', 'plug', 21]
]) $(id).innerHTML = icon(name, size);
$('chargers').innerHTML = icon('plug', 17) + 'Cargadores';
$('base-legend').innerHTML = icon('base', 13) + 'Base';

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
          <div class="vehicle-name"><i class="vehicle-dot"></i>${v.name}</div>
          <p class="vehicle-model">${v.model}</p>
        </div>${carDrawing(v.color)}</div>
        <div class="soc-row"><span>Salida <strong>${number(v.initialSoc)} %</strong></span><span>Regreso <strong>${number(r.finalSoc)} %</strong></span></div>
        <div class="battery-track" aria-hidden="true"><span style="width:${r.finalSoc}%"></span><i style="left:${v.initialSoc}%"></i></div>
        <div class="vehicle-stats">
          <span><strong>${deliveryCount(r)}</strong> entregas</span>
          <span><strong>${number(r.energyKwh)}</strong> kWh</span>
          <span><strong>${chargeCount(r)}</strong> recarga</span>
        </div>
        <button class="route-button" data-vehicle="${v.id}" aria-label="Explorar recorrido de ${v.name}">Explorar recorrido ${icon('arrow', 16)}</button>
      </article>`;
    }).join('');
    return;
  }
  const routes = selected ? [routeById(selected)] : ROUTES;
  $('sidebar-content').innerHTML =
    (selected ? `<button class="all-routes" id="all-routes">${icon('back', 14)} Ambos vehículos</button>` : '') +
    routes.map(r => {
      const v = vehicleById(r.vehicleId);
      return `<section class="route-group" style="--route:${v.color}"><div class="route-head"><i class="vehicle-dot"></i>${v.name}<small>${deliveryCount(r)} entregas · ${number(r.distanceKm)} km de demostración</small></div>` +
        r.stops.map((s, i) => {
          const n = nodeById(s.nodeId);
          const active = selectedStop?.vehicleId === v.id && selectedStop.index === i;
          return `<button class="stop-row ${active ? 'active' : ''}" data-stop="${n.id}" data-route="${v.id}" data-index="${i}" aria-pressed="${active}">
            <span class="stop-number">${n.type === 'base' ? icon('base', 16) : n.type === 'charger' ? icon('plug', 16) : n.id.substring(1)}</span>
            <span class="stop-name">${n.type === 'base' ? (i === 0 ? 'Salida de base' : 'Regreso a base') : n.label}<small>${n.type === 'charger' ? `Recarga · +${number(s.chargeKwh)} kWh` : n.id}</small></span>
            <strong>${number(s.arrivalSoc)} %</strong>
          </button>`;
        }).join('') + '</section>';
    }).join('');
}

function vehicle(id, focus = false) {
  selected = id;
  selectedStop = null;
  tab = 'stops';
  detail.hide();
  render();
  map?.selectVehicle(id);
  if (focus) $('all-routes')?.focus({ preventScroll: true });
}

function stop(node, routeId, index, trigger) {
  let route = routeById(routeId || node.vehicleId || selected);
  if (!route?.stopIds.includes(node.id)) {
    route = ROUTES.find(r => r.stopIds.includes(node.id));
  }
  const sameOccurrence = route && selectedStop?.vehicleId === route.vehicleId &&
    route.stops[selectedStop.index]?.nodeId === node.id;
  const stopIndex = index ?? (sameOccurrence ? selectedStop.index : route?.stops.findIndex(s => s.nodeId === node.id));
  const state = route?.stops[stopIndex];
  const previousFocus = document.activeElement;
  if (route && selected !== route.vehicleId) vehicle(route.vehicleId);
  selectedStop = state ? { vehicleId: route.vehicleId, index: stopIndex } : null;
  // Avoid replacing the list (and its focused button) on each stop selection.
  for (const el of document.querySelectorAll('[data-stop]')) {
    const active = el.dataset.route === selectedStop?.vehicleId && Number(el.dataset.index) === selectedStop?.index;
    el.classList.toggle('active', active);
    el.setAttribute('aria-pressed', String(active));
  }
  returnFocus = trigger?.isConnected ? trigger : previousFocus?.isConnected ? previousFocus : $('stops-tab');
  const title = node.type === 'base' && state ? (stopIndex === 0 ? 'Salida de base' : 'Regreso a base') : node.label;
  $('selection').innerHTML = `<button class="close" id="close-selection" aria-label="Cerrar detalle">${icon('close', 16)}</button>
    <p class="detail-eyebrow">${route ? vehicleById(route.vehicleId).name + ' · ' : ''}${node.id}</p>
    <h3>${title}</h3>
    <p>${node.type === 'charger' ? 'Estación registrada' : node.type === 'base' ? 'Centro de distribución' : 'Entrega prevista'}</p>
    ${state ? `<div class="stop-battery"><span>Batería al llegar<strong>${number(state.arrivalSoc)} <small>%</small></strong></span><span>Al salir<strong>${number(state.departureSoc)} <small>%</small></strong></span></div>${state.chargeKwh ? `<p class="charge-note">${icon('plug', 14)} Recarga de ejemplo: +${number(state.chargeKwh)} kWh</p>` : ''}`
      : node.type === 'charger' ? `<p>${node.connectors || 'Conectores sin información'}</p><p>Disponibilidad no verificada.</p>` : ''}`;
  $('selection-status').textContent = state
    ? `${vehicleById(route.vehicleId).name}. ${title}. Batería de ejemplo: llegada ${number(state.arrivalSoc)} %, salida ${number(state.departureSoc)} %.`
    : `${title}. ${node.type === 'charger' ? 'Disponibilidad no verificada.' : ''}`;
  detail.show();
  map?.selectNode(node.id);
}

$('sidebar-content').addEventListener('click', e => {
  const v = e.target.closest('[data-vehicle]');
  if (v) vehicle(v.dataset.vehicle, e.detail === 0);
  const s = e.target.closest('[data-stop]');
  if (s) stop(nodeById(s.dataset.stop), s.dataset.route, Number(s.dataset.index), s);
  if (e.target.closest('#all-routes')) {
    selected = null;
    selectedStop = null;
    detail.hide();
    render();
    map?.selectVehicle(null);
    if (e.detail === 0) $('stops-tab').focus({ preventScroll: true });
  }
});
function closeDetail() {
  if ($('selection').contains(document.activeElement)) returnFocus?.focus({ preventScroll: true });
  detail.hide();
}
$('selection').addEventListener('click', e => { if (e.target.closest('#close-selection')) closeDetail(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('selection').hidden && !$('about-dialog').open) closeDetail();
});
for (const key of ['fleet', 'stops']) {
  $(key + '-tab').onclick = () => { tab = key; render(); };
  $(key + '-tab').onkeydown = e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    tab = e.key === 'Home' ? 'fleet' : e.key === 'End' ? 'stops' : tab === 'fleet' ? 'stops' : 'fleet';
    render();
    $(tab + '-tab').focus();
  };
}
$('fit').onclick = () => map?.fit();
$('chargers').onclick = () => {
  const on = $('chargers').getAttribute('aria-pressed') !== 'true';
  $('chargers').setAttribute('aria-pressed', String(on));
  map?.toggleChargers(on);
};
$('about').onclick = () => $('about-dialog').showModal();
$('close-about').onclick = () => $('about-dialog').close();
render();
map = await createMap('map', {
  onSelect: n => stop(n),
  onVehicleSelect: id => vehicle(id),
  padding: () => innerWidth < 700 ? { top: 130, right: 35, bottom: 85, left: 35 } : { top: 160, right: 70, bottom: 105, left: 70 }
});
