// Inicio and Plan consume the same adapted result or explicitly selected example.
import { applyDataProvenance, DATA_SOURCE, SCENARIO, VEHICLES, NODES, ROUTES, RUN_INFO, SOURCE_DETAILS, number, visitIdsForRoute as visitsOf, routeById, chargeCount } from './shared/data.js';
import { readPlanContext } from './state.js';
import { planHref } from './home-navigation.js';
import { escapeHtml as esc } from './shared/html.js';

applyDataProvenance();

const main = document.getElementById('home-main');
const pending = DATA_SOURCE === 'pending';
const noSolution = RUN_INFO?.hasSolution === false;
const finite = value => Number.isFinite(value) ? value : null;
const count = value => number(value, 0);
const percent = value => Number.isFinite(value) ? `${number(value)} %` : '—';
const ratio = (part, whole) => Number.isFinite(part) && part >= 0 && whole > 0 ? part / whole * 100 : null;
const inScale = (value, max) => Number.isFinite(value) && value >= 0 && value <= max && max > 0;
const planLink = (params = {}) => {
  const url = new URL(planHref);
  if (RUN_INFO) url.searchParams.set('run', RUN_INFO.runId);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.href;
};

// ---- Model -------------------------------------------------------------
const palette = ['#1664ec', '#8152d9', '#0f8a6a', '#c2571a', '#b23a7a', '#5b6b7f'];
const nodeById = new Map(NODES.map(node => [node.id, node]));
const stopsOf = route => Array.isArray(route?.stops) ? route.stops : [];

const visitTotal = new Set(NODES.filter(node => node.type === 'visit').map(node => node.id)).size;
const stationTotal = NODES.filter(node => node.type === 'charger').length;
const assignedTotal = RUN_INFO ? RUN_INFO.kpis.served_deliveries ?? null
  : new Set(ROUTES.flatMap(route => [...visitsOf(route)])).size;
const unassigned = assignedTotal === null ? null : Math.max(0, visitTotal - assignedTotal);
// Zero is a valid total; a missing value on any route makes the total unavailable.
const energyTotal = RUN_INFO ? RUN_INFO.totalEnergyKwh
  : ROUTES.length && ROUTES.every(route => Number.isFinite(route?.energyKwh))
    ? ROUTES.reduce((sum, route) => sum + route.energyKwh, 0) : null;
const chargeCounts = ROUTES.map(chargeCount);
const chargeTotal = RUN_INFO ? RUN_INFO.kpis.charging_stops ?? null
  : !noSolution && chargeCounts.every(Number.isFinite) ? chargeCounts.reduce((sum, value) => sum + value, 0) : null;

const owners = new Map();
const fleet = VEHICLES.map((vehicle, index) => {
  const route = routeById(vehicle.id);
  const visits = route ? visitsOf(route) : null;
  for (const id of visits || []) owners.set(id, (owners.get(id) || 0) + 1);
  const assigned = visits ? visits.size : null;
  return {
    id: String(vehicle.id ?? ''),
    name: String(vehicle.name ?? vehicle.id ?? 'Vehículo'),
    model: String(vehicle.model ?? ''),
    color: /^#[0-9a-f]{6}$/i.test(vehicle.color) ? vehicle.color : palette[index % palette.length],
    active: !!route && route.active !== false,
    hasRoute: !!route,
    initialSoc: finite(vehicle.initialSoc),
    assigned,
    assignmentShare: ratio(assigned, visitTotal),
    energyKwh: route ? finite(route.energyKwh) : null,
    finalSoc: route ? finite(route.finalSoc) : null,
    chargeStops: route ? chargeCount(route) : null,
  };
});
const active = fleet.filter(vehicle => vehicle.active);
const overlapCount = [...owners.values()].filter(owned => owned > 1).length;
const distributed = active.reduce((sum, vehicle) => sum + vehicle.assigned, 0);
const assignmentValid = visitTotal > 0 && overlapCount === 0 && distributed === assignedTotal;
const withRoute = fleet.filter(vehicle => vehicle.hasRoute);
const representedEnergy = withRoute.reduce((sum, vehicle) => sum + (vehicle.energyKwh ?? 0), 0);
const energyValid = energyTotal !== null
  && withRoute.every(vehicle => vehicle.energyKwh !== null)
  && Math.abs(representedEnergy - energyTotal) < 1e-9 * Math.max(1, Math.abs(energyTotal));
