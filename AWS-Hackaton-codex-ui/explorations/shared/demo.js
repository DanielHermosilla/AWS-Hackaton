/* Fictional design fixture. No optimization, street routing or energy validation. */
window.ZMD = (() => {
  const routes = [
    {id:'A', name:'Vehículo A', color:'#27756c', energy:'8,1', final:'42', charge:'4,5', stops:[
      {id:'mercado', name:'Mercado del norte', x:330,y:220,battery:52},
      {id:'biblioteca', name:'Biblioteca', x:580,y:160,battery:42},
      {id:'carga', name:'Estación de ejemplo', x:690,y:290,battery:55,charge:true},
      {id:'almacen', name:'Almacén del parque', x:565,y:395,battery:49},
      {id:'galeria', name:'Galería central', x:390,y:440,battery:46}
    ]},
    {id:'B', name:'Vehículo B', color:'#6372a3', energy:'6,2', final:'29', charge:'0', stops:[
      {id:'taller', name:'Taller de la ribera', x:725,y:505,battery:53},
      {id:'local-sur', name:'Local del sur', x:865,y:630,battery:45},
      {id:'libreria', name:'Librería del barrio', x:585,y:690,battery:39},
      {id:'cafe', name:'Café de la plaza', x:325,y:645,battery:34}
    ]}
  ];
  const base={x:250,y:440};
  let selected='A', selectedStop=null, state='complete';
  const listeners=new Set();
  const emit=()=>listeners.forEach(fn=>fn({selected, selectedStop,state}));
  function select(id,stop=null){selected=id;selectedStop=stop;emit();}
  function setState(value){state=value;selectedStop=null;emit();}
  function activeStops(r){return state==='partial'&&r.id==='B'?r.stops.slice(0,2):r.stops;}
  function totals(){return state==='empty'?{served:'—',energy:'—',seconds:'—',label:'Sin solución encontrada'}:state==='partial'?{served:'6 / 8',energy:'—',seconds:'—',label:'Cobertura incompleta'}:{served:'8 / 8',energy:'14,3',seconds:'1,6',label:'Cobertura completa de ejemplo'};}
  function mapMarkup({id='map',focus=null}={}){
    const shown=state==='empty'?[]:routes.filter(r=>!focus||r.id===focus);
    const paths=shown.map(r=>{
      const points=[base,...activeStops(r),base].map(p=>`${p.x},${p.y}`).join(' ');
      return `<polyline class="route-halo" points="${points}"/><polyline class="route-line ${selected===r.id?'active':''}" data-route="${r.id}" points="${points}" stroke="${r.color}"/>`;
    }).join('');
    const framed=focus&&shown.length?[base,...activeStops(shown[0])]:null;
    const frame=framed?`${Math.min(...framed.map(p=>p.x))-110} ${Math.min(...framed.map(p=>p.y))-75} ${Math.max(...framed.map(p=>p.x))-Math.min(...framed.map(p=>p.x))+220} ${Math.max(...framed.map(p=>p.y))-Math.min(...framed.map(p=>p.y))+160}`:'0 0 1100 820';
    const pins=shown.map(r=>activeStops(r).map((s,i)=>`<g class="map-pin ${selectedStop===s.id?'chosen':''}" role="button" tabindex="0" data-route="${r.id}" data-stop="${s.id}" aria-label="${r.name}, ${s.name}${s.charge?', recarga de ejemplo':''}" transform="translate(${s.x} ${s.y})"><circle class="pin-ring" r="24"/><circle r="17" fill="${r.color}"/><text y="5" text-anchor="middle">${s.charge?'+':i+1}</text><title>${s.name}</title></g>`).join('')).join('');
    return `<div class="schematic-map"><svg viewBox="${frame}" role="group" aria-labelledby="${id}-title" preserveAspectRatio="xMidYMid meet"><title id="${id}-title">Esquema sintético interactivo. No representa calles ni rutas calculadas.</title><defs><pattern id="${id}-blocks" width="130" height="110" patternUnits="userSpaceOnUse"><rect x="11" y="11" width="105" height="85" rx="12" fill="var(--map-block)"/></pattern></defs><rect width="1100" height="820" fill="var(--map-ground)"/><rect width="1100" height="820" fill="url(#${id}-blocks)"/><path d="M-70 650 Q200 510 305 310 T770 50 L890 -70" fill="none" stroke="var(--map-water)" stroke-width="75"/><path d="M940 0 Q860 250 950 440 T1060 850" fill="none" stroke="var(--map-park)" stroke-width="190"/><g fill="none" stroke="var(--map-road)" stroke-width="12"><path d="M0 440H1100M250 0V820M565 0V820M0 645H1100M0 220H1100M865 0V820"/><path d="M40 810L980 0" stroke-width="20"/></g><g class="district" text-anchor="middle"><text x="420" y="96">DISTRITO NORTE</text><text x="830" y="350">EL PARQUE</text><text x="460" y="777">BARRIO SUR</text><text x="125" y="345" transform="rotate(-48 125 345)">LA RIBERA</text></g>${paths}<g transform="translate(${base.x} ${base.y})"><rect x="-22" y="-22" width="44" height="44" rx="13" fill="var(--ink)"/><path d="M-9 8V-4L0-11 9-4V8Z" fill="none" stroke="var(--surface)" stroke-width="2.5"/><text class="base-label" x="0" y="48" text-anchor="middle">Centro de distribución</text></g>${pins}</svg><div class="map-disclaimer">Esquema sintético · sin geometría vial</div></div>`;
  }
  function bindMap(container){
    container.querySelectorAll('[data-route]').forEach(el=>{
      const action=()=>select(el.dataset.route,el.dataset.stop||null);
      el.addEventListener('click',action);
      el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();action();}});
    });
  }
  function batteryMarkup(r){
    if(state!=='complete')return '<div class="chart-empty">Perfil no incluido en este ejemplo.<br>No equivale a batería cero.</div>';
    const values=[60,...r.stops.map(s=>s.battery),Number(r.final)];
    const points=values.map((v,i)=>`${20+i*320/(values.length-1)},${110-v*1.35}`).join(' ');
    return `<svg class="battery-chart" viewBox="0 0 360 145" role="img" aria-label="Perfil sintético de batería del vehículo ${r.id}: inicio 60 por ciento, retorno ${r.final} por ciento. No es validación energética."><path d="M20 30H340M20 70H340M20 110H340" stroke="var(--line)" fill="none"/><polyline points="${points}" fill="none" stroke="${r.color}" stroke-width="3.5" stroke-linejoin="round"/><g fill="var(--muted)" font-size="11"><text x="20" y="135">Salida · 60 %</text><text x="263" y="135">Retorno · ${r.final} %</text></g></svg>`;
  }
  function itinerary(r,{compact=false}={}){
    if(state==='empty')return '<div class="empty"><strong>No hay un plan para mostrar</strong><p>Este ejemplo representa un límite de cómputo sin solución encontrada. No demuestra que el problema sea infactible.</p></div>';
    return `<ol class="itinerary ${compact?'compact':''}"><li class="depot-row"><span class="step-index">⌂</span><span><strong>Centro de distribución</strong><small>Salida · batería inicial 60 % de ejemplo</small></span></li>${activeStops(r).map((s,i)=>`<li><button class="stop-row ${selectedStop===s.id?'selected':''}" data-route="${r.id}" data-stop="${s.id}"><span class="step-index" style="--route-color:${r.color}">${s.charge?'+':i+1}</span><span><strong>${s.name}</strong><small>${s.charge?'Recarga · dato sintético':'Entrega · '+s.id}</small></span><span class="battery-value">${state==='complete'?(s.charge?'Salida ':'')+s.battery+' %':'—'}</span></button></li>`).join('')}<li class="depot-row"><span class="step-index">⌂</span><span><strong>Regreso al centro</strong><small>${state==='complete'?'Batería de ejemplo '+r.final+' %':'Perfil energético no disponible'}</small></span></li></ol>`;
  }
  function exportExample(){
    const record={schema_version:'design-fixture-0',source:'synthetic',warning:'Exploración de interfaz. No es salida del motor, ruta vial ni prueba de factibilidad.',scenario_id:'design-demo-eight',state,metrics:totals(),routes:state==='empty'?[]:routes.map(r=>({vehicle_id:r.id,steps:activeStops(r).map(s=>({node_id:s.id,kind:s.charge?'charge':'delivery'}))}))};
    const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='zmd-ejemplo-diseno.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return {routes,select,setState,totals,mapMarkup,bindMap,batteryMarkup,itinerary,exportExample,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},get selected(){return selected;},get selectedStop(){return selectedStop;},get state(){return state;}};
})();
