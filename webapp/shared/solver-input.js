import { API_VERSION } from './solver-client.js';

const columns = ['node_id', 'node_type', 'latitude', 'longitude', 'address', 'network',
  'total_ports', 'dc_fast_ports', 'level2_ports', 'connector_types', 'max_power_kw'];
const numericColumns = new Set(['latitude', 'longitude', 'total_ports', 'dc_fast_ports', 'level2_ports', 'max_power_kw']);
const inputNumber = value => typeof value === 'number' || (typeof value === 'string' && value.trim())
  ? Number(value) : NaN;
const absent = value => value == null || value === '';

// RFC 4180 fields, including quoted newlines; no delimiter or numeric coercion guesses.
function csvRows(text) {
  const rows = [];
  let row = [], field = '', quoted = false, closed = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else field += c;
    } else if (c === '"' && field === '' && !closed) quoted = true;
    else if (c === ',' || c === '\r' || c === '\n') {
      row.push(field); field = ''; closed = false;
      if (c !== ',') {
        if (row.some(value => value !== '')) rows.push(row);
        row = [];
        if (c === '\r' && text[i + 1] === '\n') i++;
      }
    } else {
      if (closed || c === '"') throw new Error('CSV inválido: revisa las comillas de los campos.');
      field += c;
    }
  }
  if (quoted) throw new Error('CSV inválido: hay comillas sin cerrar.');
  row.push(field);
  if (row.some(value => value !== '')) rows.push(row);
  return rows;
}

export function validateNodes(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) throw new Error('La instancia debe contener nodos.');
  const ids = new Set();
  for (const node of nodes) {
    if (typeof node.node_id !== 'string' || !node.node_id.trim()) throw new Error('Cada nodo necesita un ID no vacío.');
    if (ids.has(node.node_id)) throw new Error(`ID repetido: ${node.node_id}.`);
    ids.add(node.node_id);
    if (!['base', 'visit', 'charger'].includes(node.node_type)) throw new Error(`Tipo inválido en ${node.node_id}: usa base, visit o charger.`);
    if (!Number.isFinite(inputNumber(node.latitude)) || Math.abs(inputNumber(node.latitude)) > 90) throw new Error(`Latitud inválida en ${node.node_id}.`);
    if (!Number.isFinite(inputNumber(node.longitude)) || Math.abs(inputNumber(node.longitude)) > 180) throw new Error(`Longitud inválida en ${node.node_id}.`);
    for (const key of ['total_ports', 'dc_fast_ports', 'level2_ports']) {
      if (!absent(node[key]) && (!Number.isInteger(inputNumber(node[key])) || inputNumber(node[key]) < 0))
        throw new Error(`${key} debe ser un entero no negativo en ${node.node_id}.`);
    }
    if (!absent(node.max_power_kw) && (!Number.isFinite(inputNumber(node.max_power_kw)) || inputNumber(node.max_power_kw) < 0))
      throw new Error(`Potencia inválida en ${node.node_id}.`);
    if (!absent(node.total_ports) && Number(node.dc_fast_ports ?? 0) + Number(node.level2_ports ?? 0) > Number(node.total_ports))
      throw new Error(`Puertos inconsistentes en ${node.node_id}: DC + nivel 2 supera el total.`);
  }
  if (nodes.filter(node => node.node_type === 'base').length !== 1) throw new Error('La instancia necesita exactamente un depósito (base).');
  return nodes;
}

const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nativeFields = ['schema_version', 'name', 'nodes', 'arcs', 'parameters', 'operations', 'compatible_chargers', 'provenance'];
const solverFields = ['time_limit_seconds', 'search_policy', 'energy_relative_gap', 'random_seed'];
const requireFields = (value, allowed, name) => {
  if (!record(value)) throw new Error(`Falta el objeto ${name}.`);
  const unknown = Object.keys(value).filter(key => !allowed.includes(key));
  if (unknown.length) throw new Error(`Parámetros no admitidos en ${name}: ${unknown.join(', ')}.`);
};

