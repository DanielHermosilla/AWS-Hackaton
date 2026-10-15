import * as maplibre from './vendor/maplibre/maplibre-gl.mjs';
import { NODES, ROUTES, VEHICLES, routesForNode, visitLabel } from './shared/data.js';
import { icon } from './shared/icons.js';
import { prefersReducedMotion, onReducedMotionChange } from './state.js';

// Business IDs are opaque; they must not collide with the basemap's own sources.
const mapRoutes = ROUTES.map((route, index) => ({ route, sourceId: `zmd-route-${index}` }));

const css = document.createElement('link');
css.rel = 'stylesheet';
css.href = new URL('./vendor/maplibre/maplibre-gl.css', import.meta.url);
document.head.append(css);

export async function createMap(container, options = {}) {
  const host = typeof container === 'string' ? document.getElementById(container) : container;
  const status = document.createElement('div');
  status.className = 'map-status';
  status.setAttribute('role', 'status');
  let map, ready = false, vehicleId = null, planVisible = options.showRoutes !== false;
  let chargersVisible = false, selectedId = null, cameraMode = 'fit';
  const markers = [];
  const noop = () => {};
  let observer;
  try {
    map = new maplibre.Map({
      container: host,
      style: new URL('./vendor/maplibre/positron.json', import.meta.url).href,
      center: [NODES[0].lng, NODES[0].lat],
      zoom: 11.3,
      attributionControl: true,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      renderWorldCopies: false
    });
  } catch {
    host.parentElement.classList.add('map-unavailable');
    host.append(status);
    status.textContent = 'Mapa no disponible en este navegador. Puedes explorar las paradas en la lista.';
    return {selectVehicle:noop,selectNode:noop,fit:noop,toggleChargers:noop,setPlanVisible:noop,getView:noop,restoreView:noop,destroy:noop};
  }
  host.append(status);
  status.textContent = 'Cargando cartografía…';
  const stopMotionListener = onReducedMotionChange(reduced => { if (reduced) map.stop(); });
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
    map.fitBounds(bounds, {padding, maxZoom:14, duration:prefersReducedMotion() || !animate ? 0 : 450});
  }
  function update() {
    for (const {node,el} of markers) {
      const owners = routesForNode(node.id);
      const selectedOwner = owners.find(route => route.vehicleId === vehicleId);
      const usedCharger = vehicleId ? !!selectedOwner : owners.length > 0;
      el.hidden = node.type === 'charger' && !chargersVisible && !(planVisible && usedCharger);
      el.classList.toggle('is-muted', !!vehicleId && node.type === 'visit' && !selectedOwner && planVisible);
      el.classList.toggle('is-selected', node.id === selectedId);
      el.setAttribute('aria-pressed', String(node.id === selectedId));
      if (node.type === 'visit') {
        const owner = selectedOwner || owners[0];
        el.style.background = planVisible ? VEHICLES.find(v => v.id === owner?.vehicleId)?.color || '#576b7e' : '#576b7e';
      }
    }
    if (!ready) return;
    for (const { route: r, sourceId } of mapRoutes) {
      const active = !vehicleId || r.vehicleId === vehicleId;
      for (const suffix of ['halo','line']) {
        map.setLayoutProperty(`${sourceId}-${suffix}`, 'visibility', planVisible ? 'visible' : 'none');
        map.setPaintProperty(`${sourceId}-${suffix}`, 'line-opacity', active ? (suffix === 'halo' ? .95 : .9) : .12);
      }
    }
  }
  function selectNode(id, move = true) {
    const node = NODES.find(n => n.id === id);
    if (!node) return;
    selectedId = id;
    update();
    const currentPoint = map.project([node.lng, node.lat]);
    const desired = move ? {x:host.clientWidth / 2,y:host.clientHeight / 2} : currentPoint;
    const target = options.focusPoint?.(desired) || desired;
    if (move || Math.abs(target.x - currentPoint.x) > 1 || Math.abs(target.y - currentPoint.y) > 1) {
      cameraMode = 'focus';
      map.easeTo({
        center:[node.lng,node.lat],
        zoom:move ? Math.max(map.getZoom(),12.5) : map.getZoom(),
        padding:0,
        offset:[target.x - host.clientWidth / 2,target.y - host.clientHeight / 2],
        duration:prefersReducedMotion() ? 0 : 350
      });
    }
  }
  map.on('load', () => {
    ready = true;
    clearTimeout(timer);
    status.textContent = '';
    for (const { route, sourceId } of mapRoutes) {
      map.addSource(sourceId, {type:'geojson', data:{type:'Feature', properties:{}, geometry:route.geometry}});
      const color = VEHICLES.find(v => v.id === route.vehicleId).color;
      map.addLayer({id:`${sourceId}-halo`,type:'line',source:sourceId,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#ffffff','line-width':8}});
      map.addLayer({id:`${sourceId}-line`,type:'line',source:sourceId,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':color,'line-width':4}});
      map.on('click', `${sourceId}-line`, () => options.onVehicleSelect?.(route.vehicleId));
    }
    for (const node of NODES) {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `zmd-pin type-${node.type}`;
      el.title = node.label;
      el.setAttribute('aria-label',`${node.label} (${node.id})`);
      if (node.type === 'visit') el.textContent = visitLabel(node.id);
      else el.innerHTML = node.type === 'base' ? icon('base',19) : icon('plug',14);
      el.addEventListener('click', event => {
        event.stopPropagation();
        selectedId = node.id;
        update();
        options.onSelect?.(node);
      });
      const marker = new maplibre.Marker({element:el}).setLngLat([node.lng,node.lat]).addTo(map);
      markers.push({node,el,marker});
    }
    update();
    fit();
    options.onReady?.();
    // GeoJSON sources are processed after load; wait for the first full render.
    map.once('idle', () => { host.dataset.mapReady = 'true'; });
  });
  map.on('dragstart', () => {cameraMode = 'manual';});
  map.on('zoomstart', event => {if (event.originalEvent) cameraMode = 'manual';});
  observer = new ResizeObserver(() => {
    map.resize();
    if (ready && cameraMode === 'fit') fit(false);
    else if (ready && cameraMode === 'focus' && selectedId) selectNode(selectedId);
  });
  observer.observe(host);
  return {
    selectVehicle(id, refit = true) { vehicleId = id; selectedId = null; update(); if (refit) fit(); },
    selectNode,
    fit,
    toggleChargers(value) {chargersVisible = !!value; update();},
    setPlanVisible(value) {planVisible = !!value; update();},
    getView() {
      const center = map.getCenter();
      return { center:[center.lng,center.lat], zoom:map.getZoom(), padding:map.getPadding(), mode:cameraMode };
    },
    restoreView(view) {
      if (!Array.isArray(view?.center) || view.center.length !== 2 ||
        !view.center.every(Number.isFinite) || Math.abs(view.center[0]) > 180 ||
        Math.abs(view.center[1]) > 85 || !Number.isFinite(view.zoom) || view.zoom < 0 || view.zoom > 22) return false;
      cameraMode = ['fit','focus','manual'].includes(view.mode) ? view.mode : 'manual';
      const padding = view.padding && ['top','right','bottom','left'].every(key =>
        Number.isFinite(view.padding[key]) && view.padding[key] >= 0 && view.padding[key] < Math.min(host.clientWidth,host.clientHeight) / 2
      ) ? view.padding : 0;
      map.jumpTo({center:view.center,zoom:view.zoom,padding});
      return true;
    },
    destroy() {clearTimeout(timer);stopMotionListener();observer.disconnect();map.remove();}
  };
}
