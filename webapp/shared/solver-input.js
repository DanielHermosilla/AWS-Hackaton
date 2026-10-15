import { API_VERSION } from './solver-client.js';

const columns = ['node_id', 'node_type', 'latitude', 'longitude', 'address', 'network',
  'total_ports', 'dc_fast_ports', 'level2_ports', 'connector_types', 'max_power_kw'];
const numericColumns = new Set(['latitude', 'longitude', 'total_ports', 'dc_fast_ports', 'level2_ports', 'max_power_kw']);

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
    if (!Number.isFinite(node.latitude) || Math.abs(node.latitude) > 90) throw new Error(`Latitud inválida en ${node.node_id}.`);
    if (!Number.isFinite(node.longitude) || Math.abs(node.longitude) > 180) throw new Error(`Longitud inválida en ${node.node_id}.`);
    for (const key of ['total_ports', 'dc_fast_ports', 'level2_ports']) {
      if (node[key] != null && (!Number.isInteger(node[key]) || node[key] < 0))
        throw new Error(`${key} debe ser un entero no negativo en ${node.node_id}.`);
    }
    if (node.max_power_kw != null && (!Number.isFinite(node.max_power_kw) || node.max_power_kw < 0))
      throw new Error(`Potencia inválida en ${node.node_id}.`);
    if (node.total_ports != null && (node.dc_fast_ports ?? 0) + (node.level2_ports ?? 0) > node.total_ports)
      throw new Error(`Puertos inconsistentes en ${node.node_id}: DC + nivel 2 supera el total.`);
  }
  if (nodes.filter(node => node.node_type === 'base').length !== 1) throw new Error('La instancia necesita exactamente un depósito (base).');
  return nodes;
}

export function inputNodes(input) {
  if (input.nodes) return validateNodes(input.nodes);
  const prepared = input.prepared;
  if (!prepared || prepared.esquema !== 'evrp.instancia_preparada/1')
    throw new Error('El JSON no es una instancia preparada evrp.instancia_preparada/1 admitida.');
  return validateNodes(prepared.nodos?.map(node => ({
    node_id: node.id, node_type: {base: 'base', cliente: 'visit', cargador: 'charger'}[node.tipo],
    latitude: node.lat, longitude: node.lon, address: node.direccion,
  })));
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
    if (['zmd.integration-beta.instance/1', 'zmd.integration-beta.attempt/1'].includes(value.schema_version)) value = value.request;
    else if (value.api_version === API_VERSION && value.result) value = value.result.raw?.input;
    if (!value || typeof value !== 'object') throw new Error('El archivo no contiene una entrada completa reutilizable.');
    if (value.api_version === API_VERSION) {
      const request = value;
      const allowed = {
        request: ['api_version', 'nodes', 'prepared', 'fleet', 'solver', 'network_mode', 'exclude_node_ids'],
        fleet: ['num_vehicles', 'battery_capacity_kwh', 'reserve_kwh', 'initial_soc', 'consumption_kwh_km'],
        solver: ['time_limit_seconds'],
      };
      for (const [name, object] of [['request', request], ['fleet', request.fleet], ['solver', request.solver]]) {
        if (name === 'solver' && object === undefined) continue;
        if (!object || typeof object !== 'object' || Array.isArray(object)) throw new Error(`Falta el objeto ${name} en la instancia.`);
        const unknown = Object.keys(object).filter(key => !allowed[name].includes(key));
        if (unknown.length) throw new Error(`Parámetros no admitidos en ${name}: ${unknown.join(', ')}.`);
      }
      if (request.nodes && request.network_mode !== 'haversine')
        throw new Error('Esta beta solo admite network_mode haversine explícito para una lista de nodos.');
      if (request.prepared && 'network_mode' in request)
        throw new Error('Una instancia preparada ya contiene su red y no admite network_mode.');
      value = {...request, request};
    } else if (value.esquema === 'evrp.instancia_preparada/1') value = {prepared: value};
    else throw new Error('Versión de instancia no admitida. Carga un CSV, una preparada evrp o una descarga de esta beta.');
  }
  inputNodes(value);
  if (value.nodes && value.prepared) throw new Error('Carga nodos o una instancia preparada, no ambas.');
  return value;
}

function positive(value, name) {
  if (value === '' || !Number.isFinite(Number(value)) || Number(value) <= 0)
    throw new Error(`${name} debe ser un número positivo.`);
  return Number(value);
}

export function makeSolveRequest(input, values, timeLimit) {
  inputNodes(input);
  const capacity = positive(values.battery_capacity_kwh, 'La capacidad útil');
  const initial = positive(values.initial_soc, 'El SoC inicial');
  const reserve = positive(values.reserve_kwh, 'La reserva');
  const count = positive(values.num_vehicles, 'La cantidad de vehículos');
  const consumption = positive(values.consumption_kwh_km, 'El consumo supuesto');
  if (!Number.isInteger(count) || count > 20) throw new Error('Configura entre 1 y 20 vehículos.');
  if (initial > 1) throw new Error('El SoC inicial debe ser de hasta 100 %.');
  if (reserve > initial * capacity) throw new Error('La reserva no puede superar la energía inicial.');
  const seconds = positive(timeLimit, 'El tiempo límite');
  if (seconds > 120) throw new Error('El tiempo límite de esta beta es de hasta 120 segundos.');
  return {
    api_version: API_VERSION,
    ...(input.prepared ? {prepared: input.prepared} : {nodes: input.nodes, network_mode: 'haversine'}),
    fleet: {num_vehicles: count, battery_capacity_kwh: capacity, reserve_kwh: reserve,
      initial_soc: initial, consumption_kwh_km: consumption},
    solver: {time_limit_seconds: seconds},
    ...(input.request?.exclude_node_ids ? {exclude_node_ids: input.request.exclude_node_ids} : {}),
  };
}

export const SYNTHETIC_REQUEST = {
  api_version: API_VERSION,
  network_mode: 'haversine',
  nodes: [
    {node_id: 'BASE#fin', node_type: 'base', latitude: -33.45, longitude: -70.66, address: 'Depósito sintético'},
    {node_id: 'Visita|ñ', node_type: 'visit', latitude: -33.451, longitude: -70.661, address: 'Destino sintético'},
    {node_id: 'V2', node_type: 'visit', latitude: -33.452, longitude: -70.659, address: 'Segundo destino sintético'},
  ],
  fleet: {num_vehicles: 2, battery_capacity_kwh: 10, reserve_kwh: 1, initial_soc: .6, consumption_kwh_km: 1},
  solver: {time_limit_seconds: 10},
};
