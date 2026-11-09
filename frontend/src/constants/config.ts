// src/constants/config.ts
// Server addresses come from EXPO_PUBLIC_* variables, which Expo inlines at
// build time. The defaults point at a backend running on this computer; on a
// phone or the Android emulator set EXPO_PUBLIC_API_BASE_URL to an address the
// device can reach (for example your computer's LAN IP, or 10.0.2.2 on the
// Android emulator).

const DEFAULT_API_BASE_URL = 'http://localhost:8000/api';

const stripTrailingSlash = (url: string) => url.trim().replace(/\/+$/, '');

/** Turns http(s)://host/api into ws(s)://host/api, keeping host, port and path. */
export function deriveWsBaseUrl(apiBaseUrl: string): string {
  const base = stripTrailingSlash(apiBaseUrl);
  if (/^https:\/\//i.test(base)) return base.replace(/^https:\/\//i, 'wss://');
  if (/^http:\/\//i.test(base)) return base.replace(/^http:\/\//i, 'ws://');
  return base; // already ws(s):// (or something we shouldn't rewrite)
}

/** Joins a base URL and a path without doubling or dropping slashes. */
export function joinUrl(base: string, path: string): string {
  return `${stripTrailingSlash(base)}/${path.replace(/^\/+/, '')}`;
}

export const API_BASE_URL = stripTrailingSlash(process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);

// Socket base, e.g. ws://localhost:8000/api. Paths such as /ws/pool are appended to it.
export const WS_BASE_URL = stripTrailingSlash(
  process.env.EXPO_PUBLIC_WS_BASE_URL || deriveWsBaseUrl(API_BASE_URL),
);

// Only used to load map tiles inside the map view. Place search goes through
// the backend proxy, so this key is never sent with search requests.
export const OLA_MAPS_API_KEY = process.env.EXPO_PUBLIC_OLA_MAPS_API_KEY || '';
