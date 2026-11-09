// src/components/pooling/OlaMapWebView.tsx
// Full-bleed Ola Maps view rendered in a WebView (native maps come later).
// Markers and the route are declarative props; the component replays them
// whenever the page (re)loads. Camera moves are imperative via the ref.
// If the SDK, key or network fails, or the map doesn't load in time, a
// React Native banner with a retry replaces the map. On web, where
// react-native-webview isn't supported, a placeholder card is shown instead.
import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import { Banner, Button, Card, IconBadge } from '../ui';
import { OLA_MAPS_API_KEY } from '../../constants/config';
import { palette, shadow, space, type } from '../../constants/theme';
import {
  buildMapHtml,
  commandScript,
  parseMapEvent,
  sanitizeRoute,
  type MapCommand,
  type MapFailureReason,
  type MapInsets,
  type MapPoint,
  type RouteLine,
} from './mapBridge';

export type { MapPoint, MapInsets, RouteLine } from './mapBridge';

const LOAD_TIMEOUT_MS = 25000; // the SDK bundle is large; allow for slow mobile data
const SIDE_PADDING = 48;
const FIT_MARGIN = 28;

export interface OlaMapHandle {
  /** Centre on a point. `exact` ignores the overlay insets (used when the centre pin sets the pickup). */
  flyTo: (point: MapPoint, options?: { zoom?: number; exact?: boolean }) => void;
  /** Frame pickup, destination and route above the bottom sheet. */
  fitTrip: () => void;
}

interface OlaMapWebViewProps {
  pickup: MapPoint | null;
  /** Hidden while the centre pin is used to choose a pickup. */
  showPickup?: boolean;
  userLocation?: MapPoint | null;
  destination: MapPoint | null;
  route: RouteLine | null;
  insets: MapInsets;
  pitch?: number;
  onCenterChange?: (point: MapPoint, byUser: boolean) => void;
  onReadyChange?: (ready: boolean) => void;
}

type Status = 'loading' | 'ready' | 'failed';

const pointKey = (p: MapPoint | null | undefined) => (p ? `${p.lat.toFixed(6)},${p.lng.toFixed(6)}` : '-');