const energyMin = Math.min(0, Math.floor(Math.min(0, ...withRoute.map(vehicle => vehicle.energyKwh ?? 0)) / 2) * 2);
const energyMax = Math.max(energyMin < 0 ? 0 : 2, Math.ceil(Math.max(0, ...withRoute.map(vehicle => vehicle.energyKwh ?? 0)) / 2) * 2);
const energyRange = energyMax - energyMin;

// Session context saved by the Plan; invalid or foreign context is ignored.
function resumeFrom(saved) {
  const fallback = {
    title: 'Tu plan',
    cta: 'Abrir plan',
    context: `${SCENARIO.name} · ${count(VEHICLES.length)} vehículos · ${SOURCE_DETAILS?.context || 'Datos de ejemplo'}`,
  };
  if (!saved || typeof saved !== 'object' || saved.scenario !== SCENARIO.id) return fallback;
  const vehicle = fleet.find(item => item.id === saved.vehicle);
  const stopRoute = routeById(saved.stop?.vehicleId);
  const stop = saved.stop && Number.isInteger(saved.stop.index) ? stopsOf(stopRoute)[saved.stop.index] : null;
  const valid = (saved.vehicle === null || !!vehicle)
    && ['fleet', 'stops', 'chargers'].includes(saved.tab)
    && (saved.stop === null || (!!stop && saved.stop.vehicleId === saved.vehicle))
    && typeof saved.chargers === 'boolean';
  if (!valid) return fallback;
  const node = stop ? nodeById.get(stop.nodeId) : null;
  const stopLabel = !stop ? null : node?.type === 'base'
    ? (saved.stop.index === 0 ? 'Salida de base' : saved.stop.index === stopsOf(stopRoute).length - 1 ? 'Regreso a base' : 'Base')
    : node?.label || stop.nodeId;
  return {
    title: 'Donde lo dejaste',
    cta: 'Continuar plan',
    context: [vehicle?.name || 'Toda la flota', { fleet: 'Vehículos', stops: 'Paradas', chargers: 'Cargadores' }[saved.tab], stopLabel,
      saved.chargers ? 'Estaciones visibles' : null].filter(Boolean).join(' · '),
  };
}
// ---- Text, links and the shell's single Continue action -----------------
const values = {
  scenario: SCENARIO.name,
  assignedFleet: assignedTotal === null ? '—' : count(active.filter(vehicle => vehicle.assigned > 0).length),
  vehicles: count(VEHICLES.length),
  assigned: count(assignedTotal),
  visits: count(visitTotal),
  energy: number(energyTotal),
  chargeStops: count(chargeTotal),
  stations: count(stationTotal),
};
for (const element of main.querySelectorAll('[data-value]')) {
  element.textContent = pending && element.dataset.value !== 'scenario' ? '—' : values[element.dataset.value] ?? '—';
}
const links = { fleet: planLink({ tab: 'fleet' }), stops: planLink({ tab: 'stops' }), chargers: planLink({ chargers: '1' }) };
for (const anchor of main.querySelectorAll('[data-link]')) anchor.href = links[anchor.dataset.link];

