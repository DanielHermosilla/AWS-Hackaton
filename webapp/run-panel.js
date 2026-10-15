import { API_VERSION, createSolverClient, readExecution, saveExecution } from './shared/solver-client.js';
import { parseInstanceFile, inputNodes, makeSolveRequest, makePrepareRequest, solverSettings, validateNativeInstance, SYNTHETIC_PREPARATION } from './shared/solver-input.js';
import { nativeRunResult, resultSections } from './shared/solver-output.js';

export function initRunPanel() {
  const strip = document.createElement('section');
  strip.className = 'run-strip';
  strip.setAttribute('aria-label', 'Ejecución del plan');
  strip.innerHTML = `<div class="run-summary"><strong id="run-source">Ejemplo de diseño</strong><span id="run-description">Calcula una instancia con el motor para obtener un plan.</span></div>
    <div class="run-actions"><button id="open-run" type="button">Cargar y calcular</button><button id="run-download" type="button" hidden>Descargar</button></div>`;
  document.getElementById('app-shell').after(strip);
  const dialog = document.createElement('dialog');
  dialog.id = 'run-dialog';
  dialog.className = 'app-dialog run-dialog';
  dialog.setAttribute('aria-labelledby', 'run-heading');
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="run-heading">Calcular rutas</h2><button id="close-run" type="button" aria-label="Cerrar cálculo">×</button></div>
    <p>Revisa la instancia y los supuestos antes de ejecutar. El motor se ejecuta en este servidor local.</p>
    <form id="run-form">
      <label class="run-file" for="instance-file">Instancia <input id="instance-file" type="file" accept=".csv,.json" aria-describedby="instance-help"></label>
      <p id="instance-help" class="run-help">CSV de nodos, ProblemInstance nativa 1.0 o una descarga del API 3.0. Hasta 8 MB.</p>
      <button id="use-synthetic" type="button" class="run-text-button">Usar caso sintético pequeño</button>
      <p id="input-summary" class="input-summary">Ningún archivo seleccionado.</p>
      <fieldset class="run-fields"><legend>Flota y supuestos</legend>
        <label>Vehículos<input id="run-count" name="num_vehicles" type="number" min="1" max="20" step="1" value="2" required></label>
        <label>SoC inicial · %<input id="run-soc" name="initial_soc" type="number" min="1" max="100" step="any" value="60" required></label>
        <label>Capacidad útil · kWh<input id="run-capacity" name="battery_capacity_kwh" type="number" min="0.01" step="any" placeholder="Por confirmar" required></label>
        <label>Reserva mínima · kWh<input id="run-reserve" name="reserve_kwh" type="number" min="0.001" step="any" placeholder="Supuesto explícito" required></label>
        <label>Consumo supuesto · kWh/km<input id="run-consumption" name="consumption_kwh_km" type="number" min="0.001" step="any" placeholder="Supuesto explícito" required></label>
        <label>Presupuesto solver · s<input id="run-seconds" name="time_limit_seconds" type="number" min="1" max="120" step="1" value="10" required></label>
      </fieldset>
      <p id="native-note" class="run-help" hidden></p>
      <p id="fleet-help" class="run-help">El perfil oficial usa 2 Nissan Leaf 2013 al 60 %. Capacidad útil, reserva y consumo son supuestos de esta ejecución.</p>
      <p id="network-note" class="run-help">El CSV aporta ubicaciones. Esta beta usa una aproximación por distancia, sin red vial ni pendiente. Una instancia nativa conserva sus arcos, parámetros y operaciones.</p>
      <label class="run-ack"><input id="run-ack" type="checkbox" required><span>Revisé estos parámetros y el alcance de la red.</span></label>
      <p id="run-message" class="run-message" role="status" aria-live="polite" tabindex="-1"></p>
      <div class="dialog-actions"><button id="stop-waiting" type="button" hidden>Dejar de esperar</button><button id="solve-run" type="submit" class="primary">Calcular rutas</button></div>
    </form>
    <details id="result-details" hidden><summary>Datos y límites de la ejecución</summary><div id="run-facts"></div></details>
    <div class="run-exports"><button id="export-instance" type="button" disabled>Descargar instancia</button><button id="export-result" type="button" disabled>Descargar ejecución completa</button><button id="export-native-result" type="button" disabled>Descargar resultado nativo</button><button id="export-attempt" type="button" hidden>Descargar intento fallido</button><button id="show-example" type="button">Ver ejemplo de diseño</button></div>`;
  document.body.append(dialog);
  const $ = id => document.getElementById(id);
  let input = null, rawResponse = null, lastRequest = null, lastPrepareRequest = null, canonicalInstance = null, busy = false;
  let draftEdited = false;
  let failedAttempt = null;
  let dialogOpener = $('open-run');
  let saved = readExecution();
  let fileRevision = 0;

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
      $('run-description').textContent = `${result.metadata?.time_limit_reached === true ? 'Límite de tiempo · ' : ''}${result.validation?.feasible === true && Number.isFinite(served) ? `${served}/${result.total_visits} entregas planificadas` : `${result.total_visits} destinos · entregas sin validar`} · ${result.network?.vial ? 'Red vial declarada' : 'Red no vial'} · ${result.run_id.slice(0, 8)}`;
    } else if (saved) {
      $('run-source').textContent = 'Sin resultado del motor';
      $('run-description').textContent = 'Carga una instancia o vuelve al ejemplo de diseño.';
    }
    strip.dataset.stale = String(!!saved?.stale);
    $('run-download').hidden = !rawResponse;
    if (saved && !saved.runId) {
      const main = document.querySelector('main');
      main.dataset.runPending = 'true';
      if (!main.querySelector('.run-pending-placeholder')) {
        const empty = document.createElement('section');
        empty.className = 'load-error run-pending-placeholder';
        empty.innerHTML = '<h1>Sin resultado del motor</h1><p>Revisa tu instancia en «Cargar y calcular». Aquí aparecerán las rutas cuando termine la ejecución.</p>';
        main.append(empty);
      }
    }
  }
  function message(text, isError = false) {
    $('run-message').textContent = text;
    $('run-message').classList.toggle('is-error', isError);
    if (isError) $('run-message').focus();
  }
  function setBusy(value) {
    busy = value;
    $('solve-run').disabled = value || !input;
    $('stop-waiting').hidden = !value;
    $('run-form').setAttribute('aria-busy', String(value));
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
    onPrepared(request, isCurrent) {
      validateNativeInstance(request.instance);
      if (!isCurrent()) return;
      canonicalInstance = request.instance;
      lastRequest = request;
      $('export-instance').disabled = false;
    },
    async onResult(response, isCurrent) {
      // Validate the exact result that will be consumed on both pages before retaining its ID.
      const { adaptSolverResponse } = await import('./shared/solver-adapter.js');
      if (!isCurrent()) return;
      adaptSolverResponse(response);
      save({runId: response.result.run_id, stale: false, status: 'complete', message: ''});
      location.reload();
    },
  });
  function dirty() {
    draftEdited = true;
    canonicalInstance = null;
    client.invalidate();
    setBusy(false);
    $('run-ack').checked = false;
    $('export-instance').disabled = true;
    message('Cambios sin calcular. Revisa los supuestos antes de ejecutar.');
    try { save({stale: true, status: 'editing', message: ''}); }
    catch (error) { message(error.message, true); }
    renderStrip();
  }
  function fieldsFrom(value) {
    const native = value.instance;
    const fleet = native?.parameters || value.prepareRequest?.fleet || {};
    $('run-count').value = (native ? fleet.vehicle_count : fleet.num_vehicles) ?? (native ? '' : 2);
    $('run-soc').value = fleet.initial_soc == null ? (native ? '' : 60) : fleet.initial_soc * 100;
    $('run-capacity').value = fleet.battery_capacity_kwh ?? '';
    $('run-reserve').value = fleet.reserve_kwh ?? '';
    $('run-consumption').value = native ? '' : fleet.consumption_kwh_km ?? '';
    $('run-seconds').value = value.request?.solver?.time_limit_seconds ?? 10;
  }
  function setInput(value, name) {
    input = value;
    const nodes = inputNodes(value);
    const native = !!value.instance;
    $('input-summary').textContent = `${name} · ${nodes.filter(n => n.node_type === 'base').length} depósito · ${nodes.filter(n => n.node_type === 'visit').length} destinos · ${nodes.filter(n => n.node_type === 'charger').length} cargadores${native ? ` · ${value.instance.arcs.length} arcos` : ''}`;
    $('network-note').textContent = native
      ? 'Se utilizará la red incluida en el JSON. Las coordenadas son opcionales: los nodos sin ubicación se conservan en la lista. El servidor valida la instancia sin cambiar su configuración física.'
      : 'El servidor preparará una aproximación por distancia, sin red vial ni pendiente. Las coordenadas no acreditan conectividad por calles.';
    $('native-note').hidden = !native;
    $('native-note').textContent = native ? 'Parámetros del JSON protegidos. Arcos, operaciones, conectores, compatibilidad y procedencia se conservan íntegros. Los parámetros omitidos usan los valores predeterminados del contrato nativo del motor; sus valores efectivos aparecerán en la instancia exportada después de ejecutar. Para cambiar el escenario, edita el archivo y vuelve a cargarlo. Solo el presupuesto del solver se configura aquí.' : '';
    $('fleet-help').hidden = native;
    $('run-consumption').closest('label').hidden = native;
    for (const field of dialog.querySelectorAll('.run-fields input')) {
      if (field.id !== 'run-seconds') field.disabled = native;
    }
    if (native || value.prepareRequest) fieldsFrom(value);
    canonicalInstance = native ? value.instance : null;
    $('solve-run').disabled = false;
  }
  function buildJob() {
    if (!input) throw new Error('Selecciona una instancia antes de calcular.');
    if (input.instance) return {request: makeSolveRequest(input, $('run-seconds').value), prepareRequest: null};
    const values = Object.fromEntries(['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km']
      .map(key => [key, $('run-form').elements.namedItem(key).value]));
    values.initial_soc = Number(values.initial_soc) / 100;
    return {request: {api_version: API_VERSION, solver: solverSettings($('run-seconds').value)},
      prepareRequest: makePrepareRequest(input, values)};
  }
  function open(trigger) {
    dialogOpener = trigger;
    dialog.showModal();
    (input?.instance ? $('run-seconds') : input ? $('run-capacity') : $('instance-file')).focus();
  }
  $('open-run').addEventListener('click', () => open($('open-run')));
  $('run-download').addEventListener('click', () => { open($('run-download')); $('result-details').open = true; $('export-result').focus(); });
  $('close-run').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => dialogOpener?.focus());
  $('instance-file').addEventListener('change', async event => {
    const revision = ++fileRevision;
    dirty();
    input = null;
    $('solve-run').disabled = true;
    const file = event.target.files?.[0];
    if (!file) { $('input-summary').textContent = 'Ningún archivo seleccionado.'; return; }
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('El archivo supera el límite de 8 MB de esta beta.');
      const text = await file.text();
      if (revision !== fileRevision) return;
      setInput(parseInstanceFile(text, file.name), file.name);
      message('Instancia leída. Confirma los parámetros y el alcance de la red.');
    } catch (error) { if (revision === fileRevision) message(error.message, true); }
  });
  $('use-synthetic').addEventListener('click', () => {
    fileRevision++;
    dirty();
    const prepareRequest = structuredClone(SYNTHETIC_PREPARATION);
    setInput({nodes: prepareRequest.nodes, prepareRequest}, 'Caso sintético · valores supuestos');
    $('instance-file').value = '';
    message('Caso sintético preparado para una ejecución real del motor. Capacidad 10 kWh, reserva 1 kWh y consumo 1 kWh/km son valores de prueba.');
  });
  for (const field of dialog.querySelectorAll('.run-fields input')) field.addEventListener('input', dirty);
  $('run-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    try {
      const job = buildJob();
      lastRequest = job.request;
      lastPrepareRequest = job.prepareRequest;
      canonicalInstance = input.instance || null;
      // Check minimal persistence before spending compute.
      save({stale: true, status: 'ready', message: ''});
      await client.solve(lastRequest, {prepareRequest: lastPrepareRequest});
      $('export-instance').disabled = !canonicalInstance;
    } catch (error) { message(error.message, true); }
  });
  $('stop-waiting').addEventListener('click', () => client.stopWaiting());
  $('show-example').addEventListener('click', () => {
    client.invalidate();
    saveExecution(null);
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
    if (canonicalInstance) download(canonicalInstance, 'instancia-nativa.json');
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
  addEventListener('pagehide', () => client.invalidate());
  if (saved?.status === 'running') {
    saved = {...saved, status: 'stopped', message: 'La espera anterior terminó al salir de la página. El cálculo puede continuar en el servidor.', stale: true};
    saveExecution(saved);
  }
  setBusy(false);
  renderStrip();
  return {
    setData(data) {
      rawResponse = data.RAW_RESPONSE;
      if (rawResponse) {
        const result = rawResponse.result;
        const request = result.raw.input;
        // A slow run fetch must not overwrite a draft already edited on this page.
        if (!draftEdited) {
          setInput({instance: result.raw.instance, request}, 'Instancia nativa de esta ejecución');
          canonicalInstance = result.raw.instance;
          lastRequest = request;
          $('export-instance').disabled = false;
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
    },
    fail(error) {
      message(error.message, true);
      $('run-source').textContent = 'No se pudo recuperar la ejecución';
      $('run-description').textContent = error.message;
    },
  };
}
