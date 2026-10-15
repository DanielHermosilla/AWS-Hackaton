// Canonical routes. Plan selection travels in Plan query parameters and in
// session state (state.js), never in these base URLs.
export const planHref = new URL('./plan.html', import.meta.url).href;

export function homeHref() {
  return new URL('./index.html', import.meta.url).href;
}
