// src/services/poolingService.ts

import apiClient from './api';

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
  polyline: [number, number][];
  distance_meters: number;
  duration_seconds: number;
  is_fallback: boolean;
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
    console.error('Pooling request API error:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to find matches.');
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
    // On any failure (404, 500, network error), return a failure object.
    const errorMessage = error.response?.data?.detail || 'Failed to calculate route.';
    return { success: false, route: null, error: errorMessage };
  }
};

// --- CONNECTION MANAGEMENT FUNCTIONS ---

export const sendConnectionRequest = async (
  token: string,
  targetRequestId: number
): Promise<any> => {
  console.log('poolingService - sendConnectionRequest called with:', { targetRequestId });
  try {
    const response = await apiClient.post(
      '/pool/connections/send',
      { target_request_id: targetRequestId },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    console.log('poolingService - Connection request response:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('poolingService - Send connection error:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to send connection request.');
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
    console.error('Respond to connection error:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to respond to connection.');
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
  } catch (error: any) {
    console.error('Get active connection error:', error.response?.data || error.message);
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
    console.error('Cancel request error:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to cancel request.');
  }
};
