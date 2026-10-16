import {escapeHtml as escape} from './shared/html.js';
import {readExecution} from './shared/solver-client.js';
import {buildPlanSummary} from './shared/plan-summary-model.js';

const number = (value, unit = '') => Number.isFinite(value)
  ? `${value.toLocaleString('es-CL', {maximumFractionDigits: 6})}${unit ? ` ${unit}` : ''}` : 'No disponible';
const notes = values => [...new Set(values)].map(value => `<p class="summary-note">${escape(value)}</p>`).join('');
const facts = rows => `<dl class="summary-facts">${rows.map(row =>
  `<div><dt>${escape(row.label)}</dt><dd>${escape(row.value)}${row.reason ? `<small>${escape(row.reason)}</small>` : ''}</dd></div>`).join('')}</dl>`;
const section = group => `<section class="summary-section"><h2>${escape(group.title)}</h2>${facts(group.rows)}${notes(group.notes)}</section>`;

function operationalNotes(operations) {
  const values = [];
  if (Number.isFinite(operations.service_seconds)) values.push(`Servicio por defecto: ${number(operations.service_seconds, 's')}${Object.keys(operations.service_seconds_by_customer || {}).length ? ', con tiempos específicos por destino' : ''}.`);
  if (Number.isFinite(operations.max_route_seconds)) values.push(`Límite por ruta: ${number(operations.max_route_seconds, 's')}.`);
  if (Number.isFinite(operations.assumed_speed_kph)) values.push(`Velocidad supuesta en arcos sin tiempo: ${number(operations.assumed_speed_kph, 'km/h')}.`);
  if (typeof operations.include_charging_time === 'boolean') values.push(operations.include_charging_time
    ? `Recarga incluida en los tiempos${Number.isFinite(operations.charging_power_kw) ? `, con ${number(operations.charging_power_kw, 'kW')} por defecto` : ''}${Object.keys(operations.charging_power_kw_by_station || {}).length ? ' y potencias específicas por estación' : ''}${Number.isFinite(operations.charging_efficiency) ? `; eficiencia ${number(operations.charging_efficiency * 100, '%')}` : ''}.`
    : 'Los tiempos no incluyen la duración de recarga.');
  if (Number.isFinite(operations.energy_margin_fraction)) values.push(`Margen energético: ${number(operations.energy_margin_fraction * 100, '%')}.`);
  if (Number.isFinite(operations.final_reserve_soc)) values.push(`SoC mínimo al regreso: ${number(operations.final_reserve_soc * 100, '%')}.`);
  if (operations.use_customer_time_windows) values.push('Se aplican las ventanas de clientes de la instancia.');
  if (operations.disabled_charger_ids?.length) values.push(`Cargadores deshabilitados: ${operations.disabled_charger_ids.join(', ')}.`);
  return values.join(' ');
}

function phaseTable(phases) {
  if (!phases.length) return '<p class="summary-note">No hay fases informadas.</p>';
  const value = (phase, label) => escape(phase.rows.find(row => row.label === label)?.value || 'No disponible');
  return `<table class="summary-phase-table"><caption>Certificados independientes. El gap relativo se expresa como fracción.</caption>
    <thead><tr><th scope="col">Fase / estado</th><th scope="col">Mejor solución / cota</th><th scope="col">Gap absoluto / relativo</th><th scope="col">Óptimo de fase</th><th scope="col">Terminación / tiempo</th></tr></thead>
    <tbody>${phases.map(phase => `<tr><th scope="row">${escape(phase.title.replace('Fase: ', ''))}<small>${escape(phase.status)}</small></th>
      <td data-label="Mejor solución / cota">${value(phase, 'Mejor solución')}<small>Cota: ${value(phase, 'Cota')}</small></td>
      <td data-label="Gap absoluto / relativo">${value(phase, 'Gap absoluto')}<small>Relativo: ${value(phase, 'Gap relativo (fracción)')}</small></td>
      <td data-label="Óptimo de fase">${value(phase, 'Óptimo de fase reportado por el solver')}</td>
      <td data-label="Terminación / tiempo">${value(phase, 'Terminación')}<small>${value(phase, 'Tiempo de la fase')}</small></td></tr>`).join('')}</tbody></table>`;
}

