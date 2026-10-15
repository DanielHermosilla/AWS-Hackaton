import { initShell } from './app-shell.js?v=home-v3';
import { exigirSesion } from './auth.js';

// Páginas protegidas: verifica la sesión real contra el servidor antes de montar.
// El backend ya redirige sin cookie; esto sincroniza la UI y evita parpadeos.
const autorizado = await exigirSesion('./login.html');
if (!autorizado) {
  // exigirSesion ya redirige; detener el arranque.
  throw new Error('redirigiendo-a-login');
}

const page = document.body.dataset.page;
initShell(page);
const main = document.getElementById(page === 'plan' ? 'plan-main' : 'home-main');
try {
  await import(page === 'plan' ? './plan.js' : './home.js');
  main.setAttribute('aria-busy', 'false');
} catch (error) {
  console.error('No se pudo abrir la demostración:', error);
  main.setAttribute('aria-busy', 'false');
  main.className = 'error-main';
  main.innerHTML = `<section class="load-error" aria-labelledby="load-error-heading">
    <h1 id="load-error-heading">No se pudo cargar el escenario</h1>
    <p>Los datos de esta demostración no están disponibles en este momento. Puedes volver a intentar cargarlos.</p>
    <button id="retry-load" class="primary">Volver a intentar</button>
    ${page === 'plan' ? '<a href="index.html">Ir a Inicio</a>' : ''}
  </section>`;
  document.getElementById('retry-load').addEventListener('click', () => location.reload());
}
