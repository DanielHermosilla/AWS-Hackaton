// Acceso — usa el módulo compartido auth.js (backend real FastAPI).
import { validarEmail, API, guardarSesion, destinoTrasLogin } from './auth.js';

const $ = (id) => document.getElementById(id);
const form = $('login-form');
const emailEl = $('email');
const passEl = $('password');
const note = $('form-note');

function setError(input, msgEl, message) {
  const hay = Boolean(message);
  input.classList.toggle('invalid', hay);
  input.setAttribute('aria-invalid', String(hay));
  msgEl.textContent = message || '';
  msgEl.hidden = !hay;
  return !hay;
}

function checkEmail() { return setError(emailEl, $('email-error'), validarEmail(emailEl.value)); }
function checkPass() {
  return setError(passEl, $('password-error'), passEl.value ? '' : 'Escribe tu contraseña.');
}

function showNote(kind, text) {
  note.hidden = false;
  note.className = 'form-note ' + kind;
  note.textContent = text;
}

$('toggle-pass').addEventListener('click', (e) => {
  const btn = e.currentTarget;
  const showing = passEl.type === 'text';
  passEl.type = showing ? 'password' : 'text';
  btn.textContent = showing ? 'Mostrar' : 'Ocultar';
  btn.setAttribute('aria-pressed', String(!showing));
  passEl.focus({ preventScroll: true });
});

emailEl.addEventListener('blur', checkEmail);
passEl.addEventListener('blur', checkPass);
emailEl.addEventListener('input', () => emailEl.classList.contains('invalid') && checkEmail());
passEl.addEventListener('input', () => passEl.classList.contains('invalid') && checkPass());

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const okE = checkEmail();
  const okP = checkPass();
  if (!okE || !okP) { (!okE ? emailEl : passEl).focus(); return; }

  const submit = $('submit');
  submit.disabled = true;
  const original = submit.textContent;
  submit.textContent = 'Entrando…';
  note.hidden = true;

  const res = await API.iniciarSesion({
    email: emailEl.value.trim(),
    password: passEl.value,
  });

  if (res.ok) {
    guardarSesion(res.usuario, $('remember').checked);
    showNote('ok', 'Acceso válido. Abriendo el panel…');
    location.assign(new URL('./' + destinoTrasLogin(), import.meta.url).href);
  } else {
    submit.disabled = false;
    submit.textContent = original;
    showNote('err', res.error || 'No se pudo iniciar sesión.');
    passEl.focus();
  }
});

$('forgot').addEventListener('click', (e) => {
  e.preventDefault();
  showNote('ok', 'La recuperación de contraseña se habilita con el correo del servidor.');
});
