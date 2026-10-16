import test from 'node:test';
import assert from 'node:assert/strict';
import { adaptSolverResponse } from '../shared/solver-adapter.js';
import { chargerDetails, chargerList, chargerOccurrences, chargerChargeText } from '../shared/charger-details.js';

function response(charger) {
  return {
    api_version: '3.0',
    result: {
      run_id: 'charger-metadata-test', status: 'no_solution', has_solution: false,
      nodes: [
        { node_id: 'BASE', node_type: 'base', latitude: 0, longitude: 0 },
        { node_id: 'CHARGE|<&"', node_type: 'charger', latitude: null, longitude: null, ...charger }
      ],
      fleet: [], routes: [], served_count: null, total_visits: 0,
      unserved_visit_ids: [], total_energy_kwh: null,
      validation: { feasible: null, violations: [], scope: 'Fixture sintética de presentación.' },
      phases: [], warnings: [], assumptions: [],
      runtime_seconds: { preparation: 0, solver: 0, total: 0 },
      network: {}, metadata: {
        provider: 'ev_routing', provider_commit: 'test',
        input_hash: 'test', config_hash: 'test', network_hash: 'test'
      }
    }
  };
}

test('charger projection keeps every declared station field and opaque ID', () => {
  const node = adaptSolverResponse(response({
    address: 'Avenida <norte> & "sur"', network: 'Red <declarada>',
    connector_types: ['CHAdeMO', 'J1772'], max_power_kw: 50,
    total_ports: 5, dc_fast_ports: 2, level2_ports: 3
  })).NODES[1];
  assert.equal(node.id, 'CHARGE|<&"');
  assert.equal(node.address, 'Avenida <norte> & "sur"');
  assert.equal(node.network, 'Red <declarada>');
  assert.equal(node.connectors, 'CHAdeMO; J1772');
  assert.equal(node.powerKw, 50);
  assert.equal(node.totalPorts, 5);
  assert.equal(node.dcFastPorts, 2);
  assert.equal(node.level2Ports, 3);
  assert.equal(node.lat, null);
  assert.equal(node.lng, null);
});

test('zero charger power, ports and coordinates are data, not absence', () => {
  const node = adaptSolverResponse(response({
    latitude: 0, longitude: 0, max_power_kw: 0,
    total_ports: 0, dc_fast_ports: 0, level2_ports: 0
  })).NODES[1];
  assert.equal(node.powerKw, 0);
  assert.equal(node.totalPorts, 0);
  assert.equal(node.dcFastPorts, 0);
  assert.equal(node.level2Ports, 0);
  assert.equal(node.lat, 0);
  assert.equal(node.lng, 0);
});

test('omitted and null port counts stay unavailable without inventing zeros', () => {
  for (const values of [{}, { total_ports: null, dc_fast_ports: null, level2_ports: null }]) {
    const node = adaptSolverResponse(response(values)).NODES[1];
    assert.equal(node.powerKw, null);
    assert.equal(node.totalPorts, null);
    assert.equal(node.dcFastPorts, null);
    assert.equal(node.level2Ports, null);
  }
});

test('station detail exposes source fields without presenting availability or vehicle power as verified', () => {
  const node = adaptSolverResponse(response({
    address: 'Av. 10', network: 'Red declarada', connector_types: ['CHAdeMO', 'J1772'],
    max_power_kw: 50, total_ports: 5, dc_fast_ports: 2, level2_ports: 3
  })).NODES[1];
  const html = chargerDetails(node);
  for (const value of ['Dirección', 'Av. 10', 'Red declarada', 'CHAdeMO; J1772',
    'Potencia máxima reportada', '50 kW', 'Puertos totales', '>5<', 'Puertos DC', '>2<',
    'Puertos nivel 2', '>3<', 'No verificada', 'Sin coordenadas']) assert.ok(html.includes(value), value);
  assert.match(html, /potencia aceptada por el vehículo/);
  assert.match(html, /compatibilidad/);
  assert.match(html, /tiempo de carga/);
});