if (RUN_INFO || pending) {
  main.querySelector('#delivery-heading').textContent = 'Entregas del modelo';
  main.querySelector('.console-deliveries .chart-caption').textContent = 'Servicio explícito por vehículo';
  main.querySelector('.console-fleet .panel-foot p').textContent = pending
    ? 'Carga y calcula una instancia para ver la batería de regreso.'
    : 'Batería informada por el motor. La marca señala la salida.';
  main.querySelector('.console-energy .chart-caption').textContent = energyTotal === null
    ? 'Consumo no disponible para esta ejecución' : 'Energía informada por el motor';
  main.querySelector('.vision-footer-top > p').textContent = pending
    ? 'Sin resultado. Los indicadores aparecerán después del cálculo.'
    : 'Resultado del motor · Entregas previstas por el modelo, sin telemetría en vivo';
  main.querySelector('.data-note [data-motion-detail] p').textContent = pending
    ? 'Selecciona una entrada y calcula el plan. Los datos de ejemplo se consultan como una fuente separada.'
    : 'Solo se cuentan los locales con servicio explícito en el resultado. Pasar por un local no implica atenderlo. Cada local cuenta una sola vez; las paradas repetidas conservan su orden. La batería se convierte de kWh a porcentaje con la capacidad configurada. “—” indica información no disponible. La energía de recarga es la incorporada a la batería, no la electricidad comprada. La factibilidad tiene el alcance informado por el proveedor; no garantiza el consumo real. La disponibilidad de estaciones no está verificada.';
}

// The shell owns the only Continue link (#continue-plan); only its text is updated.
function renderResume() {
  const resume = resumeFrom(readPlanContext());
  main.querySelector('[data-value="resumeTitle"]').textContent = `${resume.title}:`;
  main.querySelector('[data-value="resumeContext"]').textContent = resume.context;
  const continueLink = document.getElementById('continue-plan');
  if (continueLink) {
    continueLink.textContent = resume.cta;
    continueLink.title = resume.context;
    document.getElementById('continue-plan-description').textContent = resume.context;
  }
}
renderResume();
addEventListener('pageshow', event => { if (event.persisted) renderResume(); });

// ---- Visualizations ------------------------------------------------------
// Vehicles without a route open the Plan fleet list instead of an empty selection.
const vehicleHref = vehicle => esc(vehicle.active ? planLink({ vehicle: vehicle.id }) : links.fleet);
const mark = (vehicle, style = '') => `data-viz-vehicle="${esc(vehicle.id)}" style="--vehicle-color:${vehicle.color};${style}"`;
const energyTrack = value => {
  const baseline = -energyMin / energyRange * 100;
  const fill = Number.isFinite(value)
    ? `<span class="viz-fill viz-ink" style="left:${(Math.min(0, value) - energyMin) / energyRange * 100}%;width:${Math.abs(value) / energyRange * 100}%"></span>` : '';
  return `<span class="viz-track${energyMin < 0 ? ' signed' : ''}" aria-hidden="true">${fill}<i class="energy-zero" style="left:${baseline}%"></i></span>`;
};
const noRoute = `<small>${noSolution ? 'Sin resultado' : 'Sin recorrido'}</small>`;