// Lightweight input checks only. The backend's native Pydantic contract remains
// authoritative; the original instance is returned without defaults or rewrites.
export function validateNativeInstance(instance) {
  requireFields(instance, nativeFields, 'ProblemInstance');
  if (!['1.0', '1.1'].includes(instance.schema_version) || !Array.isArray(instance.nodes) || !Array.isArray(instance.arcs))
    throw new Error('Carga una ProblemInstance nativa con schema_version 1.0 o 1.1, nodes y arcs.');
  const ids = new Set();
  for (const node of instance.nodes) {
    if (!record(node) || typeof node.node_id !== 'string' || !node.node_id.trim() || ids.has(node.node_id))
      throw new Error('La instancia nativa contiene un ID de nodo vacío o repetido.');
    ids.add(node.node_id);
    if (!['base', 'visit', 'charger', 'junction'].includes(node.node_type)) throw new Error(`Tipo de nodo no admitido: ${node.node_type}.`);
    if ((node.latitude == null) !== (node.longitude == null)) throw new Error(`Coordenadas incompletas en ${node.node_id}.`);
    if (node.latitude != null && (!Number.isFinite(node.latitude) || Math.abs(node.latitude) > 90 || !Number.isFinite(node.longitude) || Math.abs(node.longitude) > 180))
      throw new Error(`Coordenadas inválidas en ${node.node_id}.`);
    if (node.connector_types !== undefined && (!Array.isArray(node.connector_types) || !node.connector_types.every(value => typeof value === 'string')))
      throw new Error(`connector_types debe ser una lista en ${node.node_id}.`);
  }
  if (instance.nodes.filter(node => node.node_type === 'base').length !== 1) throw new Error('La instancia necesita exactamente un depósito (base).');
  const pairs = new Set();
  const resourcePaths = instance.schema_version === '1.1' && instance.provenance?.representation?.kind === 'resource_paths';
  for (const arc of instance.arcs) {
    if (!record(arc) || !ids.has(arc.from_node_id) || !ids.has(arc.to_node_id)) throw new Error('Un arco referencia nodos desconocidos.');
    const key = resourcePaths ? arc.arc_id : JSON.stringify([arc.from_node_id, arc.to_node_id]);
    if (resourcePaths && (typeof key !== 'string' || !key || !record(arc.battery_profile)))
      throw new Error('Cada camino con recursos requiere arc_id único y perfil de batería.');
    if (pairs.has(key) || (!resourcePaths && arc.from_node_id === arc.to_node_id)) throw new Error('La instancia contiene arcos duplicados o autoarcos.');
    pairs.add(key);
    if (!Number.isFinite(arc.energy_kwh)) throw new Error('Cada arco necesita energy_kwh finita, con su signo original.');
  }
  for (const key of ['parameters', 'operations', 'provenance']) {
    if (instance[key] !== undefined && !record(instance[key])) throw new Error(`${key} debe ser un objeto.`);
  }
  return instance;
}

export function inputNodes(input) {
  if (input.instance) return validateNativeInstance(input.instance).nodes;
  if (input.nodes) return validateNodes(input.nodes);
  throw new Error('Selecciona un CSV o una ProblemInstance nativa 1.0.');
}

function parseJsonWithUniqueKeys(text) {
  // Inspect the original text before JSON.parse can overwrite a duplicate field.
  // Strings are skipped intact; JSON.parse still validates syntax and decodes keys.
  const objects = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') objects.push(new Set());
    else if (text[i] === '}') objects.pop();
    else if (text[i] === '"') {
      const start = i;
      for (i++; i < text.length && text[i] !== '"'; i++) {
        if (text[i] === '\\') i++;
      }
      let next = i + 1;
      while (/[ \t\r\n]/.test(text[next] || '')) next++;
      if (text[next] === ':' && objects.length) {
        const key = JSON.parse(text.slice(start, i + 1));
        const keys = objects.at(-1);
        if (keys.has(key)) {
          // Malformed documents retain the syntax error; no parsed value is used.
          JSON.parse(text);
          throw new Error(`El archivo contiene claves JSON duplicadas. Usa una sola definición para ${JSON.stringify(key)}.`);
        }
        keys.add(key);
      }
    }
  }
  return JSON.parse(text);
}

