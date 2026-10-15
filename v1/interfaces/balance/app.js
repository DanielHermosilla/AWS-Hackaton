let view='map';
const vehicles=document.querySelector('#vehicles');
function render(){
 const focused=document.activeElement?.dataset.stop;
 const focusedVehicle=document.activeElement?.dataset.select;
 const t=ZMD.totals();
 document.querySelector('#summary').innerHTML=`<div class="summary-item"><div class="summary-status"><span class="status-icon">${ZMD.state==='complete'?'✓':ZMD.state==='partial'?'!':'—'}</span>${t.label}</div><small>Datos sintéticos · sin validación del motor</small></div><div class="summary-item"><div class="metric-value">${t.served}</div><div class="eyebrow">Entregas · ejemplo</div></div><div class="summary-item"><div class="metric-value">${t.energy}<span>kWh</span></div><div class="eyebrow">Consumo de ejemplo</div></div><div class="summary-item"><div class="metric-value">${t.seconds}<span>s</span></div><div class="eyebrow">Cómputo de ejemplo</div></div>`;
 vehicles.innerHTML=ZMD.routes.map(r=>`<article class="vehicle-card ${ZMD.selected===r.id?'selected':''}" style="--route-color:${r.color}"><div class="vehicle-header"><div class="vehicle-title"><span class="vehicle-letter ${r.id==='B'?'square':''}">${r.id}</span><div><h3>${r.name}</h3><p>${ZMD.state==='empty'?'Sin recorrido':ZMD.state==='partial'&&r.id==='B'?'2 entregas · cobertura parcial':'4 entregas de ejemplo'}</p></div></div><button class="vehicle-select" data-select="${r.id}" aria-pressed="${ZMD.selected===r.id}">${ZMD.selected===r.id?'Seleccionado':'Seleccionar ↗'}</button></div>${view==='map'?`<div class="vehicle-map">${ZMD.mapMarkup({id:'balance-'+r.id,focus:r.id})}</div><div class="vehicle-data"><div class="data-cell"><span>Energía de ejemplo</span><strong>${ZMD.state==='complete'?r.energy:'—'}<small>kWh</small></strong></div><div class="data-cell"><span>Batería al retorno · ejemplo</span><strong>${ZMD.state==='complete'?r.final:'—'}<small>%</small></strong></div></div><div class="energy-profile"><div class="eyebrow">Perfil sintético de batería</div>${ZMD.batteryMarkup(r)}</div>`:`<div class="vehicle-stops">${ZMD.itinerary(r)}<div class="notice">Esta secuencia es de ejemplo; no es una asignación del optimizador.</div></div>`}<div class="vehicle-bottom"><span>${ZMD.state==='empty'?'Recargas no disponibles':r.id==='A'?'1 recarga en el ejemplo':'Sin recarga en el ejemplo'}</span><span>Validador real pendiente</span></div></article>`).join('');
 ZMD.bindMap(vehicles);
 vehicles.querySelectorAll('[data-select]').forEach(b=>b.addEventListener('click',()=>ZMD.select(b.dataset.select)));
 if(focused)vehicles.querySelector(`[data-stop="${focused}"]`)?.focus({preventScroll:true});
 if(focusedVehicle)vehicles.querySelector(`[data-select="${focusedVehicle}"]`)?.focus({preventScroll:true});
}
ZMD.subscribe(render);
document.querySelector('#scenario').addEventListener('change',e=>ZMD.setState(e.target.value));
document.querySelectorAll('.detail-tab').forEach(button=>button.addEventListener('click',()=>{view=button.dataset.view;document.querySelectorAll('.detail-tab').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();}));
document.querySelectorAll('#evidence-tab,#evidence-button').forEach(b=>b.addEventListener('click',()=>document.querySelector('#evidence').showModal()));
document.querySelector('#overview-tab').addEventListener('click',()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}));
document.querySelector('#export').addEventListener('click',ZMD.exportExample);
render();
