import {NODES, VEHICLES, ROUTES, nodeById, number} from '../shared/data.js';
import {createMap} from '../shared/map.js';
import {icon, carDrawing} from '../shared/icons.js';

const $ = id => document.getElementById(id);
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let selected = null, tab = 'fleet', map;
let selectedStop = null;
let selectionFocusKey = null;
const expandedProfiles = new Set();
const panelTransitions = new WeakMap();

$('about').innerHTML = icon('info',18);
$('fit').innerHTML = icon('target');
$('chargers').innerHTML = icon('plug',17) + 'Cargadores';
$('foot-icon').innerHTML = icon('info',17);
$('delivery-icon').innerHTML = icon('box',24);
$('energy-icon').innerHTML = icon('battery',24);
$('charge-icon').innerHTML = icon('plug',24);
$('base-legend').innerHTML = icon('base',13) + 'Base';

function stopName(route, index) {
  const node = nodeById(route.stops[index].nodeId);
  if (node.type !== 'base') return node.label;
  return index === 0 ? 'Salida de base' : index === route.stops.length - 1 ? 'Regreso a base' : 'Paso por base';
}

function focusKey() {
  const active = document.activeElement;
  return $('sidebar-content').contains(active) ? active.dataset.focusKey : null;
}

function restoreFocus(key) {
  if (!key) return false;
  const control = [...$('sidebar-content').querySelectorAll('[data-focus-key]')].find(el => el.dataset.focusKey === key);
  if (!control || control.closest('[hidden],[inert]')) return false;
  control?.focus({preventScroll:true});
  return document.activeElement === control;
}