function gauges() {
  if (!fleet.length) return `<p class="chart-empty">${pending ? 'Aún no hay un resultado de flota.' : 'Esta ejecución no contiene vehículos.'}</p>`;
  return `<div class="gauge-grid">${fleet.map(vehicle => {
    const start = vehicle.initialSoc;
    // Departure battery mark on the 0–100 % arc.
    const angle = Math.PI * (1 - (start ?? 0) / 100);
    const at = radius => [110 + radius * Math.cos(angle), 110 - radius * Math.sin(angle)].map(n => n.toFixed(2));
    const [x1, y1] = at(81);
    const [x2, y2] = at(100);
    const tick = inScale(start, 100) ? `<line class="gauge-initial" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>` : '';
    const fill = inScale(vehicle.finalSoc, 100) && vehicle.finalSoc > 0
      ? `<path class="gauge-fill viz-ink" d="M20 110 A90 90 0 0 1 200 110" pathLength="100" stroke-dasharray="${vehicle.finalSoc} 100"/>` : '';
    const value = vehicle.finalSoc === null ? '—' : `${number(vehicle.finalSoc)}<small>%</small>`;
    const facts = vehicle.active
      ? `<span><strong>${count(vehicle.assigned)}</strong> locales</span>${RUN_INFO ? '' : `<span><strong>${count(vehicle.chargeStops)}</strong> recarga${vehicle.chargeStops === 1 ? '' : 's'}</span>`}`
      : `<span>${noSolution ? 'Sin resultado para este vehículo' : 'Sin recorrido en este plan'}</span>`;
    return `<a class="gauge-card${vehicle.active ? '' : ' is-inactive'}" ${mark(vehicle)} href="${vehicleHref(vehicle)}">
      <span class="gauge-name"><i class="vehicle-dot viz-ink" aria-hidden="true"></i>${esc(vehicle.name)}<span aria-hidden="true">↗</span></span>
      <span class="gauge-figure"><svg viewBox="0 0 220 138" aria-hidden="true"><path class="gauge-track" d="M20 110 A90 90 0 0 1 200 110"/>${fill}${tick}</svg>
        <span class="gauge-value"><strong>${value}</strong><span>${vehicle.finalSoc === null ? 'sin datos de regreso' : vehicle.active ? 'al regreso' : 'en base'}</span></span></span>
      <span class="gauge-axis" aria-hidden="true"><span>0 %</span><span>100 %</span></span>
      <span class="gauge-departure"><i class="tick-key" aria-hidden="true"></i>Salida ${percent(start)}</span>
      ${vehicle.finalSoc !== null && !inScale(vehicle.finalSoc, 100) ? '<span class="scale-note">Valor fuera de escala</span>' : ''}
      <span class="gauge-facts">${facts}</span></a>`;
  }).join('')}</div>`;
}

function assignment() {
  if (pending) return '<p class="chart-empty">Aún no hay entregas calculadas.</p>';
  if (noSolution) return '<p class="chart-empty">No hay una solución disponible para evaluar las entregas.</p>';
  if (RUN_INFO && RUN_INFO.feasible !== true) return '<p class="chart-empty">Las entregas candidatas no están validadas. Revisa las comprobaciones en los datos de la ejecución.</p>';
  // The bar is decorative for assistive technology: the legend carries the same links and numbers.
  const segments = fleet.filter(vehicle => vehicle.assigned > 0).map(vehicle =>
    `<a class="allocation-segment" tabindex="-1" href="${vehicleHref(vehicle)}" ${mark(vehicle, `width:${vehicle.assignmentShare}%`)}><span class="viz-ink"></span></a>`).join('');
  const rest = unassigned > 0 ? `<span class="allocation-unassigned" style="width:${ratio(unassigned, visitTotal)}%"></span>` : '';
  const bar = assignmentValid
    ? `<div class="allocation-track" aria-hidden="true">${segments}${rest}</div>`
    : `<p class="chart-empty">${visitTotal === 0 ? 'Este escenario no contiene locales.'
      : 'Hay locales asignados a más de un vehículo o a recorridos fuera de la flota. El total cuenta locales únicos; revisa los vehículos en el Plan.'}</p>`;
  const rows = fleet.map(vehicle => `<li><a class="legend-row" ${mark(vehicle)} href="${vehicleHref(vehicle)}">
    <span class="legend-name"><i class="vehicle-dot viz-ink" aria-hidden="true"></i>${esc(vehicle.name)}</span>
    <strong>${vehicle.active ? `${count(vehicle.assigned)} <span class="sr-only">locales,</span><small>· ${percent(vehicle.assignmentShare)}</small>` : noRoute}</strong></a></li>`).join('');
  return `${bar}<ul class="viz-legend">${rows}<li class="legend-row legend-unassigned"><span>${RUN_INFO ? 'Pendientes' : 'Sin asignar'}</span><strong>${count(unassigned)}</strong></li></ul>`;
}

