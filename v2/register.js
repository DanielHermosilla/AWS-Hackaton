// Registro — usa el módulo compartido auth.js (backend real FastAPI).
import {
  validarEmail, requisitosContrasena, fortalezaContrasena, contrasenaValida,
  API, guardarSesion,
} from './auth.js';

const $ = (id) => document.getElementById(id);
const form = $('register-form');
const nombreEl = $('nombre');
const emailEl = $('email');
const passEl = $('password');
const confirmEl = $('confirm');
const termsEl = $('terms');
const note = $('form-note');

function setError(input, msgEl, message) {
  const hay = Boolean(message);
  input.classList.toggle('invalid', hay);
  input.setAttribute('aria-invalid', String(hay));
  if (msgEl) { msgEl.textContent = message || ''; msgEl.hidden = !hay; }
  return !hay;
}

function showNote(kind, text) {
  note.hidden = false;
  note.className = 'form-note ' + kind;
  note.textContent = text;
}

// ── Medidor de fortaleza + lista de requisitos en vivo ──
const reqsEl = $('password-reqs');
function pintarReqs() {
  const reqs = requisitosContrasena(passEl.value);
  reqsEl.innerHTML = reqs.map(r =>
    `<li class="${r.ok ? 'ok' : ''}"><span aria-hidden="true">${r.ok ? '✓' : '○'}</span>${r.texto}</li>`
  ).join('');
  const f = fortalezaContrasena(passEl.value);
  const bar = $('strength-bar');
  bar.style.width = `${(f.nivel / 4) * 100}%`;
  bar.dataset.nivel = String(f.nivel);
  $('strength-label').textContent = passEl.value ? `Fortaleza: ${f.etiqueta}` : '';
}
passEl.addEventListener('input', () => {
  pintarReqs();
  if (passEl.classList.contains('invalid')) checkPass();
  if (confirmEl.value) checkConfirm();
});
pintarReqs();

// ── Validaciones ──
function checkNombre() {
  return setError(nombreEl, $('nombre-error'), nombreEl.value.trim() ? '' : 'Escribe un nombre o equipo.');
}
function checkEmail() { return setError(emailEl, $('email-error'), validarEmail(emailEl.value)); }
function checkPass() {
  const ok = contrasenaValida(passEl.value);
  passEl.classList.toggle('invalid', !ok);
  passEl.setAttribute('aria-invalid', String(!ok));
  if (!ok) showReq();
  return ok;
}
function showReq() { reqsEl.classList.add('shake'); setTimeout(() => reqsEl.classList.remove('shake'), 400); }
function checkConfirm() {
  const msg = !confirmEl.value ? 'Repite la contraseña.'
    : confirmEl.value !== passEl.value ? 'Las contraseñas no coinciden.' : '';
  return setError(confirmEl, $('confirm-error'), msg);
}
function checkTerms() {
  const ok = termsEl.checked;
  $('terms-error').textContent = ok ? '' : 'Debes aceptar los términos.';
  $('terms-error').hidden = ok;
  return ok;
}

nombreEl.addEventListener('blur', checkNombre);
emailEl.addEventListener('blur', checkEmail);
emailEl.addEventListener('input', () => emailEl.classList.contains('invalid') && checkEmail());
confirmEl.addEventListener('blur', checkConfirm);
confirmEl.addEventListener('input', () => confirmEl.classList.contains('invalid') && checkConfirm());
termsEl.addEventListener('change', checkTerms);

$('toggle-pass').addEventListener('click', (e) => {
  const btn = e.currentTarget;
  const showing = passEl.type === 'text';
  passEl.type = confirmEl.type = showing ? 'password' : 'text';
  btn.textContent = showing ? 'Mostrar' : 'Ocultar';
  btn.setAttribute('aria-pressed', String(!showing));
});

// ── Envío ──
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const okN = checkNombre();
  const okE = checkEmail();
  const okP = contrasenaValida(passEl.value);
  if (!okP) checkPass();
  const okC = checkConfirm();
  const okT = checkTerms();
  if (!okN || !okE || !okP || !okC || !okT) {
    (!okN ? nombreEl : !okE ? emailEl : !okP ? passEl : !okC ? confirmEl : termsEl).focus();
    return;
  }

  const submit = $('submit');
  submit.disabled = true;
  const original = submit.textContent;
  submit.textContent = 'Creando cuenta…';
  note.hidden = true;

  const res = await API.registrar({
    nombre: nombreEl.value.trim(),
    email: emailEl.value.trim(),
    password: passEl.value,
  });

  if (res.ok) {
    guardarSesion(res.usuario, false);
    showNote('ok', 'Cuenta creada. Abriendo el panel…');
    location.assign(new URL('./index.html', import.meta.url).href);
  } else {
    submit.disabled = false;
    submit.textContent = original;
    showNote('err', res.error || 'No se pudo crear la cuenta.');
  }
});
