import { applyDataProvenance, SCENARIO, VEHICLES, NODES, number } from './shared/data.js';
import { icon, carDrawing } from './shared/icons.js';

applyDataProvenance();

if (!SCENARIO?.demonstration || !Array.isArray(VEHICLES) || !Array.isArray(NODES)) {
  throw new Error('El escenario de demostración no tiene la estructura esperada.');
}
const $ = id => document.getElementById(id);
$('home-location').textContent = SCENARIO.name;
$('home-deliveries').textContent = number(NODES.filter(node => node.type === 'visit').length, 0);
$('home-vehicles').textContent = number(VEHICLES.length, 0);
$('home-chargers').textContent = number(NODES.filter(node => node.type === 'charger').length, 0);
$('result-icon').innerHTML = icon('route', 22);
for (const vehicle of VEHICLES) {
  const card = document.createElement('a');
  card.className = 'home-vehicle';
  card.href = `plan.html?${new URLSearchParams({ vehicle: vehicle.id })}`;
  const color = /^#[a-f\d]{6}$/i.test(vehicle.color) ? vehicle.color : '#526a86';
  card.style.setProperty('--route', color);
  card.innerHTML = `<span class="vehicle-overview"><span class="vehicle-label"></span><span class="vehicle-caption"></span></span>
    ${carDrawing(color)}
    <span class="vehicle-charge"><strong><span class="soc-value"></span><small>%</small></strong><span>Batería inicial</span></span>
    <span class="vehicle-link">Ver recorrido ${icon('arrow', 14)}</span>`;
  card.querySelector('.vehicle-label').textContent = vehicle.name;
  card.querySelector('.vehicle-caption').textContent = vehicle.model;
  card.querySelector('.soc-value').textContent = number(vehicle.initialSoc);
  card.setAttribute('aria-label', `Explorar recorrido de ${vehicle.name}, ${vehicle.model}, batería inicial ${number(vehicle.initialSoc)} %`);
  $('home-fleet-list').append(card);
}
$('home-loading').hidden = true;
