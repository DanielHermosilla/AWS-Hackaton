import { SCENARIO, VEHICLES, ROUTES, NODES, number } from '../shared/data.js';
import { createMap } from '../shared/map.js';
import { icon, carDrawing } from '../shared/icons.js';

const $ = id => document.getElementById(id);
const nodeById = id => NODES.find(node => node.id === id);
const routeFor = id => ROUTES.find(route => route.vehicleId === id);
const finite = value => Number.isFinite(value);
const percent = value => finite(value) ? `${number(value, 1)} %` : '—';
const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const colorFor = vehicle => /^#[0-9a-f]{6}$/i.test(vehicle?.color || '') ? vehicle.color : '#1664ec';
let vehicleId = VEHICLES[0]?.id;
let selectedIndex = Math.max(0, routeFor(vehicleId)?.stops.findIndex(stop => finite(stop.chargeKwh) && stop.chargeKwh > 0) ?? 0);
let extraNode = null;
let mapApi;

function currentRoute() { return routeFor(vehicleId); }
function currentStop() { return extraNode ? null : currentRoute()?.stops[selectedIndex]; }
function currentNode() { return extraNode || nodeById(currentStop()?.nodeId); }
function stopTitle(node, index, route) {
  if (!node) return 'Parada sin datos';
  if (node.type !== 'base') return node.label;
  return index === route.stops.length - 1 ? 'Regreso a BASE' : index === 0 ? 'Salida de BASE' : 'BASE';
}
function nodeIcon(node) { return node?.type === 'base' ? 'base' : node?.type === 'charger' ? 'plug' : 'box'; }
function batteryDrawing(value, color) {
  const fill = finite(value) ? Math.min(100, Math.max(0, value)) / 100 * 56 : null;
  return `<svg class="battery-drawing" viewBox="0 0 76 37" aria-hidden="true"><rect x="1.5" y="2" width="66" height="33" rx="6" fill="none" stroke="#b2c8b8" stroke-width="2"/><path d="M71 12v13" stroke="#b2c8b8" stroke-width="4" stroke-linecap="round"/>${fill !== null ? `<rect x="6" y="6.5" width="${fill}" height="24" rx="3" fill="${color}"/>` : '<path d="M29 18h12" stroke="#b2c8b8" stroke-width="2"/>'}</svg>`;
}

$('scenario-name').textContent = SCENARIO.name || 'Escenario';
$('delivery-count').textContent = number(SCENARIO.deliveryCount, 0);
$('charger-label').textContent = `${number(SCENARIO.chargerCount, 0)} cargadores`;
$('source-text').textContent = SCENARIO.provenance || 'La procedencia de este ejemplo aún no está disponible.';
$('source-battery').textContent = finite(SCENARIO.fixtureBatteryKwh) ? `El balance ilustrativo usa una capacidad de ${number(SCENARIO.fixtureBatteryKwh)} kWh. Es un parámetro del ejemplo, no una capacidad útil confirmada de estos vehículos.` : 'La capacidad útil de batería aún no está confirmada.';

$('vehicle-selector').innerHTML = VEHICLES.map(vehicle => {
  const route = routeFor(vehicle.id);
  const color = colorFor(vehicle);
  return `<button class="vehicle-card" type="button" data-vehicle="${safe(vehicle.id)}" aria-pressed="${vehicle.id === vehicleId}" style="--card-color:${color}" aria-label="${safe(vehicle.name)}, ${safe(vehicle.model)}, salida ${percent(vehicle.initialSoc)}, regreso ${percent(route?.finalSoc)}">
    <span class="vehicle-title"><i class="vehicle-dot" aria-hidden="true"></i>${safe(vehicle.name)}</span><span class="vehicle-model">${safe(vehicle.model)}</span>${carDrawing(color)}
    <span class="vehicle-battery">${batteryDrawing(route?.finalSoc, color)}<span class="battery-reading"><strong>${number(route?.finalSoc, 1)}<small>${finite(route?.finalSoc) ? '%' : ''}</small></strong><span>Al volver a BASE</span></span></span>
    <span class="vehicle-start">Sale con <strong>${percent(vehicle.initialSoc)}</strong> de batería</span>
  </button>`;
}).join('');
$('route-legend').innerHTML = VEHICLES.map(vehicle => `<span><i style="background:${colorFor(vehicle)}" aria-hidden="true"></i>${safe(vehicle.name)}</span>`).join('');

