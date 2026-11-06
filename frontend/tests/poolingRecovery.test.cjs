require('./register-typescript.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createPoolingRecovery } = require('../src/utils/poolingRecovery.ts');
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test('a missed cancellation push converges from REST', async () => {
  let remote = { connection: { id: 1 } };
  const applied = [];
  const recovery = createPoolingRecovery(async () => remote, state => applied.push(state), assert.fail);
  await recovery.refresh();
  remote = { connection: null, ride_ended: true };
  await recovery.refresh();
  assert.equal(applied[1].connection, null);
  assert.equal(applied[1].ride_ended, true);
});

test('socket updates invalidate in-flight reads and newer reads win', async () => {
  const first = deferred(), second = deferred();
  const reads = [first, second], applied = [];
  const recovery = createPoolingRecovery(() => reads.shift().promise, state => applied.push(state), assert.fail);
  const a = recovery.refresh();
  recovery.invalidate();
  const b = recovery.refresh();
  second.resolve('new ride');
  await b;
  first.resolve('old ride');
  await a;
  assert.deepEqual(applied, ['new ride']);
});

test('polling pauses during mutations and recovers once the action finishes', async () => {
  const action = deferred(), applied = [];
  let reads = 0;
  const recovery = createPoolingRecovery(async () => { reads++; return 'ended'; }, state => applied.push(state), assert.fail);
  const pending = recovery.runAction(() => action.promise);
  await recovery.refresh();
  assert.equal(reads, 0);
  action.resolve();
  await pending;
  await Promise.resolve();
  assert.equal(reads, 1);
  assert.deepEqual(applied, ['ended']);
});

test('failed REST reads keep state and disposal suppresses late responses', async () => {
  const read = deferred(), applied = [], errors = [];
  const recovery = createPoolingRecovery(() => read.promise, state => applied.push(state), error => errors.push(error));
  const pending = recovery.refresh();
  recovery.dispose();
  read.resolve(null);
  await pending;
  assert.deepEqual(applied, []);
  const failing = createPoolingRecovery(async () => { throw new Error('offline'); }, state => applied.push(state), error => errors.push(error));
  await failing.refresh();
  assert.deepEqual(applied, []);
  assert.equal(errors[0].message, 'offline');
});
