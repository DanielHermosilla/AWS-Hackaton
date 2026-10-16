const text = value => typeof value === 'string' ? value.slice(0, 1200) : '';
const number = value => Number.isFinite(value) ? new Intl.NumberFormat('es-CL', {maximumFractionDigits: 2}).format(value) : null;
const array = value => Array.isArray(value) ? value : [];

function valueText(value) {
  if (value === null) return 'Sin dato';
  if (typeof value === 'boolean') return value ? 'Sí' : 'No';
  if (Number.isFinite(value)) return number(value);
  if (typeof value === 'string') return text(value);
  if (value && Number.isFinite(value.median)) return `mediana ${number(value.median)}`;
  return '';
}

function evidenceText(evidence) {
  if (typeof evidence === 'string') return text(evidence);
  const labels = {column: 'Columna', sample: 'Muestra', statistic: 'Estadística', metadata: 'Dato declarado', computed: 'Resumen calculado'};
  return array(evidence).slice(0, 4).map(ref => {
    const key = text(ref?.key);
    if (!key) return '';
    const value = Object.hasOwn(ref, 'value') && ref.value !== null ? valueText(ref.value) : '';
    return `${labels[ref.kind] || 'Fuente'}: ${key}${value ? ` = ${value}` : ''}`;
  }).filter(Boolean).join(' · ');
}

function detail(item, category = '') {
  const label = text(item) || text(item?.description) || text(item?.label) || text(item?.name);
  if (!label) return null;
  const value = item && typeof item === 'object' && Object.hasOwn(item, 'value') ? valueText(item.value) : '';
  const unit = text(item?.unit);
  const statistics = item?.statistics || (item?.value && typeof item.value === 'object' ? item.value : null);
  const spread = Number.isFinite(statistics?.p10) && Number.isFinite(statistics?.p90)
    ? `El 80 % central: ${number(statistics.p10)}–${number(statistics.p90)}${unit ? ` ${unit}` : ''}.` : '';
  const kind = {observed: 'Observado', observed_distribution: 'Observado', declared: 'Declarado', method: 'Método aplicado', model_assumption: 'Supuesto aplicado'}[item?.kind] || category;
  return {
    text: `${kind ? `${kind} · ` : ''}${label}${value ? `: ${value}${unit && value !== 'Sin dato' ? ` ${unit}` : ''}` : ''}`,
    note: [text(item?.explanation), spread, evidenceText(item?.evidence) || text(item?.reason)].filter(Boolean).join(' '),
  };
}

export function historyCoverageSnapshot(coverage) {
  const known = ['calibrated_arc_count', 'road_arc_count', 'arc_coverage_fraction', 'mixed_sign_arc_count'];
  return {
    summary: Object.fromEntries(known.filter(key => Number.isFinite(coverage?.summary?.[key])).map(key => [key, coverage.summary[key]])),
    assumptions: array(coverage?.assumptions).slice(0, 24).map(item => {
      if (typeof item === 'string') return text(item);
      return {
        key: text(item?.key), label: text(item?.label) || text(item?.description) || text(item?.name),
        value: valueText(item?.value), unit: text(item?.unit), kind: text(item?.kind),
        evidence: evidenceText(item?.evidence) || text(item?.reason),
      };
    }),
    warnings: array(coverage?.warnings).slice(0, 16).map(item => text(item) || text(item?.message)).filter(Boolean),
  };
}

// Presentation only: preserve measured values, evidence and explicit non-applied
// suggestions. Nothing in these groups changes the fleet or the energy model.
export function historyDetailGroups(profile, coverage) {
  if (!profile) return [];
  const known = array(profile.assumptions);
  const knownKeys = new Set(known.map(item => item?.key).filter(Boolean));
  const groups = [
    {title: 'Datos y criterios del histórico', items: known.slice(0, 24).map(item => detail(item))},
    {title: 'Observaciones de la IA', items: array(profile.ai_analysis?.observations).slice(0, 24).map(item => detail(item, 'Observado'))},
    {title: 'Sugerencias de la IA · sin aplicar', items: array(profile.ai_analysis?.assumptions).slice(0, 16).map(item => detail(item))},
    {title: 'Al preparar las calles', items: array(coverage?.assumptions).filter(item => !knownKeys.has(item?.key)).slice(0, 16).map(item => detail(item))},
  ];
  const mixed = coverage?.summary?.mixed_sign_arc_count;
  if (Number.isFinite(mixed) && mixed > 0) groups.at(-1).items.unshift({
    text: `${number(mixed)} tramos combinan descarga y recuperación.`,
    note: 'Su cálculo usa los supuestos de orden y reparto indicados aquí.',
  });
  const limitations = [...array(profile.ai_analysis?.limitations), ...array(coverage?.warnings)].slice(0, 16);
  groups.push({title: 'Alcance y datos que faltan', items: limitations.map(item => detail(item))});
  return groups.map(group => ({...group, items: group.items.filter(Boolean)})).filter(group => group.items.length);
}