function energy() {
  if (pending) return '<p class="chart-empty">Aún no hay un resultado energético.</p>';
  if (noSolution) return '<p class="chart-empty">No hay una solución cuyo consumo pueda presentarse.</p>';
  const rows = fleet.map(vehicle => `<a class="bar-row" ${mark(vehicle)} href="${vehicleHref(vehicle)}">
    <span class="chart-row-label"><span>${esc(vehicle.name)}</span><strong>${vehicle.hasRoute ? `${number(vehicle.energyKwh)} <small>kWh</small>` : noRoute}</strong></span>${energyTrack(vehicle.energyKwh)}</a>`).join('');
  const note = energyValid ? ''
    : energyTotal === null ? RUN_INFO ? 'Consumo total no disponible en esta ejecución.' : 'Consumo no disponible: al menos un recorrido no informa energía.'
    : withRoute.some(vehicle => vehicle.energyKwh === null) ? 'El desglose de consumo por vehículo no está completo.'
    : 'Los consumos por vehículo no coinciden con el total del plan. Revísalos en el Plan.';
  const anyEnergy = withRoute.some(vehicle => vehicle.energyKwh !== null);
  return `<div class="energy-chart">${anyEnergy ? `<div class="chart-axis" aria-hidden="true"><span>${number(energyMin)}</span><span>${number(energyMax)} kWh</span></div>` : ''}${rows}
    ${note ? `<p class="chart-caption">${note}</p>` : ''}
    ${energyMin < 0 ? '<p class="chart-caption">Los valores negativos conservan el balance regenerativo informado por el motor.</p>' : ''}</div>`;
}

const widgets = { 'soc-gauges': gauges, 'assignment-bar': assignment, 'energy-bars': energy };
for (const node of main.querySelectorAll('[data-visual]')) node.innerHTML = widgets[node.dataset.visual]?.() || '';

// Cross-highlighting changes chart marks and borders, never text contrast.
let hovered = null;
let focused = null;
const vehicleAt = element => element instanceof Element ? element.closest('[data-viz-vehicle]')?.dataset.vizVehicle || null : null;
const highlight = () => {
  const id = hovered || focused;
  for (const element of main.querySelectorAll('[data-viz-vehicle]')) {
    element.classList.toggle('is-other', !!id && element.dataset.vizVehicle !== id);
    element.classList.toggle('is-highlighted', !!id && element.dataset.vizVehicle === id);
  }
};
main.addEventListener('pointerover', event => { hovered = vehicleAt(event.target); highlight(); });
main.addEventListener('pointerleave', () => { hovered = null; highlight(); });
main.addEventListener('focusin', event => { focused = vehicleAt(event.target); highlight(); });
main.addEventListener('focusout', event => { focused = vehicleAt(event.relatedTarget); highlight(); });

// Optional disclosure motion. Honors the OS setting and the shared preference
// (html[data-reduced-motion], updated live with 'zmd:preferences-changed').
const osReduced = matchMedia('(prefers-reduced-motion: reduce)');
const reduceMotion = () => osReduced.matches || document.documentElement.dataset.reducedMotion === 'true';
const running = new Set();
const settleMotion = () => { for (const animation of running) animation.finish(); running.clear(); };
osReduced.addEventListener('change', settleMotion);
document.addEventListener('zmd:preferences-changed', () => { if (reduceMotion()) settleMotion(); });
for (const note of main.querySelectorAll('.data-note')) {
  const detail = note.querySelector('[data-motion-detail]');
  note.addEventListener('toggle', () => {
    if (!note.open || !detail?.animate || reduceMotion()) return;
    const animation = detail.animate(
      [{ opacity: 0, transform: 'translateY(-3px)' }, { opacity: 1, transform: 'none' }],
      { duration: 150, easing: 'cubic-bezier(.22, 1, .36, 1)' });
    running.add(animation);
    animation.onfinish = animation.oncancel = () => running.delete(animation);
  });
}
main.dataset.visualReady = 'true';
