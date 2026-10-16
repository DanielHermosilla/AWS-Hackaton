import { API_VERSION, MAX_FILE_BYTES, createSolverClient, readExecution, saveExecution } from './shared/solver-client.js';
import { parseInstanceFile, inputNodes, inputFormValues, makeSolveRequest, makePrepareRequest, solverSettings, validateNativeInstance, validateInstanceFileHeader, createSyntheticPreparation } from './shared/solver-input.js';
import { nativeRunResult, resultSections } from './shared/solver-output.js';
import { createLocationEditor } from './location-editor.js';
import { readEditableSource, saveEditableSource, readEditableDraft, saveEditableDraft, clearEditableDraft } from './shared/location-draft.js';
import { createHistoryPanel } from './shared/history-panel.js';
import { historyCoverageSnapshot } from './shared/history-details.js';
import { loadHackathonScenario, loadHistoricalCase } from './shared/scenario-client.js';

export function initRunPanel() {
  const fileLimitLabel = `${Math.round(MAX_FILE_BYTES / 1024 / 1024)} MB`;
  const strip = document.createElement('section');
  strip.className = 'run-strip';
  strip.setAttribute('aria-label', 'Ejecución del plan');
  strip.innerHTML = `<div class="run-summary"><strong id="run-source">Planifica el caso de la hackatón</strong><span id="run-description">Revisa las ubicaciones, ajusta el escenario y calcula sus rutas.</span></div>
    <div class="run-actions"><button id="open-run" type="button">Cargar y calcular</button><button id="run-download" type="button" hidden>Ver resultados</button></div>`;
  document.getElementById('app-shell').after(strip);
  const dialog = document.createElement('dialog');
  dialog.id = 'run-dialog';
  dialog.className = 'app-dialog run-dialog';
  dialog.setAttribute('aria-labelledby', 'run-heading');
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="run-heading">Calcular rutas</h2><button id="close-run" type="button" aria-label="Cerrar cálculo">×</button></div>
    <div class="run-view-switch" id="run-view-switch" hidden aria-label="Vista del cálculo"><button id="show-config" type="button" aria-pressed="true">Preparar cálculo</button><button id="show-results" type="button" aria-pressed="false">Ver resultados</button></div>
    <p id="run-intro">Carga el caso histórico de la hackatón y calcula sus rutas, o crea una variante con otros clientes, cargadores y parámetros de flota.</p>
    <form id="run-form" novalidate>
      <section class="run-input-section" aria-labelledby="instance-heading">
        <div class="run-section-heading"><h3 id="instance-heading">Instancia</h3><div class="run-format-help"><button id="instance-format" type="button" aria-label="Formato de los archivos de instancia" aria-expanded="false" aria-controls="instance-help">?</button><div id="instance-help" class="run-format-popover" role="note" hidden><strong>¿Qué archivo puedo usar?</strong><p><b>CSV:</b> una fila por lugar. Incluye <code>node_id</code>, <code>node_type</code>, <code>latitude</code> y <code>longitude</code>. Los tipos son <code>base</code>, <code>visit</code> y <code>charger</code>.</p><p><b>JSON:</b> una instancia o ejecución exportada por esta app, con sus parámetros. Máximo ${fileLimitLabel}; la instancia enviada a calcular admite hasta 64 MB. Los históricos de mediciones eVED no son instancias de rutas.</p></div></div></div>
        <input id="instance-file" class="run-visually-hidden" type="file" accept=".csv,.json" tabindex="-1" aria-label="Archivo de instancia">
        <div class="run-hackathon"><label for="hackathon-dataset">Caso histórico de la hackatón · Ann Arbor, Michigan</label><div><select id="hackathon-dataset"><option value="competition">Caso competition</option><option value="evaluation">Caso evaluation</option></select><button id="use-hackathon" type="button" class="primary">Cargar caso histórico</button></div><p class="run-help">Incluye ubicaciones e histórico eléctrico eVED del servidor, sin subir archivos. Puedes calcular el caso original o crear una variante y cambiar sus parámetros.</p>
        <details class="run-variant"><summary>Simular una variante de este caso</summary><p class="run-help">Conserva el depósito, las calles de Ann Arbor y el histórico. Puedes reducir ubicaciones o añadir clientes y cargadores simulados sobre la red vial.</p><div class="run-synthetic-fields"><label>Clientes<input id="variant-clients" type="number" min="1" max="199" step="1" value="20"></label><label>Cargadores<input id="variant-chargers" type="number" min="0" max="198" step="1" value="60"></label><label>Semilla de ubicaciones<input id="variant-seed" type="number" min="0" max="2000000000" step="1" value="0"></label><button id="simulate-hackathon" type="button">Crear variante</button></div><p class="run-help">Hasta 200 ubicaciones. Los cargadores añadidos son supuestos: J1772/CHAdeMO, dos puertos y potencia nominal máxima de 50 kW. Revisa la flota, batería y margen de consumo más abajo.</p></details></div>
        <div class="run-file-row"><button id="choose-instance" type="button"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M12 17v-5m-3 3 3-3 3 3"/></svg>Cargar mis ubicaciones</button><span id="instance-filename">CSV o JSON · hasta ${fileLimitLabel}</span></div>
        <details class="run-synthetic"><summary>Crear un caso de prueba por distancia</summary><p class="run-help">Genera ubicaciones de ejemplo para probar el cálculo por distancia.</p><div class="run-synthetic-fields"><label>Clientes<input id="synthetic-clients" type="number" min="1" max="199" step="1" value="2"></label><label>Cargadores<input id="synthetic-chargers" type="number" min="0" max="198" step="1" value="1"></label><button id="use-synthetic" type="button">Crear caso</button></div></details>
        <p id="input-summary" class="input-summary" hidden>Ningún archivo seleccionado.</p>
        <div class="run-location-review" id="location-review" hidden><button id="edit-locations" type="button" disabled>Revisar ubicaciones</button><span id="location-review-help">Carga una entrada para revisar sus puntos.</span></div>
      </section>
      <section class="run-card" aria-labelledby="fleet-heading"><h3 id="fleet-heading">Flota y supuestos</h3><div class="run-fields run-fleet-fields">
        <label>Vehículos<input id="run-count" name="num_vehicles" type="number" min="1" max="20" step="1" value="2" required></label>
        <label>Batería inicial · %<input id="run-soc" name="initial_soc" type="number" min="1" max="100" step="any" value="60" required></label>
        <label>Capacidad útil · kWh<input id="run-capacity" name="battery_capacity_kwh" type="number" min="0.01" step="any" placeholder="Por confirmar" required></label>
        <label>Reserva mínima · kWh<input id="run-reserve" name="reserve_kwh" type="number" min="0.001" step="any" placeholder="Por confirmar" required></label>
        <label>Consumo supuesto · kWh/km<input id="run-consumption" name="consumption_kwh_km" type="number" min="0.001" step="any" placeholder="Por confirmar" required></label>
        <label>Red para las ubicaciones<select id="run-network" name="network_mode"><option value="road">Calles del servidor</option><option value="haversine">Distancia · caso sintético</option></select></label>
        <label>Margen de consumo · %<input id="run-margin" name="energy_margin_percent" type="number" min="0" step="any" value="0" required aria-describedby="margin-help"></label>
      </div>
      <p id="margin-help" class="run-help">0 % conserva la estimación. Un margen mayor aumenta el consumo previsto de las calles, incluidas las calibradas con el histórico; la regeneración se conserva.</p>
      <p id="native-note" class="run-help" hidden></p>
      <p id="fleet-help" class="run-help">El escenario oficial usa 2 vehículos al 60 %. Capacidad, reserva y consumo son supuestos que puedes ajustar.</p>
      <p id="network-note" class="run-help">El CSV contiene lugares, no calles. Usa la red del servidor para rutas viales; «Distancia» une los puntos para una prueba sintética.</p><section id="run-history" class="run-history" aria-label="Consumo con históricos"></section></section>
      <section class="run-card" aria-labelledby="engine-heading"><h3 id="engine-heading">Parámetros del motor</h3><div class="run-fields">
        <label>Presupuesto solver · s<input id="run-seconds" name="time_limit_seconds" type="number" min="1" max="120" step="1" value="120" required></label>
        <label>Gap de optimalidad · %<input id="run-gap" name="energy_gap_percent" type="number" min="0" max="100" step="any" value="0.5" required aria-describedby="engine-help"></label>
        <label>Búsqueda<select id="run-policy" name="search_policy"><option value="adaptive">GPT rápido · Bedrock</option><option value="standard">Estándar</option><option value="deterministic">Determinista</option></select></label>
        <label>Semilla<input id="run-seed" name="random_seed" type="number" min="0" max="2000000000" step="1" value="0" required></label>
      </div><p id="engine-help" class="run-help">Primero se buscan más entregas; después, menor consumo. El gap permite un pequeño margen en la energía. La semilla permite repetir la búsqueda.</p></section>
      <p id="run-message" class="run-message" role="status" aria-live="polite" tabindex="-1"></p>
      <div class="dialog-actions run-submit"><button id="stop-waiting" type="button" hidden>Dejar de esperar</button><button id="solve-run" type="submit" class="primary">Calcular rutas</button></div>
    </form>
    <section id="run-results" hidden><p class="run-results-help">Estos datos pertenecen al último cálculo. Puedes volver a consultarlos desde «Ver resultados».</p><details id="result-details" hidden><summary>Datos y límites de la ejecución</summary><div id="run-facts"></div></details></section>
    <div class="run-exports"><button id="export-instance" type="button" disabled>Descargar instancia</button><button id="export-result" type="button" disabled>Descargar ejecución completa</button><button id="export-native-result" type="button" disabled>Descargar resultado nativo</button><button id="export-attempt" type="button" hidden>Descargar intento fallido</button><button id="show-example" type="button">Ver ejemplo de diseño</button></div>`;
  document.body.append(dialog);
  const $ = id => document.getElementById(id);
  let input = null, rawResponse = null, lastRequest = null, lastPrepareRequest = null, canonicalInstance = null, busy = false;
  let draftEdited = false;
  let failedAttempt = null;
  let dialogOpener = $('open-run');
  let saved = readExecution();
  let fileRevision = 0;
  let inputName = '', editorSource = null;
  let draftWarning = '';
  let scenarioLoading = null;
  let readingInstance = false;
  let startingRun = null;
  const listeners = new Set();
  function snapshot() {
    return {
      input, inputName, nodes: input?.instance?.nodes || input?.nodes || [],
      scenario: input?.prepareRequest?.scenario,
      fields: Object.fromEntries([...dialog.querySelectorAll('.run-fields input, .run-fields select')]
        .map(field => [field.name, field.value])),
      busy: busy || !!scenarioLoading || !!startingRun || !!readingInstance,
      historyId: history.profileId,
      historyName: saved?.energyProfile?.filename,
      historyChosen: Object.hasOwn(saved || {}, 'energyProfile'),
      message: $('run-message').textContent,
      error: $('run-message').classList.contains('is-error'),
      stale: !!saved?.stale,
    };
  }
  function notify() { for (const listener of listeners) listener(snapshot()); }
  const history = createHistoryPanel({host: $('run-history'), onChange(profile, {invalidate, invalidatePendingRun}) {
    synchronizeHistoryReference(profile?.profile_id);
    if (invalidate && !input?.instance) {
      if (invalidatePendingRun) startingRun = null;
      dirty();
    }
    try { save({energyProfile: profile, ...(invalidate ? {energyCoverage: null} : {})}); } catch (error) { message(error.message, true); }
    if (invalidate) persistDraft();
    if (profile?.status === 'ready' && !input && !readingInstance) {
      useHackathon().catch(error => message(error.message, true));
    }
    notify();
  }});
  function synchronizeHistoryReference(profileId) {
    if (!input?.prepareRequest) return;
    if ((input.prepareRequest.energy_profile_id || null) === (profileId || null)) return;
    const preparation = {...input.prepareRequest};
    if (profileId) preparation.energy_profile_id = profileId;
    else delete preparation.energy_profile_id;
    input = {...input, prepareRequest: preparation};
  }

  function save(patch) {
    saved = {...saved, ...patch, revision: crypto.randomUUID()};
    if (!saveExecution(saved)) throw new Error('El navegador no permite guardar el identificador de ejecución. Habilita el almacenamiento de esta pestaña para compartir el resultado entre Inicio y Plan.');
  }
  function renderStrip() {
    if (saved?.status === 'running') {
      $('run-source').textContent = 'Cálculo en curso';
      $('run-description').textContent = 'Preparando y resolviendo. Abre el cálculo para ver su estado.';
    } else if (saved?.status === 'error' || saved?.status === 'stopped') {
      $('run-source').textContent = saved.runId ? 'Resultado anterior · cálculo pendiente' : 'Sin resultado del motor';
      $('run-description').textContent = saved.message || 'La ejecución no se completó. Puedes volver a intentar.';
    } else if (saved?.stale) {
      $('run-source').textContent = saved.runId ? 'Resultado anterior · cambios sin calcular' : 'Instancia sin calcular';
      $('run-description').textContent = 'Revisa la entrada y ejecuta para obtener un resultado vigente.';
    } else if (rawResponse?.result) {
      const result = rawResponse.result;
      const noSolutionLabels = {no_solution: 'Sin solución encontrada', unavailable: 'Solver no disponible', error: 'Ejecución con error'};
      $('run-source').textContent = !result.has_solution ? noSolutionLabels[result.status] || 'Sin solución disponible' : result.validation?.feasible === true ? 'Resultado del motor · comprobado'
        : result.validation?.feasible === false ? 'Resultado del motor · validación fallida'
          : 'Resultado del motor · verificación pendiente';
      const served = (result.kpis || nativeRunResult(rawResponse)?.kpis)?.served_deliveries;
      $('run-description').textContent = `${result.metadata?.time_limit_reached === true ? 'Límite de tiempo · ' : ''}${result.validation?.feasible === true && Number.isFinite(served) ? `${served}/${result.total_visits} entregas planificadas` : `${result.total_visits} destinos · entregas sin validar`} · ${result.network?.vial ? 'Red vial' : 'Red sintética o sin verificar'}`;
    } else if (saved?.mode === 'example') {
      $('run-source').textContent = 'Ejemplo de diseño';
      $('run-description').textContent = 'Este ejemplo es ilustrativo. Carga el caso de la hackatón para calcular.';
    } else if (saved) {
      $('run-source').textContent = 'Sin resultado del motor';
      $('run-description').textContent = 'Revisa el mapa y calcula las rutas del escenario.';
    }
    strip.dataset.stale = String(!!saved?.stale);
    $('run-download').hidden = !rawResponse;
    $('run-view-switch').hidden = !rawResponse;
    if (saved && !saved.runId && saved.mode !== 'example') {
      const main = document.querySelector('main');
      main.dataset.runPending = 'true';
    }
    notify();
  }
  function message(text, isError = false) {
    $('run-message').textContent = [text, draftWarning].filter(Boolean).join(' ');
    $('run-message').classList.toggle('is-error', isError);
    if (isError && dialog.open) $('run-message').focus();
    notify();
  }
  function setBusy(value) {
    busy = value;
    $('solve-run').disabled = value;
    $('use-hackathon').disabled = value || !!scenarioLoading;
    $('simulate-hackathon').disabled = value || !!scenarioLoading;
    $('edit-locations').disabled = !input || !!scenarioLoading;
    $('solve-run').textContent = value ? 'Calculando…' : 'Calcular rutas';
    $('stop-waiting').hidden = !value;
    $('run-form').setAttribute('aria-busy', String(value || !!scenarioLoading));
    history.setRunBusy(value || !!scenarioLoading);
    notify();
  }
  const client = createSolverClient({
    onChange(state) {
      setBusy(state.status === 'running');
      message(state.message, state.status === 'error');
      if (state.status === 'running') $('export-attempt').hidden = true;
      if (state.status === 'error' && lastRequest) {
        failedAttempt = {schema_version: 'zmd.integration-beta.attempt/2', request: lastRequest, prepare_request: lastPrepareRequest, stage: state.stage,
          response: state.response, status: 'error', message: state.message, observed_at: new Date().toISOString()};
        $('export-attempt').hidden = false;
      }
      if (state.status !== 'complete') {
        try { save({status: state.status, message: state.message, stale: true}); }
        catch (error) { message(error.message, true); }
      }
      renderStrip();
    },
    onPrepared(request, isCurrent, prepared) {
      validateNativeInstance(request.instance);
      if (!isCurrent()) return;
      canonicalInstance = request.instance;
      lastRequest = request;
      $('export-instance').disabled = false;
      const coverage = prepared?.preparation?.energy_profile;
      history.showCoverage(coverage);
      if (coverage) {
        // Retain only the small display summary, never telemetry or credentials.
        save({energyCoverage: {profile_id: history.profileId, ...historyCoverageSnapshot(coverage)}});
      }
    },
    async onResult(response, isCurrent) {
      // Validate the exact result that will be consumed on both pages before retaining its ID.
      const { adaptSolverResponse } = await import('./shared/solver-adapter.js');
      if (!isCurrent()) return;
      adaptSolverResponse(response);
      // A result may finish while the independent location draft is open.
      // Confirm invalidates it; cancel allows the unchanged run to complete.
      await locationEditor.whenClosed();
      if (!isCurrent()) return;
      const editableSourceSaved = saveEditableSource(response.result.run_id, lastPrepareRequest);
      save({runId: response.result.run_id, stale: false, status: 'complete', message: '', editableSourceSaved, draftId: null, draftUnavailable: false, reopenResults: true});
      clearEditableDraft();
      location.reload();
    },
  });
  function dirty() {
    draftEdited = true;
    canonicalInstance = null;
    history.invalidateCoverage();
    client.invalidate();
    setBusy(false);
    $('export-instance').disabled = true;
    message('Cambios guardados para el próximo cálculo.');
    try { save({mode: 'model', stale: true, status: 'editing', message: '', draftId: null, energyCoverage: null}); }
    catch (error) { message(error.message, true); }
    renderStrip();
  }
  const locationEditor = createLocationEditor({
    onOpenChange() { setBusy(busy); },
    onConfirm(confirmed) {
      if (input !== editorSource) throw new Error('La entrada cambió mientras editabas. Abre de nuevo sus ubicaciones.');
      input = confirmed;
      startingRun = null;
      dirty();
      persistDraft();
      renderInputSummary();
      message('Ubicaciones actualizadas. Calcula de nuevo para obtener las rutas.');
    },
  });
  function persistDraft() {
    draftWarning = '';
    if (!input) return;
    const draftId = crypto.randomUUID();
    const fields = Object.fromEntries([...dialog.querySelectorAll('.run-fields input, .run-fields select')].map(field => [field.name, field.value]));
    const retained = saveEditableDraft(draftId, input, fields);
    try {
      save({draftId: retained ? draftId : null, draftUnavailable: !retained});
      if (retained) return;
    } catch { /* Explain the same persistence limitation below. */ }
    draftWarning = 'El navegador no pudo conservar el borrador. Mantén esta página abierta hasta calcular: si navegas o recargas perderás estos cambios.';
    message('Cambios pendientes.');
  }
  function renderInputSummary() {
    const nodes = inputNodes(input);
    const clients = nodes.filter(n => n.node_type === 'visit').length;
    const chargers = nodes.filter(n => n.node_type === 'charger').length;
    $('input-summary').textContent = `${inputName} · 1 depósito · ${clients} ${clients === 1 ? 'cliente' : 'clientes'} · ${chargers} ${chargers === 1 ? 'cargador' : 'cargadores'}${input.instance ? ` · ${input.instance.arcs.length} arcos` : ''}`;
    $('input-summary').hidden = false;
    $('location-review').hidden = false;
    notify();
  }
  function fieldsFrom(value) {
    const values = inputFormValues(value);
    for (const [name, raw] of Object.entries(values)) {
      const field = $('run-form').elements.namedItem(name === 'energy_relative_gap' ? 'energy_gap_percent' : name);
      if (field) {
        field.value = raw == null ? '' : ['initial_soc', 'energy_relative_gap'].includes(name) ? Number(raw) * 100 : raw;
        field.removeAttribute('aria-invalid');
      }
    }
  }
  function setInput(value, name, {preferSavedHistory = false} = {}) {
    locationEditor.close();
    input = value;
    lastPrepareRequest = value.prepareRequest || null;
    inputName = name;
    if (value.prepareRequest?.scenario) {
      $('hackathon-dataset').value = value.prepareRequest.scenario.dataset;
      $('variant-clients').value = value.nodes.filter(node => node.node_type === 'visit').length;
      $('variant-chargers').value = value.nodes.filter(node => node.node_type === 'charger').length;
      $('variant-seed').value = value.prepareRequest.scenario.seed ?? 0;
    }
    const native = !!value.instance;
    history.setNative(native);
    // A saved explicit choice (including removal) takes precedence over the
    // previous execution's preparation when recovering this tab's current draft.
    if (preferSavedHistory && Object.hasOwn(saved || {}, 'energyProfile')) {
      const selectedId = saved.energyProfile?.profile_id || null;
      synchronizeHistoryReference(selectedId);
      history.restore(selectedId).then(notify);
    } else if (value.prepareRequest?.energy_profile_id) history.restore(value.prepareRequest.energy_profile_id).then(notify);
    renderInputSummary();
    $('edit-locations').disabled = false;
    $('edit-locations').textContent = native ? 'Revisar ubicaciones' : 'Editar ubicaciones';
    $('location-review-help').textContent = native ? 'La red del archivo se conserva.' : 'Revisa los puntos en el formulario o en el mapa.';
    $('network-note').textContent = native
      ? 'Se usará la red incluida en el archivo. Los lugares sin coordenadas aparecen en la lista.'
      : 'El CSV contiene lugares, no calles. Usa la red del servidor para rutas viales; «Distancia» une los puntos para una prueba sintética.';
    $('run-network').disabled = native;
    $('native-note').hidden = !native;
    $('native-note').textContent = native ? 'Estos valores provienen del archivo. Para cambiar la flota o la red, edita el JSON y vuelve a cargarlo. Los parámetros del motor sí se pueden ajustar aquí.' : '';
    $('fleet-help').hidden = native;
    $('run-consumption').closest('label').hidden = native;
    for (const field of dialog.querySelectorAll('.run-fleet-fields input')) field.disabled = native;
    fieldsFrom(value);
    canonicalInstance = native ? value.instance : null;
    setBusy(busy);
  }
  async function useHackathon({withHistory = false, simulation = null} = {}) {
    if (scenarioLoading) return scenarioLoading;
    if (withHistory && history.isPending) throw new Error('Espera a que termine la carga del histórico.');
    const revision = ++fileRevision;
    startingRun = null;
    readingInstance = false;
    message(simulation ? 'Creando la variante sobre las calles de Ann Arbor…' : withHistory
      ? 'Cargando ubicaciones e histórico eléctrico de la hackatón…' : 'Cargando las ubicaciones de la hackatón en Ann Arbor…');
    $('use-hackathon').disabled = true;
    const loading = (async () => {
      const loaded = withHistory
        ? await loadHistoricalCase({dataset: $('hackathon-dataset').value, simulation,
          ...(simulation && history.profileId ? {energy_profile_id: history.profileId} : {})})
        : {scenario: await loadHackathonScenario($('hackathon-dataset').value)};
      const scenario = loaded.scenario;
      if (revision !== fileRevision) return;
      // Read the latest edits after the fetch, including changes made while the
      // historical upload was being normalized. Do not reset fleet/solver choices.
      const fields = Object.fromEntries([...dialog.querySelectorAll('.run-fields input, .run-fields select')]
        .filter(field => field.value !== '').map(field => [field.name, field.value]));
      dirty();
      const prepareRequest = {api_version: API_VERSION, nodes: scenario.nodes, network_mode: 'road',
        ...(scenario.scenario ? {scenario: scenario.scenario} : {}),
        fleet: {num_vehicles: 2, initial_soc: .6, battery_capacity_kwh: 24, reserve_kwh: 2.4, consumption_kwh_km: .2}};
      setInput({nodes: scenario.nodes, prepareRequest}, scenario.name);
      for (const [name, value] of Object.entries(fields)) $('run-form').elements.namedItem(name).value = value;
      // Selecting the challenge always requests the real street network.
      $('run-network').value = 'road';
      if (loaded.profile) history.useProfile(loaded.profile);
      synchronizeHistoryReference(history.profileId);
      $('instance-file').value = '';
      $('instance-filename').textContent = scenario.source_file;
      persistDraft();
      message(simulation
        ? 'Variante lista con el mismo histórico. Revisa las ubicaciones y ajusta flota, batería o margen de consumo antes de calcular.'
        : 'Caso de Ann Arbor cargado. Revisa la flota y calcula. Valores iniciales ajustables: capacidad útil 24 kWh, reserva 2,4 kWh y consumo de respaldo 0,2 kWh/km; no son mediciones ni reglas oficiales.');
    })();
    scenarioLoading = loading;
    setBusy(busy);
    try { await loading; }
    catch (error) { if (revision === fileRevision) throw error; }
    finally {
      if (scenarioLoading === loading) { scenarioLoading = null; setBusy(busy); }
    }
  }
  function buildJob() {
    if (readingInstance) throw new Error('Espera a que termine la lectura de la instancia antes de calcular.');
    if (!input) throw new Error('Elige el caso de la hackatón, adjunta un histórico o carga tus ubicaciones para simular la flota.');
    if (!input.instance && history.isPending) throw new Error('Espera a que termine el histórico o cancela su carga antes de calcular.');
    if (locationEditor.isOpen) throw new Error('Confirma o cancela la edición de ubicaciones antes de calcular.');
    for (const field of dialog.querySelectorAll('.run-fields input')) {
      field.removeAttribute('aria-invalid');
      if (!field.disabled && !field.checkValidity()) {
        field.setAttribute('aria-invalid', 'true');
        const label = field.closest('label').firstChild.textContent.trim();
        throw new Error(field.value === '' ? `Completa «${label}» para calcular las rutas.` : `Revisa «${label}»: ingresa un valor entre ${field.min} y ${field.max || 'un máximo válido para tu flota'}.`);
      }
    }
    const settings = [$('run-seconds').value, $('run-policy').value, Number($('run-gap').value) / 100, $('run-seed').value];
    if (input.instance) return {request: makeSolveRequest(input, ...settings), prepareRequest: null};
    const values = Object.fromEntries(['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km']
      .map(key => [key, $('run-form').elements.namedItem(key).value]));
    values.initial_soc = Number(values.initial_soc) / 100;
    values.network_mode = $('run-network').value;
    values.energy_profile_id = history.profileId;
    values.energy_margin_percent = $('run-margin').value;
    return {request: {api_version: API_VERSION, solver: solverSettings(...settings)},
      prepareRequest: makePrepareRequest(input, values)};
  }
  function showView(view) {
    const results = view === 'results' && !!rawResponse;
    $('run-form').hidden = results;
    $('run-results').hidden = !results;
    $('run-intro').hidden = results;
    $('run-heading').textContent = results ? 'Resultados del cálculo' : 'Calcular rutas';
    $('show-config').setAttribute('aria-pressed', String(!results));
    $('show-results').setAttribute('aria-pressed', String(results));
    if (results) $('result-details').open = true;
    dialog.scrollTop = 0;
  }
  function open(trigger, view = 'config') {
    dialogOpener = trigger;
    showView(view);
    if (!dialog.open) dialog.showModal();
    (view === 'results' ? $('result-details').querySelector('summary') : input?.instance ? $('run-seconds') : input ? $('run-capacity') : $('use-hackathon')).focus({preventScroll: true});
  }
  $('open-run').addEventListener('click', () => open($('open-run')));
  $('run-download').addEventListener('click', () => open($('run-download'), 'results'));
  $('show-config').addEventListener('click', () => showView('config'));
  $('show-results').addEventListener('click', () => showView('results'));
  $('choose-instance').addEventListener('click', () => $('instance-file').click());
  $('use-hackathon').addEventListener('click', () => useHackathon({withHistory: true}).catch(error => message(error.message, true)));
  $('simulate-hackathon').addEventListener('click', () => {
    const simulation = {customers: Number($('variant-clients').value), chargers: Number($('variant-chargers').value), seed: Number($('variant-seed').value)};
    if (!Number.isInteger(simulation.customers) || simulation.customers < 1 ||
        !Number.isInteger(simulation.chargers) || simulation.chargers < 0 ||
        simulation.customers + simulation.chargers > 199 ||
        !Number.isInteger(simulation.seed) || simulation.seed < 0 || simulation.seed > 2000000000) {
      message('Usa cantidades enteras: al menos un cliente, cargadores desde cero, hasta 200 ubicaciones en total y semilla entre 0 y 2.000.000.000.', true);
      return;
    }
    useHackathon({withHistory: true, simulation}).catch(error => message(error.message, true));
  });
  const help = $('instance-format').parentElement;
  const showHelp = visible => {
    $('instance-format').setAttribute('aria-expanded', String(visible));
    $('instance-help').hidden = !visible;
  };
  help.addEventListener('mouseenter', () => showHelp(true));
  help.addEventListener('mouseleave', () => { if (!help.contains(document.activeElement)) showHelp(false); });
  help.addEventListener('focusin', () => showHelp(true));
  help.addEventListener('focusout', event => { if (!help.contains(event.relatedTarget)) showHelp(false); });
  $('instance-format').addEventListener('click', () => showHelp(true));
  help.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('instance-help').hidden) { event.preventDefault(); event.stopPropagation(); showHelp(false); } });
  dialog.addEventListener('pointerdown', event => { if (!help.contains(event.target)) showHelp(false); });
  $('close-run').addEventListener('click', () => dialog.close());
  $('edit-locations').addEventListener('click', () => {
    if (!input) return;
    editorSource = input;
    locationEditor.open(input, $('edit-locations'));
  });
  dialog.addEventListener('close', () => dialogOpener?.focus());
  $('instance-file').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    const revision = ++fileRevision;
    scenarioLoading = null;
    startingRun = null;
    readingInstance = revision;
    dirty();
    locationEditor.close();
    input = null;
    $('input-summary').hidden = true;
    $('location-review').hidden = true;
    $('edit-locations').disabled = true;
    $('location-review-help').textContent = 'Carga una entrada para revisar sus puntos.';
    $('instance-filename').textContent = file.name;
    try {
      validateInstanceFileHeader(await file.slice(0, 4096).text());
      if (revision !== fileRevision) return;
      if (file.size > MAX_FILE_BYTES) throw new Error(`El archivo supera los ${fileLimitLabel}. Usa una instancia de rutas con ubicaciones y parámetros, sin históricos de mediciones.`);
      const text = await file.text();
      if (revision !== fileRevision) return;
      setInput(parseInstanceFile(text, file.name), file.name);
      persistDraft();
      message('Archivo cargado. Los parámetros incluidos ya están en el formulario.');
    } catch (error) { if (revision === fileRevision) message(error.message, true); }
    finally { if (readingInstance === revision) readingInstance = false; }
  });
  $('use-synthetic').addEventListener('click', () => {
    let prepareRequest;
    try {
      prepareRequest = createSyntheticPreparation({clients: Number($('synthetic-clients').value), chargers: Number($('synthetic-chargers').value)});
    } catch (error) { message(error.message, true); return; }
    fileRevision++;
    scenarioLoading = null;
    startingRun = null;
    readingInstance = false;
    dirty();
    setInput({nodes: prepareRequest.nodes, prepareRequest}, 'Caso sintético · valores supuestos');
    persistDraft();
    $('instance-file').value = '';
    $('instance-filename').textContent = 'Caso de prueba creado';
    dialog.querySelector('.run-synthetic').open = false;
    message('Caso listo. Las rutas se calcularán por distancia, sin conectarlas a calles reales.');
  });
  for (const field of dialog.querySelectorAll('.run-fields input')) field.addEventListener('input', () => { field.removeAttribute('aria-invalid'); dirty(); persistDraft(); });
  for (const field of dialog.querySelectorAll('.run-fields select')) field.addEventListener('change', () => { dirty(); persistDraft(); });
  $('run-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || startingRun) return;
    const attempt = {revision: fileRevision};
    startingRun = attempt;
    notify();
    try {
      if (readingInstance) throw new Error('Espera a que termine la lectura de la instancia antes de calcular.');
      if (history.isPending && !input?.instance) throw new Error('Espera a que termine la carga del histórico antes de calcular.');
      if (scenarioLoading) {
        await scenarioLoading;
        if (attempt.revision !== fileRevision) return;
      }
      if (!input && history.profileId) {
        const loading = useHackathon();
        attempt.revision = fileRevision;
        startingRun = attempt;
        await loading;
        if (attempt.revision !== fileRevision) return;
      }
      if (busy) return;
      // The default preview is cheap. Load telemetry only when the user asks to
      // calculate, preserving this draft's nodes and any explicit history choice.
      if (input?.prepareRequest?.scenario && !Object.hasOwn(saved || {}, 'energyProfile')) {
        const revision = fileRevision, source = input;
        message('Preparando el histórico eléctrico eVED del servidor…');
        const loaded = await loadHistoricalCase({dataset: input.prepareRequest.scenario.dataset});
        if (startingRun !== attempt || revision !== fileRevision || input !== source) return;
        history.useProfile(loaded.profile);
        synchronizeHistoryReference(history.profileId);
        persistDraft();
      }
      const job = buildJob();
      lastRequest = job.request;
      lastPrepareRequest = job.prepareRequest;
      canonicalInstance = input.instance || null;
      // Check minimal persistence before spending compute.
      save({stale: true, status: 'ready', message: ''});
      await client.solve(lastRequest, {prepareRequest: lastPrepareRequest});
      $('export-instance').disabled = !canonicalInstance;
    } catch (error) { if (startingRun === attempt && attempt.revision === fileRevision) message(error.message, true); }
    finally { if (startingRun === attempt) { startingRun = null; notify(); } }
  });
  $('stop-waiting').addEventListener('click', () => client.stopWaiting());
  $('show-example').addEventListener('click', () => {
    client.invalidate();
    saveEditableSource(null, null);
    clearEditableDraft();
    saveExecution({mode: 'example'});
    location.reload();
  });
  function download(value, filename) {
    const blob = new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('export-instance').addEventListener('click', () => {
    // The previous result may remain visible after a new native calculation fails.
    // Its road preparation must never replace the currently loaded instance.
    const preparation = lastPrepareRequest;
    if (canonicalInstance && preparation?.network_mode === 'road') download(preparation, 'entrada-vial.json');
    else if (canonicalInstance) download(canonicalInstance, 'instancia-nativa.json');
    else message('Prepara o carga una instancia nativa antes de descargarla.', true);
  });
  $('export-result').addEventListener('click', () => {
    if (rawResponse) download(rawResponse, `resultado-${rawResponse.result.run_id}.json`);
  });
  $('export-native-result').addEventListener('click', () => {
    const native = nativeRunResult(rawResponse);
    if (native) download(native, `resultado-nativo-${native.run_id}.json`);
  });
  $('export-attempt').addEventListener('click', () => {
    if (failedAttempt) download(failedAttempt, 'intento-fallido-beta.json');
  });
  new ResizeObserver(() => {
    document.documentElement.style.setProperty('--run-strip-height', `${strip.getBoundingClientRect().height}px`);
  }).observe(strip);
  const arrivalRevision = readExecution()?.revision;
  addEventListener('pageshow', event => {
    if (event.persisted && arrivalRevision !== readExecution()?.revision) location.reload();
  });
  addEventListener('pagehide', () => { client.invalidate(); history.close(); });
  if (saved?.status === 'running') {
    saved = {...saved, status: 'stopped', message: 'La espera anterior terminó al salir de la página. El cálculo puede continuar en el servidor.', stale: true};
    saveExecution(saved);
  }
  const restoredDraft = readEditableDraft(saved?.draftId);
  if (saved?.energyProfile?.profile_id) history.restore(saved.energyProfile.profile_id).then(() => {
    if (saved?.energyCoverage?.profile_id === history.profileId) history.showCoverage(saved.energyCoverage);
    notify();
  });
  if (restoredDraft) {
    setInput(restoredDraft.input, 'Borrador sin calcular', {preferSavedHistory: true});
    for (const [name, value] of Object.entries(restoredDraft.fields)) {
      const field = $('run-form').elements.namedItem(name);
      if (field) field.value = value;
    }
    if (restoredDraft.input.prepareRequest?.energy_profile_id !== input.prepareRequest?.energy_profile_id) persistDraft();
    draftEdited = true;
    canonicalInstance = null;
    $('export-instance').disabled = true;
    message('Recuperamos tus ubicaciones y parámetros. Puedes continuar con el cálculo.');
  } else if (saved?.stale) {
    draftEdited = true;
    message('La entrada pendiente no está disponible en esta página. Carga de nuevo su archivo; un resultado anterior no contiene los cambios sin calcular.');
  }
  setBusy(false);
  renderStrip();
  return {
    subscribe(listener) { listeners.add(listener); listener(snapshot()); return () => listeners.delete(listener); },
    async initializeScenario() {
      if (input || saved || readingInstance) return;
      try { await useHackathon(); }
      catch (error) { message(error.message, true); }
    },
    async loadScenario({dataset, simulation = null} = {}) {
      if (busy || startingRun || scenarioLoading) return;
      if (dataset) $('hackathon-dataset').value = dataset;
      try { await useHackathon({withHistory: true, simulation}); }
      catch (error) { message(error.message, true); }
    },
    open,
    editLocations(trigger, nodeId) {
      if (!input || busy || scenarioLoading || startingRun) return;
      editorSource = input;
      locationEditor.open(input, trigger, nodeId);
    },
    calculate(trigger) {
      open(trigger);
      $('run-form').requestSubmit();
      $('run-message').focus();
    },
    setData(data) {
      rawResponse = data.RAW_RESPONSE;
      if (rawResponse) {
        const result = rawResponse.result;
        const request = result.raw.input;
        // A slow run fetch must not overwrite a draft already edited on this page.
        if (!draftEdited) {
          const editable = readEditableSource(result.run_id, undefined, result.raw.instance);
          const preparation = result.raw.prepare_request || editable?.prepareRequest;
          setInput(preparation
            ? {nodes: preparation.nodes, prepareRequest: preparation, request}
            : {instance: result.raw.instance, request}, 'Entrada de esta ejecución', {preferSavedHistory: true});
          canonicalInstance = result.raw.instance;
          lastRequest = request;
          lastPrepareRequest = preparation || null;
          $('export-instance').disabled = false;
          if (saved?.editableSourceSaved === false)
            message('El navegador no conservó el origen editable. Carga el CSV original para cambiar ubicaciones; la instancia calculada mantiene su red protegida.');
        }
        $('export-result').disabled = false;
        $('export-native-result').disabled = !nativeRunResult(rawResponse);
        $('result-details').hidden = false;
        $('run-facts').replaceChildren();
        for (const group of resultSections(result)) {
          if (!group.rows.length && !group.notes.length) continue;
          const section = document.createElement('section');
          section.className = 'run-result-section';
          const heading = document.createElement('h3');
          heading.textContent = group.title;
          section.append(heading);
          const list = document.createElement('dl');
          for (const row of group.rows) {
            const term = document.createElement('dt'), description = document.createElement('dd');
            term.textContent = row.label;
            description.textContent = row.value;
            if (row.reason) {
              const reason = document.createElement('small');
              reason.textContent = row.reason;
              description.append(reason);
            }
            list.append(term, description);
          }
          section.append(list);
          for (const note of group.notes) {
            const paragraph = document.createElement('p');
            paragraph.textContent = note;
            section.append(paragraph);
          }
          $('run-facts').append(section);
        }
      }
      renderStrip();
      if (rawResponse && saved?.reopenResults) {
        save({reopenResults: false});
        open($('run-download'), 'results');
      }
    },
    fail(error) {
      message(error.message, true);
      $('run-source').textContent = 'No se pudo recuperar la ejecución';
      $('run-description').textContent = error.message;
    },
  };
}