function renderChart() {
  const route = currentRoute();
  const host = $('soc-chart');
  if (!route?.stops?.length) {
    host.innerHTML = '<p class="chart-empty">No se recibió un perfil de batería.</p>';
    return;
  }
  const width = Math.max(270, host.clientWidth);
  const height = host.clientHeight;
  const left = width < 430 ? 35 : 44, right = 27, top = 26, bottom = 35;
  const innerHeight = height - top - bottom;
  const x = index => left + index / Math.max(1, route.stops.length - 1) * (width - left - right);
  const y = value => top + (100 - Math.min(100, Math.max(0, value))) / 100 * innerHeight;
  const points = [];
  const lineParts = [];
  let segment = [];
  for (const [index, stop] of route.stops.entries()) {
    for (const value of [stop.arrivalSoc, stop.departureSoc]) {
      if (finite(value)) {
        const point = `${x(index).toFixed(2)},${y(value).toFixed(2)}`;
        if (segment.at(-1) !== point) segment.push(point);
        points.push({index, value});
      } else if (segment.length) {
        lineParts.push(segment);
        segment = [];
      }
    }
  }
  if (segment.length) lineParts.push(segment);
  const labelsEvery = width < 450 ? 3 : width < 630 ? 2 : 1;
  const grid = [0,20,40,60,80,100].map(value => `<line class="grid-line" x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-label" text-anchor="end" x="${left-9}" y="${y(value)+3.5}">${value}</text>`).join('');
  const selected = extraNode ? null : route.stops[selectedIndex];
  const guide = selected ? `<line class="selected-guide" x1="${x(selectedIndex)}" x2="${x(selectedIndex)}" y1="${top}" y2="${height-bottom}"/>` : '';
  const lines = lineParts.map(part => `<polyline class="soc-line" points="${part.join(' ')}"/>`).join('');
  const charges = route.stops.map((stop,index) => {
    if (!(finite(stop.chargeKwh) && stop.chargeKwh > 0 && finite(stop.arrivalSoc) && finite(stop.departureSoc))) return '';
    const labelY = Math.max(13, y(Math.max(stop.arrivalSoc, stop.departureSoc)) - 15);
    return `<line class="charge-line" data-charge-index="${index}" x1="${x(index)}" x2="${x(index)}" y1="${y(stop.arrivalSoc)}" y2="${y(stop.departureSoc)}"/><circle class="charge-point" cx="${x(index)}" cy="${y(stop.arrivalSoc)}" r="3.5"/><text class="charge-label" text-anchor="middle" x="${x(index)}" y="${labelY}">+${number(stop.chargeKwh)} kWh</text>`;
  }).join('');
  const stops = route.stops.map((stop,index) => {
    const node = nodeById(stop.nodeId);
    const isSelected = !extraNode && index === selectedIndex;
    const value = finite(stop.departureSoc) ? stop.departureSoc : stop.arrivalSoc;
    const cy = finite(value) ? y(value) : height-bottom;
    const base = node?.type === 'base';
    const xLabel = base ? 'BASE' : `${index}`;
    const title = stopTitle(node,index,route);
    const accessible = `${title}. Entrada ${percent(stop.arrivalSoc)}, salida ${percent(stop.departureSoc)}${finite(stop.chargeKwh) && stop.chargeKwh > 0 ? `, recarga ${number(stop.chargeKwh)} kWh` : ''}.`;
    const label = base || index % labelsEvery === 0 ? `<text class="axis-label x-label" text-anchor="middle" x="${x(index)}" y="${height-12}">${xLabel}</text>` : '';
    return `<g class="chart-target" role="button" tabindex="${isSelected || (extraNode && index === 0) ? 0 : -1}" data-chart-index="${index}" aria-label="${safe(accessible)}" aria-pressed="${isSelected}">
      <circle class="hit-area" cx="${x(index)}" cy="${cy}" r="18"/><circle class="focus-ring" cx="${x(index)}" cy="${cy}" r="10"/>
      ${finite(value) ? `<circle class="${isSelected ? 'selected-point' : 'soc-point'}" cx="${x(index)}" cy="${cy}" r="${isSelected ? 6 : 3.5}"/>` : `<path d="M${x(index)-3} ${cy}h6" stroke="#819288" stroke-width="2"/>`}${label}
    </g>`;
  }).join('');
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="group" aria-labelledby="soc-title soc-description"><title id="soc-title">Batería de ${safe(VEHICLES.find(v=>v.id===vehicleId)?.name)} por paradas</title><desc id="soc-description">Perfil ilustrativo, no validado. La línea baja durante los desplazamientos. Los tramos verticales verdes muestran batería incorporada en una recarga. Usa flechas izquierda y derecha para recorrer las paradas.</desc>${grid}${guide}${lines}${charges}${stops}</svg>`;
}

function renderSequence() {
  const route = currentRoute();
  const visits = route?.stops.filter(stop => nodeById(stop.nodeId)?.type === 'visit').length;
  $('sequence-count').textContent = `${number(visits,0)} entregas · regreso a BASE`;
  $('stop-sequence').innerHTML = (route?.stops || []).map((stop,index) => {
    const node = nodeById(stop.nodeId);
    const label = node?.type === 'base' ? 'BASE' : node?.id || '—';
    return `<button type="button" class="step-button${node?.type === 'base' ? ' is-base' : ''}${node?.type === 'charger' ? ' is-charge' : ''}" data-step-index="${index}" aria-label="${safe(stopTitle(node,index,route))}, parada ${index+1}" aria-pressed="${!extraNode && index === selectedIndex}">${node?.type === 'visit' ? `<span>${index}</span>` : icon(nodeIcon(node),14)}<span>${safe(label)}</span></button>`;
  }).join('');
}

function renderDetail() {
  const route = currentRoute(), stop = currentStop(), node = currentNode();
  const indexLabel = stop ? selectedIndex === 0 ? 'Punto de salida' : selectedIndex === route.stops.length-1 ? 'Punto de retorno' : `Parada ${selectedIndex}` : 'Fuera del recorrido';
  const title = extraNode ? node?.label || 'Punto del mapa' : stopTitle(node,selectedIndex,route);
  const name = `<div class="stop-name"><span class="stop-symbol" aria-hidden="true">${icon(nodeIcon(node),18)}</span><div><h3>${safe(title)}</h3><p>${safe(indexLabel)}${node?.type === 'charger' ? ` · ${safe(node.id)}` : ''}</p></div></div>`;
  const values = stop ? `<div class="detail-value"><span>Entrada</span><strong>${number(stop.arrivalSoc,1)}<small>${finite(stop.arrivalSoc)?'%':''}</small></strong></div><div class="detail-value"><span>Salida</span><strong>${number(stop.departureSoc,1)}<small>${finite(stop.departureSoc)?'%':''}</small></strong></div><div class="detail-value charge"><span>Recarga</span><strong>${finite(stop.chargeKwh) ? stop.chargeKwh > 0 ? `+${number(stop.chargeKwh)}` : '0' : '—'}<small>${finite(stop.chargeKwh)?'kWh':''}</small></strong></div>` : '<p class="off-route-detail">Esta estación no forma parte de la secuencia del ejemplo. No se recibió un balance de batería para ella.</p>';
  $('stop-detail').innerHTML = name + values;
  $('map-selection').innerHTML = `<span class="stop-symbol" aria-hidden="true">${icon(nodeIcon(node),18)}</span><div><strong>${safe(title)}</strong><p>${stop ? node?.type === 'charger' ? `Recarga ilustrativa de ${number(stop.chargeKwh)} kWh · ${percent(stop.arrivalSoc)} → ${percent(stop.departureSoc)}` : `${safe(node?.label)} · batería ${percent(stop.departureSoc)}` : 'Estación registrada · disponibilidad sin verificar'}</p></div><span class="selection-index">${stop ? `${selectedIndex+1} / ${route.stops.length}` : safe(node?.id)}</span>`;
  $('selection-status').textContent = `${title}. ${stop ? `Entrada ${percent(stop.arrivalSoc)}. Salida ${percent(stop.departureSoc)}.` : 'Sin perfil de batería.'}`;
}

function render() {
  const vehicle = VEHICLES.find(item => item.id === vehicleId);
  const route = currentRoute();
  document.documentElement.style.setProperty('--vehicle',colorFor(vehicle));
  for (const card of $('vehicle-selector').querySelectorAll('button')) card.setAttribute('aria-pressed',String(card.dataset.vehicle === vehicleId));
  $('active-model').textContent = `${vehicle?.name || 'Vehículo'} · ${vehicle?.model || 'Modelo sin datos'}`;
  $('route-summary').innerHTML = `<div><p>Consumo del recorrido</p><strong>${number(route?.energyKwh)}<small>${finite(route?.energyKwh)?'kWh':''}</small></strong><span class="metric-note">Valor ilustrativo</span></div><div><p>Recarga incorporada</p><strong>${finite(route?.chargeKwh) && route.chargeKwh > 0 ? '+' : ''}${number(route?.chargeKwh)}<small>${finite(route?.chargeKwh)?'kWh':''}</small></strong><span class="metric-note">En la batería</span></div><div><p>Regreso a BASE</p><strong>${number(route?.finalSoc,1)}<small>${finite(route?.finalSoc)?'%':''}</small></strong><span class="metric-note">Batería al retorno</span></div>`;
  renderChart();
  renderSequence();
  renderDetail();
}

function selectStop(index, move = true, source = '') {
  if (!currentRoute()?.stops[index]) return;
  selectedIndex = index;
  extraNode = null;
  renderChart();
  renderSequence();
  renderDetail();
  mapApi?.selectNode(currentStop().nodeId,move);
  if (source === 'chart') $('soc-chart').querySelector(`[data-chart-index="${index}"]`)?.focus({preventScroll:true});
  if (source === 'sequence') $('stop-sequence').querySelector(`[data-step-index="${index}"]`)?.focus({preventScroll:true});
}
function selectVehicle(id, selectDefault = true) {
  if (!routeFor(id)) return;
  vehicleId = id;
  extraNode = null;
  const chargeIndex = currentRoute().stops.findIndex(stop => finite(stop.chargeKwh) && stop.chargeKwh > 0);
  selectedIndex = selectDefault ? Math.max(0,chargeIndex) : 0;
  render();
  mapApi?.selectVehicle(id);
  mapApi?.selectNode(currentStop().nodeId,false);
}

$('vehicle-selector').addEventListener('click',event => {
  const card = event.target.closest('[data-vehicle]');
  if (card) selectVehicle(card.dataset.vehicle);
});
$('stop-sequence').addEventListener('click',event => {
  const button = event.target.closest('[data-step-index]');
  if (button) selectStop(Number(button.dataset.stepIndex),true,'sequence');
});
$('soc-chart').addEventListener('click',event => {
  const target = event.target.closest('[data-chart-index]');
  if (target) selectStop(Number(target.dataset.chartIndex),true,'chart');
});
$('soc-chart').addEventListener('keydown',event => {
  const target = event.target.closest('[data-chart-index]');
  if (!target) return;
  let index = Number(target.dataset.chartIndex);
  if (event.key === 'ArrowRight') index = Math.min(currentRoute().stops.length-1,index+1);
  else if (event.key === 'ArrowLeft') index = Math.max(0,index-1);
  else if (event.key === 'Home') index = 0;
  else if (event.key === 'End') index = currentRoute().stops.length-1;
  else if (!['Enter',' '].includes(event.key)) return;
  event.preventDefault();
  selectStop(index,true,'chart');
});
$('show-chargers').addEventListener('change',event => mapApi?.toggleChargers(event.target.checked));
$('fit-map').addEventListener('click',() => mapApi?.fit());
$('show-source').addEventListener('click',() => $('source-dialog').showModal());
$('close-source').addEventListener('click',() => $('source-dialog').close());
render();
new ResizeObserver(() => {
  const active = document.activeElement;
  const index = active?.dataset?.chartIndex;
  renderChart();
  if (index !== undefined) $('soc-chart').querySelector(`[data-chart-index="${index}"]`)?.focus({preventScroll:true});
}).observe($('soc-chart'));

mapApi = await createMap('map',{
  padding:44,
  onVehicleSelect:id => {
    if (id !== vehicleId) selectVehicle(id);
  },
  onSelect:node => {
    const matchedRoute = ROUTES.find(route => route.vehicleId === vehicleId && route.stopIds.includes(node.id)) || ROUTES.find(route => route.stopIds.includes(node.id));
    if (matchedRoute) {
      if (matchedRoute.vehicleId !== vehicleId) selectVehicle(matchedRoute.vehicleId,false);
      const currentMatches = currentStop()?.nodeId === node.id;
      const index = currentMatches ? selectedIndex : matchedRoute.stops.findIndex(stop => stop.nodeId === node.id);
      selectStop(index,false);
    } else {
      extraNode = node;
      renderChart();
      renderSequence();
      renderDetail();
    }
  }
});
mapApi.selectVehicle(vehicleId);
mapApi.selectNode(currentStop().nodeId,false);
document.body.dataset.appReady = 'true';
