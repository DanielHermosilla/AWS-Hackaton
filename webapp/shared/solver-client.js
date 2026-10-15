// Same-origin transport. Aborting the browser wait does not cancel the solver.
export const API_VERSION = '2.0-beta.1';
export const EXECUTION_KEY = 'zmd.webapp.execution.v1';

async function readResponse(response) {
  let body;
  try { body = await response.json(); }
  catch { throw new Error('El servicio devolvió una respuesta que no es JSON válido.'); }
  if (!response.ok) {
    const error = new Error(body?.error?.message || `El servicio respondió con error ${response.status}.`);
    error.response = body;
    throw error;
  }
  return body;
}

export async function getSavedRun(runId, fetchImpl = fetch) {
  return readResponse(await fetchImpl(`/solve?run_id=${encodeURIComponent(runId)}`, {cache: 'no-store'}));
}

export function readExecution(storage) {
  try {
    storage ??= globalThis.sessionStorage;
    const value = JSON.parse(storage.getItem(EXECUTION_KEY));
    return value && typeof value === 'object' ? value : null;
  } catch { return null; }
}

export function saveExecution(value, storage) {
  try {
    storage ??= globalThis.sessionStorage;
    if (value) storage.setItem(EXECUTION_KEY, JSON.stringify(value));
    else storage.removeItem(EXECUTION_KEY);
    return true;
  } catch { return false; }
}

export function createSolverClient({fetchImpl = fetch, onChange = () => {}, onResult = () => {}} = {}) {
  let revision = 0;
  let controller = null;
  return {
    invalidate() {
      revision++;
      controller?.abort();
      controller = null;
    },
    stopWaiting() {
      this.invalidate();
      onChange({status: 'stopped', message: 'Dejaste de esperar. El cálculo puede continuar en el servidor.'});
    },
    async solve(request) {
      this.invalidate();
      const current = revision;
      controller = new AbortController();
      onChange({status: 'running', message: 'Preparando y resolviendo la instancia…'});
      try {
        const response = await fetchImpl('/solve', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(request), signal: controller.signal,
        });
        const body = await readResponse(response);
        if (current !== revision) return null;
        await onResult(body, () => current === revision);
        if (current !== revision) return null;
        onChange({status: 'complete', message: 'Resultado disponible.'});
        return body;
      } catch (error) {
        if (current !== revision) return null;
        onChange({status: 'error', response: error.response ?? null, message: error instanceof TypeError
          ? 'No se pudo conectar con el motor. Comprueba que el servidor beta esté ejecutándose y vuelve a intentar.'
          : error.message || 'No se pudo completar la ejecución.'});
        return null;
      } finally {
        if (current === revision) controller = null;
      }
    },
  };
}
