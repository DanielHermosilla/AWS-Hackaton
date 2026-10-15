/* Acceso — lógica de cliente del prototipo.
 *
 * IMPORTANTE: esto es solo la capa de interfaz y validación de formulario.
 * NO autentica de verdad: no hay backend de usuarios en este repositorio.
 * La autenticación real (verificación de credenciales, emisión de sesión/token)
 * se conectará con la otra web mediante `enviarCredenciales()`, el único punto
 * de integración. Hoy ese punto está simulado.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const form = $('login-form');
const emailEl = $('email');
const passEl = $('password');
const note = $('form-note');

/* ---- utilidades de validación ---- */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function setError(input, msgEl, message) {
  const hasError = Boolean(message);
  input.classList.toggle('invalid', hasError);
  input.setAttribute('aria-invalid', String(hasError));
  msgEl.textContent = message || '';
  msgEl.hidden = !hasError;
  return !hasError;
}

function validateEmail() {
  const value = emailEl.value.trim();
  if (!value) return setError(emailEl, $('email-error'), 'Escribe tu correo.');
  if (!EMAIL_RE.test(value)) return setError(emailEl, $('email-error'), 'Ese correo no parece válido.');
  return setError(emailEl, $('email-error'), '');
}

function validatePassword() {
  const value = passEl.value;
  if (!value) return setError(passEl, $('password-error'), 'Escribe tu contraseña.');
  if (value.length < 8) return setError(passEl, $('password-error'), 'Debe tener al menos 8 caracteres.');
  return setError(passEl, $('password-error'), '');
}

function showNote(kind, text) {
  note.hidden = false;
  note.className = 'form-note ' + kind;
  note.textContent = text;
}

/* ---- mostrar / ocultar contraseña ---- */
$('toggle-pass').addEventListener('click', (e) => {
  const btn = e.currentTarget;
  const showing = passEl.type === 'text';
  passEl.type = showing ? 'password' : 'text';
  btn.textContent = showing ? 'Mostrar' : 'Ocultar';
  btn.setAttribute('aria-pressed', String(!showing));
  passEl.focus({ preventScroll: true });
});

/* Revalidar al salir del campo, limpiar error al escribir. */
emailEl.addEventListener('blur', validateEmail);
passEl.addEventListener('blur', validatePassword);
emailEl.addEventListener('input', () => emailEl.classList.contains('invalid') && validateEmail());
passEl.addEventListener('input', () => passEl.classList.contains('invalid') && validatePassword());

/* ---- punto de integración (simulado) ----
 * Reemplazar el cuerpo por una llamada real (fetch POST a /api/login de la otra
 * web) que devuelva { ok, token } o { ok:false, error }. La UI ya está lista:
 * solo cambia esta función.
 */
async function enviarCredenciales({ email, password, remember }) {
  await new Promise((r) => setTimeout(r, 650)); // latencia simulada
  // Demo: cualquier correo válido + contraseña >= 8 "entra".
  return { ok: true, token: 'demo-session', usuario: email };
}

/* ---- envío del formulario ---- */
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const okEmail = validateEmail();
  const okPass = validatePassword();
  if (!okEmail || !okPass) {
    (!okEmail ? emailEl : passEl).focus();
    return;
  }

  const submit = $('submit');
  submit.disabled = true;
  const original = submit.textContent;
  submit.textContent = 'Entrando…';
  note.hidden = true;

  try {
    const res = await enviarCredenciales({
      email: emailEl.value.trim(),
      password: passEl.value,
      remember: $('remember').checked,
    });
    if (res.ok) {
      showNote('ok', 'Acceso válido en el prototipo. Aquí la otra web continuará al panel.');
    } else {
      showNote('err', res.error || 'No se pudo iniciar sesión.');
    }
  } catch (err) {
    showNote('err', 'Error de conexión con el servicio de acceso.');
  } finally {
    submit.disabled = false;
    submit.textContent = original;
  }
});

/* ---- enlaces secundarios (demo) ---- */
$('sso').addEventListener('click', () => showNote('ok', 'El acceso corporativo (SSO) se conectará con la otra web.'));
$('forgot').addEventListener('click', (e) => { e.preventDefault(); showNote('ok', 'La recuperación de contraseña vive en el servicio de acceso.'); });
$('to-register').addEventListener('click', (e) => { e.preventDefault(); showNote('ok', 'La solicitud de acceso para equipos se gestiona aparte.'); });
