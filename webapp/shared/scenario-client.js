import {API_VERSION} from './solver-client.js';
import {validateNodes} from './solver-input.js';

export async function loadHackathonScenario(dataset = 'competition', fetchImpl = fetch) {
  if (!['competition', 'evaluation'].includes(dataset)) throw new Error('Elige un caso de la hackatón.');
  const response = await fetchImpl(`/scenarios/hackathon?dataset=${dataset}`, {cache: 'no-store'});
  const body = await response.json().catch(() => {
    throw new Error('No se pudo cargar el caso de la hackatón. Abre la app desde el servidor local del proyecto para acceder al dataset.');
  });
  if (!response.ok || body?.api_version !== API_VERSION || !body.scenario) {
    throw new Error(body?.error?.message || 'No se pudo cargar el caso de la hackatón. Comprueba los CSV en data/ del servidor o carga el archivo de ubicaciones.');
  }
  validateNodes(body.scenario.nodes);
  return body.scenario;
}

export async function loadHistoricalCase({dataset = 'competition', simulation, energy_profile_id} = {}, fetchImpl = fetch) {
  const response = await fetchImpl('/scenarios/hackathon', {
    method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({dataset, ...(simulation ? {simulation} : {}), ...(energy_profile_id ? {energy_profile_id} : {})}),
  });
  const body = await response.json().catch(() => {
    throw new Error('No se pudo cargar el caso histórico. Comprueba que el servidor local del proyecto esté disponible.');
  });
  if (!response.ok || body?.api_version !== API_VERSION || !body.scenario || body.profile?.status !== 'ready') {
    throw new Error(body?.error?.message || 'No se pudo cargar el caso histórico. Comprueba los CSV y la red de Ann Arbor en el servidor.');
  }
  validateNodes(body.scenario.nodes);
  return body;
}