export function parseInstanceFile(text, filename = '') {
  let value, preparationAttempt;
  const cleaned = text.replace(/^\ufeff/, '');
  if (/\.csv$/i.test(filename) || !cleaned.trimStart().startsWith('{')) {
    validateInstanceFileHeader(cleaned);
    const rows = csvRows(cleaned);
    const headers = rows.shift();
    if (!headers || headers.some(key => !columns.includes(key)) || new Set(headers).size !== headers.length
      || columns.slice(0, 4).some(key => !headers.includes(key)))
      throw new Error('Encabezado CSV inválido. Se requieren node_id, node_type, latitude y longitude; usa el formato de nodos del desafío.');
    value = {nodes: rows.map((row, index) => {
      if (row.length !== headers.length) throw new Error(`Fila ${index + 2}: la cantidad de columnas no coincide con el encabezado.`);
      return Object.fromEntries(headers.flatMap((key, j) => {
        if (row[j] === '' && !columns.slice(0, 4).includes(key)) return [];
        return [[key, numericColumns.has(key) ? (row[j].trim() ? Number(row[j]) : NaN) : row[j]]];
      }));
    })};
  } else {
    try { value = parseJsonWithUniqueKeys(cleaned); }
    catch (error) {
      if (error instanceof SyntaxError) throw new Error('El archivo no contiene JSON válido.');
      throw error;
    }
    if (value?.schema_version === 'zmd.integration-beta.attempt/2') {
      if (value.prepare_request && value.request != null) {
        const request = value.request;
        requireFields(request, ['api_version', 'solver', 'instance', 'prepared_instance_id'], 'request');
        if (request.api_version !== API_VERSION) throw new Error('Versión del intento no admitida; se requiere API 3.0.');
        if (request.solver !== undefined) requireFields(request.solver, solverFields, 'solver');
        // Rebuild paths from their source because prepared handles expire with
        // the server. Only solver settings survive recovery of a failed solve.
        preparationAttempt = {api_version: request.api_version,
          ...(request.solver !== undefined ? {solver: request.solver} : {})};
      }
      value = value.prepare_request || value.request;
    }
    if (value?.api_version === API_VERSION && value.result) {
      const raw = value.result.raw;
      if (raw?.prepare_request) {
        preparationAttempt = {api_version: API_VERSION, solver: raw.input?.solver};
        value = raw.prepare_request;
      } else value = raw?.input;
    }
    if (!record(value)) throw new Error('El archivo no contiene una entrada completa reutilizable.');
    if (value.schema_version === '1.0' && record(value.solve) && record(value.kpis))
      throw new Error('Este archivo es un resultado nativo: no contiene los nodos y arcos de su instancia. Carga la instancia correspondiente o la descarga de ejecución completa del API 3.0.');
    if (['1.0', '1.1'].includes(value.schema_version)) value = {instance: validateNativeInstance(value)};
    else if (value.api_version === API_VERSION && value.instance) {
      const request = value;
      requireFields(request, ['api_version', 'instance', 'solver', 'prepared_instance_id'], 'request');
      if (request.solver !== undefined) requireFields(request.solver, solverFields, 'solver');
      if (request.prepared_instance_id) throw new Error('Carga la ejecución completa o la entrada de preparación para reconstruir los caminos; este identificador es temporal.');
      value = {instance: validateNativeInstance(request.instance), request};
    } else if (value.api_version === API_VERSION && value.nodes) {
      requireFields(value, ['api_version', 'nodes', 'fleet', 'network_mode', 'operations', 'energy_profile_id', 'scenario'], 'prepare');
      if (value.energy_profile_id !== undefined && (typeof value.energy_profile_id !== 'string' || !value.energy_profile_id || value.energy_profile_id.length > 200))
        throw new Error('El identificador del histórico no es válido. Vuelve a adjuntar el histórico.');
      requireFields(value.fleet, ['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km', 'vehicle_connector_types'], 'fleet');
      if (!['haversine', 'road'].includes(value.network_mode)) throw new Error('La preparación requiere network_mode road o haversine explícito.');
      value = {nodes: value.nodes, prepareRequest: value, ...(preparationAttempt ? {request: preparationAttempt} : {})};
    } else throw new Error('Versión no admitida. Los formatos anteriores no son compatibles: carga un CSV o una ProblemInstance nativa 1.0.');
  }
  inputNodes(value);
  return value;
}

function positive(value, name) {
  if (!Number.isFinite(inputNumber(value)) || inputNumber(value) <= 0)
    throw new Error(`${name} debe ser un número positivo.`);
  return Number(value);
}

