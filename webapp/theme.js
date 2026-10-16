// Classic script loaded in <head> before paint. Each new document starts light,
// matching state.js; only the other presentation preferences are restored.
(() => {
  const root = document.documentElement;
  root.dataset.theme = 'light';
  const key = 'zmd.webapp.presentation.v1';
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(key));
  } catch { /* Storage denied or invalid JSON: use defaults. */ }
  if (!saved || typeof saved !== 'object') saved = {};
  root.dataset.solidSurfaces = String(saved.solidSurfaces === true);
  root.dataset.reducedMotion = String(saved.reducedMotion === true);
})();
