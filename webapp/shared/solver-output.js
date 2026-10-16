// Presentation only: values and unavailable reasons come from RunResult.
// No route metrics, timing, energy or feasibility are recomputed here.
import {phaseTermination, presentationText} from './presentation-labels.js';
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
      {label: 'Gap relativo · %', value: format(Number.isFinite(phase.relative_gap) ? phase.relative_gap * 100 : null, '%')},
      {label: 'Óptimo de fase reportado por el solver', value: text(phase.proven_optimal)},
      {label: 'Terminación', value: phaseTermination(phase)},
      {label: 'Tiempo de la fase', value: format(phase.runtime_seconds, 's')}
    ], notes: [
      phase.termination_condition === 'energy_gap_limit'
        ? 'Se alcanzó la tolerancia energética configurada; esto no acredita óptimo exacto.' : null,
      phase.has_solution && !phase.proven_optimal
        ? 'Se conserva la mejor solución encontrada, aunque podría existir una mejor.' : null,
      phase.name === 'energy' && (result.phases || []).some(item => item.name === 'deliveries' && !item.proven_optimal)
        ? 'La energía se mejoró para las entregas encontradas; no se demostró el máximo de entregas.' : null,
      result.validation?.feasible === false
      ? 'La comprobación rechazó la solución; el estado reportado por el solver no acredita un plan factible.' : null].filter(Boolean)});
  }
  sections.push({title: 'Tiempos de cómputo', rows: [
    {label: 'Preparación del servicio', value: format(result.runtime_seconds?.preparation, 's')},
    {label: 'Preparación vial original · reutilizable', value: format(result.runtime_seconds?.road_preprocessing, 's')},
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
  const policies = {standard: 'Estándar', deterministic: 'Búsqueda guiada', adaptive: 'Asistencia de IA'};
  const tuningStates = {disabled: 'Sin asistencia de IA', adaptive: 'Asistencia de IA activa',
    fallback: 'Se continuó con la búsqueda estándar', completed: 'Ajuste completado',
    applied: 'Propuesta aplicada', not_applied: 'Propuesta sin aplicar', unavailable: 'Asistencia no disponible'};
  sections.push({title: 'Asistencia de búsqueda', rows: [
    {label: 'Estado informado', value: tuningStates[tuning.status] || 'Sin detalle disponible'},
    {label: 'Modelo', value: text(tuning.model_id)},
    {label: 'Búsqueda solicitada', value: policies[tuning.requested_policy] || 'No disponible'},
    {label: 'Búsqueda utilizada', value: policies[tuning.active_policy] || 'No disponible'},
    {label: 'Consultas', value: format(tuning.calls)},
    {label: 'Decisiones aplicadas', value: format(tuning.applied_decisions)},
  ],
    notes: [tuning.reason].filter(Boolean)});
  for (const decision of tuning.decisions || []) {
    const decisionStatus = {applied: 'Aplicada', not_applied: 'Sin aplicar', rejected: 'Rechazada',
      invalid: 'Respuesta no válida', error: 'Consulta fallida', fallback: 'Búsqueda estándar'}[decision.status] || 'Sin aplicar';
    sections.push({title: `Decisión de IA ${decision.call_index ?? ''} · ${decisionStatus}`, rows: [
      {label: 'Evento / fase', value: `${text(decision.event)} / ${text(decision.phase)}`},
      {label: 'Modelo', value: text(decision.model_id)},
      {label: 'Tiempo de respuesta', value: format(decision.runtime_seconds, 's')},
      {label: 'Instante observado', value: format(decision.elapsed_seconds, 's')},
      {label: 'Cambios aceptados', value: text(decision.effective_changes || {})},
      {label: 'Campos inactivos', value: text(decision.inactive_settings || {})},
      {label: 'Respuesta validada', value: text(decision.proposal)},
      {label: 'Tokens reportados', value: text(decision.usage)},
    ], notes: [decision.reason, decision.proposal?.rationale,
      'Los cambios configuran políticas. Una etapa no ejecutada no produjo mejoras; la respuesta del LLM no certifica la solución.'
    ].filter(Boolean)});
  }
  sections.push({title: 'Trazabilidad', rows: [
    {label: 'Ejecución web', value: text(result.run_id)},
    {label: 'Ejecución nativa', value: text(native.run_id || result.metadata?.native_run_id)},
    {label: 'Estado del motor', value: {
      optimal: 'Mejor solución demostrada', feasible: 'Solución encontrada',
      infeasible: 'Sin plan factible', no_solution: 'Sin solución encontrada',
      invalid_solution: 'Solución rechazada por la comprobación', error: 'Error de ejecución',
      time_limit: 'Tiempo disponible agotado', solver_unavailable: 'Motor no disponible'
    }[native.status || result.metadata?.native_status] || 'Sin detalle disponible'},
    {label: 'Solver solicitado', value: text(solver.requested_solver)},
    {label: 'Solver utilizado', value: text(solver.used_solver)},
    {label: 'Versión del solver', value: text(solver.solver_version)},
    {label: 'Commit base del motor', value: text(result.metadata?.provider_commit)},
    {label: 'Hash de instancia', value: text(native.instance_sha256 || result.metadata?.input_hash)},
    {label: 'Optimalidad lexicográfica reportada por el solver', value: text(result.metadata?.lexicographic_optimal)}
  ], notes: [result.validation?.feasible === false ? 'La solución fue rechazada por la comprobación independiente. La optimalidad reportada no acredita su factibilidad.' : null,
    solver.fallback_reason, solver.message, result.metadata?.certificate_scope].filter(Boolean)});
  sections.push({title: 'Supuestos y advertencias', rows: [],
    notes: [...(result.assumptions || []), ...(result.warnings || [])]});
  return sections.map(section => ({
    ...section,
    rows: section.rows.map(row => ({...row, value: presentationText(row.value), reason: presentationText(row.reason)})),
    notes: section.notes.map(presentationText)
  }));
}

export function stopFacts(stop, labelForNode = () => 'Ubicación siguiente') {
  if (!stop) return [];
  const facts = [];
  if (stop.nextNodeId != null) facts.push({label: 'Próxima parada', value: labelForNode(stop.nextNodeId) || 'Ubicación siguiente'});
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
