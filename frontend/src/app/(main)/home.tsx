// src/app/(main)/home.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { WebView } from 'react-native-webview';
import { useRouter } from 'expo-router';

// --- Local Hooks & Context ---
import { useLocation } from '../../hooks/useLocation';
import { useAuth } from '../../context/AuthContext';
import { usePoolingSocket } from '../../hooks/usePoolingSocket';
import { usePoolingRecovery } from '../../hooks/usePoolingRecovery';

// --- API Service Functions & Types ---
import {
  getAddressFromCoords,
  getPlaceDetails,
  AutocompleteSuggestion,
  PlaceDetails
} from '../../services/locationService';
import {
  getRouteDetails,
  RouteDetails,
  MatchedUser,
  createRequestAndFindMatches,
  sendConnectionRequest,
  respondToConnection,
  cancelPoolingRequest,
  ActiveConnection,
  CurrentPoolingState,
} from '../../services/poolingService';

// --- UI Components ---
import OlaMapWebView from '../../components/pooling/OlaMapWebView';
import MapInterface from '../../components/pooling/MapInterface';
import LocationSearchModal from '../../components/pooling/LocationSearchModal';
import RouteConfirmationCard from '../../components/pooling/RouteConfirmationCard';
import SearchingOverlay from '../../components/pooling/SearchingOverlay';
import MatchFoundModal from '../../components/pooling/MatchFoundModal';
import ActiveRideView from '../../components/pooling/ActiveRideView';
import ActiveConnectionModal from '../../components/pooling/ActiveConnectionModal';

type ScreenState = 'idle' | 'confirming_route' | 'searching' | 'results' | 'connection_modal' | 'active_ride';
type MapPitch = 60 | 0;

