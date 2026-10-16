import {createHistoryClient, validateHistoryFile} from './history-client.js';
import {historyDetailGroups} from './history-details.js';

const text = value => typeof value === 'string' ? value.slice(0, 1200) : '';
const number = value => Number.isFinite(value) ? new Intl.NumberFormat('es-CL', {maximumFractionDigits: 2}).format(value) : null;

// An independent input: telemetry never becomes a list of delivery locations.
export function createHistoryPanel({host, onChange = () => {}, client = createHistoryClient()} = {}) {
  host.innerHTML = `<div class="run-history-heading"><div><h4>Consumo con históricos</h4><span>Opcional</span></div><button id="history-aws" type="button">Conectar con AWS</button></div>
    <p class="run-help">Adjunta mediciones eléctricas eVED u otro histórico: CSV hasta 4 GiB, JSON hasta 256 MiB. Donde haya evidencia, estimaremos el consumo por calle; en los demás tramos se usará tu consumo supuesto. Sin instancia, se cargarán las ubicaciones de la hackatón en Ann Arbor.</p>
    <p id="history-native-note" class="run-help" hidden>Este JSON ya incluye la energía de sus tramos. Para usar históricos, carga ubicaciones en CSV o crea una instancia editable.</p>
    <input id="history-file" class="run-visually-hidden" type="file" accept=".csv,.json" tabindex="-1" aria-label="Archivo de datos históricos">
    <div class="run-history-actions"><button id="choose-history" type="button">Adjuntar histórico</button><button id="history-remove" type="button" hidden>Quitar</button><button id="history-analyze" type="button" hidden>Interpretar con IA</button><button id="history-cancel" type="button" hidden>Cancelar carga</button></div>
    <div id="history-upload" hidden><progress id="history-progress" max="1" aria-label="Carga del histórico"></progress></div>
    <p id="history-state" class="run-history-state" role="status" aria-live="polite">Sin histórico. Se usará el consumo supuesto.</p>
    <div id="history-profile" hidden><strong id="history-filename"></strong><dl id="history-stats"></dl><p id="history-coverage" class="run-help" hidden></p><div id="history-warnings"></div><details id="history-assumptions" hidden><summary>Qué aportan estos datos</summary><div id="history-detail-groups"></div><p class="run-help">Las observaciones y sugerencias de la IA no cambian automáticamente la capacidad, la reserva ni la flota.</p></details></div>`;
  const dialog = document.createElement('dialog');
  dialog.id = 'bedrock-dialog';
  dialog.className = 'app-dialog run-dialog bedrock-dialog';
  dialog.setAttribute('aria-labelledby', 'bedrock-heading');
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="bedrock-heading">Conectar con AWS</h2><button id="bedrock-close" type="button" aria-label="Cerrar conexión con AWS">×</button></div>
    <p>Bedrock ayuda a interpretar otros formatos de históricos y también puede orientar la búsqueda del motor.</p>
    <form id="bedrock-form" novalidate autocomplete="off"><div class="run-fields">
      <label class="bedrock-wide">Conexión<select id="bedrock-mode"><option value="configured">Configuración del servidor</option><option value="temporary">Credenciales temporales</option></select></label>
      <label>Región AWS<input id="bedrock-region" type="text" placeholder="us-east-1" autocomplete="off" spellcheck="false"></label>
      <label>Modelo de Bedrock<input id="bedrock-model" type="text" placeholder="Identificador o perfil de inferencia" autocomplete="off" spellcheck="false"></label>
      <label id="bedrock-profile-field" class="bedrock-wide">Perfil local · opcional<input id="bedrock-profile" type="text" placeholder="Usar el perfil del servidor" autocomplete="off" spellcheck="false"></label>
      <label class="bedrock-secret bedrock-wide" hidden>Access key ID<input id="bedrock-access" type="password" autocomplete="off" spellcheck="false"></label>
      <label class="bedrock-secret bedrock-wide" hidden>Secret access key<input id="bedrock-secret" type="password" autocomplete="off" spellcheck="false"></label>
      <label class="bedrock-secret bedrock-wide" hidden>Session token<input id="bedrock-token" type="password" autocomplete="off" spellcheck="false"></label>
    </div><p class="run-help">Las credenciales quedan solo en la memoria del servidor local durante la sesión. No se guardan en archivos ni en este navegador. Para interpretar históricos se solicita razonamiento alto en un modelo compatible.</p>
    <p id="bedrock-message" class="run-message" role="status" aria-live="polite"></p>
    <div class="dialog-actions"><button id="bedrock-disconnect" type="button" hidden>Desconectar</button><button id="bedrock-connect" type="submit" class="primary">Conectar y comprobar</button></div></form>`;
  document.body.append(dialog);
  const $ = id => document.getElementById(id);
  let profile = null, session = null, native = false, pending = false, runBusy = false, generation = 0, controller = null, restoringId = null;
  let connectionPending = false;
  let coverageReport = null;
  let stateMessage = 'Sin histórico. Se usará el consumo supuesto.';
  const setState = message => { stateMessage = message; $('history-state').textContent = message; };
  const clearSecrets = () => { for (const id of ['bedrock-access', 'bedrock-secret', 'bedrock-token']) $(id).value = ''; };
  function changed(invalidate = true, invalidatePendingRun = invalidate) {
    onChange(profile ? {profile_id: profile.profile_id, filename: text(profile.filename), status: profile.status} : null,
      {invalidate, invalidatePendingRun});
  }
  function renderSession() {
    $('history-aws').textContent = session?.connected ? 'AWS conectado' : 'Conectar con AWS';
    $('bedrock-disconnect').hidden = !session?.connected;
  }
  function render() {
    $('history-native-note').hidden = !native;
    $('choose-history').disabled = native || pending || runBusy;
    $('history-remove').hidden = !profile;
    $('history-remove').disabled = pending || runBusy;
    $('history-analyze').hidden = !profile || profile.status === 'error' || ['reviewed', 'applied'].includes(profile.ai_analysis?.status);
    $('history-analyze').textContent = profile?.status === 'ready' ? 'Ampliar análisis con IA' : 'Interpretar con IA';
    $('history-analyze').disabled = native || pending || runBusy;
    $('history-cancel').hidden = !controller;
    $('history-profile').hidden = !profile;
    $('history-state').textContent = native ? 'Se conservará el consumo incluido en el JSON.' : stateMessage;
    if (!profile) return;
    $('history-filename').textContent = text(profile.filename) || 'Histórico adjunto';
    $('history-stats').replaceChildren();
    for (const [key, label, unit] of [['row_count', 'Mediciones', ''], ['trip_count', 'Viajes', ''], ['vehicle_count', 'Vehículos', ''], ['distance_km', 'Distancia observada', ' km'], ['energy_kwh', 'Energía neta observada', ' kWh'], ['excluded_interval_count', 'Intervalos descartados', '']]) {
      const value = number(profile.summary?.[key]);
      if (value === null) continue;
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = value + unit;
      $('history-stats').append(dt, dd);
    }
    $('history-warnings').replaceChildren();
    const warnings = Array.isArray(profile.warnings) ? profile.warnings : [];
    for (const warning of warnings.slice(0, 8)) {
      const content = text(warning) || text(warning?.message);
      if (!content) continue;
      const p = document.createElement('p'); p.className = 'run-help'; p.textContent = content;
      $('history-warnings').append(p);
    }
    renderDetails();
  }
  function renderDetails() {
    const container = $('history-detail-groups');
    container.replaceChildren();
    for (const group of historyDetailGroups(profile, coverageReport)) {
      const heading = document.createElement('h5'), list = document.createElement('ul');
      heading.textContent = group.title;
      for (const item of group.items) {
        const li = document.createElement('li');
        li.textContent = item.text;
        if (item.note) { const small = document.createElement('small'); small.textContent = item.note; li.append(small); }
        list.append(li);
      }
      container.append(heading, list);
    }
    $('history-assumptions').hidden = !container.children.length;
  }
  function profileMessage(value) {
    if (value.status === 'ready') return 'Histórico preparado. Comprobaremos su cobertura por calle al calcular.';
    if (value.status === 'error') return 'Este archivo no permite calibrar consumo eléctrico. Revisa el motivo indicado y adjunta un histórico EV válido.';
    return text(value.ai_analysis?.message) || 'Este formato necesita interpretación. Conecta con AWS y elige «Interpretar con IA». Puedes calcular con el consumo supuesto mientras tanto.';
  }
  function accept(value, notify = true) {
    profile = value;
    coverageReport = null;
    $('history-coverage').hidden = true;
    setState(profileMessage(value));
    render();
    if (notify) changed();
  }
  async function restore(profileId) {
    if (!profileId) {
      generation++; controller?.abort(); controller = null; restoringId = null; pending = false; profile = null;
      $('history-upload').hidden = true;
      setState('Sin histórico. Se usará el consumo supuesto.'); render();
      return;
    }
    if (profile?.profile_id === profileId || restoringId === profileId) return;
    const current = ++generation;
    controller?.abort(); controller = null; $('history-upload').hidden = true;
    restoringId = profileId;
    pending = true; setState('Recuperando el histórico…'); render();
    try {
      const value = await client.get(profileId);
      if (current === generation) { accept(value, false); changed(false); }
    } catch (error) {
      if (current !== generation) return;
      profile = null;
      setState(error.message);
      changed();
    } finally { if (current === generation) { restoringId = null; pending = false; render(); } }
  }
  $('choose-history').addEventListener('click', () => $('history-file').click());
  $('history-file').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try { validateHistoryFile(file); } catch (error) { setState(error.message); return; }
    const current = ++generation;
    restoringId = null;
    controller?.abort(); controller = new AbortController();
    profile = null; pending = true; changed(); render();
    $('history-upload').hidden = false;
    $('history-progress').value = 0;
    setState('Subiendo histórico…');
    try {
      const value = await client.upload(file, {signal: controller.signal, onProgress(progress) {
        if (current !== generation) return;
        $('history-progress').value = progress;
        setState(progress < 1 ? `Subiendo histórico · ${Math.round(progress * 100)} %` : 'Archivo recibido. Revisando viajes y mediciones…');
      }});
      if (current === generation) accept(value);
    } catch (error) {
      if (current === generation) setState(error.name === 'AbortError' ? 'Carga cancelada. Se usará el consumo supuesto.' : error.message);
    } finally {
      if (current === generation) { controller = null; pending = false; $('history-upload').hidden = true; render(); }
    }
  });
  $('history-cancel').addEventListener('click', () => controller?.abort());
  $('history-remove').addEventListener('click', async () => {
    const old = profile;
    generation++; restoringId = null; profile = null;
    setState('Histórico retirado. Se usará el consumo supuesto.'); render(); changed();
    if (old) try { await client.remove(old.profile_id); } catch (error) { if (!profile) setState(error.message); }
  });
  $('history-analyze').addEventListener('click', async () => {
    if (!profile || pending) return;
    pending = true; render();
    await refreshSession();
    if (!session?.connected) { pending = false; render(); openConnection(); return; }
    const current = ++generation;
    pending = true; setState('Interpretando el archivo con IA y razonamiento alto…'); render();
    try {
      const value = await client.analyze(profile.profile_id);
      if (current === generation) accept(value);
    } catch (error) { if (current === generation) setState(error.message); }
    finally { if (current === generation) { pending = false; render(); } }
  });
  function renderMode() {
    const temporary = $('bedrock-mode').value === 'temporary';
    $('bedrock-profile-field').hidden = temporary;
    for (const field of dialog.querySelectorAll('.bedrock-secret')) field.hidden = !temporary;
    clearSecrets();
  }
  async function refreshSession() {
    try { session = await client.session(); renderSession(); }
    catch { session = null; renderSession(); }
  }
  function openConnection() {
    $('bedrock-region').value = text(session?.region);
    $('bedrock-model').value = text(session?.model_id);
    $('bedrock-profile').value = text(session?.profile);
    $('bedrock-message').textContent = text(session?.message) || 'Usa una configuración existente o las credenciales temporales de tu cuenta AWS.';
    renderMode();
    dialog.showModal();
    $('bedrock-mode').focus();
  }
  $('history-aws').addEventListener('click', openConnection);
  $('bedrock-mode').addEventListener('change', renderMode);
  $('bedrock-close').addEventListener('click', () => { clearSecrets(); dialog.close(); });
  dialog.addEventListener('cancel', clearSecrets);
  dialog.addEventListener('close', () => { clearSecrets(); $('history-aws').focus(); });
  $('bedrock-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (connectionPending) return;
    const configuration = {mode: $('bedrock-mode').value};
    for (const [name, id] of [['region', 'bedrock-region'], ['model_id', 'bedrock-model']]) {
      if ($(id).value.trim()) configuration[name] = $(id).value.trim();
    }
    if (configuration.mode === 'temporary') {
      for (const [name, id] of [['access_key_id', 'bedrock-access'], ['secret_access_key', 'bedrock-secret'], ['session_token', 'bedrock-token']]) configuration[name] = $(id).value.trim();
      if (!configuration.access_key_id || !configuration.secret_access_key || !configuration.session_token) {
        $('bedrock-message').textContent = 'Completa los tres campos de las credenciales temporales, incluido el Session token.';
        return;
      }
    } else if ($('bedrock-profile').value.trim()) configuration.profile = $('bedrock-profile').value.trim();
    connectionPending = true;
    $('bedrock-connect').disabled = true;
    $('bedrock-disconnect').disabled = true;
    $('bedrock-message').textContent = 'Comprobando acceso a Bedrock…';
    const request = client.connect(configuration);
    clearSecrets();
    try {
      session = await request;
      renderSession();
      $('bedrock-message').textContent = text(session?.message) || (session?.connected ? 'AWS conectado. Ya puedes interpretar el histórico.' : 'No se confirmó la conexión. Revisa la configuración e inténtalo de nuevo.');
    } catch (error) { $('bedrock-message').textContent = error.message; }
    finally { connectionPending = false; $('bedrock-connect').disabled = false; $('bedrock-disconnect').disabled = false; clearSecrets(); }
  });
  $('bedrock-disconnect').addEventListener('click', async () => {
    if (connectionPending) return;
    connectionPending = true;
    $('bedrock-connect').disabled = true; $('bedrock-disconnect').disabled = true;
    clearSecrets();
    try {
      session = await client.disconnect(); renderSession();
      $('bedrock-message').textContent = 'AWS desconectado. Puedes seguir calculando con los datos y supuestos disponibles.';
    } catch (error) { $('bedrock-message').textContent = error.message; }
    finally { connectionPending = false; $('bedrock-connect').disabled = false; $('bedrock-disconnect').disabled = false; }
  });
  refreshSession();
  return {
    restore,
    useProfile(value) {
      generation++; controller?.abort(); controller = null; restoringId = null; pending = false;
      $('history-upload').hidden = true;
      // The owning scenario request already checked this response. Keep its
      // submit while retaining the usual result and coverage invalidation.
      accept(value, false);
      changed(true, false);
    },
    get profileId() { return !native && !pending && profile?.status === 'ready' ? profile.profile_id : null; },
    get isPending() { return pending; },
    setNative(value) { native = value; render(); },
    setRunBusy(value) { runBusy = value; render(); },
    invalidateCoverage() {
      coverageReport = null;
      $('history-coverage').hidden = true;
      if (profile?.status === 'ready') { setState(profileMessage(profile)); render(); }
    },
    showCoverage(coverage) {
      if (!coverage || !profile) return;
      coverageReport = coverage;
      renderDetails();
      const observed = coverage.summary?.calibrated_arc_count;
      const total = coverage.summary?.road_arc_count;
      const ratio = coverage.summary?.arc_coverage_fraction;
      let description = Number.isFinite(observed) && Number.isFinite(total) ? `${number(observed)} de ${number(total)} tramos con evidencia histórica.`
        : Number.isFinite(ratio) ? `${number(ratio * 100)} % de los tramos con evidencia histórica.` : text(coverage.message);
      if (!description) return;
      $('history-coverage').textContent = `${description} Los demás usan el consumo supuesto.`;
      $('history-coverage').hidden = false;
    },
    close() { controller?.abort(); clearSecrets(); if (dialog.open) dialog.close(); },
  };
}
