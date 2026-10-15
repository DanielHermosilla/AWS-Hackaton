import { initShell } from '../../app-shell.js?v=home-v3';
import { readPlanContext } from '../../state.js';
import { rememberHomePreview, planHref } from '../../home-navigation.js';
import { summarizePlan } from './model.js';

rememberHomePreview(document.body.dataset.preview);
initShell('home');
const main = document.getElementById('home-main');
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const planLink = params => {
  const url = new URL(planHref);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.href;
};

try {
  const data = await import('../../shared/data.js');
  data.applyDataProvenance();
  const model = summarizePlan(data, readPlanContext());
  const num = value => value === null ? '—' : data.number(value);
  for (const element of main.querySelectorAll('[data-value]')) {
    const value = element.dataset.value.split('.').reduce((object, key) => object?.[key], model);
    element.textContent = typeof value === 'number' ? num(value) : value ?? '—';
  }
  const links = {
    resume: planHref,
    stops: planLink({ tab: 'stops' }),
    fleet: planLink({ tab: 'fleet' }),
    chargers: planLink({ chargers: '1' }),
  };
  for (const anchor of main.querySelectorAll('[data-link]')) anchor.href = links[anchor.dataset.link];
  for (const mount of main.querySelectorAll('[data-widget="fleet"]')) {
    mount.innerHTML = model.fleet.map(vehicle => `
      <a class="fleet-row" href="${planLink({ vehicle: vehicle.id })}" aria-label="Abrir recorrido de ${escape(vehicle.name)}">
        <span class="fleet-identity"><span class="fleet-dot" style="--vehicle-color:${vehicle.id === 'auto-1' ? '#1664ec' : '#8152d9'}" aria-hidden="true"></span><span><strong class="fleet-name">${escape(vehicle.name)}</strong><span class="fleet-model">${escape(vehicle.model)}</span></span></span>
        <span class="fleet-count"><strong>${num(vehicle.assigned)}</strong> entregas</span>
        <span class="fleet-return"><strong>${num(vehicle.finalSoc)}%</strong><span>al regreso · ejemplo</span></span>
        <span class="fleet-arrow" aria-hidden="true">↗</span>
      </a>`).join('');
  }
  for (const mount of main.querySelectorAll('[data-widget="charge-links"]')) {
    mount.innerHTML = model.charges.slice(0, 2).map(charge => {
      const vehicle = model.fleet.find(item => item.id === charge.vehicleId);
      return `<a class="charge-link" href="${planLink({ vehicle: charge.vehicleId, tab: 'stops', stop: charge.index })}">${escape(charge.nodeId)} <span>· ${escape(vehicle?.name || charge.vehicleId)}</span><span aria-hidden="true">↗</span></a>`;
    }).join('') + (model.charges.length > 2 ? `<a class="charge-link" href="${links.stops}">Ver paradas →</a>` : '');
  }
  for (const mount of main.querySelectorAll('[data-widget="balance"]')) {
    mount.innerHTML = `<div class="table-scroll" role="region" aria-label="Resumen de vehículos" tabindex="0"><table class="balance-table">
      <caption class="sr-only">Plan ilustrativo por vehículo y total</caption>
      <thead><tr><th scope="col">Vehículo</th><th scope="col">Entregas<br>asignadas</th><th scope="col">Consumo<br><span>kWh · ejemplo</span></th><th scope="col">Paradas de<br>recarga</th><th scope="col">Batería al regreso<br><span>% · ejemplo</span></th></tr></thead>
      <tbody>${model.fleet.map(vehicle => `<tr><th scope="row"><a href="${planLink({ vehicle: vehicle.id })}">${escape(vehicle.name)} <span aria-hidden="true">↗</span><small>${escape(vehicle.model)}</small></a></th><td>${num(vehicle.assigned)}</td><td>${num(vehicle.energyKwh)}</td><td>${num(vehicle.chargeStops)}</td><td>${num(vehicle.finalSoc)}</td></tr>`).join('')}</tbody>
      <tfoot><tr><th scope="row">Total del plan</th><td>${num(model.stats.assigned)}<small>de ${num(model.stats.visits)}</small></td><td>${num(model.stats.energyKwh)}</td><td>${num(model.stats.chargeStops)}</td><td aria-label="No corresponde sumar batería">—</td></tr></tfoot>
    </table></div>`;
  }
  main.setAttribute('aria-busy', 'false');
  // Motion is optional: disclosure remains fully usable if the library is unavailable.
  import('./motion.js').catch(() => {});
} catch (error) {
  console.error('No se pudo cargar Inicio:', error);
  main.className = 'error-main';
  main.setAttribute('aria-busy', 'false');
  main.innerHTML = `<section class="load-error"><h1>No se pudo cargar el escenario</h1><p>Vuelve a intentar cargar los datos para consultar el resumen de tu plan.</p><button class="primary" id="retry-home">Volver a intentar</button></section>`;
  document.getElementById('retry-home').addEventListener('click', () => location.reload());
}