export function solverSettings(timeLimit, policy, energyGap, seed) {
  const seconds = positive(timeLimit, 'El tiempo límite');
  if (seconds < 1 || seconds > 120) throw new Error('El tiempo límite debe estar entre 1 y 120 segundos.');
  if (policy !== undefined && !['standard', 'adaptive', 'deterministic'].includes(policy)) throw new Error('Política de búsqueda inválida.');
  const gap = energyGap === undefined ? .005 : inputNumber(energyGap);
  const randomSeed = seed === undefined ? 0 : inputNumber(seed);
  if (!Number.isFinite(gap) || gap < 0 || gap > 1)
    throw new Error('El gap de optimalidad debe estar entre 0 y 100 %.');
  if (!Number.isInteger(randomSeed) || randomSeed < 0 || randomSeed > 2_000_000_000)
    throw new Error('La semilla debe ser un entero entre 0 y 2.000.000.000.');
  return {time_limit_seconds: seconds, ...(policy ? {search_policy: policy} : {}),
    ...(energyGap !== undefined ? {energy_relative_gap: gap} : {}),
    ...(seed !== undefined ? {random_seed: randomSeed} : {})};
}

export function makeSolveRequest(input, timeLimit, policy, energyGap, seed) {
  if (!input.instance) throw new Error('Primero prepara los nodos en el servidor para obtener una instancia nativa.');
  return {api_version: API_VERSION, instance: validateNativeInstance(input.instance),
    solver: solverSettings(timeLimit, policy, energyGap, seed)};
}

export function makePrepareRequest(input, values) {
  if (input.instance) throw new Error('Una instancia nativa ya contiene su red; no se reemplaza mediante preparación.');
  validateNodes(input.nodes);
  const capacity = positive(values.battery_capacity_kwh, 'La capacidad útil');
  const initial = positive(values.initial_soc, 'El SoC inicial');
  const reserve = positive(values.reserve_kwh, 'La reserva');
  const count = positive(values.num_vehicles, 'La cantidad de vehículos');
  const consumption = positive(values.consumption_kwh_km, 'El consumo supuesto');
  if (!Number.isInteger(count) || count > 20) throw new Error('Configura entre 1 y 20 vehículos.');
  if (initial > 1) throw new Error('El SoC inicial debe ser de hasta 100 %.');
  if (reserve > initial * capacity) throw new Error('La reserva no puede superar la energía inicial.');
  const connectors = input.prepareRequest?.fleet?.vehicle_connector_types;
  const networkMode = values.network_mode || input.prepareRequest?.network_mode || 'haversine';
  if (!['road', 'haversine'].includes(networkMode)) throw new Error('Modo de red inválido.');
  if (values.energy_profile_id != null && (typeof values.energy_profile_id !== 'string' || !values.energy_profile_id || values.energy_profile_id.length > 200))
    throw new Error('El identificador del histórico no es válido. Vuelve a adjuntar el histórico.');
  const operations = structuredClone(input.prepareRequest?.operations || {});
  if (values.energy_margin_percent !== undefined) {
    const margin = inputNumber(values.energy_margin_percent);
    if (!Number.isFinite(margin) || margin < 0) throw new Error('El margen de consumo debe ser un porcentaje no negativo.');
    if (margin !== 0 || 'energy_margin_fraction' in operations) operations.energy_margin_fraction = margin / 100;
  }
  return {api_version: API_VERSION, nodes: input.nodes, network_mode: networkMode,
    ...(values.energy_profile_id ? {energy_profile_id: values.energy_profile_id} : {}),
    ...(Object.keys(operations).length ? {operations} : {}),
    ...(input.prepareRequest?.scenario ? {scenario: structuredClone(input.prepareRequest.scenario)} : {}),
    fleet: {num_vehicles: count, battery_capacity_kwh: capacity, reserve_kwh: reserve,
      initial_soc: initial, consumption_kwh_km: consumption,
      ...(connectors ? {vehicle_connector_types: [...connectors]} : {})}};
}

