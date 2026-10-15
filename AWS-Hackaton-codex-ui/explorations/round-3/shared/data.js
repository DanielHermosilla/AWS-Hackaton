// Fixtures for visual exploration. Not an optimizer, backend contract or prediction.
import { validateScenario } from './safe.js';

const response = await fetch(new URL('./fixture.local.json', import.meta.url));
if (!response.ok) throw new Error('Falta el escenario local de demostración.');
// El escenario puede venir de un CSV externo: se valida antes de cualquier render.
export const { SCENARIO, VEHICLES, NODES, ROUTES } = validateScenario(await response.json());
export const nodeById = id => NODES.find(node => node.id === id);
export const routeById = id => ROUTES.find(route => route.vehicleId === id);
export const number = (n, digits = 1) => Number.isFinite(n) ? n.toLocaleString('es-CL', {maximumFractionDigits: digits}) : '—';