function routeSection(route, index) {
  const vehicle = route.vehicle;
  return `<section class="summary-section summary-route" aria-labelledby="summary-route-${index}">
    <h2 id="summary-route-${index}">${escape(route.label)} <span>${escape(route.vehicleId)}</span></h2>
    <p class="summary-note">Capacidad ${escape(number(vehicle.battery_capacity_kwh, 'kWh'))} · Reserva ${escape(number(vehicle.reserve_kwh, 'kWh'))} · SoC inicial ${escape(number(vehicle.initial_soc * 100, '%'))}</p>
    ${facts([
      {label: 'Energía neta de batería', value: number(route.energyKwh, 'kWh')},
      {label: 'Distancia', value: number(route.distanceKm, 'km')},
      {label: 'Duración operacional', value: number(route.durationSeconds, 's')},
    ])}
    <table class="summary-stops">
      <caption>Secuencia de ${escape(route.label)} · servicio explícito y batería por parada.</caption>
      <thead><tr><th scope="col">Paso y ubicación</th><th scope="col">Servicio</th><th scope="col">Llegada<br>kWh</th><th scope="col">Salida<br>kWh</th><th scope="col">Recarga<br>kWh</th></tr></thead>
      <tbody>${route.steps.map(step => `<tr>
        <th scope="row"><span class="summary-stop-title">${step.position + 1}. ${escape(step.label)}</span>${step.label !== step.node_id ? `<small>ID ${escape(step.node_id)}</small>` : ''}${Number.isFinite(step.arrival_seconds) ? `<small>Llegada desde t=0: ${escape(number(step.arrival_seconds, 's'))}</small>` : ''}</th>
        <td data-label="Servicio">${escape(step.service)}${Number.isFinite(step.service_duration_seconds) && step.service_duration_seconds > 0 ? `<small>Servicio: ${escape(number(step.service_duration_seconds, 's'))}</small>` : ''}</td>
        <td data-label="Batería de llegada · kWh">${escape(number(step.arrival_energy_kwh))}</td>
        <td data-label="Batería de salida · kWh">${escape(number(step.departure_energy_kwh))}</td>
        <td data-label="Recarga · kWh">${escape(number(step.charge_kwh))}${Number.isFinite(step.charging_duration_seconds) && step.charging_duration_seconds > 0 ? `<small>${escape(number(step.charging_duration_seconds, 's'))}</small>` : ''}</td>
      </tr>`).join('')}</tbody>
    </table>
  </section>`;
}

// Pure rendering keeps imported strings escaped and can be checked without a
// browser. The dialog and print use this same view of the same response.
export function renderPlanSummary(model) {
  const heading = `<header class="summary-heading"><p class="summary-brand">ZMD Mobility · Planificación de reparto</p>
    <h1 id="summary-heading" tabindex="-1">Resumen ${model.available ? 'del plan' : 'de la ejecución'}</h1>
    ${model.available ? `<p class="summary-scenario">${escape(model.scenarioName)}</p>` : ''}
    <p>Las entregas son previstas: no confirman entregas realizadas en terreno.</p></header>`;
  if (!model.available) return `${heading}<section class="summary-empty"><h2>${escape(model.freshness.title)}</h2><p>${escape(model.message)}</p></section>`;
  const group = title => model.sections.find(item => item.title === title);
  const metrics = group('Resultados del motor');
  const timings = group('Tiempos de cómputo');
  const find = (items, label) => items.rows.find(row => row.label === label);
  const deliveries = find(metrics, 'Entregas planificadas');
  const demand = find(metrics, 'Destinos de la instancia');
  const energy = find(metrics, 'Energía neta de batería');
  const hero = [
    {...deliveries, value: `${deliveries.value} / ${demand.value}`},
    energy,
    find(timings, 'Resolución, incluido el modelo'),
    find(timings, 'Total del servicio'),
  ];
  const otherMetrics = metrics.rows.filter(row => ![
    'Entregas planificadas', 'Destinos de la instancia', 'Energía neta de batería',
    'Ahorro de tiempo frente a referencia', 'CO₂e evitado frente a referencia', 'Tiempo acumulado de vehículos'
  ].includes(row.label));
  return `${heading}
    <aside class="summary-freshness" data-state="${model.freshness.state}" aria-label="Vigencia del resumen">
      <strong>${escape(model.freshness.title)}</strong><p>${escape(model.freshness.message)}</p>
      <p class="summary-run-id">Ejecución: ${escape(model.runId)}${model.createdAt ? `<br>Generada (UTC): ${escape(model.createdAt)}` : ''}</p>
    </aside>
    <section class="summary-status" data-tone="${model.status.tone}">
      <h2>${escape(model.status.label)}</h2>
      ${model.status.timeLimitReached ? '<p>Límite de tiempo alcanzado. Se conserva el resultado que informa el motor.</p>' : ''}
    </section>
    <div class="summary-hero">${facts(hero)}</div>
    <p class="summary-note">Energía neta efectiva de batería: incluye regeneración limitada por la capacidad. No equivale a electricidad comprada a la red. Los tiempos de cómputo no son la duración del reparto.</p>
    ${section({...metrics, title: 'Energía, recorrido y operación', rows: otherMetrics})}
    <section class="summary-section summary-validation"><h2>Comprobación independiente</h2>
      <ul>${model.validation.rows.map(row => `<li>${escape(row.label)}: <strong>${escape(row.value)}</strong></li>`).join('')}</ul>
      ${notes(model.validation.notes.slice(1))}
    </section>
    <section class="summary-section"><h2>Entregas pendientes</h2><p class="summary-note">${escape(model.pending.message)}</p>
      ${model.pending.items.length ? `<ul class="summary-pending">${model.pending.items.map(item => `<li>${escape(item.label)} <span>ID ${escape(item.id)}</span></li>`).join('')}</ul>` : ''}
    </section>
    ${model.routes.map(routeSection).join('')}
    <section class="summary-section"><h2>Fases y alcance de la solución</h2>
      <p class="summary-note">${escape(model.solutionNote)}</p>
      ${phaseTable(model.phases)}
    </section>
    <section class="summary-section summary-assumptions"><h2>Supuestos y advertencias</h2><p class="summary-note">${escape(model.network)}</p>
      ${notes([operationalNotes(model.operations), ...model.assumptions, ...model.warnings].filter(Boolean))}
    </section>
    <footer class="summary-footer">Ejecución ${escape(model.runId)} · Motor ${escape(model.provider)} @ ${escape(model.providerCommit.slice(0, 12))}.
      Valores conservados sin estimaciones adicionales. Configuración, trazabilidad y tiempos detallados en «Descargar» → «Datos y límites de la ejecución» y en el JSON nativo.</footer>`;
}

