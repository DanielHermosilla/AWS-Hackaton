import './core.js';
import { buildVisualOverview } from './visual-model.js';
import { planHref } from '../../home-navigation.js';

const main = document.getElementById('home-main');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const link = vehicle => {
  const url = new URL(planHref);
  url.searchParams.set('vehicle', vehicle.id);
  return esc(url.href);
};
const color = vehicle => /^#[0-9a-f]{6}$/i.test(vehicle.color) ? vehicle.color : '#708096';
const mark = vehicle => `data-viz-vehicle="${esc(vehicle.id)}" style="--vehicle-color:${color(vehicle)}"`;

if (!main.classList.contains('error-main')) {
  try {
    const data = await import('../../shared/data.js');
    const model = buildVisualOverview(data);
    const num = value => Number.isFinite(value) ? data.number(value) : '—';
    const energyMax = Math.max(2, Math.ceil(Math.max(...model.fleet.map(v => Number.isFinite(v.energyKwh) ? v.energyKwh : 0)) / 2) * 2);
    const percent = value => `${num(value)} %`;
    const vehicleLink = (vehicle, content, className = '') =>
      `<a class="${className}" ${mark(vehicle)} href="${link(vehicle)}">${content}</a>`;
    const track = (value, maximum, extra = '') => {
      const valid = Number.isFinite(value) && value >= 0 && value <= maximum && maximum > 0;
      return `<span class="viz-track" aria-hidden="true">${valid ? `<span class="viz-fill viz-ink" style="width:${value / maximum * 100}%"></span>` : ''}${extra}</span>`;
    };
    const initialTick = vehicle => Number.isFinite(vehicle.initialSoc) && vehicle.initialSoc >= 0 && vehicle.initialSoc <= 100
      ? `<span class="initial-tick" style="left:${vehicle.initialSoc}%" aria-hidden="true"></span>` : '';
    const legend = () => `<div class="viz-legend">${model.fleet.map(vehicle => vehicleLink(vehicle,
      `<span class="legend-name"><i class="vehicle-dot viz-ink" aria-hidden="true"></i>${esc(vehicle.name)}</span><strong>${num(vehicle.assigned)} <small>· ${percent(vehicle.assignmentShare)}</small></strong>`, 'legend-row')).join('')}
      <div class="legend-row legend-unassigned"><span>Sin asignar</span><strong>${num(model.unassigned)}</strong></div></div>`;
    const distributionFallback = () => `<p class="chart-empty">${model.stats.visits === 0 ? 'Este escenario no contiene locales.' : 'Hay asignaciones compartidas o no representadas. Revisa los vehículos en el Plan.'}</p>`;

    function assignmentRing() {
      if (!model.assignmentDistributionValid) return distributionFallback();
      let offset = 0;
      const arcs = model.fleet.map(vehicle => {
        const arc = vehicle.assignmentShare > 0 ? `<a href="${link(vehicle)}" tabindex="-1" aria-hidden="true" ${mark(vehicle)}><circle class="ring-segment viz-ink" cx="110" cy="110" r="82" pathLength="100" stroke-dasharray="${vehicle.assignmentShare} 100" stroke-dashoffset="${-offset}"/></a>` : '';
        offset += vehicle.assignmentShare;
        return arc;
      }).join('');
      return `<div class="ring-figure"><svg viewBox="0 0 220 220" aria-hidden="true"><circle class="ring-track" cx="110" cy="110" r="82"/><g transform="rotate(-90 110 110)">${arcs}</g></svg>
        <div class="ring-center"><strong>${num(model.stats.assigned)}<small> / ${num(model.stats.visits)}</small></strong><span>locales asignados</span></div></div>${legend()}`;
    }

    function assignmentBar() {
      if (!model.assignmentDistributionValid) return distributionFallback();
      return `<div class="allocation-track" aria-label="Distribución de los locales del escenario">${model.fleet.filter(vehicle => vehicle.assignmentShare > 0).map(vehicle =>
        `<a data-viz-vehicle="${esc(vehicle.id)}" href="${link(vehicle)}" class="allocation-segment" style="--vehicle-color:${color(vehicle)};width:${vehicle.assignmentShare}%" aria-label="${esc(vehicle.name)}: ${num(vehicle.assigned)} locales, ${percent(vehicle.assignmentShare)}"><span class="viz-ink"></span></a>`).join('')}
        ${model.unassigned > 0 ? `<span class="allocation-unassigned" style="width:${model.unassigned / model.stats.visits * 100}%" aria-label="${num(model.unassigned)} sin asignar"></span>` : ''}</div>${legend()}`;
    }

    function energyBars() {
      return `<div class="energy-chart"><div class="chart-axis"><span>0</span><span>${num(energyMax)} kWh</span></div>
        ${model.fleet.map(vehicle => vehicleLink(vehicle, `<span class="chart-row-label"><span>${esc(vehicle.name)}</span><strong>${num(vehicle.energyKwh)} <small>kWh</small></strong></span>${track(vehicle.energyKwh, energyMax)}`, 'bar-row')).join('')}
        <p class="chart-caption">Consumo por vehículo · ejemplo</p></div>`;
    }

    function socBars() {
      return `<div class="soc-chart"><div class="chart-axis"><span>0 %</span><span>100 %</span></div>
        ${model.fleet.map(vehicle => vehicleLink(vehicle, `<span class="chart-row-label"><span>${esc(vehicle.name)}</span><strong>${percent(vehicle.finalSoc)}</strong></span>${track(vehicle.finalSoc, 100, initialTick(vehicle))}
          <span class="bar-meta"><span>${num(vehicle.assigned)} locales</span><span>Salida ${percent(vehicle.initialSoc)}</span></span>${!vehicle.socInScale && Number.isFinite(vehicle.finalSoc) ? '<span class="scale-note">Valor fuera de escala</span>' : ''}`, 'bar-row')).join('')}
        <p class="chart-caption"><i class="tick-key" aria-hidden="true"></i> Marca de salida · Regreso ilustrativo</p></div>`;
    }

    function matrix() {
      return `<div class="matrix-scroll" role="region" aria-label="Comparación de vehículos" tabindex="0"><table class="chart-matrix">
        <caption class="sr-only">Asignación, consumo y batería al regreso del plan ilustrativo</caption>
        <thead><tr><th scope="col">Vehículo</th><th scope="col">Locales<br><small>sobre ${num(model.stats.visits)}</small></th><th scope="col">Consumo<br><small>0–${num(energyMax)} kWh · ejemplo</small></th><th scope="col">Regreso<br><small>0–100 % · ejemplo</small></th></tr></thead>
        <tbody>${model.fleet.map(vehicle => `<tr ${mark(vehicle)}><th scope="row"><a href="${link(vehicle)}"><i class="vehicle-dot viz-ink" aria-hidden="true"></i>${esc(vehicle.name)} <span aria-hidden="true">↗</span><small>${esc(vehicle.model)}</small></a></th>
          <td><strong>${num(vehicle.assigned)}</strong><small>${percent(vehicle.assignmentShare)}</small>${track(vehicle.assigned, model.stats.visits)}</td>
          <td><strong>${num(vehicle.energyKwh)}</strong><small>kWh</small>${track(vehicle.energyKwh, energyMax)}</td>
          <td><strong>${percent(vehicle.finalSoc)}</strong>${track(vehicle.finalSoc, 100, initialTick(vehicle))}<small class="matrix-initial">Salida ${percent(vehicle.initialSoc)}</small></td></tr>`).join('')}</tbody>
        <tfoot><tr><th scope="row">Total del plan</th><td>${num(model.stats.assigned)}<small> / ${num(model.stats.visits)}</small></td><td>${num(model.stats.energyKwh)}<small> kWh</small></td><td aria-label="No se suman porcentajes de batería">—</td></tr></tfoot>
      </table></div>${model.overlapCount ? '<p class="chart-caption">Hay locales asignados a más de un vehículo. El total cuenta locales únicos.</p>' : ''}`;
    }

    function gauges() {
      return `<div class="gauge-grid">${model.fleet.map(vehicle => {
        const angle = Math.PI * (1 - vehicle.initialSoc / 100);
        const tick = Number.isFinite(vehicle.initialSoc) && vehicle.initialSoc >= 0 && vehicle.initialSoc <= 100
          ? `<line class="gauge-initial" x1="${110 + 81 * Math.cos(angle)}" y1="${110 - 81 * Math.sin(angle)}" x2="${110 + 100 * Math.cos(angle)}" y2="${110 - 100 * Math.sin(angle)}"/>` : '';
        return vehicleLink(vehicle, `<span class="gauge-name"><i class="vehicle-dot viz-ink" aria-hidden="true"></i>${esc(vehicle.name)}<span aria-hidden="true">↗</span></span>
          <span class="gauge-figure"><svg viewBox="0 0 220 138" aria-hidden="true"><path class="gauge-track" d="M20 110 A90 90 0 0 1 200 110"/>
            ${vehicle.socInScale && vehicle.finalSoc > 0 ? `<path class="gauge-fill viz-ink" d="M20 110 A90 90 0 0 1 200 110" pathLength="100" stroke-dasharray="${vehicle.finalSoc} 100"/>` : ''}${tick}</svg>
            <span class="gauge-value"><strong>${num(vehicle.finalSoc)}<small>%</small></strong><span>al regreso · ejemplo</span></span>
          </span><span class="gauge-axis"><span>0 %</span><span>100 %</span></span>
          <span class="gauge-departure"><i class="tick-key" aria-hidden="true"></i>Salida ${percent(vehicle.initialSoc)}</span>
          ${!vehicle.socInScale && Number.isFinite(vehicle.finalSoc) ? '<span class="scale-note">Valor fuera de escala</span>' : ''}
          <span class="gauge-facts"><span><strong>${num(vehicle.assigned)}</strong> locales</span><span><strong>${num(vehicle.chargeStops)}</strong> recarga${vehicle.chargeStops === 1 ? '' : 's'}</span></span>`, 'gauge-card');
      }).join('')}</div>`;
    }

    for (const node of main.querySelectorAll('[data-visual-value]')) {
      const value = node.dataset.visualValue.split('.').reduce((obj, key) => obj?.[key], model);
      node.textContent = typeof value === 'number' ? num(value) : value ?? '—';
    }
    const widgets = { 'assignment-ring': assignmentRing, 'assignment-bar': assignmentBar, 'energy-bars': energyBars, 'soc-bars': socBars, matrix, 'soc-gauges': gauges };
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
    main.dataset.visualReady = 'true';
  } catch (error) {
    console.error('No se pudieron preparar los gráficos:', error);
    for (const node of main.querySelectorAll('[data-visual]')) node.innerHTML = '<p class="chart-empty">No se pudo preparar esta visualización. Puedes consultar los datos en el Plan.</p>';
    main.dataset.visualReady = 'error';
  }
}
