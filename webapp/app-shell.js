import { icon } from './shared/icons.js';
import {
  readPreferences, updatePreferences, applyPreferences, clearPlanContext, readPlanContext,
  DEFAULT_PREFERENCES, ORGANIZATION_NAME_MAX, PREFERENCE_STORAGE_KEY
} from './state.js';
import { homeHref, planHref } from './home-navigation.js';
import { ZMD_BRAND } from './assets/brand/integration/brand-assets.js';

const svg = (size, body) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const menuIcon = svg(20, '<path d="M4 6h16M4 12h16M4 18h16"/>');
const settingsIcon = svg(19, '<path d="M4 7h2m6 0h8M4 17h8m6 0h2"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>');
const closePlanIcon = svg(19, '<path d="M9 4H4v16h5m6-12 4 4-4 4M9 12h10"/>');
const sunIcon = svg(19, '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>');
const moonIcon = svg(19, '<path d="M20.7 14.6A9 9 0 0 1 9.4 3.3a9 9 0 1 0 11.3 11.3Z"/>');

// Connector words are skipped so "Transportes del Sur" becomes "TS".
const minorWords = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'the', 'of', 'and', '&']);
function organizationInitials(name) {
  const words = name.split(' ').filter(Boolean);
  const significant = words.filter(word => !minorWords.has(word.toLocaleLowerCase('es')));
  const pool = significant.length ? significant : words;
  const firstCharacter = word => word.match(/[\p{L}\p{N}]/u)?.[0] || '';
  const initials = pool.length > 1
    ? firstCharacter(pool[0]) + firstCharacter(pool[1])
    : (pool[0]?.match(/[\p{L}\p{N}]/gu) || []).slice(0, 2).join('');
  return initials.toLocaleUpperCase('es') || 'MO';
}

/**
 * Shared header, navigation rail/drawer, local profile menu, Settings and data provenance.
 * page: 'home' | 'plan'. Called once by boot.js; repeated calls are ignored.
 */