export function initPlanSummary(data, {error = null} = {}) {
  const stylesheet = document.createElement('link');
  stylesheet.rel = 'stylesheet';
  stylesheet.href = new URL('./plan-summary.css', import.meta.url).href;
  document.head.append(stylesheet);
  const opener = document.createElement('button');
  opener.id = 'open-plan-summary';
  opener.type = 'button';
  opener.textContent = 'Ver resumen';
  opener.setAttribute('aria-haspopup', 'dialog');
  document.querySelector('.run-actions').append(opener);

  const dialog = document.createElement('dialog');
  dialog.id = 'plan-summary-dialog';
  dialog.className = 'app-dialog plan-summary-dialog';
  dialog.setAttribute('aria-labelledby', 'summary-heading');
  dialog.innerHTML = `<div class="summary-toolbar"><p>Resumen de la ejecución</p><div>
    <button type="button" id="print-plan-summary">Imprimir / guardar PDF</button>
    <button type="button" id="close-plan-summary" aria-label="Cerrar resumen">×</button></div></div>
    <article class="plan-summary-document"></article>`;
  document.body.append(dialog);
  const article = dialog.querySelector('article');
  const printButton = dialog.querySelector('#print-plan-summary');
  const refresh = () => {
    const readingHeading = article.contains(document.activeElement);
    const model = buildPlanSummary(data, {
      execution: readExecution(), stale: document.querySelector('.run-strip')?.dataset.stale === 'true', error
    });
    article.innerHTML = renderPlanSummary(model);
    printButton.disabled = !model.available;
    if (readingHeading && dialog.open) article.querySelector('h1').focus({preventScroll: true});
  };
  opener.addEventListener('click', () => {
    refresh();
    dialog.showModal();
    dialog.scrollTop = 0;
    article.querySelector('h1').focus({preventScroll: true});
  });
  dialog.querySelector('#close-plan-summary').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => opener.focus());
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const buttons = [...dialog.querySelectorAll('button:not(:disabled)')];
    const first = buttons[0], last = buttons.at(-1);
    const active = document.activeElement;
    if (!buttons.includes(active) || (event.shiftKey ? active === first : active === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  });
  printButton.addEventListener('click', () => {
    refresh();
    window.print();
  });
  // Also handles the browser's own print shortcut and changes made after the
  // dialog opened. CSS prints only this article, even when the dialog is closed.
  addEventListener('beforeprint', refresh);
  return {refresh};
}
