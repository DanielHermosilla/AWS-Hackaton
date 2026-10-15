// Presentation preferences and navigation context only. No account or solver state.
const preferenceKey = 'zmd.webapp.presentation.v1';
const contextKey = 'zmd.webapp.plan.v1';
let contextInMemory = null;

export function readPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(preferenceKey));
    return { solidSurfaces: saved?.solidSurfaces === true };
  } catch {
    return { solidSurfaces: false };
  }
}

export function savePreferences(preferences) {
  try {
    localStorage.setItem(preferenceKey, JSON.stringify({
      solidSurfaces: preferences.solidSurfaces === true
    }));
    return true;
  } catch {
    return false;
  }
}

export function readPlanContext() {
  try {
    return JSON.parse(sessionStorage.getItem(contextKey)) || contextInMemory;
  } catch {
    return contextInMemory;
  }
}

export function savePlanContext(context) {
  contextInMemory = context;
  try {
    sessionStorage.setItem(contextKey, JSON.stringify(context));
  } catch {
    // Selection continues to work when browser storage is unavailable.
  }
}

export function clearPlanContext() {
  contextInMemory = null;
  try {
    sessionStorage.removeItem(contextKey);
  } catch {
    // Leaving the local demonstration does not depend on storage access.
  }
}
