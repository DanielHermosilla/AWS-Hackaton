// Asistente de flota (eje A) — cliente del chat.
//
// UX: conversacion libre. El unico dato que se pide es el archivo de nodos, y
// se adjunta con el clip sin salir del chat. Lo demas lo infiere el asistente
// de la conversacion o usa el estandar del escenario. El backend
// (POST /assist/chat) gestiona /prepare + /solve y publica el plan; este panel
// solo transporta mensajes y abre el plan resultante.

import { readExecution, saveExecution } from './shared/solver-client.js';
import { parseInstanceFile } from './shared/solver-input.js';
import { clearEditableDraft } from './shared/location-draft.js';

const API = '/assist/chat';
const STORE = 'zmd.assist.chat.v1';
const MAX_GUARDADOS = 60;
const AVISO_LENTO_MS = 4000;

const leer = () => { try { return JSON.parse(sessionStorage.getItem(STORE)) || {}; } catch { return {}; } };
const guardar = v => { try { sessionStorage.setItem(STORE, JSON.stringify(v)); } catch { /* sin almacenamiento */ } };

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

// Espera a que exista la barra de acciones (la crea run-panel de forma diferida).
function cuandoExista(selector, ms) {
  return new Promise(resolve => {
    const ya = document.querySelector(selector);
    if (ya) return resolve(ya);
    const obs = new MutationObserver(() => {
      const n = document.querySelector(selector);
      if (n) { obs.disconnect(); resolve(n); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => { obs.disconnect(); resolve(document.querySelector(selector)); }, ms);
  });
}

async function initAssistPanel() {
  const estado = { sessionId: null, mensajes: [], abierto: false, ...leer() };
  let ocupado = false;

  // --- estructura ---
  const toggle = el('button', 'assist-toggle', 'Asistente');
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', 'assist-panel');

  const panel = el('aside', 'assist-panel');
  panel.id = 'assist-panel';
  panel.setAttribute('aria-label', 'Asistente de flota');
  panel.hidden = true;
  const head = el('header', 'assist-head');
  head.append(el('strong', null, 'Asistente de flota'));
  const cerrar = el('button', 'assist-close', '×');
  cerrar.type = 'button';
  cerrar.setAttribute('aria-label', 'Cerrar asistente');
  head.append(cerrar);
  const log = el('div', 'assist-log');
  log.setAttribute('role', 'log');
  log.setAttribute('aria-live', 'polite');
  const form = el('form', 'assist-form');
  const clip = el('button', 'assist-clip', '📎');
  clip.type = 'button';
  clip.title = 'Adjuntar archivo de nodos (CSV o JSON)';
  clip.setAttribute('aria-label', 'Adjuntar archivo de nodos');
  const archivo = el('input');
  archivo.type = 'file';
  archivo.accept = '.csv,.json';
  archivo.hidden = true;
  const entrada = el('input', 'assist-input');
  entrada.type = 'text';
  entrada.autocomplete = 'off';
  entrada.placeholder = 'Ej: corre el caso CASE con 3 autos';
  entrada.setAttribute('aria-label', 'Mensaje para el asistente');
  const enviar = el('button', 'assist-send', 'Enviar');
  enviar.type = 'submit';
  form.append(clip, archivo, entrada, enviar);
  const nota = el('p', 'assist-note', 'El motor calcula y valida cada ruta; el asistente no inventa resultados.');
  panel.append(head, log, form, nota);
  document.body.append(panel);

  // Boton en la barra de acciones (junto a "Cargar y calcular"); si no existe, flotante.
  const acciones = await cuandoExista('.run-actions', 3000);
  if (acciones) acciones.prepend(toggle);
  else { toggle.classList.add('assist-toggle-flotante'); document.body.append(toggle); }

  // --- render ---
  function burbuja(rol, texto, meta) {
    const n = el('div', `assist-msg assist-${rol}`, texto);
    if (meta) n.append(el('span', 'assist-meta', meta));
    log.append(n);
    log.scrollTop = log.scrollHeight;
    return n;
  }
  function decir(rol, texto, meta) {
    estado.mensajes.push({ rol, texto, meta });
    estado.mensajes = estado.mensajes.slice(-MAX_GUARDADOS);
    guardar(estado);
    return burbuja(rol, texto, meta);
  }
  function chipAdjuntar() {
    const wrap = el('div', 'assist-msg assist-bot assist-chip-wrap');
    const adjuntar = el('button', 'assist-chip', '📎 Adjuntar archivo de nodos');
    adjuntar.type = 'button';
    adjuntar.addEventListener('click', () => archivo.click());
    const caso = el('button', 'assist-chip', 'Usar el caso CASE');
    caso.type = 'button';
    caso.addEventListener('click', () => {
      const texto = 'Corre el caso CASE';
      decir('user', texto);
      turno({ message: texto });
    });
    wrap.append(adjuntar, caso);
    log.append(wrap);
    log.scrollTop = log.scrollHeight;
  }

  function ubicar() {
    // Debajo de la barra superior para no tapar controles del mapa.
    const ref = document.querySelector('.run-strip') || document.getElementById('app-shell');
    const top = ref ? Math.max(ref.getBoundingClientRect().bottom + 8, 8) : 80;
    panel.style.top = `${Math.round(top)}px`;
  }
  function abrir(valor) {
    estado.abierto = valor;
    guardar(estado);
    panel.hidden = !valor;
    toggle.setAttribute('aria-expanded', String(valor));
    if (!valor) { toggle.focus(); return; }
    ubicar();
    if (!estado.mensajes.length) saludar();
    entrada.focus();
  }
  toggle.addEventListener('click', () => abrir(panel.hidden));
  cerrar.addEventListener('click', () => abrir(false));
  addEventListener('resize', () => { if (!panel.hidden) ubicar(); });
  panel.addEventListener('keydown', ev => { if (ev.key === 'Escape') abrir(false); });

  function saludar() {
    const hayPlan = Boolean(readExecution()?.runId);
    decir('bot', hayPlan
      ? '¡Hola! Ya hay un plan en pantalla: puedo recalcularlo («que sean 3 autos») o explicártelo.'
      : '¡Hola! Soy tu asistente de flota. Escribe «corre el caso CASE» o adjunta tu archivo con el clip y armo el plan.');
  }

  // --- conversacion ---
  async function turno(cuerpo) {
    if (ocupado) return;
    ocupado = true;
    enviar.disabled = clip.disabled = true;
    const pensando = burbuja('bot', '…');
    const lento = setTimeout(() => { pensando.textContent = 'Trabajando… si estoy calculando puede tardar unos segundos.'; }, AVISO_LENTO_MS);
    try {
      const pedido = { session_id: estado.sessionId, ...cuerpo };
      const execution = readExecution();
      const runId = execution?.runId;
      if (runId && !cuerpo.fuente) pedido.run_id = runId;
      const res = await fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pedido) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error?.message || `El servicio respondió ${res.status}.`);
      estado.sessionId = data.session_id;
      pensando.remove();
      if (data.resolvio && data.run_id && readExecution()?.revision !== execution?.revision) {
        decir('bot', 'El cálculo terminó para la entrada anterior. Conservamos tus cambios actuales sin abrir ese resultado.');
        return;
      }
      decir('bot', data.respuesta || 'Listo.', data.modo === 'local' ? 'respuesta sin IA' : null);
      if (data.necesita_archivo) chipAdjuntar();
      if (data.resolvio && data.run_id) abrirPlan(data.run_id);
    } catch (err) {
      pensando.remove();
      decir('bot', `No pude completar el pedido: ${err.message}`);
    } finally {
      clearTimeout(lento);
      ocupado = false;
      enviar.disabled = clip.disabled = false;
      entrada.focus();
    }
  }

  function abrirPlan(runId) {
    const revision = crypto.randomUUID();
    if (!saveExecution({mode: 'model', runId, stale: false, status: 'complete', message: '',
      draftId: null, draftUnavailable: false, revision})) {
      throw new Error('El navegador no permite guardar la ejecución. Conservamos tu entrada actual.');
    }
    clearEditableDraft();
    estado.abierto = true;
    guardar(estado);
    setTimeout(() => {
      if (readExecution()?.revision !== revision) return;
      if (document.body.dataset.page === 'plan') location.reload();
      else location.href = 'plan.html';
    }, 600);
  }

  form.addEventListener('submit', ev => {
    ev.preventDefault();
    const texto = entrada.value.trim();
    if (!texto || ocupado) return;
    entrada.value = '';
    decir('user', texto);
    turno({ message: texto });
  });

  clip.addEventListener('click', () => archivo.click());
  archivo.addEventListener('change', () => {
    const f = archivo.files?.[0];
    archivo.value = '';
    if (!f) return;
    const lector = new FileReader();
    lector.onload = () => {
      let fuente;
      try {
        const input = parseInstanceFile(String(lector.result), f.name);
        fuente = input.nodes ? { nodes: input.nodes, ...(input.prepareRequest ? { prepare: input.prepareRequest } : {}) }
          : { instance: input.instance };
      } catch (err) {
        decir('bot', `No pude leer ${f.name}: ${err.message}`);
        return;
      }
      decir('user', `📎 ${f.name}`);
      turno({ fuente, archivo: f.name });
    };
    lector.onerror = () => decir('bot', `No pude leer ${f.name}.`);
    lector.readAsText(f);
  });

  // Restaurar conversacion tras recargar (p. ej. despues de calcular).
  estado.mensajes.forEach(m => burbuja(m.rol, m.texto, m.meta));
  if (estado.abierto) abrir(true);
}

initAssistPanel();
