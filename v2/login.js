// Acceso a la webapp — capa de interfaz y validación de formulario.
//
// IMPORTANTE: no autentica de verdad. La webapp no tiene backend de usuarios
// (ver webapp/README.md). La verificación real se conectará reemplazando el
// cuerpo de `enviarCredenciales()` por una llamada al servicio de la otra web.
// Al "entrar", marca una sesión de demostración y abre la webapp (index.html).

const SESSION_KEY = 'zmd.webapp.session.v1';

const $ = (id) => document.getElementById(id);
const form = $('login-form');
const emailEl = $('email');
const passEl = $('password');
const note = $('form-note');

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
  const v = emailEl.value.trim();
  if (!v) return setError(emailEl, $('email-error'), 'Escribe tu correo.');
  if (!EMAIL_RE.test(v)) return setError(emailEl, $('email-error'), 'Ese correo no parece válido.');
  return setError(emailEl, $('email-error'), '');
}

function validatePassword() {
  const v = passEl.value;
  if (!v) return setError(passEl, $('password-error'), 'Escribe tu contraseña.');
  if (v.length < 8) return setError(passEl, $('password-error'), 'Debe tener al menos 8 caracteres.');
  return setError(passEl, $('password-error'), '');
}

function showNote(kind, text) {
  note.hidden = false;
  note.className = 'form-note ' + kind;
  note.textContent = text;
}

// Mostrar / ocultar contraseña
$('toggle-pass').addEventListener('click', (e) => {
  const btn = e.currentTarget;
  const showing = passEl.type === 'text';
  passEl.type = showing ? 'password' : 'text';
  btn.textContent = showing ? 'Mostrar' : 'Ocultar';
  btn.setAttribute('aria-pressed', String(!showing));
  passEl.focus({ preventScroll: true });
});

emailEl.addEventListener('blur', validateEmail);
passEl.addEventListener('blur', validatePassword);
emailEl.addEventListener('input', () => emailEl.classList.contains('invalid') && validateEmail());
passEl.addEventListener('input', () => passEl.classList.contains('invalid') && validatePassword());

// ---- punto de integración (simulado) ----
// Reemplazar por fetch POST al endpoint real; devolver { ok, token } o { ok:false, error }.
async function enviarCredenciales({ email, password, remember }) {
  await new Promise((r) => setTimeout(r, 600));
  return { ok: true, token: 'demo-session', usuario: email };
}

function marcarSesion(usuario, remember) {
  const payload = JSON.stringify({ usuario, desde: Date.now(), demo: true });
  try {
    (remember ? localStorage : sessionStorage).setItem(SESSION_KEY, payload);
  } catch {
    // El acceso de demostración continúa aunque el almacenamiento no esté disponible.
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const okEmail = validateEmail();
  const okPass = validatePassword();
  if (!okEmail || !okPass) { (!okEmail ? emailEl : passEl).focus(); return; }

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
      marcarSesion(res.usuario, $('remember').checked);
      showNote('ok', 'Acceso válido. Abriendo el panel…');
      location.assign(new URL('./index.html', import.meta.url).href);
    } else {
      submit.disabled = false;
      submit.textContent = original;
      showNote('err', res.error || 'No se pudo iniciar sesión.');
    }
  } catch (err) {
    submit.disabled = false;
    submit.textContent = original;
    showNote('err', 'Error de conexión con el servicio de acceso.');
  }
});

$('sso').addEventListener('click', () => showNote('ok', 'El acceso corporativo (SSO) se conectará con el servicio real.'));
$('forgot').addEventListener('click', (e) => { e.preventDefault(); showNote('ok', 'La recuperación de contraseña vive en el servicio de acceso.'); });
