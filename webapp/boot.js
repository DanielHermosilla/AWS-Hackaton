// Single entry point for Inicio and Plan: create the shared shell once, then
// load the page module. Any loading error (including the strict fixture loader)
// replaces the page content with a recoverable message.
import { homeHref } from './home-navigation.js';

const page = document.body.dataset.page === 'plan' ? 'plan' : 'home';
const main = document.getElementById(page === 'plan' ? 'plan-main' : 'home-main');

function showLoadError() {
  if (!main) return;
  const section = document.createElement('section');
  section.className = 'load-error';
  section.setAttribute('aria-labelledby', 'load-error-heading');
  section.innerHTML = `<h1 id="load-error-heading">No se pudo cargar el escenario</h1>
    <p>Los datos del escenario no están disponibles en este momento. Puedes volver a intentar cargarlos.</p>
    <button type="button" class="primary">Volver a intentar</button>`;
  section.querySelector('button').addEventListener('click', () => location.reload());
  if (page === 'plan') {
    const home = document.createElement('a');
    home.href = homeHref();
    home.textContent = 'Ir a Inicio';
    section.append(' ', home);
  }
  main.className = 'error-main';
  main.replaceChildren(section);
}

try {
  const { initShell } = await import('./app-shell.js');
  initShell(page);
  await import(page === 'plan' ? './plan.js' : './home.js');
} catch (error) {
  console.error('No se pudo cargar la página:', error);
  showLoadError();
} finally {
  main?.setAttribute('aria-busy', 'false');
}