export default function PoolingScreen() {
  const { token } = useAuth();
  const router = useRouter();
  const { location: liveLocation, getUserLocation } = useLocation();
  const { match, connectionUpdate, connect, disconnect, clearMatch } = usePoolingSocket(token);

  const [isSearchModalVisible, setIsSearchModalVisible] = useState(false);
  const [screenState, setScreenState] = useState<ScreenState>('idle');
  const [mapCenter, setMapCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [pickupLocationName, setPickupLocationName] = useState('Setting pickup location...');
  const [selectedDestination, setSelectedDestination] = useState<PlaceDetails | null>(null);
  const [routeDetails, setRouteDetails] = useState<RouteDetails | null>(null);
  const [matches, setMatches] = useState<MatchedUser[]>([]);
  const [mapPitch, setMapPitch] = useState<MapPitch>(60);
  const [activeConnection, setActiveConnection] = useState<ActiveConnection | null>(null);
  const [currentRequestId, setCurrentRequestId] = useState<number | null>(null);

  const webViewRef = useRef<WebView>(null);
  const isMapReady = useRef(false);

  const applyRecoveredState = (result: CurrentPoolingState) => {
    if (result.connection) {
      const sameRide = activeConnection?.id === result.connection.id;
      setActiveConnection(result.connection);
      setCurrentRequestId(result.connection.user_request_id);
      if (!sameRide) setScreenState('active_ride');
      connect();
    } else if (activeConnection) {
      // REST is authoritative even if the cancellation push was lost.
      setActiveConnection(null);
      setCurrentRequestId(null);
      setMatches([]);
      setSelectedDestination(null);
      setRouteDetails(null);
      setScreenState('idle');
      clearMatch();
      disconnect();
      webViewRef.current?.injectJavaScript('window.clearRoute(); window.clearDestinationMarker(); true;');
    }
  };
  const { invalidate: invalidateRecovery, runAction: withPoolingMutation } = usePoolingRecovery(token, applyRecoveredState);
  const processedUpdate = useRef<typeof connectionUpdate>(null);

  // --- Handle WebSocket connection updates ---
  useEffect(() => {
    if (!connectionUpdate || processedUpdate.current === connectionUpdate) return;
    processedUpdate.current = connectionUpdate;
    invalidateRecovery();

    const { type, data } = connectionUpdate;

    if (type === 'request_sent') {
      console.log('Request sent successfully:', data);
      // Update the match to show pending_sent status
      setMatches(prevMatches => {
        const updated = prevMatches.map(m => 
          m.id === data.to_user?.id
            ? { ...m, connection_status: 'pending_sent' as const, connection_id: data.connection_id }
            : m
        );
        console.log('Updated matches after request sent:', updated);
        return updated;
      });
    } else if (type === 'request_received') {
      console.log('Connection request received:', data);
      // Refresh matches to show the pending request
      setMatches(prevMatches => {
        const updated = prevMatches.map(m => 
          m.id === data.from_user?.id
            ? { ...m, connection_status: 'pending_received' as const, connection_id: data.connection_id }
            : m
        );
        console.log('Updated matches after request received:', updated);
        return updated;
      });
    } else if (type === 'approved') {
      // Connection approved, convert partner data to ActiveConnection
      if (data.partner) {
        const userRequestId = data.user_request_id ?? currentRequestId;
        if (!userRequestId) {
          console.warn('Approved connection without user_request_id');
          return;
        }
        const activeConn: ActiveConnection = {
          id: data.connection_id,
          status: 'approved',
          created_at: new Date().toISOString(),
          user_request_id: userRequestId,
          partner: {
            id: data.partner.id,
            full_name: data.partner.full_name,
            phone_number: data.partner.phone_number || null,
            email: data.partner.email || null,
            year_of_study: data.partner.year_of_study || null,
            bio: data.partner.bio || null,
            request_id: data.partner.request_id
          }
        };
        setActiveConnection(activeConn);
        setCurrentRequestId(userRequestId);
        setScreenState('connection_modal'); // Show modal first
      }
    } else if (type === 'rejected') {
      // Update match status to rejected
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.connection_id === data.connection_id
            ? { ...m, connection_status: 'rejected' }
            : m
        )
      );
    } else if (type === 'cancelled' || type === 'ride_cancelled') {
      if (activeConnection && data.connection_id && activeConnection.id !== data.connection_id) return;
      // Partner cancelled, go back to idle
      setActiveConnection(null);
      setScreenState('idle');
      setCurrentRequestId(null);
      setMatches([]);
      setSelectedDestination(null);
      setRouteDetails(null);
      clearMatch();
      disconnect();
      webViewRef.current?.injectJavaScript('window.clearRoute(); window.clearDestinationMarker(); true;');
    }
  }, [connectionUpdate, currentRequestId, activeConnection, invalidateRecovery, clearMatch, disconnect]);

  // --- Map and Location Logic ---

  const handleMapReady = useCallback(() => {
    isMapReady.current = true;
    (async () => {
      const userLocation = await getUserLocation();
      if (userLocation) {
        const coords = { lat: userLocation.coords.latitude, lng: userLocation.coords.longitude };
        flyTo(coords);
      } else {
        Alert.alert("Location Error", "Could not get your location. Please enable location services.");
      }
    })();
  }, [getUserLocation]);

  const flyTo = (coords: { lat: number; lng: number }) => {
    if (isMapReady.current && webViewRef.current) {
      webViewRef.current.injectJavaScript(`window.flyTo({ lat: ${coords.lat}, lng: ${coords.lng} }); true;`);
    }
  };

  const handleRecenter = () => {
    if (liveLocation) {
      flyTo({ lat: liveLocation.coords.latitude, lng: liveLocation.coords.longitude });
    } else {
        Alert.alert("Can't Recenter", "Your current location is not available yet.");
    }
  };

  const toggleMapPitch = () => {
    const newPitch = mapPitch === 60 ? 0 : 60;
    setMapPitch(newPitch);
    if (isMapReady.current && webViewRef.current) {
        webViewRef.current.injectJavaScript(`window.setMapPitch(${newPitch}); true;`);
    }
  };

  const handleMapCenterChange = useCallback((coords: { lat: number; lng: number }) => {
    setMapCenter(coords);
  }, []);

  useEffect(() => {
    const debounceTimeout = setTimeout(async () => {
      if (mapCenter && screenState === 'idle') {
        const address = await getAddressFromCoords({ latitude: mapCenter.lat, longitude: mapCenter.lng });
        setPickupLocationName(address);
      }
    }, 500);
    return () => clearTimeout(debounceTimeout);
  }, [mapCenter, screenState]);
  
  // --- Ride Logic ---

  const handlePlaceSelected = async (place: AutocompleteSuggestion) => {
    console.log('Place selected:', place);
    
    try {
      const details = await getPlaceDetails(place.place_id);
      console.log('Place details received:', details);
      
      if (!details) {
          console.error('Place details is null');
          Alert.alert("Error", "Could not get details for the selected location.");
          return;
      }
      
      if (!details.geometry || !details.geometry.location) {
          console.error('Missing geometry in place details:', details);
          Alert.alert("Error", "Invalid location data received.");
          return;
      }
      
      if (!mapCenter) {
          console.error('Map center is not set');
          Alert.alert("Error", "Please wait for the map to load your location.");
          return;
      }
      
      if (!token) {
          console.error('Token is missing');
          Alert.alert("Error", "Authentication error. Please log in again.");
          return;
      }

      // Only close the modal after we've confirmed the details are valid
      setIsSearchModalVisible(false);
      
      setSelectedDestination(details);
      const destinationCoords = details.geometry.location;
      
      // Fetch route details now that the Directions API is fixed
      console.log('Fetching route details...');
      const routeResult = await getRouteDetails(token, {
        start_lat: mapCenter.lat,
        start_lng: mapCenter.lng,
        end_lat: destinationCoords.lat,
        end_lng: destinationCoords.lng,
      });
      
      if (routeResult.success && routeResult.route) {
        console.log('Route details received:', routeResult.route);
        setRouteDetails(routeResult.route);
        // Draw route on map
        webViewRef.current?.injectJavaScript(
          `window.drawRoute(${JSON.stringify(routeResult.route.polyline)}); true;`
        );
      } else {
        console.warn('Route fetch failed:', routeResult.error);
        setRouteDetails(null);
      }
      
      // Add destination marker and move to confirmation screen
      console.log('Adding destination marker and changing screen state...');
      webViewRef.current?.injectJavaScript(`window.addOrUpdateDestinationMarker({lat: ${destinationCoords.lat}, lng: ${destinationCoords.lng}}); true;`);
      setScreenState('confirming_route');
      console.log('Screen state set to confirming_route');
    } catch (error: any) {
      console.error('Error in handlePlaceSelected:', error);
      Alert.alert("Error", error.message || "Failed to process location selection");
    }
  };

  const handleConfirmAndFindMatches = async () => {
    if (!mapCenter || !selectedDestination || !token) {
        Alert.alert('Error', 'Missing trip details. Please start over.');
        return;
    }
    setScreenState('searching');
    connect();

    try {
        const destCoords = selectedDestination.geometry.location;
        await withPoolingMutation(async () => {
          const response = await createRequestAndFindMatches(token, {
              start_latitude: mapCenter.lat,
              start_longitude: mapCenter.lng,
              destination_latitude: destCoords.lat,
              destination_longitude: destCoords.lng,
              destination_name: selectedDestination.name,
          });
          setCurrentRequestId(response.request_id);
          if (response.matches.length > 0) {
              setMatches(response.matches);
              setScreenState('results');
          }
        });
    } catch (error: any) {
        Alert.alert('Search Failed', error.message);
        setScreenState('confirming_route');
        disconnect();
    }
  };
  
  const handleNewSearch = async () => withPoolingMutation(async () => {
    console.log('handleNewSearch called - resetting to idle state');
    
    // Disconnect WebSocket when starting new search
    disconnect();
    
    // Clear the match state first to prevent useEffect from re-triggering
    clearMatch();
    
    // Cancel the active request on the backend if it exists
    if (token && currentRequestId) {
      try {
        await cancelPoolingRequest(token, currentRequestId);
        console.log('Pooling request cancelled on backend');
      } catch (error: any) {
        console.error('Failed to cancel pooling request:', error.message);
      }
    }
    
    setScreenState('idle');
    setSelectedDestination(null);
    setRouteDetails(null);
    setMatches([]);
    setCurrentRequestId(null);
    setActiveConnection(null);
    if (isMapReady.current && webViewRef.current) {
        webViewRef.current.injectJavaScript('window.clearRoute(); true;');
        webViewRef.current.injectJavaScript('window.clearDestinationMarker(); true;');
    }
  });

  // --- Connection Management ---
  
  const handleSendRequest = async (targetRequestId: number) => {
    console.log('handleSendRequest called for request ID:', targetRequestId);
    if (!token) {
      console.error('No token available');
      return;
    }
    try {
      console.log('Sending connection request...');
      await sendConnectionRequest(token, targetRequestId);
      console.log('Connection request sent successfully');
      // Update local state
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.request_id === targetRequestId
            ? { ...m, connection_status: 'pending_sent' }
            : m
        )
      );
    } catch (error: any) {
      console.error('Error sending request:', error);
      Alert.alert('Error', error.message);
    }
  };

  const handleApprove = async (connectionId: number) => {
    if (!token) return;
    try {
      await withPoolingMutation(() => respondToConnection(token, connectionId, 'approve'));
      // Socket delivery accelerates the REST reconciliation after this action.
    } catch (error: any) {
      Alert.alert('Error', error.message);
    }
  };

  const handleReject = async (connectionId: number) => {
    if (!token) return;
    try {
      await respondToConnection(token, connectionId, 'reject');
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.connection_id === connectionId
            ? { ...m, connection_status: 'rejected' }
            : m
        )
      );
    } catch (error: any) {
      Alert.alert('Error', error.message);
    }
  };

  const handleEndRide = async () => withPoolingMutation(async () => {
    console.log('handleEndRide called - token:', !!token, 'currentRequestId:', currentRequestId);
    
    if (!token || !currentRequestId) {
      console.warn('Cannot end ride: missing token or requestId', { hasToken: !!token, requestId: currentRequestId });
      // Reset state anyway to unblock UI
      setActiveConnection(null);
      setScreenState('idle');
      setSelectedDestination(null);
      setRouteDetails(null);
      setMatches([]);
      setCurrentRequestId(null);
      return;
    }
    
    try {
      console.log('Calling cancelPoolingRequest with requestId:', currentRequestId);
      await cancelPoolingRequest(token, currentRequestId);
      console.log('Successfully cancelled pooling request');
    } catch (error: any) {
      console.error('Error ending ride:', error);
      Alert.alert('Error', error.message);
    } finally {
      // Always reset state regardless of API success/failure
      console.log('Resetting state after end ride');
      setActiveConnection(null);
      setScreenState('idle');
      setSelectedDestination(null);
      setRouteDetails(null);
      setMatches([]);
      setCurrentRequestId(null);
      if (isMapReady.current && webViewRef.current) {
        webViewRef.current.injectJavaScript('window.clearRoute(); true;');
        webViewRef.current.injectJavaScript('window.clearDestinationMarker(); true;');
      }
    }
  });

  const handleStartChat = async () => {
    if (!activeConnection) return;
    
    // Close the modal first
    setScreenState('active_ride');
    
    // Navigate directly to chat screen - expo-router will handle tab switching
    router.push({
      pathname: '/(main)/chat',
      params: {
        partnerId: activeConnection.partner.id.toString(),
        partnerName: activeConnection.partner.full_name,
      },
    });
  };

  const handleContinueToActiveRide = () => {
    setScreenState('active_ride');
  };

  // Removed useFocusEffect that was causing stale closure issues
  // The component doesn't need to reset on focus since we're staying on the same tab

  useEffect(() => {
    if (match) {
      setMatches(prevMatches => {
        const isAlreadyMatched = prevMatches.some(prevMatch => prevMatch.id === match.id);
        if (isAlreadyMatched) {
          return prevMatches;
        }
        return [...prevMatches, match];
      });
      setScreenState('results');
      // Keep WebSocket connected for real-time notifications
    }
  }, [match]);

  // --- RENDER ---
  
  // Show ActiveRideView when there's an active connection
  if (screenState === 'active_ride' && activeConnection) {
    return (
      <ActiveRideView
        connection={activeConnection}
        onEndRide={handleEndRide}
        onStartChat={handleStartChat}
      />
    );
  }

  return (
    <View style={styles.container}>
      <OlaMapWebView
        ref={webViewRef}
        onMapReady={handleMapReady}
        onMapCenterChange={handleMapCenterChange}
      />

      {(screenState === 'idle' || screenState === 'confirming_route') && (
        <MapInterface
          pickupLocationName={pickupLocationName}
          destinationName={selectedDestination?.name}
          onWhereToPress={() => setIsSearchModalVisible(true)}
          onRecenterPress={handleRecenter}
          onTogglePitch={toggleMapPitch}
          mapPitch={mapPitch}
        />
      )}
      
      <LocationSearchModal
        visible={isSearchModalVisible}
        onDismiss={() => setIsSearchModalVisible(false)}
        pickupLocationName={pickupLocationName}
        onPlaceSelected={handlePlaceSelected}
      />

      {screenState === 'confirming_route' && selectedDestination && (
        <RouteConfirmationCard
          destinationName={selectedDestination.name}
          routeDetails={routeDetails}
          onConfirm={handleConfirmAndFindMatches}
          onCancel={handleNewSearch}
        />
      )}

      <SearchingOverlay
        visible={screenState === 'searching'}
        onCancel={() => {
          disconnect();
          handleNewSearch();
        }}
      />
      
      <MatchFoundModal
        visible={screenState === 'results'}
        matches={matches}
        onNewSearch={handleNewSearch}
        onSendRequest={handleSendRequest}
        onApprove={handleApprove}
        onReject={handleReject}
      />
      
      {activeConnection && (
        <ActiveConnectionModal
          visible={screenState === 'connection_modal'}
          partner={activeConnection.partner}
          onStartChat={handleStartChat}
          onEndRide={handleEndRide}
          onViewFullProfile={handleContinueToActiveRide}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    // Matches palette.background. Kept literal: the pooling screen test stubs
    // react-native, so importing constants/theme here would break it.
    backgroundColor: '#F6F5FB',
  },
});
