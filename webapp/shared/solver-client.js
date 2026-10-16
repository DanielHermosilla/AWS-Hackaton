// Same-origin transport. Aborting the browser wait does not cancel the solver.
export const API_VERSION = '3.0';
export const EXECUTION_KEY = 'zmd.webapp.execution.v1';
export const MAX_FILE_BYTES = 64 * 1024 * 1024;

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
  const response = await fetchImpl(`/solve?run_id=${encodeURIComponent(runId)}`, {cache: 'no-store'});
  if (response.status === 404) throw new Error('Esta ejecución expiró o pertenece a una versión anterior. Carga de nuevo la instancia y vuelve a calcular.');
  return readResponse(response);
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

export function createSolverClient({fetchImpl = fetch, onChange = () => {}, onPrepared = () => {}, onResult = () => {}} = {}) {
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
    async solve(request, {prepareRequest = null} = {}) {
      this.invalidate();
      const current = revision;
      controller = new AbortController();
      let stage = prepareRequest ? 'preparing' : 'solving';
      const post = async (url, body) => {
        const serialized = JSON.stringify(body);
        if (new TextEncoder().encode(serialized).byteLength > MAX_FILE_BYTES)
          throw new Error('La instancia supera los 64 MiB admitidos. Reduce el archivo o utiliza la ejecución por consola para esta red.');
        return readResponse(await fetchImpl(url, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: serialized, signal: controller.signal,
        }));
      };
      onChange({status: 'running', stage, message: prepareRequest ? 'Preparando la instancia en el servidor…' : 'Resolviendo la instancia nativa…'});
      try {
        let solveRequest = request;
        if (prepareRequest) {
          const prepared = await post('/prepare', prepareRequest);
          if (current !== revision) return null;
          if (prepared?.api_version !== API_VERSION || !['1.0', '1.1'].includes(prepared?.instance?.schema_version))
            throw new Error('La preparación no devolvió una instancia nativa compatible.');
          solveRequest = {api_version: API_VERSION, instance: prepared.instance, solver: request.solver,
            ...(prepared.prepared_instance_id ? {prepared_instance_id: prepared.prepared_instance_id} : {})};
          await onPrepared(solveRequest, () => current === revision);
          if (current !== revision) return null;
          stage = 'solving';
          onChange({status: 'running', stage, message: 'Instancia preparada. Resolviendo con el motor…'});
        }
        const body = await post('/solve', solveRequest);
        if (current !== revision) return null;
        await onResult(body, () => current === revision);
        if (current !== revision) return null;
        onChange({status: 'complete', message: 'Resultado disponible.'});
        return body;
      } catch (error) {
        if (current !== revision) return null;
        onChange({status: 'error', stage, response: error.response ?? null, message: error instanceof TypeError
          ? 'No se pudo conectar con el motor. Comprueba que el servidor esté ejecutándose y vuelve a intentar.'
          : error.message || 'No se pudo completar la ejecución.'});
        return null;
      } finally {
        if (current === revision) controller = null;
      }
    },
  };
}
