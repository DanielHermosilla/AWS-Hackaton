import {SCENARIO,NODES,VEHICLES,ROUTES,nodeById,number} from '../shared/data.js';
import {createMap} from '../shared/map.js';
import {icon,carDrawing} from '../shared/icons.js';

const $ = id => document.getElementById(id);
const finite = value => Number.isFinite(value);
const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent = value => finite(value) ? `${number(value)} %` : '—';
const routeById = id => ROUTES.find(route => route.vehicleId === id);
const vehicleById = id => VEHICLES.find(vehicle => vehicle.id === id);
const routeColor = vehicle => /^#[a-f\d]{6}$/i.test(vehicle?.color || '') ? vehicle.color : '#1664ec';
const deliveryCount = route => new Set(route.stops.filter(stop=>nodeById(stop.nodeId)?.type==='visit').map(stop=>stop.nodeId)).size;
const chargeCount = route => route.stops.every(stop=>finite(stop.chargeKwh)) ? route.stops.filter(stop=>stop.chargeKwh>0).length : null;
let selected = null, tab = 'fleet', selectedStop = null, map;
let selectionReturn = null;

$('about').innerHTML = icon('info',19);
$('fit').innerHTML = icon('target',20);
$('chargers').innerHTML = icon('plug',18)+'<span>Cargadores</span>';
$('foot-icon').innerHTML = icon('info',17);
$('delivery-icon').innerHTML = icon('box',23);
$('energy-icon').innerHTML = icon('battery',23);
$('charge-icon').innerHTML = icon('plug',23);
$('base-legend').innerHTML = icon('base',14)+'Base';
$('fleet-count').textContent = number(VEHICLES.length,0);
$('stops-count').textContent = number(NODES.filter(node=>node.type==='visit').length,0);
const assigned = new Set(ROUTES.flatMap(route=>route.stops.filter(stop=>nodeById(stop.nodeId)?.type==='visit').map(stop=>stop.nodeId))).size;
const demand = NODES.filter(node=>node.type==='visit').length;
$('delivery-value').innerHTML = `${number(assigned,0)} <span>/ ${number(demand,0)}</span>`;
const totalEnergy = ROUTES.every(route=>finite(route.energyKwh)) ? ROUTES.reduce((sum,route)=>sum+route.energyKwh,0) : null;
$('energy-value').innerHTML = `${number(totalEnergy)}${finite(totalEnergy)?' <span>kWh</span>':''}`;
const totalCharges = ROUTES.every(route=>finite(chargeCount(route))) ? ROUTES.reduce((sum,route)=>sum+chargeCount(route),0) : null;
$('charge-value').textContent = number(totalCharges,0);

