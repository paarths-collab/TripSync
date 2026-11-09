// src/app/(main)/home.tsx
// Rides tab: choose a pickup and destination, then find students going the
// same way. This file holds state and logic only; every visual piece lives in
// components/pooling, so the screen can be tested with a minimal
// react-native stub (see tests/poolingScreen.test.cjs).
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import type { LocationObject } from 'expo-location';

// --- Local Hooks & Context ---
import { useLocation } from '../../hooks/useLocation';
import { useAuth } from '../../context/AuthContext';
import { usePoolingSocket } from '../../hooks/usePoolingSocket';
import { usePoolingRecovery } from '../../hooks/usePoolingRecovery';

// --- API Service Functions & Types ---
import {
  getPlaceDetails,
  reverseGeocode,
  shortPlaceLabel,
  toPlacesError,
  type PlaceDetails,
  type PlaceSuggestion,
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
import type { MapPoint, OlaMapHandle } from '../../components/pooling/OlaMapWebView';
import MapInterface from '../../components/pooling/MapInterface';
import LocationSearchModal from '../../components/pooling/LocationSearchModal';
import RouteConfirmationCard from '../../components/pooling/RouteConfirmationCard';
import type { PickupState, RouteState } from '../../components/pooling/RouteConfirmationCard';
import PickupAdjustSheet from '../../components/pooling/PickupAdjustSheet';
import SearchingOverlay from '../../components/pooling/SearchingOverlay';
import MatchFoundModal from '../../components/pooling/MatchFoundModal';
import ActiveRideView from '../../components/pooling/ActiveRideView';
import ActiveConnectionModal from '../../components/pooling/ActiveConnectionModal';

type ScreenState = 'idle' | 'confirming_route' | 'searching' | 'results' | 'connection_modal' | 'active_ride';
type MapPitch = 60 | 0;

/** The pickup is explicit: GPS by default, or a spot the user confirmed on the map. */
interface PickupPoint extends MapPoint {
  label: string | null; // null while the address is being looked up
  source: 'gps' | 'manual';
}

// A GPS pickup follows the user only while no trip is being planned, and only
// after a meaningful move (keeps reverse-geocode calls low).
const PICKUP_REFRESH_METERS = 75;
const DRAFT_GEOCODE_DELAY_MS = 450;

const toPoint = (location: LocationObject | null | undefined): MapPoint | null =>
  location ? { lat: location.coords.latitude, lng: location.coords.longitude } : null;

function distanceMeters(a: MapPoint, b: MapPoint): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export default function PoolingScreen() {
  const { token, user } = useAuth();
  const router = useRouter();

  // GPS is watched (Balanced accuracy) only while this tab is focused.
  const [isFocused, setIsFocused] = useState(false);
  useFocusEffect(
    useCallback(() => {
      setIsFocused(true);
      return () => setIsFocused(false);
    }, []),
  );
  const { location: liveLocation, errorMsg: locationError, getUserLocation } = useLocation({ watch: isFocused });
  const { match, connectionUpdate, connect, disconnect, clearMatch } = usePoolingSocket(token);

  const [isSearchModalVisible, setIsSearchModalVisible] = useState(false);
  const [screenState, setScreenState] = useState<ScreenState>('idle');
  const [selectedDestination, setSelectedDestination] = useState<PlaceDetails | null>(null);
  const [routeDetails, setRouteDetails] = useState<RouteDetails | null>(null);
  const [routeStatus, setRouteStatus] = useState<Exclude<RouteState, 'idle'>>('loading');
  const [matches, setMatches] = useState<MatchedUser[]>([]);
  const [mapPitch, setMapPitch] = useState<MapPitch>(0);
  const [activeConnection, setActiveConnection] = useState<ActiveConnection | null>(null);
  const [currentRequestId, setCurrentRequestId] = useState<number | null>(null);

  // Pickup and the "Adjust pickup" mode
  const [pickup, setPickup] = useState<PickupPoint | null>(null);
  const [isAdjustingPickup, setIsAdjustingPickup] = useState(false);
  const [pickupDraft, setPickupDraft] = useState<MapPoint | null>(null);
  const [draftLabel, setDraftLabel] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);

  // Destination search
  const [resolvingPlaceId, setResolvingPlaceId] = useState<string | null>(null);
  const [placeError, setPlaceError] = useState<string | null>(null);

  // Map
  const mapRef = useRef<OlaMapHandle>(null);
  const lastMapCenter = useRef<MapPoint | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [topInset, setTopInset] = useState(0);
  const [bottomInset, setBottomInset] = useState(0);
  const mapInsets = useMemo(() => ({ top: topInset, bottom: bottomInset }), [topInset, bottomInset]);

  const livePoint = useMemo(() => toPoint(liveLocation), [liveLocation]);

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
      // Update the match to show pending_sent status
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.id === data.to_user?.id
            ? { ...m, connection_status: 'pending_sent' as const, connection_id: data.connection_id }
            : m
        )
      );
    } else if (type === 'request_received') {
      // Refresh matches to show the pending request
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.id === data.from_user?.id
            ? { ...m, connection_status: 'pending_received' as const, connection_id: data.connection_id }
            : m
        )
      );
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
    }
  }, [connectionUpdate, currentRequestId, activeConnection, invalidateRecovery, clearMatch, disconnect]);

  // --- Pickup ---

  // Default pickup = current location. Once a destination is chosen (or the
  // user pinned a spot) the pickup only changes when they confirm a new one.
  useEffect(() => {
    if (!livePoint || isAdjustingPickup) return;
    setPickup(current => {
      if (current?.source === 'manual') return current;
      if (current && (selectedDestination || screenState !== 'idle')) return current;
      if (current && distanceMeters(current, livePoint) < PICKUP_REFRESH_METERS) return current;
      return { lat: livePoint.lat, lng: livePoint.lng, label: null, source: 'gps' };
    });
  }, [livePoint, isAdjustingPickup, selectedDestination, screenState]);

  // Look up a readable label for the pickup.
  useEffect(() => {
    if (!pickup || pickup.label !== null) return;
    let cancelled = false;
    const target = { lat: pickup.lat, lng: pickup.lng };
    const fallback = pickup.source === 'manual' ? 'Pinned location' : 'Current location';
    const sameTarget = (p: PickupPoint | null): p is PickupPoint =>
      !!p && p.lat === target.lat && p.lng === target.lng && p.label === null;
    reverseGeocode(target, { token })
      .then(result => {
        if (!cancelled) setPickup(current => (sameTarget(current) ? { ...current, label: shortPlaceLabel(result) } : current));
      })
      .catch(() => {
        if (!cancelled) setPickup(current => (sameTarget(current) ? { ...current, label: fallback } : current));
      });
    return () => {
      cancelled = true;
    };
  }, [pickup, token]);

  const pickupPoint = useMemo<MapPoint | null>(
    () => (pickup ? { lat: pickup.lat, lng: pickup.lng } : null),
    [pickup?.lat, pickup?.lng], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const planning = screenState === 'idle' || screenState === 'confirming_route';
  const adjusting = planning && isAdjustingPickup;
  const canAdjustPickup = planning && mapReady;

  // Panning the map never moves the pickup, except in "Adjust pickup" mode
  // where the centre pin chooses a draft that must be confirmed.
  const handleMapCenterChange = useCallback(
    (center: MapPoint) => {
      lastMapCenter.current = center;
      if (!isAdjustingPickup) return;
      setPickupDraft(center);
      setDraftLabel(null);
      setDraftError(null);
    },
    [isAdjustingPickup],
  );

  useEffect(() => {
    if (!isAdjustingPickup || !pickupDraft) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      reverseGeocode(pickupDraft, { token })
        .then(result => {
          if (cancelled) return;
          setDraftLabel(shortPlaceLabel(result));
          setDraftError(null);
        })
        .catch(error => {
          if (cancelled) return;
          const placesError = toPlacesError(error);
          setDraftLabel(null);
          setDraftError(
            placesError.code === 'rate_limited' || placesError.code === 'network'
              ? placesError.message
              : "Couldn't find an address here, but you can still use this spot."
          );
        });
    }, DRAFT_GEOCODE_DELAY_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [isAdjustingPickup, pickupDraft, token]);

  const startAdjustPickup = useCallback(() => {
    if (!canAdjustPickup) return;
    const start = pickupPoint ?? livePoint ?? lastMapCenter.current;
    setIsSearchModalVisible(false);
    setIsAdjustingPickup(true);
    setPickupDraft(start);
    setDraftLabel(start && pickupPoint === start ? pickup?.label ?? null : null);
    setDraftError(null);
    if (start) mapRef.current?.flyTo(start, { exact: true, zoom: 17 });
  }, [canAdjustPickup, pickupPoint, livePoint, pickup?.label]);

  const finishAdjustPickup = useCallback(() => {
    setIsAdjustingPickup(false);
    setPickupDraft(null);
    setDraftLabel(null);
    setDraftError(null);
  }, []);

  const confirmPickup = () => {
    if (!pickupDraft) return;
    setPickup({
      lat: pickupDraft.lat,
      lng: pickupDraft.lng,
      label: draftLabel ?? (draftError ? 'Pinned location' : null),
      source: 'manual',
    });
    finishAdjustPickup();
  };

  const cancelAdjustPickup = () => {
    finishAdjustPickup();
    mapRef.current?.fitTrip();
  };

  const pickCurrentLocation = async () => {
    const point = livePoint ?? toPoint(await getUserLocation());
    if (!point) {
      Alert.alert('Location unavailable', locationError || 'Turn on location services, or place the pin on the map.');
      return;
    }
    setPickup({ lat: point.lat, lng: point.lng, label: null, source: 'gps' });
    finishAdjustPickup();
    if (!selectedDestination) mapRef.current?.flyTo(point);
  };

  // --- Map controls ---

  const handleLocate = async () => {
    const point = livePoint ?? toPoint(await getUserLocation());
    if (!point) {
      Alert.alert('Location unavailable', locationError || 'Your current location is not available yet.');
      return;
    }
    mapRef.current?.flyTo(point, { exact: adjusting });
  };

  const toggleMapPitch = () => setMapPitch(pitch => (pitch === 60 ? 0 : 60));

  // --- Route preview (pickup -> destination) ---

  const routeQuery = useMemo(
    () =>
      pickupPoint && selectedDestination
        ? {
            start_lat: pickupPoint.lat,
            start_lng: pickupPoint.lng,
            end_lat: selectedDestination.lat,
            end_lng: selectedDestination.lng,
          }
        : null,
    [pickupPoint, selectedDestination],
  );

  useEffect(() => {
    if (!routeQuery || !token) return;
    let cancelled = false;
    setRouteStatus('loading');
    setRouteDetails(null);
    getRouteDetails(token, routeQuery).then(result => {
      if (cancelled) return; // destination or pickup changed meanwhile
      if (result.success && result.route) {
        setRouteDetails(result.route);
        setRouteStatus('ready');
      } else {
        setRouteDetails(null);
        setRouteStatus('unavailable');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [routeQuery, token]);

  // --- Ride Logic ---

  const handlePlaceSelected = async (place: PlaceSuggestion) => {
    if (!token) {
      setPlaceError('Your session has expired. Please sign in again.');
      return;
    }
    setResolvingPlaceId(place.place_id);
    setPlaceError(null);
    try {
      const details = await getPlaceDetails(place.place_id, { token });
      // Only close the sheet once we have usable coordinates.
      setIsSearchModalVisible(false);
      setSelectedDestination(details);
      setScreenState('confirming_route');
    } catch (error) {
      setPlaceError(toPlacesError(error).message);
    } finally {
      setResolvingPlaceId(null);
    }
  };

  const openSearch = () => {
    setPlaceError(null);
    setIsSearchModalVisible(true);
  };

  const handleConfirmAndFindMatches = async () => {
    if (!pickup || !selectedDestination || !token) {
      Alert.alert('Missing trip details', 'Set your pickup and destination first.');
      return;
    }
    setScreenState('searching');
    connect();

    try {
      await withPoolingMutation(async () => {
        const response = await createRequestAndFindMatches(token, {
          start_latitude: pickup.lat,
          start_longitude: pickup.lng,
          destination_latitude: selectedDestination.lat,
          destination_longitude: selectedDestination.lng,
          destination_name: selectedDestination.name,
        });
        setCurrentRequestId(response.request_id);
        if (response.matches.length > 0) {
          setMatches(response.matches);
          setScreenState('results');
        }
      });
    } catch (error: any) {
      Alert.alert('Search failed', error.message);
      setScreenState('confirming_route');
      disconnect();
    }
  };

  const handleNewSearch = async () => withPoolingMutation(async () => {
    // Disconnect WebSocket when starting new search
    disconnect();

    // Clear the match state first to prevent useEffect from re-triggering
    clearMatch();

    // Cancel the active request on the backend if it exists
    if (token && currentRequestId) {
      try {
        await cancelPoolingRequest(token, currentRequestId);
      } catch {
        console.warn('Could not cancel the pooling request');
      }
    }

    setScreenState('idle');
    setSelectedDestination(null);
    setRouteDetails(null);
    setMatches([]);
    setCurrentRequestId(null);
    setActiveConnection(null);
  });

  // --- Connection Management ---

  const handleSendRequest = async (targetRequestId: number) => {
    if (!token) return;
    try {
      await sendConnectionRequest(token, targetRequestId);
      // Update local state
      setMatches(prevMatches =>
        prevMatches.map(m =>
          m.request_id === targetRequestId
            ? { ...m, connection_status: 'pending_sent' }
            : m
        )
      );
    } catch (error: any) {
      Alert.alert('Could not send request', error.message);
    }
  };

  const handleApprove = async (connectionId: number) => {
    if (!token) return;
    try {
      await withPoolingMutation(() => respondToConnection(token, connectionId, 'approve'));
      // Socket delivery accelerates the REST reconciliation after this action.
    } catch (error: any) {
      Alert.alert('Could not accept', error.message);
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
      Alert.alert('Could not decline', error.message);
    }
  };

  const handleEndRide = async () => withPoolingMutation(async () => {
    if (!token || !currentRequestId) {
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
      await cancelPoolingRequest(token, currentRequestId);
    } catch (error: any) {
      Alert.alert('Could not end the match', error.message);
    } finally {
      // Always reset state regardless of API success/failure
      setActiveConnection(null);
      setScreenState('idle');
      setSelectedDestination(null);
      setRouteDetails(null);
      setMatches([]);
      setCurrentRequestId(null);
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

  const pickupState: PickupState = pickup ? 'ready' : locationError ? 'unavailable' : 'locating';
  const pickupLabel = pickup
    ? pickup.label || (pickup.source === 'manual' ? 'Pinned location' : 'Current location')
    : locationError
      ? 'Location unavailable'
      : 'Finding your location…';
  const routeState: RouteState = selectedDestination && pickup ? routeStatus : 'idle';
  const destinationPoint = selectedDestination ? { lat: selectedDestination.lat, lng: selectedDestination.lng } : null;

  return (
    <View style={styles.container}>
      <OlaMapWebView
        ref={mapRef}
        pickup={pickupPoint}
        showPickup={!adjusting}
        userLocation={adjusting || pickup?.source === 'manual' ? livePoint : null}
        destination={destinationPoint}
        route={selectedDestination && routeDetails ? routeDetails.polyline : null}
        insets={mapInsets}
        pitch={mapPitch}
        onCenterChange={handleMapCenterChange}
        onReadyChange={setMapReady}
      />

      {planning && (
        <MapInterface
          userName={user?.full_name}
          hasDestination={!!selectedDestination}
          adjustingPickup={adjusting}
          mapAvailable={mapReady}
          mapPitch={mapPitch}
          onSearchPress={openSearch}
          onLocatePress={handleLocate}
          onTogglePitch={toggleMapPitch}
          onCancelAdjust={cancelAdjustPickup}
          onAvatarPress={() => router.push('/(main)/profile')}
          onTopInsetChange={setTopInset}
        />
      )}

      {planning && !adjusting && (
        <RouteConfirmationCard
          pickupLabel={pickupLabel}
          pickupSource={pickup?.source ?? null}
          pickupState={pickupState}
          canAdjustPickup={canAdjustPickup}
          onAdjustPickup={startAdjustPickup}
          destinationName={selectedDestination?.name ?? null}
          destinationAddress={selectedDestination?.address ?? null}
          onDestinationPress={openSearch}
          onClearDestination={handleNewSearch}
          routeDetails={routeDetails}
          routeState={routeState}
          onConfirm={handleConfirmAndFindMatches}
          confirmDisabled={!pickup || !selectedDestination || screenState !== 'confirming_route'}
          onHeightChange={setBottomInset}
        />
      )}

      {adjusting && (
        <PickupAdjustSheet
          draftLabel={draftLabel}
          draftError={draftError}
          canConfirm={!!pickupDraft}
          canUseCurrentLocation={!!livePoint}
          onConfirm={confirmPickup}
          onUseCurrentLocation={pickCurrentLocation}
          onHeightChange={setBottomInset}
        />
      )}

      <LocationSearchModal
        visible={isSearchModalVisible}
        onDismiss={() => setIsSearchModalVisible(false)}
        token={token}
        pickupLabel={pickupLabel}
        near={pickupPoint ?? livePoint}
        onAdjustPickup={canAdjustPickup ? startAdjustPickup : undefined}
        onPlaceSelected={handlePlaceSelected}
        resolvingPlaceId={resolvingPlaceId}
        selectionError={placeError}
      />

      <SearchingOverlay
        visible={screenState === 'searching'}
        destinationName={selectedDestination?.name}
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
    // The tab scene already paints the app background; the map fills this view.
    flex: 1,
  },
});