export function initShell(page) {
  const mount = document.getElementById('app-shell');
  if (!mount || mount.dataset.shellReady === 'true') return;
  mount.dataset.shellReady = 'true';
  const mainId = page === 'plan' ? 'plan-main' : 'home-main';
  const home = homeHref();
  const continueLabel = readPlanContext() ? 'Continuar plan' : 'Abrir plan';

  mount.innerHTML = `
    <a class="skip-link" href="#${mainId}">Saltar al contenido</a>
    <header class="topbar" data-shell-page="${page === 'plan' ? 'plan' : 'home'}">
      <div class="topbar-start">
        <button id="nav-toggle" class="icon-button nav-toggle" type="button" aria-label="Abrir navegación" aria-haspopup="dialog" aria-controls="nav-drawer" aria-expanded="false">${menuIcon}</button>
        <div class="org-identity" id="org-identity">
          <span class="org-initials" id="org-initials" aria-hidden="true"></span>
          <span class="org-name" id="org-name"></span>
        </div>
      </div>
      <a class="zmd-brand topbar-brand" href="${home}" aria-label="ZMD Mobility, inicio"><img id="brand-logo" class="zmd-brand__logo" src="${ZMD_BRAND.logo}" width="272" height="64" alt=""></a>
      <div class="topbar-end top-actions">
        <button id="data-badge" class="data-badge" type="button" aria-label="Datos de ejemplo" aria-haspopup="dialog" aria-controls="about-dialog"><span id="about" class="data-badge__icon" aria-hidden="true">${icon('info', 15)}</span><span class="data-badge__full" aria-hidden="true">Datos de ejemplo</span><span class="data-badge__short" aria-hidden="true">Ejemplo</span></button>
        <button id="theme-toggle" class="icon-button theme-toggle" type="button" aria-label="Tema oscuro" aria-pressed="false"><span class="theme-toggle__icon" data-theme-icon="light">${sunIcon}</span><span class="theme-toggle__icon" data-theme-icon="dark" hidden>${moonIcon}</span></button>
        ${page === 'home' ? `<a id="continue-plan" class="continue-plan" href="${planHref}" aria-describedby="continue-plan-description">${continueLabel}</a><span id="continue-plan-description" class="sr-only"></span>` : ''}
      </div>
    </header>
    <div id="desktop-rail">
      <aside class="app-rail" aria-label="Navegación de la aplicación">
        <div class="drawer-heading"><span>Navegación</span><button id="close-nav" class="icon-button" type="button" aria-label="Cerrar navegación">${icon('close', 18)}</button></div>
        <nav class="app-nav" aria-label="Principal">
          <a class="nav-link" href="${home}" ${page === 'home' ? 'aria-current="page"' : ''}>${icon('grid', 21)}<span>Inicio</span></a>
          <a class="nav-link" href="${planHref}" ${page === 'plan' ? 'aria-current="page"' : ''}>${icon('map', 21)}<span>Plan</span></a>
        </nav>
        <div class="rail-foot">
          <button id="profile-button" class="profile-button" type="button" aria-label="Diego Caballero, perfil local" aria-haspopup="menu" aria-expanded="false" aria-controls="profile-menu"><span aria-hidden="true">DC</span></button>
          <span class="rail-local" aria-hidden="true">Perfil local</span>
        </div>
        <div id="profile-popover" class="profile-popover" popover="auto">
          <div class="profile-heading"><strong>Diego Caballero</strong><span>Perfil local en este navegador</span></div>
          <div id="profile-menu" role="menu" aria-label="Perfil local">
            <button id="open-settings" type="button" role="menuitem" tabindex="-1">${settingsIcon}<span>Ajustes<small>Apariencia y organización</small></span></button>
            <button id="close-plan" type="button" role="menuitem" tabindex="-1">${closePlanIcon}<span>Cerrar plan<small>Restablece la selección del Plan en esta pestaña. Conserva tus ajustes.</small></span></button>
          </div>
        </div>
      </aside>
    </div>
    <dialog id="nav-drawer" aria-label="Navegación de la aplicación"></dialog>
    <dialog id="settings-dialog" class="app-dialog settings-dialog" aria-labelledby="settings-heading">
      <div class="dialog-heading"><h2 id="settings-heading">Ajustes</h2><button id="close-settings" class="icon-button" type="button" aria-label="Cerrar ajustes">${icon('close', 18)}</button></div>
      <p class="settings-intro">El tema se aplica solo a esta página, que siempre inicia en claro. Los demás ajustes se guardan en este navegador.</p>
      <section class="settings-section" aria-labelledby="appearance-heading">
        <h3 id="appearance-heading">Apariencia</h3>
        <fieldset class="theme-choice">
          <legend>Tema de esta página</legend>
          <label class="theme-option"><input type="radio" name="theme-choice" value="light">${sunIcon}<span>Claro</span></label>
          <label class="theme-option"><input type="radio" name="theme-choice" value="dark">${moonIcon}<span>Oscuro</span></label>
        </fieldset>
        <label class="preference-row" for="solid-surfaces"><span><strong>Superficies sólidas</strong><small>Quita las transparencias de la navegación, los menús y los controles del mapa.</small></span><input type="checkbox" id="solid-surfaces"></label>
        <label class="preference-row" for="reduced-motion"><span><strong>Reducir movimiento</strong><small>Desactiva las animaciones de la interfaz y los desplazamientos animados del mapa.</small></span><input type="checkbox" id="reduced-motion" aria-describedby="os-motion-note"></label>
        <p id="os-motion-note" class="settings-note"></p>
      </section>
      <section class="settings-section" aria-labelledby="organization-heading">
        <h3 id="organization-heading">Organización</h3>
        <label class="field-label" for="organization-name">Nombre en la cabecera</label>
        <input id="organization-name" class="text-field" type="text" maxlength="${ORGANIZATION_NAME_MAX}" autocomplete="organization" spellcheck="false" aria-describedby="organization-help">
        <p id="organization-help" class="settings-note">Hasta ${ORGANIZATION_NAME_MAX} caracteres. Si lo dejas vacío, se muestra «${DEFAULT_PREFERENCES.organizationName}».</p>
      </section>
      <p id="preference-status" class="settings-status" role="status"></p>
      <div class="dialog-actions"><button id="reset-preferences" type="button">Restablecer apariencia</button><button id="done-settings" type="button" class="primary">Listo</button></div>
    </dialog>
    <dialog id="about-dialog" class="app-dialog about-dialog" aria-labelledby="about-heading">
      <div class="dialog-heading"><h2 id="about-heading">Datos de ejemplo</h2><button id="close-about" class="icon-button" type="button" aria-label="Cerrar información de los datos">${icon('close', 18)}</button></div>
      <p class="about-source"><span>Fuente en uso</span> <strong data-source-text="title">Ejemplo de diseño</strong></p>
      <p data-source-text="description">ZMD Mobility desarrolla esta experiencia de planificación eléctrica.</p>
      <p data-source-text="geometry">Los recorridos son ilustrativos.</p>
      <p data-source-text="stations">Estaciones del ejemplo; disponibilidad sin verificar.</p>
      <p class="about-caveat">Con cualquier fuente, la asignación de entregas, el orden de visitas, el consumo, las recargas y la batería son ilustrativos. No hay validación real, optimización del motor ni telemetría en vivo, y ninguna entrega figura como completada.</p>
      <div class="dialog-actions"><button id="done-about" type="button" class="primary">Entendido</button></div>
    </dialog>`;

  const $ = id => document.getElementById(id);
  const rail = mount.querySelector('.app-rail');
  const drawer = $('nav-drawer');
  const navToggle = $('nav-toggle');
  const avatar = $('profile-button');
  const popover = $('profile-popover');
  const items = [...popover.querySelectorAll('[role="menuitem"]')];
  const settings = $('settings-dialog');
  const about = $('about-dialog');
  const badge = $('data-badge');
  const themeToggle = $('theme-toggle');
  const themeRadios = [...settings.querySelectorAll('input[name="theme-choice"]')];
  const solidInput = $('solid-surfaces');
  const motionInput = $('reduced-motion');
  const orgInput = $('organization-name');
  const mobile = matchMedia('(max-width: 760px)');
  const osMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let preferences = applyPreferences(readPreferences(), { notify: false });

  // Fill provenance text in the shell; the page module reports load failures itself.
  import('./shared/data.js').then(data => data.applyDataProvenance(mount)).catch(() => {});

  function updateMotionNote() {
    $('os-motion-note').textContent = osMotion.matches
      ? 'Tu sistema pide reducir el movimiento; se respeta aunque desactives esta opción.'
      : 'También se respeta la preferencia de movimiento de tu sistema.';
  }

  // User text is only assigned through textContent, title and input.value.
  function render({ syncInput = true } = {}) {
    const name = preferences.organizationName;
    const dark = preferences.theme === 'dark';
    $('org-name').textContent = name;
    $('org-initials').textContent = organizationInitials(name);
    $('org-identity').title = name;
    themeToggle.setAttribute('aria-pressed', String(dark));
    themeToggle.title = dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
    themeToggle.querySelector('[data-theme-icon="light"]').hidden = dark;
    themeToggle.querySelector('[data-theme-icon="dark"]').hidden = !dark;
    $('brand-logo').src = dark ? ZMD_BRAND.logoInverse : ZMD_BRAND.logo;
    for (const radio of themeRadios) radio.checked = radio.value === preferences.theme;
    solidInput.checked = preferences.solidSurfaces;
    motionInput.checked = preferences.reducedMotion;
    if (syncInput) orgInput.value = name;
    updateMotionNote();
  }

  function setStatus(saved) {
    $('preference-status').textContent = saved
      ? 'Ajustes aplicados. El tema vuelve a claro al cargar otra página.'
      : 'Aplicado en esta pestaña. El navegador no permite guardar los ajustes.';
  }

  function commit(patch, options) {
    const result = updatePreferences(patch);
    preferences = result.preferences;
    render(options);
    setStatus(result.saved);
  }

  render();
  $('preference-status').textContent = 'Los cambios se aplican de inmediato.';
  osMotion.addEventListener('change', updateMotionNote);
  // Keep other open tabs of this app in step.
  addEventListener('storage', event => {
    if (event.key !== null && event.key !== PREFERENCE_STORAGE_KEY) return;
    preferences = applyPreferences(readPreferences());
    render({ syncInput: document.activeElement !== orgInput });
  });
  addEventListener('pageshow', event => {
    if (!event.persisted) return;
    preferences = applyPreferences(readPreferences());
    render({ syncInput: document.activeElement !== orgInput });
  });

  themeToggle.addEventListener('click', () => {
    commit({ theme: preferences.theme === 'dark' ? 'light' : 'dark' });
  });
  for (const radio of themeRadios) {
    radio.addEventListener('change', () => { if (radio.checked) commit({ theme: radio.value }); });
  }
  solidInput.addEventListener('change', () => commit({ solidSurfaces: solidInput.checked }));
  motionInput.addEventListener('change', () => commit({ reducedMotion: motionInput.checked }));
  // Live header update while typing; the field shows the stored value once committed.
  orgInput.addEventListener('input', () => commit({ organizationName: orgInput.value }, { syncInput: false }));
  orgInput.addEventListener('change', () => { orgInput.value = preferences.organizationName; });
  $('reset-preferences').addEventListener('click', () => commit({
    theme: DEFAULT_PREFERENCES.theme,
    solidSurfaces: DEFAULT_PREFERENCES.solidSurfaces,
    reducedMotion: DEFAULT_PREFERENCES.reducedMotion
  }));

  // Profile menu (popover with menu semantics).
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

  // Desktop rail; on mobile the same rail moves into a modal drawer.
  function placeNavigation() {
    closeMenu();
    if (!mobile.matches && drawer.open) drawer.close();
    (mobile.matches ? drawer : $('desktop-rail')).append(rail);
    navToggle.setAttribute('aria-expanded', String(drawer.open));
  }
  placeNavigation();
  mobile.addEventListener('change', placeNavigation);
  navToggle.addEventListener('click', () => {
    drawer.showModal();
    navToggle.setAttribute('aria-expanded', 'true');
    $('close-nav').focus();
  });
  $('close-nav').addEventListener('click', () => drawer.close());
  drawer.addEventListener('close', () => {
    closeMenu();
    navToggle.setAttribute('aria-expanded', 'false');
    if (mobile.matches) navToggle.focus({ preventScroll: true });
  });
  drawer.addEventListener('click', event => {
    const bounds = drawer.getBoundingClientRect();
    if (event.target === drawer && (event.clientX > bounds.right || event.clientY > bounds.bottom || event.clientX < bounds.left || event.clientY < bounds.top)) drawer.close();
  });

  // Settings dialog.
  $('open-settings').addEventListener('click', () => {
    closeMenu();
    render();
    settings.showModal();
    (themeRadios.find(radio => radio.checked) || themeRadios[0]).focus();
  });
  for (const id of ['close-settings', 'done-settings']) $(id).addEventListener('click', () => settings.close());
  settings.addEventListener('close', () => {
    orgInput.value = preferences.organizationName;
    (mobile.matches && !drawer.open ? navToggle : avatar).focus({ preventScroll: true });
  });

  // Close the local plan: clears the session context; preferences remain.
  $('close-plan').addEventListener('click', () => {
    closeMenu();
    document.body.dataset.leavingDemo = 'true';
    clearPlanContext();
    location.assign(new URL('./salida.html', import.meta.url).href);
  });

  // Data provenance dialog, opened only from the shared badge.
  badge.addEventListener('click', () => about.showModal());
  for (const id of ['close-about', 'done-about']) $(id).addEventListener('click', () => about.close());
  about.addEventListener('close', () => badge.focus({ preventScroll: true }));
}
