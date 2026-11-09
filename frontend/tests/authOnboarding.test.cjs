require('./register-typescript.cjs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { AxiosError } = require('axios');

const v = require('../src/components/onboarding/validation.ts');
const api = require('../src/services/api.ts');
const apiClient = api.default;

/* ---------- sign-up validation mirrors the server ---------- */

test('college email must use exactly one of the college domains', () => {
  const domains = ['djsce.ac.in'];
  assert.equal(v.emailMatchesDomains(' Student@DJSCE.ac.in ', domains), true);
  assert.equal(v.emailMatchesDomains('student@evil-djsce.ac.in', domains), false);
  assert.equal(v.emailMatchesDomains('student@djsce.ac.in.example.com', domains), false);
  assert.equal(v.emailMatchesDomains('student@mail.djsce.ac.in', domains), false);
  const college = { name: 'DJSCE', email_domains: domains };
  assert.equal(v.validateCollegeEmail('student@djsce.ac.in', college), null);
  assert.match(v.validateCollegeEmail('student@gmail.com', college), /@djsce\.ac\.in/);
  assert.equal(v.formatDomains(['a.ac.in', 'b.ac.in']), '@a.ac.in or @b.ac.in');
});

test('date of birth: 18 on the day, not the day before; real dates only', () => {
  const today = new Date(2026, 10, 9); // 9 Nov 2026, local time
  assert.deepEqual(v.validateDateOfBirth({ day: '9', month: '11', year: '2008' }, today), { iso: '2008-11-09', error: null });
  assert.match(v.validateDateOfBirth({ day: '10', month: '11', year: '2008' }, today).error, /18 or older/);
  assert.match(v.validateDateOfBirth({ day: '31', month: '02', year: '2000' }, today).error, /real date/);
  assert.equal(v.validateDateOfBirth({ day: '29', month: '02', year: '2004' }, today).iso, '2004-02-29');
  assert.match(v.validateDateOfBirth({ day: '01', month: '01', year: '2030' }, today).error, /future/);
  assert.match(v.validateDateOfBirth({ day: '1', month: '1', year: '99' }, today).error, /DD \/ MM \/ YYYY/);
});

test('password rules: at least 8 characters and at most 72 UTF-8 bytes', () => {
  assert.match(v.validatePassword('short'), /at least 8/);
  assert.equal(v.validatePassword('long enough'), null);
  assert.equal(v.utf8ByteLength('₹'), 3);
  assert.match(v.validatePassword('₹'.repeat(25)), /too long/); // 25 chars, 75 bytes
  assert.equal(v.passwordStrength('password').score, 1);
  assert.ok(v.passwordStrength('Correct-Horse-9').score >= 3);
});

test('every API error code in the contract has friendly text', () => {
  for (const code of [
    'email_taken', 'email_domain_mismatch', 'underage', 'weak_password', 'invalid_college',
    'invalid_date_of_birth', 'invalid_code', 'code_expired', 'too_many_requests', 'email_not_verified',
  ]) {
    assert.equal(typeof v.messageForCode(code), 'string', code);
  }
  assert.match(v.messageForCode('too_many_requests', { retryAfterSeconds: 45 }), /45 seconds/);
  assert.equal(v.messageForCode('something_new'), null);
});

/* ---------- API error parsing ---------- */

const fail = (status, data, config = {}) =>
  new AxiosError('fail', 'ERR_BAD_REQUEST', config, {}, { status, data, headers: {}, config, statusText: '' });

test('parseApiError reads coded, string, validation-list and network errors', () => {
  assert.deepEqual(
    api.parseApiError(fail(429, { detail: { code: 'too_many_requests', message: 'Slow down', retry_after_seconds: 42 } })),
    { status: 429, code: 'too_many_requests', message: 'Slow down', retryAfterSeconds: 42, isNetworkError: false },
  );
  assert.equal(api.parseApiError(fail(401, { detail: 'Incorrect email or password' })).message, 'Incorrect email or password');
  assert.equal(api.parseApiError(fail(422, { detail: [{ msg: 'field required' }] })).message, 'field required');
  const offline = api.parseApiError(new AxiosError('Network Error', 'ERR_NETWORK', {}, {}));
  assert.equal(offline.isNetworkError, true);
  assert.equal(offline.status, null);
});

/* ---------- 401 handling ---------- */

function respondWith(status, { delay = 0 } = {}) {
  apiClient.defaults.adapter = (config) =>
    new Promise((_, reject) => setTimeout(() => reject(fail(status, { detail: 'nope' }, config)), delay));
}

async function settle(promise) {
  await promise.catch(() => {});
  await new Promise((r) => setTimeout(r, 0));
}

test('a 401 on an authenticated request signs out once, even for parallel requests', async () => {
  let signOuts = 0;
  api.setUnauthorizedHandler(() => {
    signOuts += 1;
    api.setAuthToken(null);
  });
  api.setAuthToken('token-a');
  respondWith(401);
  await settle(Promise.all([apiClient.get('/profile/me'), apiClient.get('/pooling/state')]));
  assert.equal(signOuts, 1);
  assert.equal(apiClient.defaults.headers.common.Authorization, undefined);
});

test('a failed log-in (401 from /auth/token) does not trigger sign-out', async () => {
  let signOuts = 0;
  api.setUnauthorizedHandler(() => { signOuts += 1; });
  api.setAuthToken('token-a');
  respondWith(401);
  await settle(apiClient.post('/auth/token', 'username=a&password=b'));
  assert.equal(signOuts, 0);
  api.setAuthToken(null);
});

test('a late 401 for an old token does not sign out the new session', async () => {
  let signOuts = 0;
  api.setUnauthorizedHandler(() => { signOuts += 1; });
  api.setAuthToken('old-token');
  respondWith(401, { delay: 10 });
  const pending = apiClient.get('/profile/me');
  api.setAuthToken('new-token'); // user signed in again before the old reply came back
  await settle(pending);
  assert.equal(signOuts, 0);
  api.setAuthToken(null);
});

test('no handler call without a token, and other errors are passed through', async () => {
  let signOuts = 0;
  api.setUnauthorizedHandler(() => { signOuts += 1; });
  respondWith(401);
  await settle(apiClient.get('/auth/colleges'));
  api.setAuthToken('token-a');
  respondWith(403);
  await assert.rejects(apiClient.get('/profile/me'), (e) => e.response.status === 403);
  assert.equal(signOuts, 0);
  api.setAuthToken(null);
  api.setUnauthorizedHandler(null);
});
