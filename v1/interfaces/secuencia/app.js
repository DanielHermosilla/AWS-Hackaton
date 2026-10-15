/* Shared synthetic fixture only. No solver, routing or energy calculation. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const D = window.ZMD;
  if (!D) throw new Error('Falta el ejemplo compartido de ZMD.');
  const guided = Boolean($('step-0'));
  const ui = {scene:'complete', filter:null, zoom:1, step:0, version:1, soc:60, configError:null};
  const messages = {
    complete:['Ejemplo completo','Las ocho entregas están incluidas en esta muestra. El motor no se ha ejecutado.'],
    partial:['Sólo diagnóstico','Faltan dos pedidos obligatorios. Este ejemplo no representa un plan para despachar.'],
    empty:['Sin resultado','No hay un plan para mostrar. Esto no demuestra que el problema sea infactible.'],
    error:['Falta ubicar un pedido','La Librería del barrio sigue en la lista; su ubicación no se dibuja hasta corregirla.'],
    stale:['Resultado desactualizado','El escenario cambió. El resultado anterior deja de estar vigente y sus métricas se retiran.']
  };
  const text = (id,value) => { if ($(id)) $(id).textContent = value; };
  const click = (id,fn) => { if ($(id)) $(id).addEventListener('click',fn); };
  const currentRoute = () => D.routes.find(r=>r.id===D.selected)||D.routes[0];
  const baseState = () => ['partial','empty'].includes(ui.scene)?ui.scene:'complete';
  function setScene(scene) {
    ui.scene = scene;
    D.setState(baseState());
    if ($('scene')) $('scene').value = scene;
  }
  function addPendingMarkers(host) {
    if (ui.scene!=='partial'||ui.filter==='A') return;
    const svg = host.querySelector('svg');
    if (!svg) return;
    D.routes.find(r=>r.id==='B').stops.slice(2).forEach(stop=>{
      const pin = document.createElementNS('http://www.w3.org/2000/svg','g');
      pin.setAttribute('transform',`translate(${stop.x} ${stop.y})`);
      pin.setAttribute('class',`map-pin unserved-pin${D.selectedStop===stop.id?' chosen':''}`);
      pin.setAttribute('role','button');
      pin.setAttribute('tabindex','0');
      pin.setAttribute('aria-label',`${stop.name}, pedido pendiente de ejemplo`);
      pin.dataset.route='B'; pin.dataset.stop=stop.id;
      pin.innerHTML='<circle r="20" fill="var(--surface,#fff)" stroke="#99652c" stroke-width="3"/><text y="5" text-anchor="middle" fill="#805021">!</text>';
      svg.append(pin);
    });
  }
  function renderMap() {
    const host = $('map');
    if (!host) return;
    host.innerHTML = D.mapMarkup({id:guided?'secuencia-map':'atlas-map',focus:ui.filter});
    host.classList.toggle('is-stale',ui.scene==='stale');
    host.classList.toggle('is-unlocated',ui.scene==='error');
    addPendingMarkers(host);
    if (ui.scene==='error') {
      host.querySelectorAll('[data-stop="libreria"]').forEach(el=>el.remove());
      host.querySelectorAll('.route-line,.route-halo').forEach(el=>el.style.opacity='.15');
    }
    D.bindMap(host);
    applyMapView();
  }
  function applyMapView() {
    const host = $('map'), svg = host?.querySelector('svg');
    if (svg) {svg.style.transform=`scale(${ui.zoom})`;svg.style.transformOrigin='50% 50%';}
    text('zoom-label',`${Math.round(ui.zoom*100)} %`);
    if (host) {
      host.querySelectorAll('.route-line,.route-halo').forEach(el=>{
        el.style.display=$('layer-routes')&&!$('layer-routes').checked?'none':'';
      });
      host.querySelectorAll('.map-pin').forEach(el=>{
        const charging=el.dataset.stop==='carga';
        const hidden=(charging&&$('layer-chargers')&&!$('layer-chargers').checked)||
          (!charging&&$('layer-stops')&&!$('layer-stops').checked);
        el.style.display=hidden?'none':'';
      });
    }
  }
  function renderIssues() {
    const host = $('issues');
    if (!host) return;
    if (ui.scene==='partial') {
      host.innerHTML='<p>Pedidos pendientes del diagnóstico de ejemplo:</p><div class="pending-list"><button data-route="B" data-stop="libreria">Librería del barrio · pendiente</button><button data-route="B" data-stop="cafe">Café de la plaza · pendiente</button></div>';
      D.bindMap(host);
    } else if (ui.scene==='error') {
      host.innerHTML='<p><strong>Librería del barrio · sin ubicar.</strong> Corrige la ubicación antes de pedir un plan. En esta exploración, «Restablecer ejemplo» repone los datos sintéticos.</p>';
    } else if (ui.scene==='stale') {
      host.innerHTML='<p>Versión '+ui.version+' del escenario. Las métricas del resultado anterior no corresponden a estos parámetros.</p>';
    } else host.innerHTML='';
    host.hidden=!['partial','error','stale'].includes(ui.scene);
    if ($('review-issues')) $('review-issues').hidden=host.hidden;
  }
  function render() {
    const focused = document.activeElement;
    const focusStop = focused?.dataset?.stop;
    const focusContainer = focused?.closest('#map')?'map':focused?.closest('#itinerary')?'itinerary':null;
    const route = currentRoute(), message = ui.configError ? ['Revisa el SoC inicial',ui.configError] : messages[ui.scene];
    const metrics = D.totals(), validExample = ui.scene==='complete';
    document.body.dataset.scene=ui.scene;
    text('status',message[0]); text('state-caption',message[1]);
    text('served',['complete','partial'].includes(ui.scene)?metrics.served:'—');
    text('energy',validExample?metrics.energy:'—');
    text('return-soc',validExample?`${route.final} %`:'—');
    text('selected-name',route.name);
    const stop=route.stops.find(s=>s.id===D.selectedStop);
    const detail=stop?`${stop.name} · ${stop.charge?'recarga de ejemplo; compatibilidad por confirmar':'pedido '+stop.id}`:'Selecciona una parada en el mapa o en la lista.';
    text('selected-detail',detail);text('selected-description',detail);
    if ($('itinerary')) {
      $('itinerary').innerHTML=D.itinerary(route);
      if (!validExample) {
        $('itinerary').querySelectorAll('.battery-value').forEach(el=>el.textContent='—');
        const depotNotes=$('itinerary').querySelectorAll('.depot-row small');
        if(depotNotes[0]) depotNotes[0].textContent=Number.isFinite(ui.soc)?`Entrada actual: ${ui.soc} % · sin validación del motor`:'Batería inicial por completar';
        if(depotNotes[1]) depotNotes[1].textContent='Batería de retorno no disponible para el escenario actual';
      }
      D.bindMap($('itinerary'));
    }
    if ($('battery')) $('battery').innerHTML=validExample?D.batteryMarkup(route):'<p class="chart-empty">Perfil energético no vigente o no disponible en esta escena. No equivale a batería cero.</p>';
    if ($('review-list')) $('review-list').innerHTML=`<ul class="review-facts"><li>8 pedidos obligatorios · objetivo del ejemplo</li><li>2 vehículos · batería inicial ${Number.isFinite(ui.soc)?ui.soc+' %':'por completar'}</li><li>Regreso de ambos al centro · condición del desafío</li><li>Compatibilidad y disponibilidad de cargadores · por confirmar</li></ul>`;
    ['all','a','b'].forEach(key=>$('vehicle-'+key)?.setAttribute('aria-pressed',String(ui.filter===(key==='all'?null:key.toUpperCase()))));
    renderMap();renderIssues();renderSteps();
    if (focusStop&&focusContainer) {
      const replacement=[...$(focusContainer).querySelectorAll('[data-stop]')].find(el=>el.dataset.stop===focusStop);
      replacement?.focus({preventScroll:true});
    }
  }
  function renderSteps() {
    if (!guided) return;
    for (let i=0;i<3;i++) {
      if ($('panel-'+i)) $('panel-'+i).hidden=i!==ui.step;
      $('step-'+i)?.setAttribute('aria-current',i===ui.step?'step':'false');
    }
    text('step-caption',`${ui.step+1} de 3 · exploración de decisiones`);
    if ($('previous')) $('previous').disabled=ui.step===0;
    text('next',ui.step<2?'Continuar':ui.scene==='partial'?'Revisar pedidos pendientes':ui.scene==='error'?'Corregir escenario':'Volver a preparar');
  }
  function setStep(index) {
    ui.step=Math.max(0,Math.min(2,index));renderSteps();
    $('panel-'+ui.step)?.querySelector('h1,h2')?.setAttribute('tabindex','-1');
    $('panel-'+ui.step)?.querySelector('h1,h2')?.focus({preventScroll:true});
  }
  function reset() {
    ui.version++;ui.soc=60;ui.zoom=1;ui.configError=null;
    $('soc')?.removeAttribute('aria-invalid');
    if ($('soc')) $('soc').value='60';
    setScene('complete');
  }
  function editSoc() {
    const field=$('soc');
    if (!field) return;
    ui.version++;
    const raw=field.value.trim();
    if (raw===''||!field.checkValidity()||!Number.isFinite(Number(raw))) {
      ui.soc=null;
      ui.configError=raw===''?'Completa la batería inicial. Un campo vacío no significa 0 %.':'El SoC debe ser un número entre 0 y 100 %.';
      field.setAttribute('aria-invalid','true');
      setScene('stale');
      return;
    }
    ui.configError=null;field.removeAttribute('aria-invalid');
    ui.soc=Number(raw);setScene('stale');
  }
  function closeSettings() { const dialog=$('settings');if(dialog?.open)dialog.close();$('configure')?.focus(); }
  click('configure',()=>{const dialog=$('settings');if(dialog?.showModal)dialog.showModal();});
  click('close-settings',closeSettings);
  click('save-settings',event=>{event.preventDefault();editSoc();closeSettings();});
  $('soc')?.addEventListener('input',editSoc);
  $('settings')?.addEventListener('cancel',()=>$('configure')?.focus());
  $('scene')?.addEventListener('change',event=>{
    ui.soc=60;ui.configError=null;
    if($('soc')){$('soc').value='60';$('soc').removeAttribute('aria-invalid');}
    setScene(event.target.value);
  });
  ['all','a','b'].forEach(key=>click('vehicle-'+key,()=>{
    ui.filter=key==='all'?null:key.toUpperCase();D.select(ui.filter||D.selected);
  }));
  click('zoom-in',()=>{ui.zoom=Math.min(1.8,ui.zoom+.15);applyMapView();});
  click('zoom-out',()=>{ui.zoom=Math.max(.75,ui.zoom-.15);applyMapView();});
  click('fit',()=>{ui.zoom=1;applyMapView();});
  ['routes','stops','chargers'].forEach(layer=>$('layer-'+layer)?.addEventListener('change',applyMapView));
  click('reset-scene',reset);click('use-example',reset);
  click('review-issues',()=>{$('issues')?.scrollIntoView({block:'nearest',behavior:'instant'});$('issues')?.querySelector('button')?.focus();if(guided)setStep(1);});
  [0,1,2].forEach(i=>click('step-'+i,()=>setStep(i)));
  click('previous',()=>setStep(ui.step-1));
  click('next',()=>setStep(ui.step<2?ui.step+1:ui.scene==='partial'?1:0));
  D.subscribe(event=>{
    if(ui.filter&&event.selected!==ui.filter)ui.filter=event.selected;
    render();
  });
  render();
})();