function stopName(node,index,route) {
  if (!node) return 'Parada sin datos';
  if (node.type !== 'base') return node.label;
  return index === 0 ? 'Salida de BASE' : index === route.stops.length-1 ? 'Regreso a BASE' : 'Paso por BASE';
}
function batteryMeter(value,color) {
  const width = finite(value) ? Math.min(100,Math.max(0,value))*.42 : null;
  return `<svg class="battery-meter" viewBox="0 0 56 26" aria-hidden="true"><rect x="1" y="2" width="48" height="22" rx="5" fill="none" stroke="#8794a3" stroke-width="1.8"/><path d="M53 9v8" stroke="#8794a3" stroke-width="3" stroke-linecap="round"/>${width!==null?`<rect x="4" y="5" width="${width}" height="16" rx="2.5" fill="${color}"/>`:'<path d="M20 13h10" stroke="#8794a3" stroke-width="1.8"/>'}</svg>`;
}
function focusStop(routeId,index) {
  const rows = [...$('sidebar-content').querySelectorAll('[data-stop]')];
  rows.find(row=>row.dataset.route===routeId && Number(row.dataset.index)===index)?.focus({preventScroll:true});
}
function renderSidebar(restore = true) {
  const active = document.activeElement;
  const focusKey = active?.dataset?.stop ? {route:active.dataset.route,index:Number(active.dataset.index)} : null;
  $('fleet-tab').setAttribute('aria-selected',String(tab==='fleet'));
  $('stops-tab').setAttribute('aria-selected',String(tab==='stops'));
  $('fleet-tab').tabIndex = tab==='fleet' ? 0 : -1;
  $('stops-tab').tabIndex = tab==='stops' ? 0 : -1;
  $('sidebar-content').setAttribute('aria-labelledby',tab==='fleet'?'fleet-tab':'stops-tab');
  $('sidebar-content').classList.toggle('stops',tab==='stops');
  if (tab==='fleet') {
    $('sidebar-content').innerHTML = VEHICLES.map(vehicle=>{
      const route=routeById(vehicle.id),color=routeColor(vehicle);
      return `<article class="vehicle-card ${selected===vehicle.id?'active':''}" style="--route:${color}"><div class="vehicle-heading"><div><div class="vehicle-name"><i class="vehicle-dot" aria-hidden="true"></i>${safe(vehicle.name)}</div><p class="vehicle-model">${safe(vehicle.model)}</p></div>${batteryMeter(route?.finalSoc,color)}</div>${carDrawing(color)}<div class="soc-row"><span>Salida <strong>${percent(vehicle.initialSoc)}</strong></span><span>Regreso <strong>${percent(route?.finalSoc)}</strong></span></div><div class="battery-track" aria-hidden="true">${finite(route?.finalSoc)?`<span style="width:${Math.min(100,Math.max(0,route.finalSoc))}%"></span>`:''}</div><div class="vehicle-stats"><div><strong>${route?number(deliveryCount(route),0):'—'}</strong><small>entregas</small></div><div><strong>${number(route?.energyKwh)}</strong><small>kWh</small></div><div><strong>${route?number(chargeCount(route),0):'—'}</strong><small>recarga</small></div></div><button type="button" class="route-button" data-vehicle="${safe(vehicle.id)}">Explorar recorrido ${icon('arrow',16)}</button></article>`;
    }).join('');
  } else {
    const routes = selected ? ROUTES.filter(route=>route.vehicleId===selected) : ROUTES;
    $('sidebar-content').innerHTML = (selected?'<button type="button" class="all-routes" id="all-routes">'+icon('back',16)+'Ver ambos vehículos</button>':'')+routes.map(route=>`<div class="route-head"><h2>${safe(vehicleById(route.vehicleId)?.name)}</h2><small>${number(deliveryCount(route),0)} entregas · ${number(route.distanceKm)} km de demostración</small></div>`+route.stops.map((stop,index)=>{
      const node=nodeById(stop.nodeId),active=selectedStop?.vehicleId===route.vehicleId && selectedStop.index===index;
      return `<button type="button" class="stop-row ${active?'active':''}" data-stop="${safe(stop.nodeId)}" data-route="${safe(route.vehicleId)}" data-index="${index}" aria-pressed="${active}"><span class="stop-number" aria-hidden="true">${node?.type==='base'?icon('base',16):node?.type==='charger'?icon('plug',16):safe(node?.id?.replace(/^V/,''))}</span><span class="stop-name">${safe(stopName(node,index,route))}<small>${node?.type==='charger'?`Recarga · ${finite(stop.chargeKwh)&&stop.chargeKwh>0?'+':''}${number(stop.chargeKwh)} kWh`:safe(stop.nodeId)}</small></span><strong>${percent(stop.arrivalSoc)}</strong></button>`;
    }).join('')).join('');
  }
  if (restore && focusKey && tab==='stops') focusStop(focusKey.route,focusKey.index);
}
function selectVehicle(id,focus = false) {
  if (!routeById(id)) return;
  selected=id;
  selectedStop=null;
  tab='stops';
  $('selection').hidden=true;
  renderSidebar(false);
  map?.selectVehicle(id);
  if (focus) focusStop(id,0);
}
function selectStop(node,routeId,indexHint,move = true) {
  if (!node) return;
  const previousFocus=document.activeElement;
  let route=routeId ? routeById(routeId) : ROUTES.find(route=>route.vehicleId===selected && route.stopIds.includes(node.id)) || ROUTES.find(route=>route.stopIds.includes(node.id));
  let index=null;
  if (route) {
    if (Number.isInteger(indexHint) && route.stops[indexHint]?.nodeId===node.id) index=indexHint;
    else if (selectedStop?.vehicleId===route.vehicleId && route.stops[selectedStop.index]?.nodeId===node.id) index=selectedStop.index;
    else index=route.stops.findIndex(stop=>stop.nodeId===node.id);
    if (route.vehicleId!==selected) {
      selected=route.vehicleId;
      map?.selectVehicle(selected);
    }
    selectedStop={vehicleId:route.vehicleId,index};
    tab='stops';
  } else selectedStop=null;
  renderSidebar();
  const stop=route?.stops[index];
  const title=stop ? stopName(node,index,route) : node.label;
  $('selection').hidden=false;
  $('selection').innerHTML=`<button type="button" class="close" id="close-selection" aria-label="Cerrar detalle">${icon('close',17)}</button><h3>${safe(title)}</h3><p>${safe(node.id)} · ${node.type==='charger'?'Estación registrada':node.type==='base'?'Centro de distribución':'Entrega prevista'}${route?' · '+safe(vehicleById(route.vehicleId)?.name):''}</p>${stop?`<div class="stop-battery"><span>Batería al llegar<strong>${percent(stop.arrivalSoc)}</strong></span><span>Al salir<strong>${percent(stop.departureSoc)}</strong></span></div>${finite(stop.chargeKwh)&&stop.chargeKwh>0?`<p class="charge-detail">${icon('plug',15)}Recarga de ejemplo: +${number(stop.chargeKwh)} kWh</p>`:''}`:node.type==='charger'?`<p>${safe(node.connectors||'Conectores sin información')}</p><p>Disponibilidad no verificada.</p>`:'<p>Batería sin información para esta parada.</p>'}`;
  $('selection-status').textContent=`${title}${route?' de '+vehicleById(route.vehicleId)?.name:''}. ${stop?'Entrada '+percent(stop.arrivalSoc)+'. Salida '+percent(stop.departureSoc)+'.':'Sin balance de batería para esta estación.'}`;
  selectionReturn = previousFocus?.classList?.contains('zmd-pin') ? {element:previousFocus} : stop ? {route:route.vehicleId,index} : {element:$('stops-tab')};
  map?.selectNode(node.id,move);
}
function closeSelection() {
  $('selection').hidden=true;
  if (selectionReturn?.element?.isConnected && !selectionReturn.element.hidden) selectionReturn.element.focus({preventScroll:true});
  else if (selectionReturn?.route) focusStop(selectionReturn.route,selectionReturn.index);
  else $('stops-tab').focus({preventScroll:true});
}
function setTab(next) {
  tab=next;
  renderSidebar(false);
}
$('sidebar-content').addEventListener('click',event=>{
  const vehicle=event.target.closest('[data-vehicle]');
  if (vehicle) selectVehicle(vehicle.dataset.vehicle,true);
  const stop=event.target.closest('[data-stop]');
  if (stop) selectStop(nodeById(stop.dataset.stop),stop.dataset.route,Number(stop.dataset.index));
  if (event.target.closest('#all-routes')) {
    selected=null;
    selectedStop=null;
    $('selection').hidden=true;
    renderSidebar(false);
    map?.selectVehicle(null);
    $('stops-tab').focus({preventScroll:true});
  }
});
$('selection').addEventListener('click',event=>{if(event.target.closest('#close-selection'))closeSelection();});
$('fleet-tab').onclick=()=>setTab('fleet');
$('stops-tab').onclick=()=>setTab('stops');
for (const [id,next] of [['fleet-tab','stops'],['stops-tab','fleet']]) $(id).addEventListener('keydown',event=>{
  if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const target=event.key==='Home'?'fleet':event.key==='End'?'stops':next;
  setTab(target);
  $(target==='fleet'?'fleet-tab':'stops-tab').focus();
});
$('fit').onclick=()=>map?.fit();
$('chargers').onclick=()=>{
  const on=$('chargers').getAttribute('aria-pressed')!=='true';
  $('chargers').setAttribute('aria-pressed',String(on));
  map?.toggleChargers(on);
};
$('about').onclick=()=>$('about-dialog').showModal();
$('close-about').onclick=()=>$('about-dialog').close();
document.addEventListener('keydown',event=>{
  if(event.key==='Escape' && !$('about-dialog').open && !$('selection').hidden) closeSelection();
});
renderSidebar(false);
map=await createMap('map',{
  onSelect:node=>selectStop(node,undefined,undefined,false),
  onVehicleSelect:id=>{if(id!==selected)selectVehicle(id);},
  padding:()=>innerWidth<700?{top:196,right:32,bottom:132,left:32}:{top:165,right:68,bottom:106,left:68}
});
document.body.dataset.appReady='true';
