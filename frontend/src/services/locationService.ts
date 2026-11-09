// src/services/locationService.ts
// Place search, place details and reverse geocoding go through our backend
// (/api/map/places/*), which holds the maps key, caches and rate-limits. No
// maps key is ever sent from the app for these calls.
//
// Privacy: addresses and coordinates are personal data. Nothing here logs
// them, and errors carry only a short code and a friendly message.
import { isCancel } from 'axios';
import apiClient from './api';

export interface LatLng {
  lat: number;
  lng: number;
}

/** One autocomplete prediction (no coordinates yet). */
export interface PlaceSuggestion {
  place_id: string;
  description: string;
  main_text: string;
  secondary_text: string;
}

/** A resolved place with coordinates. */
export interface PlaceDetails {
  place_id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
}

export interface ReverseGeocodeResult {
  address: string;
  name: string;
}

export type PlacesErrorCode =
  | 'rate_limited'
  | 'unavailable'
  | 'timeout'
  | 'bad_input'
  | 'unauthorized'
  | 'network'
  | 'cancelled'
  | 'invalid_response'
  | 'unknown';

export class PlacesError extends Error {
  code: PlacesErrorCode;
  retryAfterSeconds: number | null;

  constructor(code: PlacesErrorCode, message: string, retryAfterSeconds: number | null = null) {
    super(message);
    Object.setPrototypeOf(this, PlacesError.prototype); // keeps instanceof working when compiled to ES5
    this.name = 'PlacesError';
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export const MIN_QUERY_LENGTH = 3;

interface RequestOptions {
  token?: string | null;
  signal?: AbortSignal;
}

const REQUEST_TIMEOUT_MS = 12000;

// ~110 m for the search bias (enough for ranking, less precise than needed to
// pinpoint someone); ~1 m for reverse geocoding, where precision is the point.
const round = (value: number, digits: number) => Number(value.toFixed(digits));

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const asText = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

function config(options: RequestOptions, params: Record<string, string | number>) {
  return {
    params,
    signal: options.signal,
    timeout: REQUEST_TIMEOUT_MS,
    headers: options.token ? { Authorization: `Bearer ${options.token}` } : undefined,
  };
}

/** Maps any request failure to a PlacesError with a message that can be shown inline. */
export function toPlacesError(error: unknown): PlacesError {
  if (error instanceof PlacesError) return error;
  if (isCancel(error) || (error as { name?: string })?.name === 'CanceledError') {
    return new PlacesError('cancelled', 'Search cancelled.');
  }
  const response = (error as { response?: { status?: number; data?: any } })?.response;
  const status = response?.status;
  if (!status) {
    const code = (error as { code?: string })?.code;
    if (code === 'ECONNABORTED' || code === 'ETIMEDOUT') {
      return new PlacesError('timeout', 'Place search took too long. Please try again.');
    }
    return new PlacesError('network', "Can't reach the server. Check your connection and try again.");
  }
  if (status === 429) {
    const detail = response?.data?.detail;
    const retry = isFiniteNumber(detail?.retry_after_seconds) ? Math.max(1, Math.ceil(detail.retry_after_seconds)) : null;
    return new PlacesError(
      'rate_limited',
      retry
        ? `Too many searches. Please wait ${retry} second${retry === 1 ? '' : 's'} and try again.`
        : 'Too many searches. Please wait a moment and try again.',
      retry,
    );
  }
  if (status === 502 || status === 503) {
    return new PlacesError('unavailable', 'Place search is unavailable right now. Please try again shortly.');
  }
  if (status === 504) {
    return new PlacesError('timeout', 'Place search took too long. Please try again.');
  }
  if (status === 401 || status === 403) {
    return new PlacesError('unauthorized', 'Your session has expired. Please sign in again.');
  }
  if (status === 400 || status === 422) {
    return new PlacesError('bad_input', 'Try a different search.');
  }
  return new PlacesError('unknown', 'Something went wrong with place search. Please try again.');
}

/** Autocomplete. Returns [] for queries shorter than MIN_QUERY_LENGTH. */
export async function searchPlaces(
  input: string,
  options: RequestOptions & { near?: LatLng | null } = {},
): Promise<PlaceSuggestion[]> {
  const query = input.trim();
  if (query.length < MIN_QUERY_LENGTH) return [];
  const params: Record<string, string | number> = { input: query };
  if (options.near && isFiniteNumber(options.near.lat) && isFiniteNumber(options.near.lng)) {
    params.lat = round(options.near.lat, 3);
    params.lng = round(options.near.lng, 3);
  }
  try {
    const response = await apiClient.get('/map/places/autocomplete', config(options, params));
    const predictions: unknown = response.data?.predictions;
    if (!Array.isArray(predictions)) return [];
    return predictions
      .filter((p) => p && typeof p.place_id === 'string' && p.place_id)
      .map((p) => {
        const description = asText(p.description);
        const main = asText(p.main_text) || description;
        return {
          place_id: p.place_id as string,
          description,
          main_text: main,
          secondary_text: asText(p.secondary_text),
        };
      });
  } catch (error) {
    throw toPlacesError(error);
  }
}

/** Resolves a suggestion to coordinates. */
export async function getPlaceDetails(placeId: string, options: RequestOptions = {}): Promise<PlaceDetails> {
  if (!placeId) throw new PlacesError('bad_input', 'That place could not be found.');
  try {
    const response = await apiClient.get('/map/places/details', config(options, { place_id: placeId }));
    const data = response.data ?? {};
    const lat = Number(data.lat);
    const lng = Number(data.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
      throw new PlacesError('invalid_response', "We couldn't find that place on the map. Try another result.");
    }
    const address = asText(data.address);
    return {
      place_id: asText(data.place_id) || placeId,
      name: asText(data.name) || address || 'Selected place',
      address,
      lat,
      lng,
    };
  } catch (error) {
    throw toPlacesError(error);
  }
}

/** Address for a point (used for the pickup label). */
export async function reverseGeocode(point: LatLng, options: RequestOptions = {}): Promise<ReverseGeocodeResult> {
  try {
    const response = await apiClient.get(
      '/map/places/reverse-geocode',
      config(options, { lat: round(point.lat, 5), lng: round(point.lng, 5) }),
    );
    const address = asText(response.data?.address);
    const name = asText(response.data?.name);
    if (!address && !name) throw new PlacesError('invalid_response', 'No address found for this spot.');
    return { address: address || name, name: name || address };
  } catch (error) {
    throw toPlacesError(error);
  }
}

/** Short label for a reverse-geocoded point: the place name, else the first part of the address. */
export function shortPlaceLabel(result: ReverseGeocodeResult): string {
  if (result.name && result.name !== result.address) return result.name;
  const first = result.address.split(',').slice(0, 2).join(',').trim();
  return first || result.address;
}
