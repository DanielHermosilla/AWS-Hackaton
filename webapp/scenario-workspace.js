// Preview the same editable input used by /prepare. No routes or energy are
// computed here; simulated locations come from the server's road sampler.
import {escapeHtml as esc} from './shared/html.js';

const labels = {base: 'Depósito', visit: 'Cliente', charger: 'Cargador', junction: 'Intersección'};
const coordinates = node => Number.isFinite(node.latitude) && Number.isFinite(node.longitude)
  && Math.abs(node.latitude) <= 85.051129 && Math.abs(node.longitude) <= 180
  ? [node.longitude, node.latitude] : null;

export function initScenarioWorkspace(main, runPanel, {hasResult = false} = {}) {
  const host = document.createElement('section');
  host.className = 'scenario-workspace';
  host.setAttribute('aria-labelledby', 'scenario-heading');
  host.innerHTML = `
    <header class="scenario-header">
      <div><p class="eyebrow">Hackatón CASE · Planificador eléctrico</p>
        <h1 id="scenario-heading">Tu escenario, en el mapa.</h1>
        <p id="scenario-caption">Cargando las ubicaciones del dataset…</p></div>
      <span class="scenario-preview-badge">Ubicaciones · antes de calcular</span>
    </header>
    <div class="scenario-layout">
      <div class="scenario-controls">
        <section class="scenario-card" aria-labelledby="scenario-source-heading">
          <h2 id="scenario-source-heading"><span>1</span> Elige el caso</h2>
          <label for="scenario-dataset">Dataset de la hackatón</label>
          <select id="scenario-dataset"><option value="competition">Competencia · competition</option><option value="evaluation">Evaluación · evaluation</option></select>
          <button id="scenario-original" type="button">Cargar caso original + histórico</button>
          <p>Ubicaciones originales en Ann Arbor, Michigan. El consumo se apoya en el histórico eléctrico eVED.</p>
        </section>
        <section class="scenario-card" aria-labelledby="scenario-simulation-heading">
          <h2 id="scenario-simulation-heading"><span>2</span> Simula más ubicaciones</h2>
          <form id="scenario-variant-form">
            <div class="scenario-quantities">
              <label>Clientes<input id="scenario-customers" type="number" min="1" max="199" step="1" required></label>
              <label>Cargadores<input id="scenario-chargers" type="number" min="0" max="198" step="1" required></label>
            </div>
            <label class="scenario-seed">Semilla de ubicaciones<input id="scenario-seed" type="number" min="0" max="2000000000" step="1" value="0" required></label>
            <button id="scenario-preview" type="submit">Actualizar mapa</button>
          </form>
          <p>Mismo depósito, zona y calles. Hasta 200 puntos en total. La semilla permite repetir la simulación.</p>
          <p id="scenario-unapplied" class="scenario-notice" hidden>Aplica los cambios con «Actualizar mapa» antes de calcular.</p>
        </section>
        <section class="scenario-card scenario-launch" aria-labelledby="scenario-run-heading">
          <h2 id="scenario-run-heading"><span>3</span> Revisa la flota</h2>
          <p id="scenario-fleet">2 Nissan Leaf · batería inicial 60 %</p>
          <p id="scenario-assumptions"></p>
          <p id="scenario-history"></p>
          <button id="scenario-settings" type="button">Ajustar flota y cálculo</button>
          <p id="scenario-budget"></p>
        </section>
        <p id="scenario-message" class="scenario-message" role="status" aria-live="polite"></p>
      </div>
      <section class="scenario-map-panel" aria-label="Mapa y ubicaciones del escenario">
        <div class="scenario-map-heading"><div><strong id="scenario-map-title">Área del dataset</strong><p id="scenario-counts">Esperando ubicaciones</p></div>
          <div class="scenario-map-actions"><button id="scenario-fit" type="button" disabled>Centrar mapa</button><button id="scenario-calculate" type="button" class="primary" disabled>Calcular rutas</button></div></div>
        <div id="scenario-map" aria-label="Mapa del depósito, clientes y cargadores"></div>
        <p id="scenario-map-status" role="status">Las ubicaciones aparecerán aquí, sin rutas ilustrativas.</p>
        <div class="scenario-legend"><span><i class="scenario-key base"></i>Depósito</span><span><i class="scenario-key visit"></i>Clientes</span><span><i class="scenario-key charger"></i>Cargadores</span><span><i class="scenario-key simulated"></i>Simulados</span></div>
        <div id="scenario-selected" class="scenario-selected" hidden><p></p><button id="scenario-edit" type="button">Editar este punto</button></div>
        <details class="scenario-location-list"><summary>Ver ubicaciones en lista</summary><div id="scenario-locations"></div></details>
        <p id="scenario-simulation-note" class="scenario-map-note" hidden>Los puntos añadidos son simulados. Cargadores nuevos: J1772/CHAdeMO, dos puertos y máximo nominal de 50 kW; no representa potencia efectiva.</p>
        <p class="scenario-map-note">Los recorridos, las entregas y el consumo aparecerán al terminar el cálculo y su validación.</p>
      </section>
    </div>`;
  main.prepend(host);
  if (!hasResult) {
    const metrics = main.querySelector('.vision-content');
    if (metrics) metrics.hidden = true;
  }
  const $ = id => host.querySelector(`#${id}`);
  let state, lastNodes, selectedId, map, maplibre, mapLoading = false, mapFailed = false;
  let nodes = [], markers = [], pendingChanges = false, disposed = false;
  let observer, mapTimer;
  const mapped = () => nodes.filter(coordinates);
  const title = node => `${labels[node.node_type] || 'Punto'} · ${node.address || node.node_id}`;
  function showMessage(text, error = false) {
    $('scenario-message').textContent = text;
    $('scenario-message').classList.toggle('is-error', error);
  }
  function fit() {
    const points = mapped().map(coordinates);
    if (!map || !points.length) return;
    const bounds = points.reduce((box, point) => box.extend(point), new maplibre.LngLatBounds(points[0], points[0]));
    map.fitBounds(bounds, {padding: 45, maxZoom: 15, duration: 0});
  }
  function select(nodeId) {
    selectedId = nodeId;
    const node = nodes.find(node => node.node_id === nodeId);
    $('scenario-selected').hidden = !node;
    if (!node) return;
    $('scenario-selected').querySelector('p').textContent = `${title(node)}${coordinates(node) ? ` · ${node.latitude.toFixed(5)}, ${node.longitude.toFixed(5)}` : ' · Sin coordenadas'}`;
    $('scenario-edit').textContent = state.input?.instance ? 'Revisar este punto' : 'Editar este punto';
    $('scenario-edit').disabled = state.busy;
    for (const {id, element} of markers) element.setAttribute('aria-pressed', String(id === nodeId));
  }
  function drawMarkers() {
    for (const {marker} of markers) marker.remove();
    markers = [];
    let number = 0;
    for (const node of mapped()) {
      const element = document.createElement('button');
      element.type = 'button';
      const simulated = state.scenario?.kind === 'hackathon_simulation' && node.node_id.startsWith('SIM-');
      element.className = `scenario-pin ${node.node_type}${simulated ? ' simulated' : ''}`;
      element.textContent = node.node_type === 'base' ? 'D' : node.node_type === 'charger' ? 'ϟ' : String(++number);
      element.setAttribute('aria-label', title(node));
      element.setAttribute('aria-pressed', 'false');
      element.addEventListener('click', () => select(node.node_id));
      const marker = new maplibre.Marker({element}).setLngLat(coordinates(node)).addTo(map);
      markers.push({id: node.node_id, marker, element});
    }
    $('scenario-map').dataset.nodeCount = String(markers.length);
    $('scenario-fit').disabled = !markers.length;
    fit();
  }
  async function updateMap() {
    if (!mapped().length) {
      for (const {marker} of markers) marker.remove();
      markers = [];
      $('scenario-map').dataset.nodeCount = '0';
      $('scenario-fit').disabled = true;
      $('scenario-map-status').textContent = 'Esta instancia no incluye coordenadas representables. Sus puntos siguen en la lista.';
      return;
    }
    if (map) { drawMarkers(); return; }
    if (mapLoading || mapFailed) return;
    mapLoading = true;
    try {
      maplibre = await import('./vendor/maplibre/maplibre-gl.mjs');
      if (disposed || !mapped().length) return;
      const href = new URL('./vendor/maplibre/maplibre-gl.css', import.meta.url).href;
      if (![...document.styleSheets].some(sheet => sheet.href === href)) {
        const link = document.createElement('link');
        link.rel = 'stylesheet'; link.href = href; document.head.append(link);
      }
      map = new maplibre.Map({
        container: $('scenario-map'), center: coordinates(mapped()[0]), zoom: 11,
        style: new URL('./vendor/maplibre/positron.json', import.meta.url).href,
        attributionControl: true, pitchWithRotate: false, dragRotate: false,
        touchPitch: false, renderWorldCopies: false,
      });
      map.addControl(new maplibre.NavigationControl({showCompass: false}), 'bottom-right');
      map.on('load', () => {
        clearTimeout(mapTimer);
        $('scenario-map').dataset.mapReady = 'true';
        if (!mapFailed) $('scenario-map-status').textContent = 'Selecciona un punto para revisar o editar su ubicación.';
      });
      map.on('error', () => {
        mapFailed = true;
        $('scenario-map-status').textContent = 'La cartografía no está disponible. Los puntos y la lista conservan sus coordenadas.';
      });
      mapTimer = setTimeout(() => {
        if (!mapFailed) $('scenario-map-status').textContent = 'La cartografía tarda en cargar. Puedes usar la lista de ubicaciones.';
      }, 12000);
      observer = new ResizeObserver(() => { map?.resize(); fit(); });
      observer.observe($('scenario-map'));
      $('scenario-fit').disabled = false;
      drawMarkers();
    } catch {
      mapFailed = true;
      $('scenario-map-status').textContent = 'Mapa no disponible en este navegador. Revisa y edita los puntos desde la lista.';
    } finally { mapLoading = false; }
  }
  function updateActions() {
    const locked = !state || state.busy;
    for (const id of ['scenario-original', 'scenario-preview', 'scenario-dataset', 'scenario-customers', 'scenario-chargers', 'scenario-seed']) $(id).disabled = locked;
    $('scenario-calculate').disabled = locked || !state?.input || pendingChanges;
    $('scenario-calculate').textContent = locked ? 'Preparando…' : 'Calcular rutas';
    $('scenario-unapplied').hidden = !pendingChanges;
    if (selectedId) $('scenario-edit').disabled = locked;
  }
  function changed() { pendingChanges = true; updateActions(); }
  for (const id of ['scenario-customers', 'scenario-chargers', 'scenario-seed']) $(id).addEventListener('input', changed);
  $('scenario-dataset').addEventListener('change', () => {
    changed();
    $('scenario-unapplied').textContent = 'Carga el caso original o actualiza el mapa para aplicar el dataset elegido.';
  });
  $('scenario-original').addEventListener('click', () => runPanel.loadScenario({dataset: $('scenario-dataset').value}));
  $('scenario-variant-form').addEventListener('submit', event => {
    event.preventDefault();
    const simulation = {customers: Number($('scenario-customers').value), chargers: Number($('scenario-chargers').value), seed: Number($('scenario-seed').value)};
    if (simulation.customers + simulation.chargers > 199) {
      showMessage('Elige hasta 199 clientes y cargadores en total, más el depósito.', true);
      return;
    }
    runPanel.loadScenario({dataset: $('scenario-dataset').value, simulation});
  });
  $('scenario-settings').addEventListener('click', () => runPanel.open($('scenario-settings')));
  $('scenario-calculate').addEventListener('click', () => runPanel.calculate($('scenario-calculate')));
  $('scenario-edit').addEventListener('click', () => runPanel.editLocations($('scenario-edit'), selectedId));
  $('scenario-fit').addEventListener('click', fit);
  $('scenario-locations').addEventListener('click', event => {
    const item = event.target.closest('[data-node-index]');
    if (item) {
      select(nodes[Number(item.dataset.nodeIndex)].node_id);
      runPanel.editLocations(item, selectedId);
    }
  });
  const unsubscribe = runPanel.subscribe(next => {
    state = next;
    if (lastNodes !== next.nodes && next.input) {
      lastNodes = next.nodes;
      nodes = next.nodes.filter(node => node.node_type !== 'junction');
      pendingChanges = false;
      const customers = nodes.filter(node => node.node_type === 'visit').length;
      const chargers = nodes.filter(node => node.node_type === 'charger').length;
      const bases = nodes.filter(node => node.node_type === 'base').length;
      $('scenario-customers').value = customers;
      $('scenario-chargers').value = chargers;
      $('scenario-seed').value = next.scenario?.seed ?? 0;
      if (next.scenario?.dataset) $('scenario-dataset').value = next.scenario.dataset;
      $('scenario-counts').textContent = `${bases} depósito · ${customers} clientes · ${chargers} cargadores`;
      const variant = next.scenario?.kind === 'hackathon_simulation';
      $('scenario-map-title').textContent = next.scenario ? variant ? 'Simulación en Ann Arbor' : 'Ann Arbor, Michigan' : 'Ubicaciones de tu instancia';
      $('scenario-caption').textContent = next.scenario
        ? `${variant ? 'Variante simulada' : 'Caso de la hackatón'} · ${next.scenario.dataset} · Ann Arbor, Michigan`
        : next.inputName;
      $('scenario-simulation-note').hidden = !variant;
      $('scenario-locations').innerHTML = nodes.map((node, index) => {
        return `<button type="button" data-node-index="${index}">${esc(title(node))}</button>`;
      }).join('');
      select(null);
      updateMap();
    } else if (!next.input && lastNodes) {
      lastNodes = null;
      nodes = [];
      for (const {marker} of markers) marker.remove();
      markers = [];
      $('scenario-map').dataset.nodeCount = '0';
      $('scenario-counts').textContent = 'Sin ubicaciones cargadas';
      $('scenario-locations').replaceChildren();
      $('scenario-caption').textContent = 'Carga un caso o tus ubicaciones para continuar.';
      select(null);
    }
    const fields = next.fields;
    $('scenario-fleet').textContent = `${fields.num_vehicles} vehículos · batería inicial ${fields.initial_soc} %`;
    $('scenario-assumptions').textContent = next.input
      ? `Supuestos: batería útil ${fields.battery_capacity_kwh} kWh · reserva ${fields.reserve_kwh} kWh.`
      : 'Revisa aquí los supuestos antes de calcular.';
    $('scenario-history').textContent = next.input?.instance ? 'Se conserva el consumo de la red incluida en el archivo.'
      : next.historyId ? `Histórico: ${next.historyName || 'eléctrico preparado'}.`
      : next.historyChosen ? 'Sin histórico seleccionado. Se usará el consumo supuesto.'
        : next.scenario ? 'eVED se cargará del servidor al calcular; no necesitas subir archivos.' : 'Puedes adjuntar tu histórico desde los ajustes.';
    $('scenario-budget').textContent = `${fields.time_limit_seconds} s de búsqueda · ${fields.search_policy === 'adaptive' ? 'GPT por Bedrock' : fields.search_policy === 'deterministic' ? 'Búsqueda determinista' : 'Búsqueda estándar'}.`;
    showMessage(next.message, next.error);
    updateActions();
  });
  addEventListener('pagehide', event => {
    if (event.persisted) return;
    disposed = true; unsubscribe(); clearTimeout(mapTimer); observer?.disconnect();
    for (const {marker} of markers) marker.remove();
    map?.remove();
  });
  runPanel.initializeScenario();
}
