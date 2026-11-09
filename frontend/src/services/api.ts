// src/services/api.ts
// One axios client for the REST API. AuthContext sets the bearer token here and
// registers a handler that runs when an authenticated request comes back 401,
// so an expired or revoked token signs the user out in one place.
import axios, { AxiosHeaders } from 'axios';
import { API_BASE_URL } from '../constants/config';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

let currentToken: string | null = null;
let unauthorizedHandler: (() => void | Promise<void>) | null = null;
let handlingUnauthorized = false;

/** Attach (or clear) the bearer token sent with every request. */
export function setAuthToken(token: string | null) {
  currentToken = token;
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
}

/** AuthContext registers its sign-out here; pass null to unregister. */
export function setUnauthorizedHandler(handler: (() => void | Promise<void>) | null) {
  unauthorizedHandler = handler;
}

function sentAuthorization(config: unknown): string | null {
  const headers = (config as { headers?: unknown } | undefined)?.headers;
  if (!headers) return null;
  const value = AxiosHeaders.from(headers as AxiosHeaders).get('Authorization');
  return typeof value === 'string' ? value : null;
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = String(error?.config?.url ?? '');
    // Only a 401 on a request made with the *current* token means the session is
    // over. Login failures (no token yet) and late replies to requests sent with
    // an older token are ignored, so this can never loop or sign out a new session.
    if (
      status === 401 &&
      unauthorizedHandler &&
      currentToken &&
      !handlingUnauthorized &&
      !url.includes('/auth/token') &&
      sentAuthorization(error?.config) === `Bearer ${currentToken}`
    ) {
      handlingUnauthorized = true;
      Promise.resolve()
        .then(() => unauthorizedHandler?.())
        .catch(() => {})
        .finally(() => {
          handlingUnauthorized = false;
        });
    }
    return Promise.reject(error);
  },
);

export interface ApiErrorInfo {
  status: number | null;
  /** Machine-readable code from {"detail": {"code": ...}}, when the server sent one. */
  code: string | null;
  /** Human text from the server, when it sent any. */
  message: string | null;
  retryAfterSeconds: number | null;
  /** True when no response arrived (offline, server down, timeout). */
  isNetworkError: boolean;
}

/**
 * Normalise an axios error. Handles the new {"detail": {"code", "message"}} shape,
 * plain string details, and FastAPI validation errors (a list of {msg}).
 */
export function parseApiError(error: unknown): ApiErrorInfo {
  const err = error as {
    response?: { status?: number; data?: any; headers?: Record<string, unknown> };
    request?: unknown;
    message?: string;
  };
  const response = err?.response;
  if (!response) {
    return {
      status: null,
      code: null,
      message: null,
      retryAfterSeconds: null,
      isNetworkError: !!err?.request || err?.message === 'Network Error',
    };
  }

  const detail = response.data?.detail;
  let code: string | null = null;
  let message: string | null = null;
  let retryAfterSeconds: number | null = null;

  if (typeof detail === 'string') {
    message = detail;
  } else if (Array.isArray(detail)) {
    const first = detail.find((d) => d && typeof d.msg === 'string');
    message = first ? first.msg : null;
  } else if (detail && typeof detail === 'object') {
    code = typeof detail.code === 'string' ? detail.code : null;
    message = typeof detail.message === 'string' ? detail.message : null;
    const retry = Number(detail.retry_after_seconds);
    if (Number.isFinite(retry) && retry > 0) retryAfterSeconds = Math.ceil(retry);
  }

  if (retryAfterSeconds === null && response.headers) {
    const header = Number(response.headers['retry-after']);
    if (Number.isFinite(header) && header > 0) retryAfterSeconds = Math.ceil(header);
  }

  return {
    status: typeof response.status === 'number' ? response.status : null,
    code,
    message,
    retryAfterSeconds,
    isNetworkError: false,
  };
}

/** A readable message for any API error, falling back to `fallback`. */
export function getApiErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const info = parseApiError(error);
  if (info.isNetworkError) return "Can't reach the server. Check your connection and try again.";
  return info.message || fallback;
}

export default apiClient;
