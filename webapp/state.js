// Local presentation preferences and Plan navigation context only.
// There is no account, permission, billing or solver state in this module.
export const PREFERENCE_STORAGE_KEY = 'zmd.webapp.presentation.v1';
// Theme chosen in the former console exploration; read once for migration.
const legacyThemeKey = 'zmd.homepage.console-theme.v1';
const contextKey = 'zmd.webapp.plan.v1';

export const PREFERENCES_EVENT = 'zmd:preferences-changed';
export const DEFAULT_ORGANIZATION_NAME = 'Mi organización';
export const ORGANIZATION_NAME_MAX = 60;
export const DEFAULT_PREFERENCES = Object.freeze({
  theme: 'dark',
  solidSurfaces: false,
  reducedMotion: false,
  organizationName: DEFAULT_ORGANIZATION_NAME
});

const themes = new Set(['light', 'dark']);
// Control, zero-width and bidirectional override characters cannot spoof the header.
const unsafeCharacters = /[\u0000-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff]/g;
const osReducedMotion = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;

// Used only when the browser refuses storage, so the current page keeps working.
let unsavedPreferences = null;
let contextInMemory = null;
// Set by "Cerrar plan" so a later pagehide cannot write the closed plan back.
let contextClosed = false;

export function normalizeOrganizationName(value) {
  if (typeof value !== 'string') return DEFAULT_ORGANIZATION_NAME;
  const clean = value.replace(unsafeCharacters, '').replace(/\s+/g, ' ').trim();
  // Count code points, not UTF-16 units, so the limit never splits a character.
  const bounded = [...clean].slice(0, ORGANIZATION_NAME_MAX).join('').trim();
  return bounded || DEFAULT_ORGANIZATION_NAME;
}

export function normalizePreferences(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  return {
    theme: themes.has(source.theme) ? source.theme : DEFAULT_PREFERENCES.theme,
    solidSurfaces: source.solidSurfaces === true,
    reducedMotion: source.reducedMotion === true,
    organizationName: normalizeOrganizationName(source.organizationName)
  };
}

function readLegacyTheme() {
  try {
    const value = localStorage.getItem(legacyThemeKey);
    return themes.has(value) ? value : null;
  } catch {
    return null;
  }
}

export function readPreferences() {
  if (unsavedPreferences) return { ...unsavedPreferences };
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(PREFERENCE_STORAGE_KEY));
  } catch {
    saved = null;
  }
  const stored = saved && typeof saved === 'object' ? saved : {};
  return normalizePreferences({
    ...stored,
    theme: themes.has(stored.theme) ? stored.theme : readLegacyTheme() || DEFAULT_PREFERENCES.theme
  });
}

export function savePreferences(preferences) {
  const normalized = normalizePreferences(preferences);
  try {
    localStorage.setItem(PREFERENCE_STORAGE_KEY, JSON.stringify(normalized));
    unsavedPreferences = null;
    try { localStorage.removeItem(legacyThemeKey); } catch { /* Migration already stored. */ }
    return true;
  } catch {
    unsavedPreferences = normalized;
    return false;
  }
}

/** Reflect preferences on <html> and notify listeners on this page. */
export function applyPreferences(preferences, { notify = true } = {}) {
  const normalized = normalizePreferences(preferences);
  const root = document.documentElement;
  root.dataset.theme = normalized.theme;
  root.dataset.solidSurfaces = String(normalized.solidSurfaces);
  root.dataset.reducedMotion = String(normalized.reducedMotion);
  if (notify) {
    document.dispatchEvent(new CustomEvent(PREFERENCES_EVENT, { detail: { ...normalized } }));
  }
  return normalized;
}

/** Merge, persist (when allowed) and apply immediately. */
export function updatePreferences(patch) {
  const preferences = normalizePreferences({ ...readPreferences(), ...patch });
  const saved = savePreferences(preferences);
  applyPreferences(preferences);
  return { preferences, saved };
}

/** True when either the local preference or the operating system asks for less motion. */
export function prefersReducedMotion() {
  return document.documentElement.dataset.reducedMotion === 'true' || !!osReducedMotion?.matches;
}

/** Calls back when the combined reduced-motion state changes. Returns an unsubscribe function. */
export function onReducedMotionChange(callback) {
  let last = prefersReducedMotion();
  const check = () => {
    const now = prefersReducedMotion();
    if (now === last) return;
    last = now;
    callback(now);
  };
  osReducedMotion?.addEventListener?.('change', check);
  document.addEventListener(PREFERENCES_EVENT, check);
  return () => {
    osReducedMotion?.removeEventListener?.('change', check);
    document.removeEventListener(PREFERENCES_EVENT, check);
  };
}

export function readPlanContext() {
  if (contextClosed) return null;
  try {
    const saved = JSON.parse(sessionStorage.getItem(contextKey));
    return saved && typeof saved === 'object' ? saved : contextInMemory;
  } catch {
    return contextInMemory;
  }
}

export function savePlanContext(context) {
  if (contextClosed) return false;
  contextInMemory = context;
  try {
    sessionStorage.setItem(contextKey, JSON.stringify(context));
  } catch {
    // Selection continues to work when browser storage is unavailable.
  }
  return true;
}

export function clearPlanContext() {
  contextInMemory = null;
  contextClosed = true;
  try {
    sessionStorage.removeItem(contextKey);
  } catch {
    // Closing the local plan does not depend on storage access.
  }
}

// Returning to a cached Plan page with Back reopens it intentionally.
addEventListener('pageshow', event => {
  if (event.persisted) contextClosed = false;
});
