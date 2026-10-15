// Classic script loaded in <head> before paint. Mirrors normalizePreferences in state.js.
(() => {
  const root = document.documentElement;
  const key = 'zmd.webapp.presentation.v1';
  const legacyKey = 'zmd.homepage.console-theme.v1';
  const themes = ['light', 'dark'];
  let saved = null;
  let legacy = null;
  try {
    saved = JSON.parse(localStorage.getItem(key));
  } catch { /* Storage denied or invalid JSON: use defaults. */ }
  try {
    legacy = localStorage.getItem(legacyKey);
  } catch { /* Storage denied: use defaults. */ }
  if (!saved || typeof saved !== 'object') saved = {};
  // Dark preserves the selected console appearance unless a theme was chosen.
  const theme = themes.includes(saved.theme) ? saved.theme : themes.includes(legacy) ? legacy : 'dark';
  root.dataset.theme = theme;
  root.dataset.solidSurfaces = String(saved.solidSurfaces === true);
  root.dataset.reducedMotion = String(saved.reducedMotion === true);
})();