test('station detail distinguishes unknown values, empty text and numeric zeros', () => {
  const node = adaptSolverResponse(response({
    address: '  ', network: '', connector_types: [], latitude: 0, longitude: 0,
    max_power_kw: 0, total_ports: 0, dc_fast_ports: null, level2_ports: 0
  })).NODES[1];
  const html = chargerDetails(node);
  assert.match(html, /Potencia máxima reportada<\/dt><dd>0 kW</);
  assert.match(html, /Puertos totales<\/dt><dd>0</);
  assert.match(html, /Puertos DC<\/dt><dd>Sin informar</);
  assert.match(html, /Puertos nivel 2<\/dt><dd>0</);
  assert.match(html, /Dirección<\/dt><dd>Sin informar</);
  assert.match(html, /Conectores declarados<\/dt><dd>Sin informar</);
  assert.match(html, /Latitud 0 · longitud 0/);
});

test('detail and keyboard list escape station IDs, address, network and connectors', () => {
  const node = adaptSolverResponse(response({
    address: '<img src=x onerror=alert(1)>', network: 'Red "A" & <B>',
    connector_types: ['<script>evil()</script>']
  })).NODES[1];
  for (const html of [chargerDetails(node), chargerList([node], [])]) {
    assert.doesNotMatch(html, /<img|<script>|onerror=(?![^<]*&gt;)/);
    assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  }
  assert.match(chargerDetails(node), /Red &quot;A&quot; &amp; &lt;B&gt;/);
  assert.match(chargerDetails(node), /&lt;script&gt;evil\(\)&lt;\/script&gt;/);
  assert.match(chargerList([node], []), /data-charger="CHARGE\|&lt;&amp;&quot;"/);
});

test('all stations have list buttons including unused stations and missing coordinates', () => {
  const nodes = [
    { id: 'used', type: 'charger', label: 'Usada', lat: 0, lng: 0 },
    { id: 'unused', type: 'charger', label: 'No usada', lat: 1, lng: 1 },
    { id: 'unmapped', type: 'charger', label: 'Sin mapa', lat: null, lng: null },
    { id: 'delivery', type: 'visit', label: 'Entrega' }
  ];
  const html = chargerList(nodes, [{ vehicleId: 'V1', stops: [{ nodeId: 'used', chargeKwh: 0 }] }]);
  assert.equal((html.match(/data-charger=/g) || []).length, 3);
  assert.match(html, /data-charger="used"/);
  assert.match(html, /data-charger="unused"/);
  assert.match(html, /data-charger="unmapped"/);
  assert.match(html, /En el recorrido/);
  assert.match(html, /Fuera del recorrido/);
  assert.match(html, /Sin coordenadas/);
  assert.doesNotMatch(html, /data-charger="delivery"|disabled/);
});

test('no incumbent does not describe stations as excluded by a route that does not exist', () => {
  const html = chargerList([{ id: 'C', type: 'charger', label: 'Estación' }], [], { noSolution: true });
  assert.match(html, /Sin recorrido calculado/);
  assert.doesNotMatch(html, /Fuera del recorrido/);
});

test('repeat station occurrences preserve route, index and separate charge amounts', () => {
  const routes = [
    { vehicleId: 'V|1', stops: [{ nodeId: 'BASE' }, { nodeId: 'C#', chargeKwh: 2 }, { nodeId: 'C#', chargeKwh: 0 }] },
    { vehicleId: 'V|2', stops: [{ nodeId: 'C#', chargeKwh: null }] }
  ];
  const occurrences = chargerOccurrences('C#', routes);
  assert.deepEqual(occurrences.map(({ vehicleId, index, state }) => [vehicleId, index, state.chargeKwh]),
    [['V|1', 1, 2], ['V|1', 2, 0], ['V|2', 0, null]]);
  assert.equal(occurrences[0].state, routes[0].stops[1]);
  assert.equal(chargerChargeText(occurrences[0].state.chargeKwh), 'Incorporada a batería: 2 kWh');
  assert.equal(chargerChargeText(occurrences[1].state.chargeKwh), 'Paso sin recarga · 0 kWh');
  assert.equal(chargerChargeText(occurrences[2].state.chargeKwh), 'Recarga no informada');
  assert.equal(chargerChargeText(3, true), 'Recarga de ejemplo: 3 kWh');
});

test('example station power uses its existing maxPowerKw field without treating its label as an address', () => {
  const html = chargerDetails({ id: 'SAMPLE', label: 'Estación ficticia', maxPowerKw: 22 });
  assert.match(html, /22 kW/);
  assert.match(html, /Dirección<\/dt><dd>Sin informar</);
});