const OlaMapWebView = forwardRef<OlaMapHandle, OlaMapWebViewProps>(function OlaMapWebView(
  { pickup, showPickup = true, userLocation = null, destination, route, insets, pitch = 0, onCenterChange, onReadyChange },
  ref,
) {
  const isWeb = Platform.OS === 'web';
  const webRef = useRef<WebView>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<Status>(isWeb || !OLA_MAPS_API_KEY ? 'failed' : 'loading');
  const [failure, setFailure] = useState<MapFailureReason | null>(isWeb ? null : OLA_MAPS_API_KEY ? null : 'missing_key');
  const ready = status === 'ready';

  // Latest values for callbacks that shouldn't re-subscribe.
  const latest = useRef({ pickup, destination, insets, onCenterChange, onReadyChange });
  latest.current = { pickup, destination, insets, onCenterChange, onReadyChange };

  const html = useMemo(
    () =>
      buildMapHtml({
        apiKey: OLA_MAPS_API_KEY,
        colors: {
          background: palette.background,
          ink: palette.ink,
          ink2: palette.ink2,
          yellow: palette.yellow,
          white: palette.surface,
        },
      }),
    [],
  );

  const send = useCallback(
    (command: MapCommand) => {
      if (!ready) return;
      webRef.current?.injectJavaScript(commandScript(command));
    },
    [ready],
  );

  const fail = useCallback((reason: MapFailureReason) => {
    setStatus((current) => (current === 'loading' ? 'failed' : current));
    setFailure((current) => current ?? reason);
  }, []);

  useEffect(() => {
    latest.current.onReadyChange?.(ready);
  }, [ready]);

  // Give up if the page never reports that the map loaded.
  useEffect(() => {
    if (status !== 'loading') return;
    const timer = setTimeout(() => fail('timeout'), LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [status, reloadKey, fail]);

  const retry = useCallback(() => {
    if (isWeb || !OLA_MAPS_API_KEY) return;
    setFailure(null);
    setStatus('loading');
    setReloadKey((key) => key + 1);
  }, [isWeb]);

  // --- Declarative layers (re-sent whenever the page becomes ready) ---
  const visiblePickup = showPickup ? pickup : null;
  const cleanRoute = useMemo(() => sanitizeRoute(route), [route]);

  useEffect(() => {
    send({ type: 'setPickup', point: visiblePickup });
  }, [send, visiblePickup]);
  useEffect(() => {
    send({ type: 'setUser', point: userLocation });
  }, [send, userLocation]);
  useEffect(() => {
    send({ type: 'setDestination', point: destination });
  }, [send, destination]);
  useEffect(() => {
    send({ type: 'setRoute', coords: cleanRoute });
  }, [send, cleanRoute]);
  useEffect(() => {
    send({ type: 'insets', top: insets.top, bottom: insets.bottom });
  }, [send, insets.top, insets.bottom]);
  useEffect(() => {
    send({ type: 'pitch', value: pitch });
  }, [send, pitch]);

  // --- Camera ---
  const flyTo = useCallback(
    (point: MapPoint, options?: { zoom?: number; exact?: boolean }) => {
      const { top, bottom } = latest.current.insets;
      send({
        type: 'flyTo',
        point,
        zoom: options?.zoom ?? 16,
        offsetY: options?.exact ? 0 : Math.round((top - bottom) / 2),
      });
    },
    [send],
  );

  const fitTrip = useCallback(() => {
    const { insets: current, destination: dest, pickup: start } = latest.current;
    if (!dest) {
      if (start) flyTo(start);
      return;
    }
    send({
      type: 'fit',
      padding: { top: current.top + FIT_MARGIN, bottom: current.bottom + FIT_MARGIN, side: SIDE_PADDING },
    });
  }, [send, flyTo]);

  useImperativeHandle(ref, () => ({ flyTo, fitTrip }), [flyTo, fitTrip]);

  // Re-frame the trip when its geometry or the sheet height changes.
  const tripKey = destination
    ? `${pointKey(destination)}|${pointKey(pickup)}|${cleanRoute?.length ?? 0}|${Math.round(insets.bottom / 24)}`
    : null;
  useEffect(() => {
    if (ready && tripKey) fitTrip();
  }, [ready, tripKey, fitTrip]);

  // First frame: centre on the pickup as soon as both the map and a pickup exist.
  const hasPickup = !!pickup;
  const centredOnce = useRef(false);
  useEffect(() => {
    if (!ready) {
      centredOnce.current = false;
      return;
    }
    if (centredOnce.current || !hasPickup || latest.current.destination) return;
    centredOnce.current = true;
    const start = latest.current.pickup;
    if (start) flyTo(start);
  }, [ready, hasPickup, flyTo]);

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      const message = parseMapEvent(event.nativeEvent.data);
      if (!message) return; // ignore anything malformed or unexpected
      if (message.type === 'ready') {
        setStatus((current) => (current === 'loading' ? 'ready' : current));
      } else if (message.type === 'error') {
        fail(message.reason);
      } else if (message.type === 'center') {
        latest.current.onCenterChange?.({ lat: message.lat, lng: message.lng }, message.byUser);
      }
    },
    [fail],
  );

  if (isWeb) {
    return (
      <View style={styles.fill}>
        <View style={[styles.placeholderWrap, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
          <Card style={styles.placeholderCard}>
            <IconBadge icon="map-outline" tone="primary" size={48} />
            <Text style={[type.title3, styles.placeholderTitle]}>Map preview is in the mobile app</Text>
            <Text style={[type.label, styles.placeholderBody]}>
              You can still choose a destination and find students going your way here.
            </Text>
          </Card>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.fill}>
      {status !== 'failed' ? (
        <WebView
          key={reloadKey}
          ref={webRef}
          style={styles.webview}
          originWhitelist={['*']}
          source={{ html }}
          javaScriptEnabled
          domStorageEnabled
          scrollEnabled={false}
          bounces={false}
          overScrollMode="never"
          setBuiltInZoomControls={false}
          showsHorizontalScrollIndicator={false}
          showsVerticalScrollIndicator={false}
          onMessage={handleMessage}
          onError={() => fail('webview')}
          onContentProcessDidTerminate={retry}
          onRenderProcessGone={retry}
          accessibilityLabel="Map"
        />
      ) : (
        <View style={styles.failedMap} />
      )}

      {status === 'failed' && failure ? (
        <View style={[styles.bannerWrap, { top: insets.top + space.sm }]} pointerEvents="box-none">
          <Banner
            tone="warning"
            icon="map-outline"
            text={failureMessage(failure)}
            style={styles.banner}
            action={
              failure === 'missing_key' ? undefined : (
                <Button label="Retry" size="sm" variant="dark" fullWidth={false} onPress={retry} style={styles.retry} />
              )
            }
          />
        </View>
      ) : null}
    </View>
  );
});

function failureMessage(reason: MapFailureReason): string {
  const stillWorks = 'You can still choose a destination and find students going your way.';
  switch (reason) {
    case 'missing_key':
      return `The map isn't set up in this build. ${stillWorks}`;
    case 'auth':
      return `The map service didn't accept this app's map key. ${stillWorks}`;
    case 'timeout':
      return `The map is taking too long to load. Check your connection. ${stillWorks}`;
    default:
      return `The map couldn't load. Check your connection. ${stillWorks}`;
  }
}

export default OlaMapWebView;

const styles = StyleSheet.create({
  fill: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: palette.background,
  },
  webview: {
    flex: 1,
    backgroundColor: palette.background,
  },
  failedMap: {
    flex: 1,
    backgroundColor: palette.surfaceMuted,
  },
  bannerWrap: {
    position: 'absolute',
    left: space.md,
    right: space.md,
  },
  banner: {
    alignItems: 'center',
    ...shadow.card,
  },
  retry: {
    marginLeft: space.xs,
  },
  placeholderWrap: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    backgroundColor: palette.surfaceMuted,
  },
  placeholderCard: {
    alignItems: 'center',
    paddingVertical: space.xl,
    paddingHorizontal: space.lg,
  },
  placeholderTitle: {
    marginTop: space.md,
    textAlign: 'center',
  },
  placeholderBody: {
    marginTop: space.xxs,
    color: palette.textMuted,
    textAlign: 'center',
  },
});
