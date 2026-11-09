// src/services/poolingService.ts

import apiClient from './api';

// Privacy: request/response bodies carry names, contact details and
// coordinates, so nothing here logs them.

/** Server errors are either {detail: "text"} or {detail: {code, message}}. */
export function apiErrorMessage(error: any, fallback: string): string {
  const status = error?.response?.status;
  if (status === 429) return 'Too many requests. Please wait a moment and try again.';
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message;
  if (!error?.response) return "Can't reach the server. Check your connection and try again.";
  return fallback;
}

// --- INTERFACES / TYPES ---

interface PoolingRequestData {
  start_latitude: number;
  start_longitude: number;
  destination_latitude: number;
  destination_longitude: number;
  destination_name: string;
}

export interface PoolingMatchResponse {
  request_id: number;
  matches: MatchedUser[];
}

export interface MatchedUser {
  id: number;
  full_name: string;
  phone_number?: string;
  email?: string;
  year_of_study?: string;
  bio?: string;
  profile_image_url?: string;
  request_id: number;
  connection_status?: 'none' | 'pending_sent' | 'pending_received' | 'approved' | 'rejected';
  connection_id?: number;
}

export interface ActiveConnection {
  id: number;
  status: string;
  created_at: string;
  user_request_id: number;
  partner: MatchedUser;
}

export interface CurrentPoolingState {
  request: { id: number; status: string; destination_name: string | null; created_at: string } | null;
  connection: ActiveConnection | null;
  ride_ended: boolean;
}

export const getCurrentPoolingState = async (token: string): Promise<CurrentPoolingState> => {
  const response = await apiClient.get<CurrentPoolingState>('/pool/requests/current', {
    headers: { Authorization: `Bearer ${token}` },
  });
  // A failed request must not be interpreted as an ended ride.
  return response.data;
};

interface RouteRequestData {
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
}

export interface RouteDetails {
  polyline: [number, number][]; // [lng, lat] pairs
  distance_meters: number;
  duration_seconds: number;
  is_fallback?: boolean;
}

// --- NEW: A result type for our resilient function ---
export interface RouteResult {
  success: boolean;
  route: RouteDetails | null;
  error: string | null;
}


// --- API FUNCTIONS ---

export const createRequestAndFindMatches = async (
  token: string,
  requestData: PoolingRequestData
): Promise<PoolingMatchResponse> => {
  try {
    const response = await apiClient.post('/pool/requests', requestData, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch (error: any) {
    throw new Error(apiErrorMessage(error, 'Could not search for students right now.'));
  }
};

// --- THIS IS THE DEFINITIVE FIX ---
// The function no longer throws an error for API failures.
// It always returns a RouteResult object.
export const getRouteDetails = async (
  token: string,
  routeData: RouteRequestData
): Promise<RouteResult> => {
  try {
    const response = await apiClient.post('/map/route', routeData, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.data?.status === 'success' && response.data?.route) {
      // On success, return a success object with the route data.
      return { success: true, route: response.data.route, error: null };
    } else {
      // If the server gives a weird success response, treat it as a failure.
      return { success: false, route: null, error: 'Invalid route response from server.' };
    }
  } catch (error: any) {
    // On any failure (404, 429, 5xx, network error), return a failure object.
    return { success: false, route: null, error: apiErrorMessage(error, 'Route preview unavailable.') };
  }
};

// --- CONNECTION MANAGEMENT FUNCTIONS ---

export const sendConnectionRequest = async (
  token: string,
  targetRequestId: number
): Promise<any> => {
  try {
    const response = await apiClient.post(
      '/pool/connections/send',
      { target_request_id: targetRequestId },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  } catch (error: any) {
    throw new Error(apiErrorMessage(error, 'Could not send the request.'));
  }
};

export const respondToConnection = async (
  token: string,
  connectionId: number,
  action: 'approve' | 'reject'
): Promise<any> => {
  try {
    const response = await apiClient.post(
      `/pool/connections/${connectionId}/respond`,
      { action },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  } catch (error: any) {
    throw new Error(apiErrorMessage(error, 'Could not respond to the request.'));
  }
};

export const getActiveConnection = async (
  token: string
): Promise<{ connection: ActiveConnection | null }> => {
  try {
    const response = await apiClient.get('/pool/connections/active', {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch {
    console.warn('Could not load the active trip match');
    return { connection: null };
  }
};

export const cancelPoolingRequest = async (
  token: string,
  requestId: number
): Promise<any> => {
  try {
    const response = await apiClient.delete(`/pool/requests/${requestId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch (error: any) {
    throw new Error(apiErrorMessage(error, 'Could not cancel the request.'));
  }
};
