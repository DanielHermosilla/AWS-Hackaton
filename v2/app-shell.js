import { icon } from './shared/icons.js';
import { readPreferences, savePreferences, clearPlanContext } from './state.js';
import { homeHref, planHref } from './home-navigation.js';
import { ZMD_BRAND } from './assets/brand/integration/brand-assets.js';

const menuIcon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
const settingsIcon = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="white"/><circle cx="15" cy="17" r="3" fill="white"/></svg>';
const exitIcon = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4H4v16h5m6-12 4 4-4 4M9 12h10"/></svg>';

export function initShell(page) {
  const mainId = page === 'plan' ? 'plan-main' : 'home-main';
  const mount = document.getElementById('app-shell');
  mount.innerHTML = `
    <a class="skip-link" href="#${mainId}">Saltar al contenido</a>
    <header class="topbar">
      <button id="nav-toggle" class="icon-button nav-toggle" aria-label="Abrir navegación" aria-haspopup="dialog" aria-controls="nav-drawer" aria-expanded="false">${menuIcon}</button>
      <a class="zmd-brand" href="${homeHref()}" aria-label="ZMD Mobility, inicio"><img class="zmd-brand__logo" src="${ZMD_BRAND.logo}" width="272" height="64" alt=""></a>
      <div class="app-name">Planificación de flota eléctrica</div>
      <div class="top-actions"><span class="demo-tag"><span class="sr-only">Demostración</span><span class="demo-full" aria-hidden="true">Demostración</span><span class="demo-short" aria-hidden="true">Demo</span></span>
        <button id="about" class="icon-button" aria-label="Acerca de los datos">${icon('info', 18)}</button>
      </div>
    </header>
    <div id="desktop-rail">
      <aside class="app-rail" aria-label="Navegación de la aplicación">
        <div class="drawer-heading"><span>Navegación</span><button id="close-nav" class="icon-button" aria-label="Cerrar navegación">${icon('close', 18)}</button></div>
        <nav class="app-nav" aria-label="Principal">
          <a class="zmd-brand zmd-brand--symbol rail-brand" href="${homeHref()}" aria-label="ZMD Mobility, inicio"><img class="zmd-brand__symbol" src="${ZMD_BRAND.symbol}" width="96" height="96" alt=""></a>
          <a class="nav-link" href="${homeHref()}" ${page === 'home' ? 'aria-current="page"' : ''}>${icon('grid', 21)}<span>Inicio</span></a>
          <a class="nav-link" href="${planHref}" ${page === 'plan' ? 'aria-current="page"' : ''}>${icon('map', 21)}<span>Plan</span></a>
        </nav>
        <div class="rail-foot">
          <button id="profile-button" class="profile-button" aria-label="Opciones de la demostración, DC" aria-haspopup="menu" aria-expanded="false" aria-controls="profile-menu"><span aria-hidden="true">DC</span></button>
          <span class="rail-local">Local</span>
        </div>
        <div id="profile-popover" class="profile-popover" popover="auto">
          <div class="profile-heading"><strong>Demostración local</strong><span>Sin cuenta conectada</span></div>
          <div id="profile-menu" role="menu" aria-label="Opciones de la demostración">
            <button id="open-settings" role="menuitem" tabindex="-1">${settingsIcon}<span>Ajustes de apariencia</span></button>
            <button id="leave-demo" role="menuitem" tabindex="-1">${exitIcon}<span>Salir de la demostración<small>Cierra el plan; conserva tus ajustes.</small></span></button>
          </div>
        </div>
      </aside>
    </div>
    <dialog id="nav-drawer" aria-label="Navegación de la aplicación"></dialog>
    <dialog id="settings-dialog" class="app-dialog" aria-labelledby="settings-heading">
      <div class="dialog-heading"><h2 id="settings-heading">Ajustes de apariencia</h2><button id="close-settings" class="icon-button" aria-label="Cerrar ajustes">${icon('close', 18)}</button></div>
      <p>Personaliza cómo se muestran los controles.</p>
      <label class="preference-row" for="solid-surfaces"><span><strong>Superficies sólidas</strong><small>Quita las transparencias de la navegación y los controles del mapa.</small></span><input type="checkbox" id="solid-surfaces"></label>
      <p class="settings-note">Las preferencias de accesibilidad de tu sistema también se respetan.</p>
      <p id="preference-status" class="settings-status" role="status">Los cambios se guardan en este navegador.</p>
      <div class="dialog-actions"><button id="reset-preferences">Restablecer apariencia</button><button id="done-settings" class="primary">Listo</button></div>
    </dialog>
    <dialog id="about-dialog" class="app-dialog" aria-labelledby="about-heading">
      <div class="dialog-heading"><h2 id="about-heading">Acerca de esta demostración</h2><button id="close-about" class="icon-button" aria-label="Cerrar información">${icon('close', 18)}</button></div>
      <p data-source-text="description">ZMD Mobility desarrolla esta demostración de planificación eléctrica.</p>
      <p data-source-text="geometry">Recorridos, consumo, recarga y batería ilustrativos, sin resultados ni validación del motor.</p>
      <p><span data-source-text="stations">Estaciones del ejemplo; disponibilidad sin verificar.</span> No hay resultados de ahorro ni telemetría en vivo.</p>
      <div class="dialog-actions"><button id="done-about" class="primary">Entendido</button></div>
    </dialog>`;

  const $ = id => document.getElementById(id);
  const rail = mount.querySelector('.app-rail');
  const drawer = $('nav-drawer');
  const avatar = $('profile-button');
  const popover = $('profile-popover');
  const items = [...popover.querySelectorAll('[role="menuitem"]')];
  const settings = $('settings-dialog');
  const mobile = matchMedia('(max-width: 760px)');
  const preferences = readPreferences();
  const applyPreferences = () => {
    document.documentElement.dataset.solidSurfaces = String(preferences.solidSurfaces);
    $('solid-surfaces').checked = preferences.solidSurfaces;
  };
  applyPreferences();

  function positionMenu() {
    const anchor = avatar.getBoundingClientRect();
    const bounds = popover.getBoundingClientRect();
    const left = mobile.matches ? anchor.left : anchor.right + 12;
    const top = mobile.matches ? anchor.top - bounds.height - 10 : anchor.bottom - bounds.height;
    popover.style.left = `${Math.max(12, Math.min(left, innerWidth - bounds.width - 12))}px`;
    popover.style.top = `${Math.max(12, Math.min(top, innerHeight - bounds.height - 12))}px`;
  }
  function closeMenu(restoreFocus = false) {
    if (popover.matches(':popover-open')) popover.hidePopover();
    avatar.setAttribute('aria-expanded', 'false');
    if (restoreFocus) avatar.focus({ preventScroll: true });
  }
  function openMenu(last = false) {
    popover.showPopover();
    avatar.setAttribute('aria-expanded', 'true');
    positionMenu();
    items[last ? items.length - 1 : 0].focus({ preventScroll: true });
  }
  avatar.addEventListener('click', () => {
    if (popover.matches(':popover-open')) closeMenu(true);
    else openMenu();
  });
  avatar.addEventListener('keydown', event => {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    event.preventDefault();
    openMenu(event.key === 'ArrowUp');
  });
  popover.addEventListener('toggle', event => {
    const open = event.newState === 'open';
    avatar.setAttribute('aria-expanded', String(open));
    if (!open && popover.contains(document.activeElement)) avatar.focus({ preventScroll: true });
  });
  popover.addEventListener('keydown', event => {
    const current = items.indexOf(document.activeElement);
    let next;
    if (event.key === 'ArrowDown') next = (current + 1) % items.length;
    if (event.key === 'ArrowUp') next = (current - 1 + items.length) % items.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = items.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      items[next].focus();
    } else if (event.key === 'Tab') {
      // Return to the invoker before the browser makes its normal tab movement.
      closeMenu(true);
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && popover.matches(':popover-open')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeMenu(true);
    }
  }, true);
  document.addEventListener('focusin', event => {
    if (popover.matches(':popover-open') && !popover.contains(event.target) && event.target !== avatar) closeMenu();
  });
  addEventListener('resize', () => {
    if (popover.matches(':popover-open')) positionMenu();
  });

  function placeNavigation() {
    closeMenu();
    if (!mobile.matches && drawer.open) drawer.close();
    (mobile.matches ? drawer : $('desktop-rail')).append(rail);
    $('nav-toggle').setAttribute('aria-expanded', String(drawer.open));
  }
  placeNavigation();
  mobile.addEventListener('change', placeNavigation);
  $('nav-toggle').addEventListener('click', () => {
    drawer.showModal();
    $('nav-toggle').setAttribute('aria-expanded', 'true');
    $('close-nav').focus();
  });
  $('close-nav').addEventListener('click', () => drawer.close());
  drawer.addEventListener('close', () => {
    closeMenu();
    $('nav-toggle').setAttribute('aria-expanded', 'false');
    if (mobile.matches) $('nav-toggle').focus({ preventScroll: true });
  });
  drawer.addEventListener('click', event => {
    const bounds = drawer.getBoundingClientRect();
    if (event.target === drawer && (event.clientX > bounds.right || event.clientY > bounds.bottom || event.clientX < bounds.left || event.clientY < bounds.top)) drawer.close();
  });

  $('open-settings').addEventListener('click', () => {
    closeMenu();
    settings.showModal();
    $('solid-surfaces').focus();
  });
  for (const id of ['close-settings', 'done-settings']) $(id).addEventListener('click', () => settings.close());
  settings.addEventListener('close', () => avatar.focus({ preventScroll: true }));
  function persistPreference() {
    applyPreferences();
    $('preference-status').textContent = savePreferences(preferences)
      ? 'Apariencia guardada en este navegador.'
      : 'Aplicado a esta vista. El navegador no permite guardar los ajustes.';
  }
  $('solid-surfaces').addEventListener('change', event => {
    preferences.solidSurfaces = event.target.checked;
    persistPreference();
  });
  $('reset-preferences').addEventListener('click', () => {
    preferences.solidSurfaces = false;
    persistPreference();
  });
  $('leave-demo').addEventListener('click', async () => {
    document.body.dataset.leavingDemo = 'true';
    clearPlanContext();
    try {
      const { API, cerrarSesion } = await import('./auth.js');
      await API.cerrarSesionServidor();  // invalida el token en el servidor
      cerrarSesion();                    // limpia la marca de sesión del cliente
    } catch { /* La salida no depende de esto. */ }
    location.assign(new URL('./salida.html', import.meta.url));
  });
  $('about').addEventListener('click', () => $('about-dialog').showModal());
  for (const id of ['close-about', 'done-about']) $(id).addEventListener('click', () => $('about-dialog').close());
}
