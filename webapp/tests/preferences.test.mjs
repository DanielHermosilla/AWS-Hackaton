import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const key = 'zmd.webapp.presentation.v1';
const legacyKey = 'zmd.homepage.console-theme.v1';
const themeScript = await readFile(new URL('../theme.js', import.meta.url), 'utf8');
let documentNumber = 0;

async function inDocument({ stored, legacy, blocked = false } = {}, check) {
  const storage = new Map();
  if (stored !== undefined) storage.set(key, typeof stored === 'string' ? stored : JSON.stringify(stored));
  if (legacy !== undefined) storage.set(legacyKey, legacy);
  const localStorage = {
    getItem(name) { if (blocked) throw new Error('Storage denied'); return storage.get(name) ?? null; },
    setItem(name, value) { if (blocked) throw new Error('Storage denied'); storage.set(name, value); },
    removeItem(name) { if (blocked) throw new Error('Storage denied'); storage.delete(name); }
  };
  const document = {
    documentElement: { dataset: {} },
    dispatchEvent() {},
    addEventListener() {},
    removeEventListener() {}
  };
  const environment = {
    localStorage, document,
    matchMedia: query => ({ matches: query.includes('prefers-color-scheme: dark'), addEventListener() {} }),
    addEventListener() {}
  };
  vm.runInNewContext(themeScript, environment);
  const originals = Object.fromEntries(Object.keys(environment).map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  for (const [name, value] of Object.entries(environment)) Object.defineProperty(globalThis, name, { value, writable: true, configurable: true });
  try {
    const state = await import(new URL(`../state.js?document=${++documentNumber}`, import.meta.url));
    await check({ state, document, storage });
  } finally {
    for (const [name, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
}

for (const [name, options] of [
  ['system dark preference', {}],
  ['legacy dark preference', { legacy: 'dark' }],
  ['invalid saved JSON', { stored: '{' }],
  ['blocked storage', { blocked: true }]
]) {
  test(`a new document starts light despite ${name}`, async () => {
    await inDocument(options, ({ state, document }) => {
      assert.equal(document.documentElement.dataset.theme, 'light', 'head bootstrap must be light before the module loads');
      assert.equal(state.DEFAULT_PREFERENCES.theme, 'light');
      const preferences = state.readPreferences();
      assert.equal(preferences.theme, 'light', 'an absent or invalid theme uses the light default');
      assert.equal(state.applyPreferences(preferences).theme, 'light');
      if (options.stored?.organizationName) {
        assert.equal(preferences.organizationName, 'Flota CASE');
        assert.equal(preferences.solidSurfaces, true);
        assert.equal(preferences.reducedMotion, true);
        assert.equal(document.documentElement.dataset.solidSurfaces, 'true');
        assert.equal(document.documentElement.dataset.reducedMotion, 'true');
      }
    });
  });
}

for (const blocked of [false, true]) {
  test(`manual dark survives other preference updates with storage ${blocked ? 'blocked' : 'available'}`, async () => {
    await inDocument({ blocked }, ({ state, document, storage }) => {
      state.updatePreferences({ theme: 'dark' });
      for (const patch of [{ organizationName: 'Flota CASE' }, { solidSurfaces: true }, { reducedMotion: true }]) {
        const result = state.updatePreferences(patch);
        assert.equal(result.preferences.theme, 'dark');
        assert.equal(document.documentElement.dataset.theme, 'dark');
        assert.equal(result.saved, !blocked);
      }
      assert.deepEqual(state.readPreferences(), {
        theme: 'dark', organizationName: 'Flota CASE', solidSurfaces: true, reducedMotion: true
      });
      if (!blocked) assert.deepEqual(JSON.parse(storage.get(key)), {
        theme: 'dark', organizationName: 'Flota CASE', solidSurfaces: true, reducedMotion: true
      }, 'the selected theme belongs in localStorage with the other preferences');
      state.updatePreferences({ theme: 'light' });
      assert.equal(state.readPreferences().theme, 'light');
    });
  });
}

test('other tabs update the same persisted theme and preferences', async () => {
  await inDocument({}, ({ state, document, storage }) => {
    state.updatePreferences({ theme: 'dark' });
    storage.set(key, JSON.stringify({ theme: 'light', organizationName: 'Otra flota', solidSurfaces: true }));
    state.applyPreferences(state.readPreferences());
    assert.equal(document.documentElement.dataset.theme, 'light');
    assert.equal(state.readPreferences().organizationName, 'Otra flota');
    assert.equal(state.readPreferences().solidSurfaces, true);
  });
});

test('a new document restores manual dark before paint and keeps the other preferences', async () => {
  let saved;
  await inDocument({}, ({ state, storage }) => {
    state.updatePreferences({ theme: 'dark', organizationName: 'Flota CASE', reducedMotion: true });
    saved = storage.get(key);
  });
  await inDocument({ stored: saved }, ({ state, document }) => {
    assert.equal(document.documentElement.dataset.theme, 'dark');
    assert.deepEqual(state.readPreferences(), {
      theme: 'dark', organizationName: 'Flota CASE', solidSurfaces: false, reducedMotion: true
    });
  });
});

test('a saved dark theme is restored before paint and by the app shell', async () => {
  await inDocument({stored: {theme: 'dark', solidSurfaces: true, organizationName: 'Flota CASE'}}, ({state, document}) => {
    assert.equal(document.documentElement.dataset.theme, 'dark');
    assert.equal(document.documentElement.dataset.solidSurfaces, 'true');
    assert.equal(state.applyPreferences(state.readPreferences()).theme, 'dark');
    assert.equal(state.readPreferences().organizationName, 'Flota CASE');
  });
});
