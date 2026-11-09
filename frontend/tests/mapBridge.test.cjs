require('./register-typescript.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const {
  parseMapEvent, commandScript, sanitizeRoute, buildMapHtml, MAP_MESSAGE_SOURCE,
} = require('../src/components/pooling/mapBridge.ts');

const colors = { background: '#F7F4EC', ink: '#16140F', ink2: '#2B2822', yellow: '#FFC629', white: '#FFFFFF' };
// Values created inside the vm have a different Array prototype; compare plain copies.
const plain = value => JSON.parse(JSON.stringify(value));
const msg = body => JSON.stringify({ source: MAP_MESSAGE_SOURCE, ...body });

test('page messages are validated and anything malformed is ignored', () => {
  assert.deepEqual(parseMapEvent(msg({ type: 'ready' })), { type: 'ready' });
  assert.deepEqual(parseMapEvent(msg({ type: 'center', lat: 19.1, lng: 72.8, byUser: true })),
    { type: 'center', lat: 19.1, lng: 72.8, byUser: true });
  assert.deepEqual(parseMapEvent(msg({ type: 'error', reason: 'auth' })), { type: 'error', reason: 'auth' });
  assert.deepEqual(parseMapEvent(msg({ type: 'error', reason: 'whatever' })), { type: 'error', reason: 'init' });
  for (const bad of [
    'not json', '', null, 42, '{"type":"ready"}', msg({ type: 'unknown' }),
    msg({ type: 'center', lat: 'x', lng: 1 }), msg({ type: 'center', lat: 95, lng: 1 }),
    JSON.stringify({ source: 'someone-else', type: 'ready' }), 'x'.repeat(5000),
  ]) assert.equal(parseMapEvent(bad), null, String(bad).slice(0, 40));
});

test('injected commands cannot break out of the script', () => {
  const script = commandScript({ type: 'setRoute', coords: null, evil: '</script> ' });
  assert.ok(!script.includes('<'));
  assert.ok(!script.includes(' '));
  assert.match(script, /^window\.__tripsync&&window\.__tripsync\.receive\(.*\);true;$/);
});

test('routes keep only finite [lng, lat] pairs', () => {
  assert.equal(sanitizeRoute(null), null);
  assert.equal(sanitizeRoute([[72.8, 19.1]]), null);
  assert.deepEqual(sanitizeRoute([[72.8, 19.1], ['a', 1], [72.9, 19.2, 5], [NaN, 1]]), [[72.8, 19.1], [72.9, 19.2]]);
});

// Runs the real page script against a fake Ola Maps SDK.
function runPage({ sdkLoaded = true, apiKey = 'test-key' } = {}) {
  const html = buildMapHtml({ apiKey, colors });
  const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));
  const posted = [], markers = [], calls = [];
  const handlers = {};
  const sources = {};
  const map = {
    on: (event, fn) => { handlers[event] = fn; },
    getCenter: () => ({ lat: 19.2, lng: 72.9 }),
    getContainer: () => ({ clientWidth: 400, clientHeight: 800 }),
    getSource: id => sources[id],
    addSource: (id, spec) => { sources[id] = { data: plain(spec.data), setData(d) { this.data = plain(d); } }; },
    addLayer: layer => calls.push(['addLayer', plain(layer)]),
    fitBounds: (bounds, options) => calls.push(['fitBounds', plain(bounds), plain(options)]),
    flyTo: options => calls.push(['flyTo', plain(options)]),
    easeTo: options => calls.push(['easeTo', plain(options)]),
  };
  class OlaMaps {
    constructor(options) { calls.push(['constructor', plain(options)]); }
    init(options) { calls.push(['init', plain(options)]); return map; }
    addMarker(options) {
      const marker = { options, lngLat: null, added: false, removed: false };
      marker.setLngLat = ll => { marker.lngLat = plain(ll); return marker; };
      marker.addTo = target => { marker.added = target === map; return marker; };
      marker.remove = () => { marker.removed = true; };
      markers.push(marker);
      return marker;
    }
  }
  const element = () => ({ className: '', innerHTML: '', setAttribute() {} });
  const window = {
    ReactNativeWebView: { postMessage: data => posted.push(JSON.parse(data)) },
    ...(sdkLoaded ? { OlaMaps } : {}),
  };
  const document = { createElement: element, documentElement: { style: { setProperty: (k, v) => calls.push(['css', k, v]) } } };
  vm.runInNewContext(script, { window, document, isFinite, Math, Array, JSON, Infinity });
  const send = command => vm.runInNewContext(commandScript(command), { window });
  return { posted, markers, calls, handlers, sources, send };
}

