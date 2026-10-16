// Presentation only: values and unavailable reasons come from Daniel's RunResult.
// No route metrics, timing, energy or feasibility are recomputed here.
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const format = (value, unit = '') => Number.isFinite(value)
  ? `${value.toLocaleString('es-CL', {maximumFractionDigits: 6})}${unit ? ` ${unit}` : ''}`
  : 'No disponible';
const text = value => value == null ? 'No disponible'
  : typeof value === 'boolean' ? value ? 'Sí' : 'No'
    : typeof value === 'object' ? JSON.stringify(value) : String(value);

export function nativeRunResult(envelope) {
  const native = envelope?.result?.raw?.result;
  return native?.schema_version === '1.0' && record(native.solve) && record(native.kpis) ? native : null;
}

export function resultSections(result) {
  const native = nativeRunResult({result}) || {};
  const kpis = result.kpis || native.kpis || {};
  const timings = native.runtime_seconds || {};
  const solver = result.metadata?.native_solver || native.solve || {};
  const checks = result.validation?.checks || native.validation?.checks || {};
  const tuning = result.tuning || native.tuning || {};
  const sections = [];
  const metric = (key, label, unit = '') => ({
    label, value: format(kpis[key], unit),
    reason: kpis[key] == null ? kpis.unavailable_reasons?.[key] || 'El motor no informa este dato para esta ejecución.' : null
  });
  sections.push({title: 'Resultados del motor', rows: [
    metric('served_deliveries', 'Entregas planificadas'), metric('total_deliveries', 'Destinos de la instancia'),
    metric('net_battery_energy_kwh', 'Energía neta de batería', 'kWh'),
    metric('charged_to_battery_kwh', 'Energía incorporada a batería', 'kWh'),
    metric('grid_energy_kwh', 'Electricidad de la red', 'kWh'),
    metric('minimum_battery_kwh', 'Mínima batería de llegada', 'kWh'),
    metric('distance_km', 'Distancia recorrida', 'km'), metric('charging_stops', 'Paradas de recarga'),
    metric('operational_duration_seconds', 'Tiempo hasta el último retorno', 's'),
    ...(Object.hasOwn(kpis, 'total_vehicle_time_seconds') ? [metric('total_vehicle_time_seconds', 'Tiempo acumulado de vehículos', 's')] : []),
    metric('time_saved_seconds', 'Ahorro de tiempo frente a referencia', 's'),
    metric('co2e_saved_kg', 'CO₂e evitado frente a referencia', 'kg CO₂e')
  ], notes: kpis.operational_duration_definition ? [kpis.operational_duration_definition] : []});
  const checkLabels = {fleet: 'Flota', topology: 'Continuidad y retorno', deliveries: 'Entregas',
    battery: 'Batería', charging: 'Recarga', energy: 'Balance energético', time: 'Tiempos operacionales'};
  sections.push({title: 'Comprobación independiente', rows: Object.entries(checks).map(([key, value]) => ({
    label: checkLabels[key] || key, value: value === true ? 'Cumple' : value === false ? 'No cumple' : 'No disponible'
  })), notes: [
    result.validation?.feasible === true ? 'La solución pasó la comprobación del modelo.'
      : result.validation?.feasible === false ? 'La solución no pasó la comprobación.' : 'No hay una solución comprobada.',
    result.validation?.scope, ...(result.validation?.violations || [])
  ].filter(Boolean)});
  for (const phase of result.phases || []) {
    const unit = phase.name === 'energy' ? 'kWh' : 'entregas';
    sections.push({title: phase.name === 'energy' ? 'Fase: minimizar energía' : 'Fase: maximizar entregas', rows: [
      {label: 'Mejor solución', value: format(phase.incumbent, unit)},
      {label: 'Cota', value: format(phase.best_bound, unit)},
      {label: 'Gap absoluto', value: format(phase.absolute_gap, unit)},
      {label: 'Gap relativo (fracción)', value: format(phase.relative_gap)},
      {label: 'Óptimo de fase reportado por el solver', value: text(phase.proven_optimal)},
      {label: 'Terminación', value: text(phase.termination_condition)},
      {label: 'Tiempo de la fase', value: format(phase.runtime_seconds, 's')}
    ], notes: [phase.message, result.validation?.feasible === false
      ? 'La comprobación rechazó la solución; el estado reportado por el solver no acredita un plan factible.' : null].filter(Boolean)});
  }
  sections.push({title: 'Tiempos de cómputo', rows: [
    {label: 'Preparación del servicio', value: format(result.runtime_seconds?.preparation, 's')},
    {label: 'Resolución, incluido el modelo', value: format(timings.resolution_including_model ?? result.runtime_seconds?.solver, 's')},
    {label: 'Comprobación independiente', value: format(timings.validation, 's')},
    {label: 'Comprobación de solución inicial', value: format(timings.initial_solution_validation, 's')},
    {label: 'LLM, incluido en resolución', value: format(timings.llm, 's')},
    {label: 'Total del motor', value: format(timings.total, 's')},
    {label: 'Total del servicio', value: format(result.runtime_seconds?.total, 's')}
  ], notes: ['Son intervalos con inclusiones y posibles solapamientos; no se suman. Los tiempos operacionales se muestran por separado.']});
  const operations = result.operations || native.operations;
  if (operations) sections.push({title: 'Configuración operacional', rows: [
    ['service_seconds', 'Servicio por defecto', 's'],
    ['max_route_seconds', 'Límite de duración por ruta', 's'],
    ['assumed_speed_kph', 'Velocidad supuesta cuando falta tiempo de arco', 'km/h'],
    ['include_charging_time', 'Tiempo de carga incluido'],
    ['charging_power_kw', 'Potencia de carga por defecto', 'kW'],
    ['charging_efficiency', 'Eficiencia de carga (fracción)'],
    ['energy_margin_fraction', 'Margen energético (fracción)'],
    ['final_reserve_soc', 'SoC mínimo al regreso (fracción)'],
    ['use_customer_time_windows', 'Ventanas de clientes activas'],
    ['service_seconds_by_customer', 'Servicio por cliente · segundos'],
    ['charging_power_kw_by_station', 'Potencia por estación · kW'],
    ['customer_time_windows', 'Ventanas por cliente · segundos desde t=0'],
    ['disabled_charger_ids', 'Cargadores deshabilitados']
  ].filter(([key]) => Object.hasOwn(operations, key)).map(([key, label, unit]) => ({
    label, value: operations[key] === null ? 'Sin configurar' : typeof operations[key] === 'number'
      ? format(operations[key], unit) : text(operations[key])
  })), notes: ['Son supuestos de esta instancia. El archivo nativo conserva toda la configuración.']});
  sections.push({title: 'Tuning', rows: [{label: 'Estado informado', value: text(tuning.status)}],
    notes: [tuning.reason].filter(Boolean)});
  sections.push({title: 'Trazabilidad', rows: [
    {label: 'Ejecución web', value: text(result.run_id)},
    {label: 'Ejecución nativa', value: text(native.run_id || result.metadata?.native_run_id)},
    {label: 'Estado nativo', value: text(native.status || result.metadata?.native_status)},
    {label: 'Solver solicitado', value: text(solver.requested_solver)},
    {label: 'Solver utilizado', value: text(solver.used_solver)},
    {label: 'Versión del solver', value: text(solver.solver_version)},
    {label: 'Commit del motor', value: text(result.metadata?.provider_commit)},
    {label: 'Hash de instancia', value: text(native.instance_sha256 || result.metadata?.input_hash)},
    {label: 'Optimalidad lexicográfica reportada por el solver', value: text(result.metadata?.lexicographic_optimal)}
  ], notes: [result.validation?.feasible === false ? 'La solución fue rechazada por la comprobación independiente. La optimalidad reportada no acredita su factibilidad.' : null,
    solver.fallback_reason, solver.message, result.metadata?.certificate_scope].filter(Boolean)});
  sections.push({title: 'Supuestos y advertencias', rows: [],
    notes: [...(result.assumptions || []), ...(result.warnings || [])]});
  return sections;
}

export function stopFacts(stop) {
  if (!stop) return [];
  const facts = [];
  if (stop.nextNodeId != null) facts.push({label: 'Siguiente nodo', value: stop.nextNodeId});
  for (const [key, label, unit] of [
    ['predictedArcEnergyKwh', 'Energía prevista al siguiente nodo', 'kWh'],
    ['effectiveArcEnergyKwh', 'Energía efectiva al siguiente nodo', 'kWh'],
    ['arrivalSeconds', 'Llegada desde t=0', 's'],
    ['serviceStartSeconds', 'Inicio de servicio desde t=0', 's'],
    ['departureSeconds', 'Salida desde t=0', 's'],
    ['serviceDurationSeconds', 'Duración del servicio', 's'],
    ['chargingDurationSeconds', 'Duración de recarga', 's'],
    ['travelTimeSeconds', 'Viaje al siguiente nodo', 's']
  ]) if (Number.isFinite(stop[key])) facts.push({label, value: format(stop[key], unit)});
  return facts;
}