// A short preview is enough to reject telemetry without reading a multi-GB file.
export function validateInstanceFileHeader(text) {
  const firstLine = text.replace(/^\ufeff/, '').split(/\r?\n/, 1)[0];
  if (firstLine.trimStart().startsWith('{')) return;
  const headers = firstLine.split(',').map(value => value.replace(/^"|"$/g, '').trim().toLowerCase());
  if (headers.includes('vehid') && headers.includes('trip'))
    throw new Error('Este archivo es un histórico eVED de mediciones. Adjunta ese archivo en «Consumo con históricos». Aquí se carga el CSV de ubicaciones o el JSON de la instancia.');
}

export function inputFormValues(input) {
  const instance = input.instance;
  const parameters = instance?.parameters || {};
  const fleet = input.prepareRequest?.fleet || {};
  const solver = input.request?.solver || {};
  const native = !!instance;
  const network = instance?.provenance?.network || {};
  return {
    num_vehicles: native ? parameters.vehicle_count ?? 2 : fleet.num_vehicles ?? 2,
    initial_soc: native ? parameters.initial_soc ?? .6 : fleet.initial_soc ?? .6,
    battery_capacity_kwh: native ? parameters.battery_capacity_kwh ?? 24 : fleet.battery_capacity_kwh ?? '',
    reserve_kwh: native ? parameters.reserve_kwh ?? 2.4 : fleet.reserve_kwh ?? '',
    consumption_kwh_km: native
      ? instance.provenance?.consumption_kwh_km ?? instance.provenance?.energy_model?.kwh_per_km ?? ''
      : fleet.consumption_kwh_km ?? '',
    time_limit_seconds: solver.time_limit_seconds ?? 120,
    search_policy: solver.search_policy ?? (input.request ? 'standard' : 'adaptive'),
    energy_relative_gap: solver.energy_relative_gap ?? .005,
    energy_margin_percent: 100 * ((native ? instance.operations : input.prepareRequest?.operations)?.energy_margin_fraction ?? 0),
    random_seed: solver.random_seed ?? 0,
    network_mode: input.prepareRequest?.network_mode || (network.kind === 'haversine' ? 'haversine' : 'road'),
  };
}

export function createSyntheticPreparation({clients = 2, chargers = 1} = {}) {
  if (!Number.isInteger(clients) || clients < 1 || !Number.isInteger(chargers) || chargers < 0)
    throw new Error('Elige un número entero de clientes (al menos 1) y estaciones (puede ser 0).');
  if (1 + clients + chargers > 200)
    throw new Error('El ejemplo admite hasta 200 ubicaciones, incluido el depósito.');
  const nodes = [{node_id: 'BASE', node_type: 'base', latitude: -33.45, longitude: -70.66, address: 'Depósito'}];
  // Deterministic nearby coordinates keep small examples feasible with the
  // user's 7 kWh / 2 kWh reserve scenario. No street coverage is implied.
  for (let index = 0; index < clients + chargers; index++) {
    const isClient = index < clients;
    const number = isClient ? index + 1 : index - clients + 1;
    const angle = index * 2.399963229728653;
    const radius = .0012 + .00018 * Math.sqrt(index);
    nodes.push({
      node_id: `${isClient ? 'C' : 'F'}${number}`, node_type: isClient ? 'visit' : 'charger',
      latitude: Number((-33.45 + Math.sin(angle) * radius).toFixed(7)),
      longitude: Number((-70.66 + Math.cos(angle) * radius).toFixed(7)),
      address: `${isClient ? 'Cliente' : 'Estación'} ${number}`,
      ...(!isClient ? {connector_types: 'J1772;CHAdeMO', total_ports: 2, dc_fast_ports: 1, level2_ports: 1} : {}),
    });
  }
  return {api_version: API_VERSION, network_mode: 'haversine', nodes,
    fleet: {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1}};
}

// Retain the historical example for existing consumers and opaque-ID tests.
// New UI examples use the configurable generator above.
export const SYNTHETIC_PREPARATION = {
  api_version: API_VERSION, network_mode: 'haversine',
  nodes: [
    {node_id: 'BASE#fin', node_type: 'base', latitude: -33.45, longitude: -70.66, address: 'Depósito sintético'},
    {node_id: 'Visita|ñ', node_type: 'visit', latitude: -33.451, longitude: -70.661, address: 'Destino sintético'},
    {node_id: 'V2', node_type: 'visit', latitude: -33.452, longitude: -70.659, address: 'Segundo destino sintético'},
  ],
  fleet: {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1},
};
