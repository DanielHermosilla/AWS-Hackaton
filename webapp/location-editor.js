import { createLocationDraft } from './shared/location-draft.js';
import { validateNodes } from './shared/solver-input.js';

const typeLabels = {base: 'Depósito', visit: 'Destino', charger: 'Cargador', junction: 'Intersección'};
const mapCoordinate = node => {
  if (node?.latitude == null || node?.longitude == null || String(node.latitude).trim() === '' || String(node.longitude).trim() === '') return null;
  const lat = Number(node.latitude), lng = Number(node.longitude);
  return Number.isFinite(lat) && Math.abs(lat) <= 85.051129 && Number.isFinite(lng) && Math.abs(lng) <= 180 ? [lng, lat] : null;
};

export function createLocationEditor({onConfirm, onOpenChange = () => {}}) {
  const dialog = document.createElement('dialog');
  dialog.id = 'location-dialog';
  dialog.className = 'app-dialog location-dialog';
  dialog.setAttribute('aria-labelledby', 'location-heading');
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="location-heading">Editar ubicaciones</h2><button id="close-locations" class="icon-button" type="button" aria-label="Cerrar ubicaciones">×</button></div>
    <p id="location-scope"></p>
    <form id="location-form">
      <div class="location-layout">
        <div class="location-list">
          <label for="location-search">Buscar entre los puntos cargados</label>
          <input id="location-search" type="search" placeholder="ID o dirección" autocomplete="off">
          <label for="location-node">Punto seleccionado</label>
          <select id="location-node" size="8" aria-describedby="location-count"></select>
          <p id="location-count" class="location-help" role="status"></p>
        </div>
        <section class="location-detail" aria-label="Ubicación del punto">
          <dl class="location-identity"><div><dt>ID</dt><dd id="location-id"></dd></div><div><dt>Tipo</dt><dd id="location-type"></dd></div></dl>
          <label for="location-address">Dirección o referencia</label>
          <input id="location-address" type="text" autocomplete="off" aria-describedby="location-address-help">
          <p id="location-address-help" class="location-help">Referencia escrita, sin búsqueda en línea. Cambiar el texto no mueve el punto: confirma sus coordenadas o ajusta el marcador.</p>
          <div class="location-coordinates">
            <label for="location-latitude">Latitud · °<input id="location-latitude" type="number" step="any" min="-90" max="90" required></label>
            <label for="location-longitude">Longitud · °<input id="location-longitude" type="number" step="any" min="-180" max="180" required></label>
          </div>
          <div class="location-map-tools"><button id="center-location" type="button" disabled>Centrar punto</button><button id="pick-location" type="button" aria-pressed="false" disabled>Elegir en el mapa</button></div>
          <div id="location-map" class="location-map" aria-label="Mapa de la ubicación seleccionada"></div>
          <p id="location-map-status" class="location-help" role="status">Cargando mapa…</p>
        </section>
      </div>
      <p id="location-validation" class="location-validation" role="status" aria-live="polite" tabindex="-1"></p>
      <div class="dialog-actions location-actions"><button id="cancel-locations" type="button">Cancelar</button><button id="confirm-locations" type="submit" class="primary">Confirmar ubicaciones</button></div>
    </form>`;
  document.body.append(dialog);
  const $ = id => dialog.querySelector(`#${id}`);
  let draft, selectedId, opener, map, marker, mapObserver, mapTimer;
  let generation = 0, picking = false, mapFailed = false, mapReady = false, markerAdded = false;
  let closed = Promise.resolve(), resolveClosed;
  const node = () => draft?.nodes.find(value => value.node_id === selectedId);

  function setPicking(value) {
    picking = value;
    $('pick-location').setAttribute('aria-pressed', String(value));
    $('pick-location').textContent = value ? 'Cancelar selección en mapa' : 'Elegir en el mapa';
    if (map) map.getCanvas().style.cursor = value ? 'crosshair' : '';
    renderMapStatus();
  }
  function renderMapStatus() {
    $('location-map-status').textContent = !map
      ? 'Mapa no disponible. Puedes revisar y confirmar la ubicación con el formulario.'
      : !mapCoordinate(node())
        ? draft?.readOnly
          ? 'La instancia no incluye coordenadas representables para este punto. Sus datos permanecen en la lista.'
          : 'Este punto no se puede representar en el mapa. Revisa las coordenadas; las latitudes polares se conservan en el formulario.'
        : [
          mapFailed ? 'No se pudo cargar la cartografía. Las coordenadas y el formulario siguen disponibles.' : !mapReady ? 'Cargando cartografía…' : '',
          draft?.readOnly ? 'Ubicación de la instancia nativa.' : picking ? 'Haz clic para elegir la ubicación; después confirma los cambios.' : 'Arrastra el marcador o usa las coordenadas. El mapa no valida accesos ni calles.',
        ].filter(Boolean).join(' ');
  }
  function renderValidation() {
    let error = '';
    if (!draft.readOnly) {
      try { validateNodes(draft.nodes); }
      catch (failure) { error = failure.message; }
    }
    $('confirm-locations').disabled = !!error;
    $('location-validation').textContent = error || (draft.readOnly ? '' : draft.changed
      ? 'Cambios pendientes. Se aplicarán juntos al confirmar y habrá que calcular de nuevo.'
      : 'Sin cambios. Cancelar conserva la entrada y cualquier cálculo en curso.');
    $('location-validation').classList.toggle('is-error', !!error);
  }
  function renderList() {
    const query = $('location-search').value.trim().toLocaleLowerCase('es');
    const nodes = draft.nodes;
    const matches = nodes.map((value, index) => ({value, index})).filter(({value}) =>
      `${value.node_id} ${value.address || ''}`.toLocaleLowerCase('es').includes(query));
    // A native network can contain thousands of junctions. Search keeps the
    // selector manageable without dropping any node from the input.
    const displayed = matches.slice(0, 200);
    const selected = nodes.findIndex(value => value.node_id === selectedId);
    if (!displayed.some(({index}) => index === selected)) displayed.unshift({value: nodes[selected], index: selected});
    $('location-node').replaceChildren(...displayed.map(({value, index}) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = `${typeLabels[value.node_type]} · ${value.node_id}${value.address ? ` · ${value.address}` : ''}`;
      option.selected = value.node_id === selectedId;
      return option;
    }));
    $('location-count').textContent = query
      ? `${matches.length} coincidencias locales.${matches.length > 200 ? ' Se muestran las primeras 200; afina la búsqueda.' : ''} El punto seleccionado se conserva.`
      : `${nodes.length} puntos cargados.${nodes.length > 200 ? ' Usa la búsqueda para encontrar otros puntos.' : ''}`;
  }
  function updateMarker(center = false) {
    if (!map || !marker) return;
    const coordinates = mapCoordinate(node());
    $('center-location').disabled = !coordinates;
    if (!coordinates) {
      marker.remove(); markerAdded = false;
    } else {
      marker.setLngLat(coordinates);
      marker.getElement().setAttribute('aria-label', `${typeLabels[node().node_type]} ${selectedId}`);
      if (!markerAdded) { marker.addTo(map); markerAdded = true; }
      if (center) map.jumpTo({center: coordinates, zoom: 14});
    }
    renderMapStatus();
  }
  function renderFields(center = false) {
    const selected = node();
    $('location-id').textContent = selected.node_id;
    $('location-type').textContent = typeLabels[selected.node_type];
    for (const field of ['address', 'latitude', 'longitude']) {
      const input = $(`location-${field}`);
      input.value = selected[field] ?? '';
      input.readOnly = draft.readOnly;
      input.placeholder = draft.readOnly ? 'Sin dato' : '';
    }
    updateMarker(center);
    renderValidation();
  }
  function chooseCoordinates(coordinates) {
    if (!draft || draft.readOnly) return;
    const longitude = Number(coordinates.lng.toFixed(6));
    const latitude = Number(coordinates.lat.toFixed(6));
    if (Math.abs(longitude) > 180 || Math.abs(latitude) > 90) return;
    draft.update(selectedId, {latitude, longitude});
    renderFields();
    setPicking(false);
  }
  async function loadMap(current) {
    try {
      const maplibre = await import('./vendor/maplibre/maplibre-gl.mjs');
      if (current !== generation || !dialog.open) return;
      const href = new URL('./vendor/maplibre/maplibre-gl.css', import.meta.url).href;
      if (![...document.querySelectorAll('link[rel="stylesheet"]')].some(link => link.href === href)) {
        const css = document.createElement('link');
        css.rel = 'stylesheet'; css.href = href; document.head.append(css);
      }
      map = new maplibre.Map({
        container: $('location-map'),
        style: new URL('./vendor/maplibre/positron.json', import.meta.url).href,
        center: mapCoordinate(node()) || [0, 0], zoom: mapCoordinate(node()) ? 14 : 1,
        attributionControl: true, pitchWithRotate: false, dragRotate: false, touchPitch: false, renderWorldCopies: false,
      });
      map.addControl(new maplibre.NavigationControl({showCompass: false}), 'bottom-right');
      marker = new maplibre.Marker({draggable: !draft.readOnly, color: '#216b68'});
      marker.getElement().setAttribute('tabindex', '-1');
      marker.on('dragend', () => chooseCoordinates(marker.getLngLat()));
      map.on('click', event => { if (picking) chooseCoordinates(event.lngLat); });
      map.on('error', () => { mapFailed = true; renderMapStatus(); });
      map.on('load', () => { mapReady = true; renderMapStatus(); });
      mapObserver = new ResizeObserver(() => map?.resize());
      mapObserver.observe($('location-map'));
      mapTimer = setTimeout(() => {
        if (!mapReady && !mapFailed) $('location-map-status').textContent = 'La cartografía tarda en cargar. Puedes editar con el formulario.';
      }, 12000);
      $('pick-location').disabled = draft.readOnly;
      updateMarker();
    } catch {
      if (current !== generation || !dialog.open) return;
      marker?.remove(); map?.remove();
      marker = null; map = null;
      $('center-location').disabled = true;
      $('pick-location').disabled = true;
      renderMapStatus();
    }
  }
  function finish() {
    if (!draft) return;
    draft.cancel(); draft = null; generation++;
    clearTimeout(mapTimer);
    mapObserver?.disconnect(); mapObserver = null;
    marker?.remove(); marker = null;
    map?.remove(); map = null;
    markerAdded = false;
    onOpenChange(false);
    resolveClosed?.(); resolveClosed = null;
    opener?.focus();
  }
  function close() { if (dialog.open) dialog.close(); finish(); }
  dialog.addEventListener('close', () => { if (!dialog.open) finish(); });
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  $('close-locations').addEventListener('click', close);
  $('cancel-locations').addEventListener('click', close);
  $('location-search').addEventListener('input', renderList);
  $('location-node').addEventListener('change', () => {
    selectedId = draft.nodes[Number($('location-node').value)].node_id;
    setPicking(false);
    renderFields(true);
  });
  for (const field of ['address', 'latitude', 'longitude']) {
    $(`location-${field}`).addEventListener('input', event => {
      if (draft.readOnly) return;
      draft.update(selectedId, {[field]: event.target.value});
      if (field === 'address') renderList();
      updateMarker();
      renderValidation();
    });
  }
  $('center-location').addEventListener('click', () => updateMarker(true));
  $('pick-location').addEventListener('click', () => setPicking(!picking));
  $('location-form').addEventListener('submit', event => {
    event.preventDefault();
    if (draft.readOnly) return;
    try {
      const changed = draft.changed;
      const confirmed = draft.commit();
      if (changed) onConfirm(confirmed);
      close();
    } catch (error) {
      $('location-validation').textContent = error.message;
      $('location-validation').classList.add('is-error');
      $('location-validation').focus();
    }
  });
  return {
    get isOpen() { return dialog.open; },
    whenClosed() { return closed; },
    close,
    open(input, trigger) {
      if (dialog.open) return;
      draft = createLocationDraft(input);
      opener = trigger;
      selectedId = draft.nodes[0].node_id;
      picking = false; mapFailed = false; mapReady = false;
      closed = new Promise(resolve => { resolveClosed = resolve; });
      $('location-search').value = '';
      $('location-heading').textContent = draft.readOnly ? 'Ubicaciones de la instancia' : 'Editar ubicaciones';
      $('location-scope').textContent = draft.readOnly
        ? 'Esta instancia conserva una red nativa ya calculada. Para mover sus puntos, carga un CSV o una entrada de ubicaciones y vuelve a preparar la red.'
        : 'Revisa depósito, destinos y cargadores. El ID y el tipo se conservan. Al confirmar, el servidor deberá preparar de nuevo la aproximación por distancia; no es una red vial.';
      $('location-address-help').hidden = draft.readOnly;
      $('confirm-locations').hidden = draft.readOnly;
      $('cancel-locations').textContent = draft.readOnly ? 'Volver al cálculo' : 'Cancelar';
      $('pick-location').hidden = draft.readOnly;
      $('pick-location').disabled = true;
      $('center-location').disabled = true;
      $('location-map').replaceChildren();
      renderList(); renderFields();
      dialog.showModal();
      $('location-node').focus();
      onOpenChange(true);
      setPicking(false);
      loadMap(++generation);
    },
  };
}