test('the page reports ready only after the map loads, and 3D options go to the constructor', () => {
  const page = runPage();
  assert.deepEqual(page.posted, []);
  const ctor = page.calls.find(c => c[0] === 'constructor')[1];
  assert.equal(ctor.mode, '3d');
  assert.match(ctor.threedTileset, /3dtiles\/tileset\.json$/);
  const init = page.calls.find(c => c[0] === 'init')[1];
  assert.equal(init.mode, undefined);
  assert.equal(init.container, 'map');
  page.handlers.load();
  assert.deepEqual(page.posted.map(p => p.type), ['ready']);
  assert.equal(page.posted[0].source, MAP_MESSAGE_SOURCE);
});

test('a missing SDK or a rejected key is reported instead of hanging', () => {
  assert.deepEqual(runPage({ sdkLoaded: false }).posted.map(p => [p.type, p.reason]), [['error', 'sdk']]);
  const page = runPage();
  page.handlers.error({ error: { status: 403 } });
  assert.deepEqual(page.posted.map(p => [p.type, p.reason]), [['error', 'auth']]);
});

test('markers are placed with setLngLat().addTo(map); the route is cased; fit pads for the sheet', () => {
  const page = runPage();
  page.send({ type: 'setPickup', point: { lat: 19.1, lng: 72.8 } }); // before ready: ignored
  assert.equal(page.markers.length, 0);
  page.handlers.load();

  page.send({ type: 'setPickup', point: { lat: 19.1, lng: 72.8 } });
  page.send({ type: 'setDestination', point: { lat: 19.0, lng: 72.85 } });
  assert.equal(page.markers.length, 2);
  assert.ok(page.markers.every(m => m.added));
  assert.deepEqual(page.markers[0].lngLat, [72.8, 19.1]);
  assert.equal(page.markers[0].options.element.className, 'tp-pickup');
  assert.equal(page.markers[1].options.element.className, 'tp-dest');
  assert.equal(page.markers[1].options.anchor, 'bottom');

  page.send({ type: 'setPickup', point: { lat: 19.11, lng: 72.81 } }); // moves, no new marker
  assert.equal(page.markers.length, 2);
  assert.deepEqual(page.markers[0].lngLat, [72.81, 19.11]);

  page.send({ type: 'setRoute', coords: [[72.81, 19.11], [72.83, 19.05], [72.85, 19.0]] });
  const layers = page.calls.filter(c => c[0] === 'addLayer').map(c => c[1]);
  assert.deepEqual(layers.map(l => [l.id, l.paint['line-width'], l.paint['line-color']]),
    [['tp-route-casing', 8, '#FFFFFF'], ['tp-route-line', 6, '#16140F']]);
  assert.equal(layers[0].layout['line-cap'], 'round');
  assert.equal(page.sources['tp-route'].data.geometry.coordinates.length, 3);

  page.send({ type: 'fit', padding: { top: 180, bottom: 420, side: 48 } });
  const [, bounds, options] = page.calls.find(c => c[0] === 'fitBounds');
  assert.deepEqual(bounds, [[72.81, 19.0], [72.85, 19.11]]);
  assert.deepEqual(options.padding, { top: 180, bottom: 420, left: 48, right: 48 });

  page.send({ type: 'setDestination', point: null });
  assert.equal(page.markers[1].removed, true);
  page.send({ type: 'setRoute', coords: null });
  assert.equal(page.sources['tp-route'].data.features.length, 0);
});

test('malformed commands are ignored and the page keeps working', () => {
  const page = runPage();
  page.handlers.load();
  for (const bad of [null, {}, { type: 'nope' }, { type: 'toString' }, { type: 'hasOwnProperty' },
    { type: 'setPickup', point: { lat: 'x', lng: 1 } }, { type: 'fit' }, { type: 'setRoute', coords: 'zzz' }]) {
    assert.doesNotThrow(() => page.send(bad));
  }
  assert.equal(page.markers.length, 0);
  assert.equal(page.calls.some(c => c[0] === 'fitBounds'), false);
  page.send({ type: 'flyTo', point: { lat: 19.1, lng: 72.8 }, zoom: 16, offsetY: -120 });
  assert.deepEqual(page.calls.find(c => c[0] === 'flyTo')[1].offset, [0, -120]);
  page.handlers.moveend({ originalEvent: {} });
  assert.deepEqual(page.posted.at(-1), { type: 'center', lat: 19.2, lng: 72.9, byUser: true, source: MAP_MESSAGE_SOURCE });
});
