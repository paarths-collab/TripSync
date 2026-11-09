// src/components/pooling/mapBridge.ts
// The message bridge between React Native and the Ola Maps page running in the
// WebView, plus the page itself. Kept free of React Native imports so it can be
// unit tested in Node.
//
// RN -> page: injectJavaScript(commandScript(command))
// page -> RN: window.ReactNativeWebView.postMessage(JSON) parsed by parseMapEvent.
// Anything that doesn't match the expected shape is ignored on both sides.

export interface MapPoint {
  lat: number;
  lng: number;
}

/** Screen space (px) covered by overlays at the top and bottom of the map. */
export interface MapInsets {
  top: number;
  bottom: number;
}

/** [lng, lat] pairs, as returned by POST /map/route. */
export type RouteLine = [number, number][];

export type MapFailureReason = 'missing_key' | 'sdk' | 'init' | 'auth' | 'timeout' | 'webview';

export type MapCommand =
  | { type: 'setPickup'; point: MapPoint | null }
  | { type: 'setUser'; point: MapPoint | null }
  | { type: 'setDestination'; point: MapPoint | null }
  | { type: 'setRoute'; coords: RouteLine | null }
  | { type: 'insets'; top: number; bottom: number }
  | { type: 'pitch'; value: number }
  | { type: 'flyTo'; point: MapPoint; zoom: number; offsetY: number }
  | { type: 'fit'; padding: { top: number; bottom: number; side: number } };

export type MapEvent =
  | { type: 'ready' }
  | { type: 'error'; reason: MapFailureReason }
  | { type: 'center'; lat: number; lng: number; byUser: boolean };

export const MAP_MESSAGE_SOURCE = 'tripsync-map';

// DJ Sanghvi College, Vile Parle: a sensible first frame before GPS arrives.
export const DEFAULT_MAP_CENTER: MapPoint = { lat: 19.1073, lng: 72.8371 };

const SDK_URL = 'https://cdn.jsdelivr.net/npm/olamaps-web-sdk@1.1.4/dist/olamaps-web-sdk.umd.min.js';
const STYLE_URL = 'https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json';
const TILESET_URL = 'https://api.olamaps.io/tiles/vector/v1/3dtiles/tileset.json';

const FAILURE_REASONS: MapFailureReason[] = ['missing_key', 'sdk', 'init', 'auth', 'timeout', 'webview'];

const isCoordinate = (value: unknown, limit: number): value is number =>
  typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= limit;

export const isMapPoint = (value: unknown): value is MapPoint =>
  !!value && isCoordinate((value as MapPoint).lat, 90) && isCoordinate((value as MapPoint).lng, 180);

/** Parses a message posted by the map page. Returns null for anything unexpected. */
export function parseMapEvent(raw: unknown): MapEvent | null {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 4096) return null;
  let data: any;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object' || data.source !== MAP_MESSAGE_SOURCE) return null;
  switch (data.type) {
    case 'ready':
      return { type: 'ready' };
    case 'error':
      return { type: 'error', reason: FAILURE_REASONS.includes(data.reason) ? data.reason : 'init' };
    case 'center':
      if (!isMapPoint(data)) return null;
      return { type: 'center', lat: data.lat, lng: data.lng, byUser: (data as { byUser?: unknown }).byUser === true };
    default:
      return null;
  }
}

const LINE_SEPARATOR = String.fromCharCode(0x2028);
const PARAGRAPH_SEPARATOR = String.fromCharCode(0x2029);

/** JS to inject for a command. JSON is escaped so it can't break out of the script. */
export function commandScript(command: MapCommand): string {
  // Escape "<" and the two line separators JSON allows but older JS engines don't.
  const json = JSON.stringify(command)
    .replace(/</g, '\\u003c')
    .split(LINE_SEPARATOR)
    .join('\\u2028')
    .split(PARAGRAPH_SEPARATOR)
    .join('\\u2029');
  return `window.__tripsync&&window.__tripsync.receive(${json});true;`;
}

/** Keeps only finite [lng, lat] pairs so a bad route can't break the map. */
export function sanitizeRoute(coords: unknown): RouteLine | null {
  if (!Array.isArray(coords)) return null;
  const clean = coords.filter(
    (pair): pair is [number, number] =>
      Array.isArray(pair) && pair.length >= 2 && isCoordinate(pair[0], 180) && isCoordinate(pair[1], 90),
  );
  return clean.length >= 2 ? clean.map(([lng, lat]) => [lng, lat] as [number, number]) : null;
}