// Horizontal position is stop order, not time or distance. The vertical scale is 0–100 %.
// A charge is drawn at one stop, from its supplied arrival to departure value.
function profileChart(route, detailed = false) {
  const width = 276, height = detailed ? 112 : 48;
  const left = detailed ? 22 : 5, right = detailed ? 266 : 271;
  const top = detailed ? 9 : 5, bottom = detailed ? 91 : 43;
  const x = i => left + i / Math.max(1, route.stops.length - 1) * (right - left);
  const y = soc => top + (100 - soc) / 100 * (bottom - top);
  const color = VEHICLES.find(v => v.id === route.vehicleId).color;
  let path = '', charging = '', connected = false;
  const points = [];
  route.stops.forEach((stop, index) => {
    if (!Number.isFinite(stop.arrivalSoc) || !Number.isFinite(stop.departureSoc)) {
      connected = false;
      return;
    }
    const px = x(index), arrival = y(stop.arrivalSoc), departure = y(stop.departureSoc);
    path += `${connected ? 'L' : 'M'}${px.toFixed(2)} ${arrival.toFixed(2)}L${px.toFixed(2)} ${departure.toFixed(2)}`;
    connected = true;
    if (stop.chargeKwh > 0) charging += `M${px.toFixed(2)} ${arrival.toFixed(2)}L${px.toFixed(2)} ${departure.toFixed(2)}`;
    points.push({stop, index, x:px, y:departure});
  });
  const grid = detailed ? `<path d="M22 ${top}H266M22 ${(top + bottom)/2}H266M22 ${bottom}H266" class="profile-grid"/><text x="0" y="${top+3}">100</text><text x="6" y="${(top+bottom)/2+3}">50</text><text x="12" y="${bottom+3}">0</text>` : '';
  const markers = detailed ? '' : points.filter(p => p.index === 0 || p.index === route.stops.length-1 || p.stop.chargeKwh > 0)
    .map(p => `<circle cx="${p.x}" cy="${p.y}" r="${p.stop.chargeKwh > 0 ? 2.5 : 2}" fill="${p.stop.chargeKwh > 0 ? '#21835b' : color}"/>`).join('');
  const svg = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><g>${grid}<path d="${path}" class="profile-line" stroke="${color}"/><path d="${charging}" class="charge-line"/>${markers}</g></svg>`;
  if (!detailed) return svg;
  const controls = points.map(({stop, index, x:px, y:py}) => {
    const isCharge = stop.chargeKwh > 0;
    const label = `${stopName(route,index)}, ${stop.nodeId}, llegada ${number(stop.arrivalSoc)} %, salida ${number(stop.departureSoc)} %${isCharge ? `, recarga de ejemplo ${number(stop.chargeKwh)} kWh` : ''}`;
    return `<button type="button" class="profile-point ${isCharge ? 'is-charge' : ''}" data-stop="${esc(stop.nodeId)}" data-route="${esc(route.vehicleId)}" data-index="${index}" data-focus-key="profile:${esc(route.vehicleId)}:${index}" aria-label="${esc(label)}" title="${esc(label)}" aria-pressed="false" style="left:${px / width * 100}%;top:${py / height * 100}%"><span>${isCharge ? icon('plug',9) : ''}</span></button>`;
  }).join('');
  return `<div class="profile-plot" role="group" aria-label="Paradas del perfil de batería de ejemplo">${svg}${controls}</div>`;
}

function miniProfile(route) {
  const name = VEHICLES.find(v => v.id === route.vehicleId).name;
  return `<figure class="mini-profile" aria-label="Perfil de batería de ejemplo de ${esc(name)} por parada">
    <figcaption><span>Durante el recorrido</span><span class="charge-caption">${icon('plug',11)} +${number(route.chargeKwh)} kWh</span></figcaption>
    ${profileChart(route)}
    <div class="mini-axis"><span>Salida</span><span>Regreso a base</span></div>
  </figure>`;
}

function expandedProfile(route) {
  const open = expandedProfiles.has(route.vehicleId);
  const id = esc(route.vehicleId);
  return `<section class="energy-profile" style="--route:${VEHICLES.find(v => v.id === route.vehicleId).color}">
    <button class="profile-toggle" id="profile-toggle-${id}" data-profile-toggle="${id}" data-focus-key="toggle:${id}" aria-expanded="${open}" aria-controls="profile-content-${id}"><span>${icon('battery',16)}Batería del recorrido</span><span class="profile-chevron">${icon('arrow',14)}</span></button>
    <div class="profile-content" id="profile-content-${id}" data-profile-body="${id}" ${open ? '' : 'hidden inert'} style="height:${open ? 'auto' : '0px'};opacity:${open ? 1 : 0}">
      <div class="profile-inner">
        <div class="profile-label"><span>Carga de batería <small>%</small></span><span>Por parada</span></div>
        ${profileChart(route,true)}
        <div class="profile-axis"><span>Salida</span><span>Regreso a base</span></div>
        <div class="profile-legend"><span><i class="route-line"></i>Recorrido</span><span><i class="charge-line-key"></i>Recarga</span></div>
        <p class="profile-context" data-profile-context="${id}">Selecciona un punto para ver su parada.</p>
        <p class="profile-note">Valores ilustrativos por parada.<br>No validan la energía entre paradas.</p>
      </div>
    </div>
  </section>`;
}

function render(key = focusKey()) {
  $('fleet-tab').setAttribute('aria-selected',String(tab === 'fleet'));
  $('stops-tab').setAttribute('aria-selected',String(tab === 'stops'));
  $('fleet-tab').tabIndex = tab === 'fleet' ? 0 : -1;
  $('stops-tab').tabIndex = tab === 'stops' ? 0 : -1;
  $('sidebar-content').setAttribute('aria-labelledby',tab === 'fleet' ? 'fleet-tab' : 'stops-tab');
  $('sidebar-content').classList.toggle('stops',tab === 'stops');
  if (tab === 'fleet') {
    $('sidebar-content').innerHTML = VEHICLES.map(vehicle => {
      const route = ROUTES.find(r => r.vehicleId === vehicle.id);
      return `<article class="vehicle-card ${selected === vehicle.id ? 'active' : ''}" style="--route:${vehicle.color}">
        <div class="vehicle-heading"><div><div class="vehicle-name"><i class="vehicle-dot"></i>${esc(vehicle.name)}</div><p class="vehicle-model">${esc(vehicle.model)}</p></div>${icon('battery',19)}</div>
        ${carDrawing(vehicle.color)}
        <div class="soc-row"><span>Salida <strong>${number(vehicle.initialSoc)} %</strong></span><span>Regreso <strong>${number(route.finalSoc)} %</strong></span></div>
        ${miniProfile(route)}
        <div class="vehicle-stats"><div><strong>10</strong><small>entregas</small></div><div><strong>${number(route.energyKwh)}</strong><small>kWh</small></div><div><strong>1</strong><small>recarga</small></div></div>
        <button class="route-button" data-vehicle="${esc(vehicle.id)}" data-focus-key="vehicle:${esc(vehicle.id)}">Explorar recorrido ${icon('arrow',16)}</button>
      </article>`;
    }).join('');
  } else {
    const routes = selected ? ROUTES.filter(r => r.vehicleId === selected) : ROUTES;
    $('sidebar-content').innerHTML = (selected ? '<button class="all-routes" id="all-routes">← Ver ambos vehículos</button>' : '') + routes.map(route => {
      const heading = `<div class="route-head">${esc(VEHICLES.find(v => v.id === route.vehicleId).name)}<small>10 entregas · ${number(route.distanceKm)} km de demostración</small></div>`;
      const profile = selected === route.vehicleId ? expandedProfile(route) : '';
      const stops = route.stops.map((stop,index) => {
        const node = nodeById(stop.nodeId);
        return `<button class="stop-row" data-stop="${esc(node.id)}" data-route="${esc(route.vehicleId)}" data-index="${index}" data-focus-key="stop:${esc(route.vehicleId)}:${index}" aria-pressed="false">
          <span class="stop-number">${node.type === 'base' ? icon('base',16) : node.type === 'charger' ? icon('plug',16) : esc(node.id.substring(1))}</span>
          <span class="stop-name">${esc(stopName(route,index))}<small>${node.type === 'charger' ? `Recarga · +${number(stop.chargeKwh)} kWh` : esc(node.id)}</small></span>
          <strong>${number(stop.arrivalSoc)} %</strong>
        </button>`;
      }).join('');
      return heading + profile + `<div class="route-stops">${stops}</div>`;
    }).join('');
  }
  syncSelection();
  restoreFocus(key);
}

function syncSelection() {
  for (const control of $('sidebar-content').querySelectorAll('[data-stop]')) {
    const active = selectedStop?.routeId === control.dataset.route && selectedStop?.index === Number(control.dataset.index);
    control.classList.toggle('active',active);
    control.setAttribute('aria-pressed',String(active));
  }
  for (const context of $('sidebar-content').querySelectorAll('[data-profile-context]')) {
    const route = ROUTES.find(r => r.vehicleId === context.dataset.profileContext);
    const stop = selectedStop?.routeId === route.vehicleId ? route.stops[selectedStop.index] : null;
    context.textContent = stop
      ? `${stopName(route,selectedStop.index)} · ${number(stop.arrivalSoc)} %${stop.chargeKwh > 0 ? ` → ${number(stop.departureSoc)} % · +${number(stop.chargeKwh)} kWh` : ' al llegar'}`
      : 'Selecciona un punto para ver su parada.';
  }
}

function vehicle(id) {
  const keyboardFocus = !!focusKey();
  selected = id;
  selectedStop = null;
  tab = 'stops';
  $('selection').hidden = true;
  render(keyboardFocus ? `toggle:${id}` : null);
  map?.selectVehicle(id);
}

function stop(node, routeId, index) {
  if (!node) return;
  const key = focusKey();
  selectionFocusKey = key;
  let route = ROUTES.find(r => r.vehicleId === (routeId || node.vehicleId || selected));
  if (node.type !== 'base' && !route?.stops.some(s => s.nodeId === node.id)) route = ROUTES.find(r => r.stops.some(s => s.nodeId === node.id));
  let stopIndex = Number.isInteger(index) ? index : -1;
  if (route && stopIndex < 0) {
    // BASE is shared by departure and return. Keep the selected occurrence on a map click.
    const current = selectedStop?.routeId === route.vehicleId ? route.stops[selectedStop.index] : null;
    stopIndex = current?.nodeId === node.id ? selectedStop.index : route.stops.findIndex(s => s.nodeId === node.id);
  }
  const supplied = route?.stops[stopIndex];
  const sameNode = supplied?.nodeId === node.id;
  const changedRoute = sameNode && route.vehicleId !== selected;
  if (changedRoute) {
    selected = route.vehicleId;
    tab = 'stops';
  }
  selectedStop = sameNode ? {routeId:route.vehicleId,index:stopIndex} : null;
  if (changedRoute) {
    render(key);
    map?.selectVehicle(selected);
  } else {
    syncSelection();
  }
  const title = sameNode ? stopName(route,stopIndex) : node.label;
  $('selection').hidden = false;
  $('selection').dataset.route = sameNode ? route.vehicleId : '';
  $('selection').dataset.index = sameNode ? String(stopIndex) : '';
  $('selection').innerHTML = `<button class="close" id="close-selection" aria-label="Cerrar detalle">${icon('close',16)}</button><h3>${esc(title)}</h3><p>${esc(node.id)} · ${node.type === 'charger' ? 'Estación registrada' : node.type === 'base' ? 'Centro de distribución' : 'Entrega prevista'}</p>
    ${sameNode ? `<div class="stop-battery"><span>Batería al llegar<strong>${number(supplied.arrivalSoc)} %</strong></span><span>Al salir<strong>${number(supplied.departureSoc)} %</strong></span></div>${supplied.chargeKwh > 0 ? `<p>Recarga de ejemplo: +${number(supplied.chargeKwh)} kWh</p>` : ''}` : node.type === 'charger' ? `<p>${esc(node.connectors || 'Conectores sin información')}</p><p>Disponibilidad no verificada.</p>` : ''}`;
  $('selection-status').textContent = sameNode
    ? `${VEHICLES.find(v => v.id === route.vehicleId).name}. ${title}. Llegada ${number(supplied.arrivalSoc)} %, salida ${number(supplied.departureSoc)} %. Valores de ejemplo.`
    : `${node.label}. ${node.type === 'charger' ? 'Disponibilidad no verificada.' : ''}`;
  map?.selectNode(node.id);
}

function toggleProfile(id, instant = false) {
  const panel = $(`profile-content-${id}`);
  const toggle = $(`profile-toggle-${id}`);
  const open = !expandedProfiles.has(id);
  if (open) expandedProfiles.add(id); else expandedProfiles.delete(id);
  toggle.classList.toggle('instant',instant || reduced.matches);
  toggle.setAttribute('aria-expanded',String(open));
  panelTransitions.get(panel)?.();
  const height = panel.hidden ? 0 : panel.getBoundingClientRect().height;
  const opacity = panel.hidden ? 0 : Number(getComputedStyle(panel).opacity);
  panel.hidden = false;
  panel.inert = !open;
  panel.classList.add('instant');
  panel.style.height = `${height}px`;
  panel.style.opacity = String(opacity);
  const finish = () => {
    if (expandedProfiles.has(id) !== open) return;
    panel.classList.add('instant');
    panel.style.height = open ? 'auto' : '0px';
    panel.style.opacity = open ? '1' : '0';
    panel.hidden = !open;
    panel.inert = !open;
    void panel.offsetHeight;
    panel.classList.remove('instant');
  };
  if (instant || reduced.matches) {
    finish();
    return;
  }
  void panel.offsetHeight;
  panel.classList.remove('instant');
  panel.style.height = open ? `${panel.querySelector('.profile-inner').scrollHeight}px` : '0px';
  panel.style.opacity = open ? '1' : '0';
  // Finish when the browser finishes painting the transitions, not on a wall-clock
  // timer that could hide the panel before a busy map has produced its next frame.
  let cancelled = false;
  const cleanup = () => { cancelled = true; };
  panelTransitions.set(panel,cleanup);
  const transitions = panel.getAnimations().filter(animation => ['height','opacity'].includes(animation.transitionProperty));
  Promise.allSettled(transitions.map(animation => animation.finished)).then(() => {
    if (!cancelled && panelTransitions.get(panel) === cleanup) finish();
  });
}

$('sidebar-content').addEventListener('click',event => {
  const toggle = event.target.closest('[data-profile-toggle]');
  if (toggle) return toggleProfile(toggle.dataset.profileToggle,event.detail === 0);
  const chosen = event.target.closest('[data-vehicle]');
  if (chosen) return vehicle(chosen.dataset.vehicle);
  const point = event.target.closest('[data-stop]');
  if (point) return stop(nodeById(point.dataset.stop),point.dataset.route,Number(point.dataset.index));
  if (event.target.closest('#all-routes')) {
    selected = null;
    selectedStop = null;
    $('selection').hidden = true;
    render(null);
    map?.selectVehicle(null);
    $('stops-tab').focus({preventScroll:true});
  }
});
function closeSelection() {
  $('selection').hidden = true;
  if (restoreFocus(selectionFocusKey)) return;
  if (selectedStop && restoreFocus(`${tab === 'fleet' ? 'vehicle' : 'toggle'}:${selectedStop.routeId}`)) return;
  (document.querySelector('.zmd-pin.is-selected:not([hidden])') || $('chargers')).focus({preventScroll:true});
}
$('selection').addEventListener('click',event => {
  if (event.target.closest('#close-selection')) closeSelection();
});
document.addEventListener('keydown',event => {
  if (event.key === 'Escape' && !$('selection').hidden && !$('about-dialog').open) {
    event.preventDefault();
    closeSelection();
  }
});
$('fleet-tab').onclick = () => { tab = 'fleet'; render(null); };
$('stops-tab').onclick = () => { tab = 'stops'; render(null); };
document.querySelector('.sidebar-tabs').addEventListener('keydown',event => {
  const controls = [$('fleet-tab'),$('stops-tab')];
  const current = controls.indexOf(event.target);
  if (current < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? controls.length-1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + controls.length) % controls.length;
  tab = next === 0 ? 'fleet' : 'stops';
  render(null);
  controls[next].focus({preventScroll:true});
});
$('fit').onclick = () => map?.fit();
$('chargers').onclick = () => {
  const on = $('chargers').getAttribute('aria-pressed') !== 'true';
  $('chargers').setAttribute('aria-pressed',String(on));
  map?.toggleChargers(on);
};
$('about').onclick = () => $('about-dialog').showModal();
$('close-about').onclick = () => $('about-dialog').close();

render(null);
map = await createMap('map',{
  onSelect:node => stop(node),
  onVehicleSelect:vehicle,
  padding:() => innerWidth < 700 ? {top:130,right:35,bottom:85,left:35} : {top:160,right:70,bottom:105,left:70}
});
