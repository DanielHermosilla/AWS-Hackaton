import {API_VERSION} from './solver-client.js';

export const MAX_HISTORY_BYTES = 4 * 1024 * 1024 * 1024;
export const MAX_HISTORY_JSON_BYTES = 256 * 1024 * 1024;

export function validateHistoryFile(file) {
  if (!file || !/\.(csv|json)$/i.test(file.name)) throw new Error('Elige un histórico CSV o JSON con mediciones del vehículo.');
  if (!file.size) throw new Error('Este archivo está vacío. Elige un histórico con mediciones.');
  if (/\.json$/i.test(file.name) && file.size > MAX_HISTORY_JSON_BYTES) throw new Error('El JSON histórico supera 256 MiB. Expórtalo como CSV (hasta 4 GiB).');
  if (file.size > MAX_HISTORY_BYTES) throw new Error('El histórico supera 4 GiB. Exporta una selección de viajes completos en CSV.');
}

async function responseBody(response, fallback, historical = false) {
  if (response.status === 404 && historical) {
    const error = new Error('Este histórico ya no está en el servidor. Adjunta de nuevo el archivo; mientras tanto se usará el consumo supuesto.');
    error.expired = true;
    throw error;
  }
  let body;
  try { body = await response.json(); } catch { throw new Error(fallback); }
  if (!response.ok || body?.api_version !== API_VERSION) throw new Error(fallback);
  return body;
}

// Credentials travel only in the body of the local connection request. They are
// never retained in this client, URLs, errors, browser storage or file exports.
export function createHistoryClient({fetchImpl = fetch, xhrFactory = () => new XMLHttpRequest()} = {}) {
  const json = async (path, payload, fallback) => responseBody(await fetchImpl(path, {
    method: payload === undefined ? 'GET' : 'POST',
    cache: 'no-store',
    ...(payload === undefined ? {} : {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}),
  }).catch(() => { throw new Error(fallback); }), fallback, path.startsWith('/history'));
  return {
    async session() {
      return (await json('/bedrock/session', undefined, 'No pudimos consultar AWS. Comprueba que el servidor local esté abierto.')).status;
    },
    async connect(configuration) {
      const fallback = 'No pudimos conectar. Revisa la región, el modelo y las credenciales vigentes con permiso para usar Bedrock.';
      return (await json('/bedrock/session', configuration, fallback)).status;
    },
    async disconnect() {
      return (await json('/bedrock/disconnect', {}, 'No pudimos desconectar AWS. Vuelve a intentar.')).status;
    },
    async get(profileId) {
      return (await json(`/history?profile_id=${encodeURIComponent(profileId)}`, undefined, 'No pudimos recuperar el histórico. Vuelve a adjuntarlo o usa el consumo supuesto.')).profile;
    },
    async analyze(profileId) {
      return (await json('/history/analyze', {profile_id: profileId}, 'No pudimos interpretar el histórico. Revisa la conexión con AWS; puedes seguir con el consumo supuesto.')).profile;
    },
    async remove(profileId) {
      await json('/history/remove', {profile_id: profileId}, 'El histórico se quitó de este cálculo, pero no pudimos retirarlo del servidor. Se borrará cuando termine la sesión.');
    },
    upload(file, {signal, onProgress = () => {}} = {}) {
      validateHistoryFile(file);
      return new Promise((resolve, reject) => {
        const xhr = xhrFactory();
        const failure = () => reject(new Error('No pudimos procesar el histórico. Revisa que sea un CSV o JSON de mediciones de un vehículo eléctrico y vuelve a intentar.'));
        const abort = () => xhr.abort();
        const clear = () => signal?.removeEventListener('abort', abort);
        xhr.open('POST', '/history/upload');
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        xhr.setRequestHeader('X-History-Filename', encodeURIComponent(file.name));
        xhr.upload.onprogress = event => {
          if (event.lengthComputable) onProgress(Math.min(1, event.loaded / event.total));
        };
        xhr.onload = () => {
          clear();
          try {
            const body = JSON.parse(xhr.responseText);
            if (xhr.status < 200 || xhr.status >= 300 || body?.api_version !== API_VERSION || !body.profile?.profile_id) return failure();
            resolve(body.profile);
          } catch { failure(); }
        };
        xhr.onerror = () => { clear(); failure(); };
        xhr.onabort = () => { clear(); reject(new DOMException('Carga cancelada', 'AbortError')); };
        signal?.addEventListener('abort', abort, {once: true});
        if (signal?.aborted) { clear(); reject(new DOMException('Carga cancelada', 'AbortError')); return; }
        xhr.send(file);
      });
    },
  };
}
