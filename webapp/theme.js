// Classic script loaded in <head> before paint, including on the exit page.
// Restore the chosen theme before any styled content can flash.
(() => {
  const root = document.documentElement;
  const key = 'zmd.webapp.presentation.v1';
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(key));
  } catch { /* Storage denied or invalid JSON: use defaults. */ }
  if (!saved || typeof saved !== 'object') saved = {};
  root.dataset.theme = saved.theme === 'dark' ? 'dark' : 'light';
  root.dataset.solidSurfaces = String(saved.solidSurfaces === true);
  root.dataset.reducedMotion = String(saved.reducedMotion === true);
})();
