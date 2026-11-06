require('./register-typescript.cjs');
const { test, beforeEach, afterEach, mock } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const React = require('react');
const { create, act } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

let focused = true, serverState, fetchState, renderer;
const intervals = new Map(), listeners = new Set(), sockets = [];
let nextTimer = 0;
const native = {
  View: 'View', StyleSheet: { create: value => value }, Alert: { alert() {} },
  AppState: { currentState: 'active', addEventListener: (_, fn) => { listeners.add(fn); return { remove: () => listeners.delete(fn) }; } },
};
const connection = { id: 7, status: 'APPROVED', created_at: '2026-01-01T00:00:00Z', user_request_id: 4,
  partner: { id: 2, full_name: 'Partner Example', request_id: 5 } };
const active = { request: { id: 4, status: 'CONNECTED' }, connection, ride_ended: false };
const ended = { request: { id: 4, status: 'CANCELLED' }, connection: null, ride_ended: true };
const api = {
  getCurrentPoolingState: () => fetchState(),
  getActiveConnection: async () => ({ connection: serverState.connection }),
  cancelPoolingRequest: async () => { serverState = ended; },
};
const originalLoad = Module._load;
Module._load = function(request, parent, ...rest) {
  if (request === 'react-native') return native;
  if (request === 'react-native-webview') return { WebView: 'WebView' };
  if (request === 'expo-router') return {
    useRouter: () => ({ push() {} }),
    useFocusEffect: callback => React.useEffect(() => focused ? callback() : undefined, [callback, focused]),
  };
  if (request.endsWith('/context/AuthContext')) return { useAuth: () => ({ token: 'test-token', user: { id: 1 } }) };
  if (request.endsWith('/hooks/useLocation')) return { useLocation: () => ({ location: null, getUserLocation: async () => null }) };
  if (request.endsWith('/services/poolingService')) return api;
  if (request.endsWith('/services/locationService')) return {};
  if (request.includes('/components/pooling/')) return { __esModule: true, default: request.split('/').pop() };
  return originalLoad.call(this, request, parent, ...rest);
};
const Screen = require('../src/app/(main)/home.tsx').default;
Module._load = originalLoad;

class FakeSocket {
  static OPEN = 1;
  readyState = 1;
  constructor() { sockets.push(this); queueMicrotask(() => this.onopen?.()); }
  close() { this.readyState = 3; this.onclose?.({ code: 1000 }); }
  push(data) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
const mount = async () => { await act(async () => { renderer = create(React.createElement(Screen)); }); };
const poll = async () => { await act(async () => { for (const callback of intervals.values()) callback(); }); };
const isRiding = () => renderer.root.findAllByType('ActiveRideView').length === 1;

beforeEach(() => {
  focused = true; serverState = active; fetchState = async () => serverState;
  sockets.length = 0;
  mock.method(global, 'setInterval', callback => { const id = ++nextTimer; intervals.set(id, callback); return id; });
  mock.method(global, 'clearInterval', id => intervals.delete(id));
  global.WebSocket = FakeSocket;
});
afterEach(async () => {
  if (renderer) await act(async () => renderer.unmount());
  renderer = null;
  assert.equal(intervals.size, 0);
  assert.equal(listeners.size, 0);
  mock.restoreAll();
});

test('mounted screen clears a cancelled ride when the socket push is lost', async () => {
  await mount();
  assert.ok(isRiding());
  assert.equal(sockets[0].readyState, FakeSocket.OPEN);
  serverState = ended; // deliberately do not send a socket event
  await poll();
  assert.equal(isRiding(), false);
  assert.equal(sockets[0].readyState, 3);
});

test('approval keeps the pooling socket open for immediate cancellation', async () => {
  await mount();
  await act(async () => sockets[0].push({ type: 'connection_approved', connection_id: 7,
    user_request_id: 4, partner: connection.partner }));
  assert.equal(sockets[0].readyState, FakeSocket.OPEN);
  serverState = ended;
  await act(async () => sockets[0].push({ type: 'ride_cancelled', connection_id: 7, request_id: 4 }));
  assert.equal(isRiding(), false);
});

test('a late REST response cannot revive a ride after a cancellation event', async () => {
  await mount();
  let resolveRead;
  fetchState = () => new Promise(resolve => { resolveRead = resolve; });
  // Start a poll without resolving its read yet.
  await poll();
  serverState = ended;
  await act(async () => sockets[0].push({ type: 'ride_cancelled', connection_id: 7, request_id: 4 }));
  assert.equal(isRiding(), false);
  await act(async () => resolveRead(active));
  assert.equal(isRiding(), false);
});

test('focus and app resume reconcile; transient errors preserve the active ride', async () => {
  await mount();
  fetchState = async () => { throw new Error('offline'); };
  await poll();
  assert.ok(isRiding());
  focused = false;
  await act(async () => renderer.update(React.createElement(Screen)));
  assert.equal(intervals.size, 0);
  serverState = ended; fetchState = async () => serverState;
  focused = true;
  await act(async () => renderer.update(React.createElement(Screen)));
  assert.equal(isRiding(), false);
  serverState = active;
  await act(async () => { for (const listener of listeners) listener('active'); });
  assert.ok(isRiding());
});