export interface MapColors {
  background: string;
  ink: string;
  ink2: string;
  yellow: string;
  white: string;
}

const scriptLiteral = (value: unknown) => JSON.stringify(value).replace(/</g, '\\u003c');

/** The page loaded into the WebView. */
export function buildMapHtml({ apiKey, colors, center = DEFAULT_MAP_CENTER }: {
  apiKey: string;
  colors: MapColors;
  center?: MapPoint;
}): string {
  const destinationSvg =
    `<svg width="34" height="44" viewBox="0 0 34 44" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">` +
    `<path d="M17 42.5C17 42.5 3 27 3 16.8A14 14 0 0 1 31 16.8C31 27 17 42.5 17 42.5Z" fill="${colors.yellow}" stroke="${colors.ink}" stroke-width="2.5" stroke-linejoin="round"/>` +
    `<circle cx="17" cy="16.8" r="5.2" fill="${colors.ink}"/></svg>`;

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="initial-scale=1, maximum-scale=1, width=device-width, user-scalable=no" />
<style>
  html, body, #map { height: 100%; width: 100%; margin: 0; padding: 0; background: ${colors.background}; overflow: hidden; }
  body { -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
  .maplibregl-ctrl-bottom-left, .maplibregl-ctrl-bottom-right { bottom: var(--tp-inset-bottom, 0px) !important; }
  .tp-pickup { width: 16px; height: 16px; border-radius: 50%; background: ${colors.ink}; border: 4px solid ${colors.white}; box-shadow: 0 2px 8px rgba(22, 20, 15, 0.35); }
  .tp-me { width: 12px; height: 12px; border-radius: 50%; background: ${colors.ink2}; border: 2px solid ${colors.white}; box-shadow: 0 0 0 8px rgba(22, 20, 15, 0.14); }
  .tp-dest { width: 34px; height: 44px; filter: drop-shadow(0 3px 4px rgba(22, 20, 15, 0.3)); }
</style>
<script src="${SDK_URL}"></script>
</head>
<body>
<div id="map"></div>
<script>
(function () {
  var SOURCE = ${scriptLiteral(MAP_MESSAGE_SOURCE)};
  var loaded = false, failed = false;
  var sdk = null, map = null;
  var state = { pickup: null, user: null, destination: null, route: null };
  var markers = { pickup: null, user: null, destination: null };

  function post(message) {
    try {
      message.source = SOURCE;
      window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify(message));
    } catch (e) {}
  }
  function fail(reason) {
    if (failed || loaded) return;
    failed = true;
    post({ type: 'error', reason: reason });
  }
  function validPoint(p) {
    return !!p && typeof p.lat === 'number' && typeof p.lng === 'number' && isFinite(p.lat) && isFinite(p.lng);
  }
  function makeElement(kind) {
    var el = document.createElement('div');
    el.className = 'tp-' + kind;
    if (kind === 'dest') el.innerHTML = ${scriptLiteral(destinationSvg)};
    return el;
  }
  function placeMarker(key, point, kind, anchor) {
    var existing = markers[key];
    if (!validPoint(point)) {
      if (existing) existing.remove();
      markers[key] = null;
      return;
    }
    if (!existing) {
      markers[key] = sdk.addMarker({ element: makeElement(kind), anchor: anchor })
        .setLngLat([point.lng, point.lat])
        .addTo(map);
    } else {
      existing.setLngLat([point.lng, point.lat]);
    }
  }
  function emptyRoute() { return { type: 'FeatureCollection', features: [] }; }
  function routeData(coords) {
    return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } };
  }
  function ensureRouteLayers() {
    if (map.getSource('tp-route')) return;
    map.addSource('tp-route', { type: 'geojson', data: emptyRoute() });
    map.addLayer({ id: 'tp-route-casing', type: 'line', source: 'tp-route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ${scriptLiteral(colors.white)}, 'line-width': 8 } });
    map.addLayer({ id: 'tp-route-line', type: 'line', source: 'tp-route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ${scriptLiteral(colors.ink)}, 'line-width': 6 } });
  }
  function setRoute(coords) {
    ensureRouteLayers();
    var valid = Array.isArray(coords) && coords.length >= 2;
    state.route = valid ? coords : null;
    map.getSource('tp-route').setData(valid ? routeData(coords) : emptyRoute());
  }
  function clampPadding(p) {
    var el = map.getContainer();
    var w = el.clientWidth || 360, h = el.clientHeight || 640;
    var top = Math.max(0, p.top || 0), bottom = Math.max(0, p.bottom || 0);
    var room = h - 80;
    if (top + bottom > room && top + bottom > 0) {
      var scale = Math.max(0, room) / (top + bottom);
      top *= scale; bottom *= scale;
    }
    var side = Math.max(0, Math.min(p.side || 0, (w - 80) / 2));
    return { top: top, bottom: bottom, left: side, right: side };
  }
  function fit(padding) {
    var points = [];
    if (validPoint(state.pickup)) points.push([state.pickup.lng, state.pickup.lat]);
    if (validPoint(state.destination)) points.push([state.destination.lng, state.destination.lat]);
    if (state.route) points = points.concat(state.route);
    if (!points.length) return;
    var minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
    for (var i = 0; i < points.length; i++) {
      var lng = points[i][0], lat = points[i][1];
      if (!isFinite(lng) || !isFinite(lat)) continue;
      if (lng < minLng) minLng = lng; if (lng > maxLng) maxLng = lng;
      if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
    }
    if (!isFinite(minLng)) return;
    var pad = clampPadding(padding);
    if (minLng === maxLng && minLat === maxLat) {
      map.easeTo({ center: [minLng, minLat], zoom: 16, offset: [0, (pad.top - pad.bottom) / 2], duration: 700 });
      return;
    }
    map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: pad, maxZoom: 16, duration: 700 });
  }

  var handlers = {
    setPickup: function (c) { state.pickup = validPoint(c.point) ? c.point : null; placeMarker('pickup', state.pickup, 'pickup', 'center'); },
    setUser: function (c) { state.user = validPoint(c.point) ? c.point : null; placeMarker('user', state.user, 'me', 'center'); },
    setDestination: function (c) { state.destination = validPoint(c.point) ? c.point : null; placeMarker('destination', state.destination, 'dest', 'bottom'); },
    setRoute: function (c) { setRoute(c.coords); },
    insets: function (c) { document.documentElement.style.setProperty('--tp-inset-bottom', Math.max(0, +c.bottom || 0) + 'px'); },
    pitch: function (c) { map.easeTo({ pitch: Math.max(0, Math.min(60, +c.value || 0)), duration: 600 }); },
    flyTo: function (c) {
      if (!validPoint(c.point)) return;
      map.flyTo({ center: [c.point.lng, c.point.lat], zoom: +c.zoom || 16, offset: [0, +c.offsetY || 0], duration: 900, essential: true });
    },
    fit: function (c) { fit(c.padding || {}); }
  };

  window.__tripsync = {
    receive: function (command) {
      if (!loaded || !command || typeof command.type !== 'string' || !handlers.hasOwnProperty(command.type)) return;
      try { handlers[command.type](command); } catch (e) {}
    }
  };

  if (typeof window.OlaMaps !== 'function') { fail('sdk'); return; }
  try {
    sdk = new window.OlaMaps({ apiKey: ${scriptLiteral(apiKey)}, mode: '3d', threedTileset: ${scriptLiteral(TILESET_URL)} });
    map = sdk.init({
      container: 'map',
      style: ${scriptLiteral(STYLE_URL)},
      center: [${center.lng}, ${center.lat}],
      zoom: 15,
      pitch: 0
    });
  } catch (e) { fail('init'); return; }

  map.on('error', function (event) {
    var status = event && event.error && event.error.status;
    if (!loaded && (status === 401 || status === 403)) fail('auth');
  });
  map.on('load', function () {
    if (failed) return;
    loaded = true;
    post({ type: 'ready' });
  });
  map.on('moveend', function (event) {
    if (!loaded) return;
    var c = map.getCenter();
    post({ type: 'center', lat: c.lat, lng: c.lng, byUser: !!(event && event.originalEvent) });
  });
})();
</script>
</body>
</html>`;
}
