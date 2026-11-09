// src/context/AuthContext.tsx
// Holds the session (token + profile), keeps it in secure storage, and decides
// which screen a user may be on: signed-out users stay in the (auth) group,
// unverified users are sent to Verify email, and a fresh sign-in passes through
// the one-time location primer before the main app.
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { useRootNavigationState, useRouter, useSegments } from 'expo-router';
import apiClient, { parseApiError, setAuthToken, setUnauthorizedHandler } from '../services/api';
import type { UserProfile } from '../services/profileService';

const TOKEN_KEY = 'my-jwt';
const LOCATION_PRIMER_KEY = 'location-primer-seen';

// Secure storage on devices, localStorage on web.
const platformStorage = {
  async getItem(key: string): Promise<string | null> {
    try {
      if (Platform.OS === 'web') {
        return (globalThis as any).localStorage?.getItem(key) ?? null;
      }
      return await SecureStore.getItemAsync(key);
    } catch {
      return null;
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    try {
      if (Platform.OS === 'web') {
        (globalThis as any).localStorage?.setItem(key, value);
      } else {
        await SecureStore.setItemAsync(key, value);
      }
    } catch {
      if (__DEV__) console.warn(`Could not save ${key} to storage.`);
    }
  },
  async removeItem(key: string): Promise<void> {
    try {
      if (Platform.OS === 'web') {
        (globalThis as any).localStorage?.removeItem(key);
      } else {
        await SecureStore.deleteItemAsync(key);
      }
    } catch {
      if (__DEV__) console.warn(`Could not remove ${key} from storage.`);
    }
  },
};

/** The profile plus the fields GET /profile/me gained for email verification. */
export type AuthUser = UserProfile & {
  email_verified?: boolean;
  date_of_birth?: string | null;
};

interface AuthContextData {
  token: string | null;
  user: AuthUser | null;
  isLoading: boolean;
  /** Store a new token and load the profile. Throws if the server rejects the token. */
  signIn: (token: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-fetch the profile (e.g. after editing it). */
  refreshUser: () => Promise<void>;
  locationPrimerSeen: boolean;
  markLocationPrimerSeen: () => Promise<void>;
}

const AuthContext = createContext<AuthContextData>({} as AuthContextData);

export function useAuth() {
  return useContext(AuthContext);
}

// Auth-group screens a signed-out user may stay on.
const PUBLIC_AUTH_SCREENS = new Set([
  undefined,
  'index',
  'welcome',
  'landing',
  'login',
  'register',
  'verify-email',
  'forgot-password',
  'reset-password',
]);

async function fetchProfile(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>('/profile/me', { timeout: 20000 });
  return data;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [locationPrimerSeen, setLocationPrimerSeen] = useState(false);
  const segments = useSegments() as string[];
  const router = useRouter();
  const navigationState = useRootNavigationState();
  const tokenRef = useRef<string | null>(null);

  const signOut = useCallback(async () => {
    tokenRef.current = null;
    setAuthToken(null);
    setUser(null);
    setToken(null);
    await platformStorage.removeItem(TOKEN_KEY);
  }, []);

  const signIn = useCallback(async (newToken: string) => {
    setAuthToken(newToken);
    tokenRef.current = newToken;
    let profile: AuthUser | null = null;
    try {
      profile = await fetchProfile();
    } catch (error) {
      if (parseApiError(error).status === 401) {
        // The interceptor has already cleared the session.
        throw new Error('Your session could not be started. Please log in again.');
      }
      // Offline or server trouble: stay signed in; the profile loads later.
    }
    if (tokenRef.current !== newToken) return; // signed out meanwhile
    await platformStorage.setItem(TOKEN_KEY, newToken);
    setUser(profile);
    setToken(newToken);
  }, []);

  const refreshUser = useCallback(async () => {
    const current = tokenRef.current;
    if (!current) return;
    try {
      const profile = await fetchProfile();
      if (tokenRef.current === current) setUser(profile);
    } catch {
      // A 401 signs out through the interceptor; anything else can wait.
    }
  }, []);

  const markLocationPrimerSeen = useCallback(async () => {
    setLocationPrimerSeen(true);
    await platformStorage.setItem(LOCATION_PRIMER_KEY, '1');
  }, []);

  // Any 401 on an authenticated request ends the session.
  useEffect(() => {
    setUnauthorizedHandler(() => signOut());
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  // Restore the session on launch.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [storedToken, primer] = await Promise.all([
        platformStorage.getItem(TOKEN_KEY),
        platformStorage.getItem(LOCATION_PRIMER_KEY),
      ]);
      if (cancelled) return;
      setLocationPrimerSeen(primer === '1');
      if (storedToken) {
        setAuthToken(storedToken);
        tokenRef.current = storedToken;
        try {
          const profile = await fetchProfile();
          if (!cancelled && tokenRef.current === storedToken) {
            setUser(profile);
            setToken(storedToken);
          }
        } catch (error) {
          // 401: the interceptor signed out (old or revoked token).
          // Anything else (offline, server down): keep the session and retry later.
          if (!cancelled && parseApiError(error).status !== 401 && tokenRef.current === storedToken) {
            setToken(storedToken);
          }
        }
      }
      if (!cancelled) setIsLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // If the profile could not load at launch, try again when the app comes back.
  useEffect(() => {
    if (!token || user) return;
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') refreshUser();
    });
    return () => sub.remove();
  }, [token, user, refreshUser]);

  const group = segments[0];
  const screen = segments[1];
  const navigationReady = !!navigationState?.key;

  useEffect(() => {
    if (isLoading || !navigationReady) return;
    const inAuthGroup = group === '(auth)';

    if (!token) {
      if (!inAuthGroup || !PUBLIC_AUTH_SCREENS.has(screen)) {
        router.replace('/(auth)/welcome');
      }
      return;
    }

    // Accounts created before email verification still need to verify.
    if (user?.email_verified === false) {
      if (!(inAuthGroup && screen === 'verify-email')) {
        router.replace({ pathname: '/(auth)/verify-email', params: { email: user.email } });
      }
      return;
    }

    if (inAuthGroup) {
      if (screen === 'location') return;
      // Just signed in: show the location primer once per install, then the app.
      router.replace(locationPrimerSeen ? '/(main)/home' : '/(auth)/location');
      return;
    }

    if (group !== '(main)') {
      router.replace('/(main)/home');
    }
  }, [token, user, isLoading, navigationReady, group, screen, locationPrimerSeen, router]);

  const value = useMemo(
    () => ({ token, user, isLoading, signIn, signOut, refreshUser, locationPrimerSeen, markLocationPrimerSeen }),
    [token, user, isLoading, signIn, signOut, refreshUser, locationPrimerSeen, markLocationPrimerSeen],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
