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
const requireFields = (value, allowed, name) => {
  if (!record(value)) throw new Error(`Falta el objeto ${name}.`);
  const unknown = Object.keys(value).filter(key => !allowed.includes(key));
  if (unknown.length) throw new Error(`Parámetros no admitidos en ${name}: ${unknown.join(', ')}.`);
};

// Lightweight input checks only. The backend's native Pydantic contract remains
// authoritative; the original instance is returned without defaults or rewrites.
export function validateNativeInstance(instance) {
  requireFields(instance, nativeFields, 'ProblemInstance');
  if (instance.schema_version !== '1.0' || !Array.isArray(instance.nodes) || !Array.isArray(instance.arcs))
    throw new Error('Carga una ProblemInstance nativa con schema_version 1.0, nodes y arcs.');
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
  for (const arc of instance.arcs) {
    if (!record(arc) || !ids.has(arc.from_node_id) || !ids.has(arc.to_node_id)) throw new Error('Un arco referencia nodos desconocidos.');
    const key = JSON.stringify([arc.from_node_id, arc.to_node_id]);
    if (pairs.has(key) || arc.from_node_id === arc.to_node_id) throw new Error('La instancia contiene arcos duplicados o autoarcos.');
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

export function parseInstanceFile(text, filename = '') {
  let value;
  const cleaned = text.replace(/^\ufeff/, '');
  if (/\.csv$/i.test(filename) || !cleaned.trimStart().startsWith('{')) {
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
    try { value = JSON.parse(cleaned); }
    catch { throw new Error('El archivo no contiene JSON válido.'); }
    if (value?.schema_version === 'zmd.integration-beta.attempt/2') value = value.request?.instance ? value.request : value.prepare_request || value.request;
    if (value?.api_version === API_VERSION && value.result) value = value.result.raw?.input;
    if (!record(value)) throw new Error('El archivo no contiene una entrada completa reutilizable.');
    if (value.schema_version === '1.0') value = {instance: validateNativeInstance(value)};
    else if (value.api_version === API_VERSION && value.instance) {
      const request = value;
      requireFields(request, ['api_version', 'instance', 'solver'], 'request');
      if (request.solver !== undefined) requireFields(request.solver, ['time_limit_seconds'], 'solver');
      value = {instance: validateNativeInstance(request.instance), request};
    } else if (value.api_version === API_VERSION && value.nodes) {
      requireFields(value, ['api_version', 'nodes', 'fleet', 'network_mode'], 'prepare');
      requireFields(value.fleet, ['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km', 'vehicle_connector_types'], 'fleet');
      if (value.network_mode !== 'haversine') throw new Error('La preparación de nodos requiere network_mode haversine explícito.');
      value = {nodes: value.nodes, prepareRequest: value};
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

export function solverSettings(timeLimit) {
  const seconds = positive(timeLimit, 'El tiempo límite');
  if (seconds < 1 || seconds > 120) throw new Error('El tiempo límite debe estar entre 1 y 120 segundos.');
  return {time_limit_seconds: seconds};
}

export function makeSolveRequest(input, timeLimit) {
  if (!input.instance) throw new Error('Primero prepara los nodos en el servidor para obtener una instancia nativa.');
  return {api_version: API_VERSION, instance: validateNativeInstance(input.instance), solver: solverSettings(timeLimit)};
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
  return {api_version: API_VERSION, nodes: input.nodes, network_mode: 'haversine',
    fleet: {num_vehicles: count, battery_capacity_kwh: capacity, reserve_kwh: reserve,
      initial_soc: initial, consumption_kwh_km: consumption,
      ...(connectors ? {vehicle_connector_types: [...connectors]} : {})}};
}

export const SYNTHETIC_PREPARATION = {
  api_version: API_VERSION,
  network_mode: 'haversine',
  nodes: [
    {node_id: 'BASE#fin', node_type: 'base', latitude: -33.45, longitude: -70.66, address: 'Depósito sintético'},
    {node_id: 'Visita|ñ', node_type: 'visit', latitude: -33.451, longitude: -70.661, address: 'Destino sintético'},
    {node_id: 'V2', node_type: 'visit', latitude: -33.452, longitude: -70.659, address: 'Segundo destino sintético'},
  ],
  fleet: {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1},
};
