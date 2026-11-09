// The pickup is explicit: GPS by default, changed only by confirming
// "Adjust pickup". Panning the map must never move it.
require('./register-typescript.cjs');
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const React = require('react');
const { create, act } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

let gps, renderer, requests, routeCalls, geocodes;
const native = {
  View: 'View', StyleSheet: { create: value => value }, Alert: { alert() {} },
  AppState: { currentState: 'active', addEventListener: () => ({ remove() {} }) },
};
const location = (lat, lng) => ({ coords: { latitude: lat, longitude: lng } });
const pooling = {
  getCurrentPoolingState: async () => ({ request: null, connection: null, ride_ended: false }),
  getRouteDetails: async (_token, query) => {
    routeCalls.push(query);
    return { success: true, route: { polyline: [[query.start_lng, query.start_lat], [query.end_lng, query.end_lat]], distance_meters: 4200, duration_seconds: 900 }, error: null };
  },
  createRequestAndFindMatches: async (_token, body) => { requests.push(body); return { request_id: 11, matches: [] }; },
  cancelPoolingRequest: async () => ({}),
};
const places = {
  getPlaceDetails: async placeId => ({ place_id: placeId, name: 'Juhu Beach', address: 'Juhu, Mumbai', lat: 19.0988, lng: 72.8267 }),
  reverseGeocode: async point => { geocodes.push(point); return { address: `Spot ${point.lat.toFixed(3)}`, name: '' }; },
  shortPlaceLabel: result => result.address,
  toPlacesError: error => error,
};
const originalLoad = Module._load;
Module._load = function (request, parent, ...rest) {
  if (request === 'react-native') return native;
  if (request === 'expo-router') return {
    useRouter: () => ({ push() {} }),
    useFocusEffect: callback => React.useEffect(() => callback(), [callback]),
  };
  if (request.endsWith('/context/AuthContext')) return { useAuth: () => ({ token: 'test-token', user: { id: 1, full_name: 'Asha Rao' } }) };
  if (request.endsWith('/hooks/useLocation')) return { useLocation: () => ({ location: gps, errorMsg: null, getUserLocation: async () => gps }) };
  if (request.endsWith('/services/poolingService')) return pooling;
  if (request.endsWith('/services/locationService')) return places;
  if (request.includes('/components/pooling/')) return { __esModule: true, default: request.split('/').pop() };
  return originalLoad.call(this, request, parent, ...rest);
};
const Screen = require('../src/app/(main)/home.tsx').default;
Module._load = originalLoad;

class FakeSocket {
  readyState = 1;
  close() { this.readyState = 3; }
}
const find = name => renderer.root.findAllByType(name)[0];
const props = name => find(name)?.props;
const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
const mount = async () => { await act(async () => { renderer = create(React.createElement(Screen)); }); await flush(); };
const rerender = async () => { await act(async () => renderer.update(React.createElement(Screen))); await flush(); };

beforeEach(() => {
  gps = location(19.1073, 72.8371);
  requests = []; routeCalls = []; geocodes = [];
  global.WebSocket = FakeSocket;
});
afterEach(async () => {
  if (renderer) await act(async () => renderer.unmount());
  renderer = null;
});

test('pickup defaults to GPS and panning after choosing a destination does not move it', async () => {
  await mount();
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1073, lng: 72.8371 });
  assert.equal(props('RouteConfirmationCard').pickupState, 'ready');
  assert.equal(props('RouteConfirmationCard').pickupLabel, 'Spot 19.107');
  assert.equal(props('MapInterface').userName, 'Asha Rao');

  await act(async () => props('LocationSearchModal').onPlaceSelected({ place_id: 'juhu', description: 'Juhu Beach', main_text: 'Juhu Beach', secondary_text: '' }));
  await flush();
  assert.equal(props('RouteConfirmationCard').destinationName, 'Juhu Beach');
  assert.equal(props('RouteConfirmationCard').routeState, 'ready');
  assert.deepEqual(routeCalls.at(-1), { start_lat: 19.1073, start_lng: 72.8371, end_lat: 19.0988, end_lng: 72.8267 });

  // The user pans and zooms around the map, and GPS drifts.
  await act(async () => props('OlaMapWebView').onCenterChange({ lat: 19.2, lng: 72.95 }, true));
  gps = location(19.115, 72.845);
  await rerender();
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1073, lng: 72.8371 });
  assert.equal(routeCalls.length, 1);

  await act(async () => props('RouteConfirmationCard').onConfirm());
  assert.equal(requests.length, 1);
  assert.equal(requests[0].start_latitude, 19.1073);
  assert.equal(requests[0].start_longitude, 72.8371);
  assert.equal(requests[0].destination_name, 'Juhu Beach');
});

test('"Adjust pickup" uses the centre pin and only applies on confirm', async () => {
  await mount();
  assert.equal(props('RouteConfirmationCard').canAdjustPickup, false); // map not loaded yet
  await act(async () => props('OlaMapWebView').onReadyChange(true));
  assert.equal(props('RouteConfirmationCard').canAdjustPickup, true);

  await act(async () => props('RouteConfirmationCard').onAdjustPickup());
  assert.ok(find('PickupAdjustSheet'));
  assert.equal(find('RouteConfirmationCard'), undefined);
  assert.equal(props('OlaMapWebView').showPickup, false);
  assert.equal(props('MapInterface').adjustingPickup, true);

  await act(async () => props('OlaMapWebView').onCenterChange({ lat: 19.1201, lng: 72.8502 }, true));
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1073, lng: 72.8371 }); // not yet
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 500)); });
  assert.equal(props('PickupAdjustSheet').draftLabel, 'Spot 19.120');

  await act(async () => props('PickupAdjustSheet').onConfirm());
  await flush();
  assert.equal(find('PickupAdjustSheet'), undefined);
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1201, lng: 72.8502 });
  assert.equal(props('OlaMapWebView').showPickup, true);
  assert.equal(props('RouteConfirmationCard').pickupSource, 'manual');
  assert.equal(props('RouteConfirmationCard').pickupLabel, 'Spot 19.120');

  // A confirmed manual pickup is not replaced by later GPS fixes, and the map
  // centre is ignored again outside adjust mode.
  gps = location(19.2, 72.9);
  await rerender();
  await act(async () => props('OlaMapWebView').onCenterChange({ lat: 18.95, lng: 72.8 }, true));
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1201, lng: 72.8502 });
});

test('cancelling adjust mode keeps the previous pickup', async () => {
  await mount();
  await act(async () => props('OlaMapWebView').onReadyChange(true));
  await act(async () => props('RouteConfirmationCard').onAdjustPickup());
  await act(async () => props('OlaMapWebView').onCenterChange({ lat: 19.3, lng: 72.9 }, true));
  await act(async () => props('MapInterface').onCancelAdjust());
  assert.equal(find('PickupAdjustSheet'), undefined);
  assert.deepEqual(props('OlaMapWebView').pickup, { lat: 19.1073, lng: 72.8371 });
  assert.equal(props('RouteConfirmationCard').pickupSource, 'gps');
});
