// src/hooks/useLocation.ts
// Foreground location. Pass { watch: true } only while the screen that needs
// live updates is focused: the watch uses Balanced accuracy (Wi-Fi/cell + GPS
// as needed) and stops as soon as `watch` turns false or the screen unmounts.
import { useCallback, useEffect, useState } from 'react';
import * as Location from 'expo-location';

const WATCH_OPTIONS: Location.LocationOptions = {
  accuracy: Location.Accuracy.Balanced,
  timeInterval: 10000,
  distanceInterval: 25,
};

const DENIED_MESSAGE = 'Location permission is off. Turn it on in Settings, or set your pickup on the map.';
const UNAVAILABLE_MESSAGE = "Couldn't get your location. Check that location services are on.";

export function useLocation(options: { watch?: boolean } = {}) {
  const watch = !!options.watch;
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const getUserLocation = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setErrorMsg(DENIED_MESSAGE);
        return null;
      }
      const currentLocation = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setLocation(currentLocation);
      setErrorMsg(null);
      return currentLocation;
    } catch {
      setErrorMsg(UNAVAILABLE_MESSAGE);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!watch) return;
    let cancelled = false;
    let subscription: Location.LocationSubscription | null = null;

    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (cancelled) return;
        if (status !== 'granted') {
          setErrorMsg(DENIED_MESSAGE);
          return;
        }
        // A recent cached fix shows the map quickly while the watch warms up.
        const lastKnown = await Location.getLastKnownPositionAsync({ maxAge: 120000, requiredAccuracy: 200 }).catch(
          () => null,
        );
        if (!cancelled && lastKnown) setLocation((previous) => previous ?? lastKnown);

        const watcher = await Location.watchPositionAsync(WATCH_OPTIONS, (next) => {
          if (cancelled) return;
          setLocation(next);
          setErrorMsg(null);
        });
        if (cancelled) watcher.remove();
        else subscription = watcher;
      } catch {
        if (!cancelled) setErrorMsg(UNAVAILABLE_MESSAGE);
      }
    })();

    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [watch]);

  return { location, errorMsg, getUserLocation };
}
