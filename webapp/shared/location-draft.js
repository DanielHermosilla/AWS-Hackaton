import { inputNodes, parseInstanceFile, validateNodes } from './solver-input.js';

const SOURCE_KEY = 'zmd.webapp.editable-source.v1';
const DRAFT_KEY = 'zmd.webapp.location-draft.v1';
const formFields = new Set(['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km', 'time_limit_seconds']);
const editableFields = new Set(['address', 'latitude', 'longitude']);
const coordinate = value => typeof value === 'number' || (typeof value === 'string' && value.trim())
  ? Number(value) : NaN;
const normalize = nodes => nodes.map(node => ({...node,
  latitude: coordinate(node.latitude), longitude: coordinate(node.longitude)}));

// Coordinates are input data only. Preparing their network remains a backend task.
export function createLocationDraft(input) {
  const original = structuredClone(input);
  let nodes = structuredClone(inputNodes(original));
  const readOnly = !!original.instance;
  let closed = false;
  function requireEditable() {
    if (closed) throw new Error('El borrador está cerrado.');
    if (readOnly) throw new Error('La red nativa está protegida. Se necesita una instancia preparada para la nueva ubicación.');
  }
  return {
    readOnly,
    get nodes() { return structuredClone(nodes); },
    get changed() {
      return !readOnly && JSON.stringify(normalize(nodes)) !== JSON.stringify(normalize(original.nodes));
    },
    update(nodeId, patch) {
      requireEditable();
      if (Object.keys(patch).some(key => !editableFields.has(key))) throw new Error('El campo no pertenece a la ubicación editable.');
      const node = nodes.find(node => node.node_id === nodeId);
      if (!node) throw new Error('No se encontró el nodo seleccionado.');
      Object.assign(node, structuredClone(patch));
    },
    commit() {
      requireEditable();
      const confirmed = normalize(nodes);
      validateNodes(confirmed);
      const result = structuredClone(original);
      result.nodes = confirmed;
      if (result.prepareRequest) result.prepareRequest.nodes = structuredClone(confirmed);
      closed = true;
      return result;
    },
    cancel() { closed = true; },
  };
}

// Remember only preparations initiated here, linked to the accepted run. Imported
// native JSON never acquires editing permission by inspecting its provenance.
export function saveEditableSource(runId, prepareRequest, storage) {
  try {
    storage ??= globalThis.sessionStorage;
    if (prepareRequest) storage.setItem(SOURCE_KEY, JSON.stringify({runId, prepareRequest}));
    else storage.removeItem(SOURCE_KEY);
    return true;
  } catch { return false; }
}

export function readEditableSource(runId, storage, instance) {
  try {
    storage ??= globalThis.sessionStorage;
    const saved = JSON.parse(storage.getItem(SOURCE_KEY));
    if (!saved || saved.runId !== runId) return null;
    const input = parseInstanceFile(JSON.stringify(saved.prepareRequest), 'preparacion.json');
    if (instance) {
      const locations = nodes => nodes.map(node => [node.node_id, node.node_type,
        node.latitude, node.longitude, node.address ?? null]);
      if (JSON.stringify(locations(input.nodes)) !== JSON.stringify(locations(instance.nodes))) return null;
    }
    return input.instance ? null : input;
  } catch { return null; }
}

export function saveEditableDraft(draftId, input, fields, storage) {
  try {
    if (input.instance) return false;
    validateNodes(input.nodes);
    storage ??= globalThis.sessionStorage;
    storage.setItem(DRAFT_KEY, JSON.stringify({draftId, input, fields}));
    return true;
  } catch { return false; }
}

export function readEditableDraft(draftId, storage) {
  try {
    if (!draftId) return null;
    storage ??= globalThis.sessionStorage;
    const saved = JSON.parse(storage.getItem(DRAFT_KEY));
    if (!saved || saved.draftId !== draftId || saved.input?.instance) return null;
    validateNodes(saved.input.nodes);
    if (!saved.fields || Object.entries(saved.fields).some(([key, value]) => !formFields.has(key) || typeof value !== 'string')) return null;
    return {input: saved.input, fields: saved.fields};
  } catch { return null; }
}

export function clearEditableDraft(storage) {
  try {
    storage ??= globalThis.sessionStorage;
    storage.removeItem(DRAFT_KEY);
  } catch { /* The execution's draftId is also cleared, so this entry cannot be restored. */ }
}
