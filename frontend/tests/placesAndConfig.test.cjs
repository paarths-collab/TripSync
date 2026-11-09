require('./register-typescript.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');

const configPath = require.resolve('../src/constants/config.ts');
const freshConfig = env => {
  const saved = { ...process.env };
  delete process.env.EXPO_PUBLIC_API_BASE_URL;
  delete process.env.EXPO_PUBLIC_WS_BASE_URL;
  Object.assign(process.env, env);
  delete require.cache[configPath];
  try { return require(configPath); } finally { process.env = saved; delete require.cache[configPath]; }
};

test('socket URLs are derived from the API URL without touching the host', () => {
  const { deriveWsBaseUrl, joinUrl } = freshConfig({});
  assert.equal(deriveWsBaseUrl('http://localhost:8000/api'), 'ws://localhost:8000/api');
  assert.equal(deriveWsBaseUrl('https://api.example.com/api/'), 'wss://api.example.com/api');
  assert.equal(joinUrl(deriveWsBaseUrl('https://api.example.com/api'), '/ws/pool'), 'wss://api.example.com/api/ws/pool');
  assert.equal(joinUrl('ws://10.0.2.2:8000/api/', 'ws/pool'), 'ws://10.0.2.2:8000/api/ws/pool');
});

test('config defaults to localhost and honours EXPO_PUBLIC_* overrides', () => {
  const defaults = freshConfig({});
  assert.equal(defaults.API_BASE_URL, 'http://localhost:8000/api');
  assert.equal(defaults.WS_BASE_URL, 'ws://localhost:8000/api');
  const derived = freshConfig({ EXPO_PUBLIC_API_BASE_URL: 'https://api.example.com/api/' });
  assert.equal(derived.API_BASE_URL, 'https://api.example.com/api');
  assert.equal(derived.WS_BASE_URL, 'wss://api.example.com/api');
  const explicit = freshConfig({ EXPO_PUBLIC_API_BASE_URL: 'https://a.example.com/api', EXPO_PUBLIC_WS_BASE_URL: 'wss://ws.example.com/api/' });
  assert.equal(explicit.WS_BASE_URL, 'wss://ws.example.com/api');
});

test('the pooling socket connects to <WS_BASE_URL>/ws/pool', () => {
  const saved = { ...process.env };
  process.env.EXPO_PUBLIC_API_BASE_URL = 'https://api.example.com/api';
  delete process.env.EXPO_PUBLIC_WS_BASE_URL;
  delete require.cache[configPath];
  const original = Module._load;
  Module._load = function (request, ...rest) {
    if (request === 'react-native') return { Alert: { alert() {} } };
    return original.call(this, request, ...rest);
  };
  try {
    const { POOLING_SOCKET_URL } = require('../src/hooks/usePoolingSocket.ts');
    assert.equal(POOLING_SOCKET_URL, 'wss://api.example.com/api/ws/pool');
  } finally {
    Module._load = original;
    process.env = saved;
    delete require.cache[configPath];
  }
});

// --- Place search through the backend proxy ---
const calls = [];
let respond = async () => ({ data: {} });
const fakeClient = { get: async (url, config) => { calls.push({ url, config }); return respond(url, config); } };
const originalLoad = Module._load;
Module._load = function (request, parent, ...rest) {
  if (request === './api' && parent?.filename?.endsWith('locationService.ts')) return { __esModule: true, default: fakeClient };
  return originalLoad.call(this, request, parent, ...rest);
};
const places = require('../src/services/locationService.ts');
Module._load = originalLoad;
const httpError = (status, data) => Object.assign(new Error('http'), { response: { status, data } });

test('autocomplete calls the proxy with the bearer token, never a maps key, and maps predictions', async () => {
  calls.length = 0;
  assert.deepEqual(await places.searchPlaces('  ab '), []);
  assert.equal(calls.length, 0);
  respond = async () => ({ data: { predictions: [
    { place_id: 'p1', description: 'Juhu Beach, Mumbai', main_text: 'Juhu Beach', secondary_text: 'Mumbai' },
    { description: 'no id' },
    { place_id: 'p2', description: 'Andheri Station' },
  ] } });
  const result = await places.searchPlaces(' Juhu ', { token: 't0k', near: { lat: 19.107345, lng: 72.837123 } });
  assert.equal(calls[0].url, '/map/places/autocomplete');
  assert.deepEqual(calls[0].config.params, { input: 'Juhu', lat: 19.107, lng: 72.837 });
  assert.equal(calls[0].config.headers.Authorization, 'Bearer t0k');
  assert.ok(!JSON.stringify(calls[0].config).toLowerCase().includes('api_key'));
  assert.deepEqual(result, [
    { place_id: 'p1', description: 'Juhu Beach, Mumbai', main_text: 'Juhu Beach', secondary_text: 'Mumbai' },
    { place_id: 'p2', description: 'Andheri Station', main_text: 'Andheri Station', secondary_text: '' },
  ]);
});

test('details and reverse geocode validate the response', async () => {
  respond = async url => url.endsWith('/details')
    ? { data: { place_id: 'p1', name: 'Juhu Beach', address: 'Juhu, Mumbai', lat: 19.09, lng: 72.82 } }
    : { data: { address: 'Vile Parle West, Mumbai, Maharashtra', name: '' } };
  assert.deepEqual(await places.getPlaceDetails('p1'), { place_id: 'p1', name: 'Juhu Beach', address: 'Juhu, Mumbai', lat: 19.09, lng: 72.82 });
  const reverse = await places.reverseGeocode({ lat: 19.1073456, lng: 72.8371234 });
  assert.deepEqual(calls.at(-1).config.params, { lat: 19.10735, lng: 72.83712 });
  assert.equal(places.shortPlaceLabel(reverse), 'Vile Parle West, Mumbai');
  respond = async () => ({ data: { name: 'Nowhere', lat: 'abc', lng: null } });
  await assert.rejects(places.getPlaceDetails('p9'), { code: 'invalid_response' });
});

test('429, 502 and 504 become friendly inline messages', async () => {
  const cases = [
    [httpError(429, { detail: { code: 'too_many_requests', message: 'x', retry_after_seconds: 7.2 } }), 'rate_limited', /wait 8 seconds/],
    [httpError(429, { detail: { code: 'too_many_requests' } }), 'rate_limited', /wait a moment/],
    [httpError(502, { detail: { code: 'maps_unavailable' } }), 'unavailable', /unavailable right now/],
    [httpError(504, { detail: { code: 'maps_timeout' } }), 'timeout', /took too long/],
    [httpError(422, {}), 'bad_input', /different search/],
    [Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' }), 'network', /connection/],
    [Object.assign(new Error('canceled'), { name: 'CanceledError', __CANCEL__: true }), 'cancelled', /cancelled/],
  ];
  for (const [error, code, message] of cases) {
    respond = async () => { throw error; };
    await assert.rejects(places.searchPlaces('Juhu beach'), err => err.code === code && message.test(err.message));
  }
});
