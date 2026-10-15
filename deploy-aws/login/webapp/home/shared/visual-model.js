import { summarizePlan } from './model.js';

// Presentation aggregates from the existing Plan fixture; no operational progress.
export function buildVisualOverview(data) {
  const base = summarizePlan(data, null);
  const visits = new Set(data.NODES.filter(node => node.type === 'visit').map(node => node.id));
  const owners = new Map();
  const ratio = (part, whole) => Number.isFinite(part) && part >= 0 && whole > 0 ? part / whole * 100 : null;
  const fleet = base.fleet.map(vehicle => {
    const route = data.ROUTES.find(item => item.vehicleId === vehicle.id);
    const assignedIds = new Set((route?.stopIds || []).filter(id => visits.has(id)));
    for (const id of assignedIds) owners.set(id, (owners.get(id) || 0) + 1);
    return {
      ...vehicle,
      assigned: assignedIds.size,
      assignmentShare: ratio(assignedIds.size, base.stats.visits),
      energyShare: ratio(vehicle.energyKwh, base.stats.energyKwh),
      initialSoc: vehicle.initialSoc,
      socInScale: Number.isFinite(vehicle.finalSoc) && vehicle.finalSoc >= 0 && vehicle.finalSoc <= 100,
    };
  });
  const overlapCount = [...owners.values()].filter(count => count > 1).length;
  const distributed = fleet.reduce((sum, vehicle) => sum + vehicle.assigned, 0);
  const representedEnergy = fleet.reduce((sum, vehicle) => sum + (Number.isFinite(vehicle.energyKwh) ? vehicle.energyKwh : 0), 0);
  return {
    ...base, fleet,
    assignmentPercent: ratio(base.stats.assigned, base.stats.visits),
    unassigned: Math.max(0, base.stats.visits - base.stats.assigned),
    assignedFleet: fleet.filter(vehicle => vehicle.assigned > 0).length,
    overlapCount,
    assignmentDistributionValid: overlapCount === 0 && distributed === base.stats.assigned && base.stats.visits > 0,
    energyDistributionValid: fleet.every(vehicle => Number.isFinite(vehicle.energyKwh) && vehicle.energyKwh >= 0)
      && base.stats.energyKwh > 0 && Math.abs(representedEnergy - base.stats.energyKwh) < 1e-9,
  };
}
