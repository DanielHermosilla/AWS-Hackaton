const map=document.querySelector('#map'), routeSections=document.querySelector('#route-sections');
const dialog=document.querySelector('#evidence');
const openRoutes=new Set(['A']);
function render(){
  const focused=document.activeElement?.dataset.stop;
  const focusedOnMap=Boolean(document.activeElement?.closest('.schematic-map'));
  map.innerHTML=ZMD.mapMarkup({id:'cuaderno-map'});
  const total=ZMD.totals();
  document.querySelector('#summary').innerHTML=`<div><strong>${total.served}</strong><small>Entregas · ejemplo</small></div><div><strong>${total.energy}<small style="display:inline;margin-left:3px">kWh</small></strong><small>Energía de ejemplo</small></div><div><strong>${total.seconds}<small style="display:inline;margin-left:3px">s</small></strong><small>Cómputo de ejemplo</small></div>`;
  routeSections.innerHTML=ZMD.routes.map(r=>`<details class="route-section" data-id="${r.id}" ${openRoutes.has(r.id)?'open':''}><summary><i class="route-dot ${r.id==='B'?'square':''}" style="--route-color:${r.color}"></i>${r.name}<small>${ZMD.state==='empty'?'Sin recorrido':ZMD.state==='partial'&&r.id==='B'?'2 entregas · parcial':'4 entregas'}</small><span class="chevron">›</span></summary>${ZMD.itinerary(r)}</details>`).join('');
  routeSections.querySelectorAll('details').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)openRoutes.add(d.dataset.id);else openRoutes.delete(d.dataset.id);}));
  ZMD.bindMap(map);ZMD.bindMap(routeSections);
  document.querySelector('#map-selection').textContent=ZMD.state==='empty'?'Sin resultado · no implica infactibilidad':`Vehículo ${ZMD.selected}${ZMD.selectedStop?' · parada seleccionada':' seleccionado'}`;
  if(focused)document.querySelector(`${focusedOnMap?".map-pin":".stop-row"}[data-stop="${focused}"]`)?.focus({preventScroll:true});
}
ZMD.subscribe(({selected})=>{openRoutes.add(selected);render();});
document.querySelector('#scenario').addEventListener('change',e=>ZMD.setState(e.target.value));
document.querySelectorAll('[data-evidence]').forEach(b=>b.addEventListener('click',()=>dialog.showModal()));
document.querySelector('#show-all').addEventListener('click',()=>{openRoutes.add('A');openRoutes.add('B');render();});
document.querySelector('#export').addEventListener('click',ZMD.exportExample);
render();
