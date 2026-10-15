// Per-tab preview choice. The allowlist cannot redirect outside this application.
const previewKey = 'zmd.webapp.home-preview.v1';
const previews = new Set(['01', '02', '03', '04', '05']);

// Version the static entry during this preview; `v` does not replace Plan context.
export const planHref = new URL('./plan.html?v=home-v3', import.meta.url).href;

export function rememberHomePreview(id) {
  if (!previews.has(id)) return;
  try { sessionStorage.setItem(previewKey, id); } catch { /* Preview still opens. */ }
}

export function homeHref() {
  let id;
  try { id = sessionStorage.getItem(previewKey); } catch { /* Use original home. */ }
  return new URL(previews.has(id) ? `./home/${id}/index.html` : './index.html', import.meta.url).href;
}
