// Módulo de autenticación del cliente (compartido por login y registro).
//
// ─────────────────────────────────────────────────────────────────────────────
// AVISO DE SEGURIDAD (honesto):
// Esta webapp es estática (sin backend). TODO lo que ocurre aquí es validación
// de interfaz y una SESIÓN DE DEMOSTRACIÓN guardada en el navegador. Esto NO es
// seguridad real: cualquiera con las DevTools puede ver o editar estos datos.
// La seguridad verdadera (hash en servidor, tokens, rate-limiting, correo de
// verificación, almacenamiento cifrado) vive en el backend de la otra web.
//
// Puntos de integración con el backend real: `API.iniciarSesion` y
// `API.registrar`. Hoy están SIMULADOS. Para conectar el backend real, cambia
// `API.base` y el cuerpo de esas dos funciones por llamadas `fetch` a tu API.
// ─────────────────────────────────────────────────────────────────────────────

const SESSION_KEY = 'zmd.webapp.session.v1';

/* ───────────────────────── Validación ───────────────────────── */

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validarEmail(valor) {
  const v = (valor || '').trim();
  if (!v) return 'Escribe tu correo.';
  if (!EMAIL_RE.test(v)) return 'Ese correo no parece válido.';
  if (v.length > 254) return 'El correo es demasiado largo.';
  return '';
}

// Reglas de contraseña fuerte. Devuelve lista de requisitos y si cada uno se cumple.
export function requisitosContrasena(valor) {
  const v = valor || '';
  return [
    { id: 'len', texto: 'Al menos 10 caracteres', ok: v.length >= 10 },
    { id: 'may', texto: 'Una letra mayúscula', ok: /[A-Z]/.test(v) },
    { id: 'min', texto: 'Una letra minúscula', ok: /[a-z]/.test(v) },
    { id: 'num', texto: 'Un número', ok: /\d/.test(v) },
    { id: 'sim', texto: 'Un símbolo (!@#$…)', ok: /[^A-Za-z0-9]/.test(v) },
  ];
}

// Fortaleza 0..4 y etiqueta, para el medidor en vivo.
export function fortalezaContrasena(valor) {
  const reqs = requisitosContrasena(valor);
  const cumplidos = reqs.filter(r => r.ok).length;
  // penaliza patrones obvios
  const v = valor || '';
  const debil = /^(.)\1+$/.test(v) || /1234|abcd|qwerty|password|contrasena/i.test(v);
  let nivel = Math.max(0, cumplidos - 1); // 0..4
  if (debil) nivel = Math.min(nivel, 1);
  const etiquetas = ['Muy débil', 'Débil', 'Aceptable', 'Fuerte', 'Muy fuerte'];
  return { nivel, etiqueta: etiquetas[nivel], cumplidos, total: reqs.length };
}

export function contrasenaValida(valor) {
  return requisitosContrasena(valor).every(r => r.ok);
}

/* ───────────────────────── Sesión (demo) ───────────────────────── */

export function sesionActual() {
  for (const store of [sessionStorage, localStorage]) {
    try {
      const raw = store.getItem(SESSION_KEY);
      if (raw) return JSON.parse(raw);
    } catch { /* almacenamiento no disponible */ }
  }
  return null;
}

export function haySesion() {
  return Boolean(sesionActual());
}

export function guardarSesion(usuario, recordar) {
  // Solo para la interfaz (mostrar el usuario). La sesión segura es la cookie
  // httpOnly del servidor; esto no otorga acceso por sí mismo.
  const payload = JSON.stringify({ usuario, desde: Date.now() });
  try {
    (recordar ? localStorage : sessionStorage).setItem(SESSION_KEY, payload);
    return true;
  } catch {
    return false;
  }
}

export function cerrarSesion() {
  for (const store of [sessionStorage, localStorage]) {
    try { store.removeItem(SESSION_KEY); } catch { /* ignore */ }
  }
}

// Verifica la sesión REAL contra el servidor (/auth/me) y redirige si no hay.
// El backend ya protege las páginas, pero esto evita parpadeos y sincroniza la UI.
export async function exigirSesion(loginUrl = './login.html') {
  const r = await API.yo();
  if (!r.ok) {
    cerrarSesion();
    const destino = new URL(loginUrl, import.meta.url);
    destino.searchParams.set('next', location.pathname.split('/').pop() || 'index.html');
    location.replace(destino.href);
    return false;
  }
  guardarSesion(r.usuario, false);
  return true;
}

/* ─────────────── "Almacén" de cuentas: eliminado ───────────────
   La autenticación real la maneja el backend (FastAPI + SQLite + bcrypt).
   El cliente solo recuerda, para la interfaz, el correo de la sesión actual;
   la sesión segura vive en una cookie httpOnly puesta por el servidor. */

/* ───────────────────── Puntos de integración (backend real) ─────────────────────
   Conectados al backend FastAPI que sirve esta misma webapp (mismo origen).
   Las respuestas son { ok:true, usuario } o { ok:false, error }. La sesión se
   mantiene con una cookie httpOnly puesta por el servidor (no accesible por JS). */

export const API = {
  base: '', // mismo origen (el backend sirve la webapp). Cambiar si la API vive en otro host.

  async _post(ruta, cuerpo) {
    try {
      const r = await fetch(`${this.base}${ruta}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(cuerpo),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) return { ok: false, error: data.error || 'No se pudo completar la operación.' };
      return data;
    } catch {
      return { ok: false, error: 'No hay conexión con el servidor de acceso.' };
    }
  },

  async iniciarSesion({ email, password }) {
    return this._post('/auth/login', { email, password });
  },

  async registrar({ nombre, email, password }) {
    return this._post('/auth/register', { nombre, email, password });
  },

  async cerrarSesionServidor() {
    try { await fetch(`${this.base}/auth/logout`, { method: 'POST', credentials: 'same-origin' }); }
    catch { /* la cookie expira igual */ }
  },

  async yo() {
    try {
      const r = await fetch(`${this.base}/auth/me`, { credentials: 'same-origin' });
      if (!r.ok) return { ok: false };
      return await r.json();
    } catch {
      return { ok: false };
    }
  },
};

/* ───────────────────── Utilidad: destino tras login ───────────────────── */

export function destinoTrasLogin() {
  const next = new URLSearchParams(location.search).get('next');
  // Lista blanca: solo páginas conocidas de la app (evita redirección abierta).
  const permitidas = new Set(['index.html', 'plan.html']);
  return permitidas.has(next) ? next : 'index.html';
}
