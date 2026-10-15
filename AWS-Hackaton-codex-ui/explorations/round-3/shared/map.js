import * as maplibre from '../../round-2/shared/vendor/maplibre-gl.mjs';
import { NODES, ROUTES, VEHICLES } from './data.js';
import { icon } from './icons.js';

const css = document.createElement('link');
css.rel = 'stylesheet';
css.href = new URL('../../round-2/shared/vendor/maplibre-gl.css', import.meta.url);
document.head.append(css);

export async function createMap(container, options = {}) {
  const host = typeof container === 'string' ? document.getElementById(container) : container;
  const status = document.createElement('div');
  status.className = 'map-status';
  status.setAttribute('role', 'status');
  let map, ready = false, vehicleId = null, planVisible = options.showRoutes !== false;
  let chargersVisible = false, selectedId = null, cameraMode = 'fit';
  const markers = [];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const noop = () => {};
  let observer;
  try {
    map = new maplibre.Map({
      container: host,
      style: new URL('../../round-2/shared/vendor/positron.json', import.meta.url).href,
      center: [-83.753, 42.274],
      zoom: 11.3,
      attributionControl: true,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      renderWorldCopies: false
    });
  } catch {
    host.append(status);
    status.textContent = 'Mapa no disponible en este navegador. Puedes explorar las paradas en la lista.';
    return {selectVehicle:noop,selectNode:noop,fit:noop,toggleChargers:noop,setPlanVisible:noop,destroy:noop};
  }
  host.append(status);
  status.textContent = 'Cargando cartografía…';
  map.addControl(new maplibre.NavigationControl({showCompass:false}), 'bottom-right');
  map.addControl(new maplibre.ScaleControl({unit:'metric'}), 'bottom-left');
  const timer = setTimeout(() => {
    if (!ready) status.textContent = 'La cartografía está tardando en cargar. La lista de paradas sigue disponible.';
  }, 12000);
  map.on('error', () => {
    status.textContent = 'No se pudo cargar parte de la cartografía. Las paradas siguen disponibles.';
  });
  function fit(animate = true) {
    cameraMode = 'fit';
    const visibleRoutes = vehicleId ? ROUTES.filter(r => r.vehicleId === vehicleId) : ROUTES;
    const stopIds = new Set(visibleRoutes.flatMap(r => r.stopIds));
    const coords = planVisible
      ? [...visibleRoutes.flatMap(r => r.geometry.coordinates), ...NODES.filter(n => stopIds.has(n.id)).map(n => [n.lng,n.lat])]
      : NODES.filter(n => n.type !== 'charger').map(n => [n.lng, n.lat]);
    const bounds = coords.reduce((b,c) => b.extend(c), new maplibre.LngLatBounds(coords[0], coords[0]));
    const requestedPadding = typeof options.padding === 'function' ? options.padding() : options.padding || 56;
    const padding = typeof requestedPadding === 'number'
      ? {top:requestedPadding,right:requestedPadding,bottom:requestedPadding,left:requestedPadding}
      : {...requestedPadding};
    // Attribution wraps on narrow maps; keep the full marker above that area.
    if (host.clientWidth < 700) padding.bottom = Math.max(padding.bottom || 0, 80);
    map.fitBounds(bounds, {padding, maxZoom:14, duration:reduce.matches || !animate ? 0 : 450});
  }
  function update() {
    for (const {node,el} of markers) {
      const usedCharger = ROUTES.some(r => (!vehicleId || r.vehicleId === vehicleId) && r.stopIds.includes(node.id));
      el.hidden = node.type === 'charger' && !chargersVisible && !(planVisible && usedCharger);
      el.classList.toggle('is-muted', !!vehicleId && node.type === 'visit' && node.vehicleId !== vehicleId && planVisible);
      el.classList.toggle('is-selected', node.id === selectedId);
      el.setAttribute('aria-pressed', String(node.id === selectedId));
      if (node.type === 'visit') el.style.background = planVisible ? VEHICLES.find(v => v.id === node.vehicleId)?.color || '#576b7e' : '#576b7e';
    }
    if (!ready) return;
    for (const r of ROUTES) {
      const active = !vehicleId || r.vehicleId === vehicleId;
      for (const suffix of ['halo','line']) {
        map.setLayoutProperty(`${r.vehicleId}-${suffix}`, 'visibility', planVisible ? 'visible' : 'none');
        map.setPaintProperty(`${r.vehicleId}-${suffix}`, 'line-opacity', active ? (suffix === 'halo' ? .95 : .9) : .12);
      }
    }
  }
  function selectNode(id, move = true) {
    const node = NODES.find(n => n.id === id);
    if (!node) return;
    selectedId = id;
    update();
    if (move) {
      cameraMode = 'focus';
      map.easeTo({center:[node.lng,node.lat],zoom:Math.max(map.getZoom(),12.5),duration:reduce.matches ? 0 : 350});
    }
  }
  map.on('load', () => {
    ready = true;
    clearTimeout(timer);
    status.textContent = '';
    for (const route of ROUTES) {
      map.addSource(route.vehicleId, {type:'geojson', data:{type:'Feature', properties:{}, geometry:route.geometry}});
      const color = VEHICLES.find(v => v.id === route.vehicleId).color;
      map.addLayer({id:`${route.vehicleId}-halo`,type:'line',source:route.vehicleId,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#ffffff','line-width':8}});
      map.addLayer({id:`${route.vehicleId}-line`,type:'line',source:route.vehicleId,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':color,'line-width':4}});
      map.on('click', `${route.vehicleId}-line`, () => options.onVehicleSelect?.(route.vehicleId));
    }
    for (const node of NODES) {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `zmd-pin type-${node.type}`;
      el.title = node.label;
      el.setAttribute('aria-label',`${node.label} (${node.id})`);
      if (node.type === 'base' || node.type === 'charger') el.innerHTML = icon(node.type === 'base' ? 'base' : 'plug', node.type === 'base' ? 19 : 14);
      else el.textContent = node.id.substring(1);
      el.addEventListener('click', event => {
        event.stopPropagation();
        selectNode(node.id, false);
        options.onSelect?.(node);
      });
      const marker = new maplibre.Marker({element:el}).setLngLat([node.lng,node.lat]).addTo(map);
      markers.push({node,el,marker});
    }
    update();
    fit();
    // GeoJSON sources are processed after load; wait for the first full render.
    map.once('idle', () => { host.dataset.mapReady = 'true'; });
  });
  map.on('dragstart', () => {cameraMode = 'manual';});
  map.on('zoomstart', event => {if (event.originalEvent) cameraMode = 'manual';});
  observer = new ResizeObserver(() => {
    map.resize();
    if (ready && cameraMode === 'fit') fit(false);
  });
  observer.observe(host);
  return {
    selectVehicle(id) { vehicleId = id; selectedId = null; update(); fit(); },
    selectNode,
    fit,
    toggleChargers(value) {chargersVisible = !!value; update();},
    setPlanVisible(value) {planVisible = !!value; update();},
    destroy() {clearTimeout(timer);observer.disconnect();map.remove();}
  };
}
