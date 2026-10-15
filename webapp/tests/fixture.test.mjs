import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateFixture } from '../shared/validate-fixture.js';

const example = JSON.parse(readFileSync(new URL('../data/demo.synthetic.json', import.meta.url), 'utf8'));
const fixture = () => structuredClone(example);

test('the included example is structurally valid', () => {
  const data = fixture();
  assert.equal(validateFixture(data), data);
});

test('an unassigned vehicle and repeated stops remain valid', () => {
  const data = fixture();
  data.ROUTES.pop();
  const route = data.ROUTES[0];
  route.stops.splice(2, 0, structuredClone(route.stops[1]));
  route.stopIds.splice(2, 0, route.stopIds[1]);
  assert.doesNotThrow(() => validateFixture(data));
});

test('IDs remain opaque strings; HTML-like text must be escaped when rendering', () => {
  const data = fixture();
  const node = data.NODES.find(item => item.type === 'visit');
  const original = node.id;
  node.id = 'local <norte> "A"';
  node.label = '<img src=x onerror=alert(1)>';
  for (const route of data.ROUTES) {
    route.stopIds = route.stopIds.map(id => id === original ? node.id : id);
    for (const stop of route.stops) if (stop.nodeId === original) stop.nodeId = node.id;
  }
  assert.doesNotThrow(() => validateFixture(data));
});

for (const [name, change, field] of [
  ['unknown route vehicle', d => { d.ROUTES[0].vehicleId = 'unknown'; }, /vehicleId desconocido/],
  ['duplicate map source', d => { d.ROUTES.push(structuredClone(d.ROUTES[0])); }, /vehicleId duplicado/],
  ['duplicate node ID', d => { d.NODES[1].id = d.NODES[0].id; }, /NODES.id duplicado/],
  ['missing route geometry', d => { delete d.ROUTES[0].geometry; }, /geometry/],
  ['non-finite geometry', d => { d.ROUTES[0].geometry.coordinates[0][0] = Infinity; }, /geometry/],
  ['unknown stop', d => { d.ROUTES[0].stops[0].nodeId = 'unknown'; }, /nodeId desconocido/],
  ['inconsistent stop lists', d => { d.ROUTES[0].stopIds.reverse(); }, /no coincide/],
  ['color attribute injection', d => { d.VEHICLES[0].color = '"><img src=x>'; }, /color/],
  ['battery style injection', d => { d.ROUTES[0].finalSoc = '1"><img src=x>'; }, /finalSoc/],
]) {
  test(`rejects ${name} before map initialization`, () => {
    const data = fixture();
    change(data);
    assert.throws(() => validateFixture(data), field);
  });
}
