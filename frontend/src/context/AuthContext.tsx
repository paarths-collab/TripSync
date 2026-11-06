import React, { createContext, useState, useContext, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { useRouter, useSegments } from 'expo-router';
import apiClient from '../services/api';
import { UserProfile, getMyProfile } from '../services/profileService';

const TOKEN_KEY = 'my-jwt';

// Platform-specific storage helper
const platformStorage = {
  async getItem(key: string): Promise<string | null> {
    try {
      if (Platform.OS === 'web') {
        if (typeof globalThis !== 'undefined' && typeof (globalThis as any).localStorage !== 'undefined') {
          return (globalThis as any).localStorage.getItem(key);
        }
        return null;
      } else {
        return await SecureStore.getItemAsync(key);
      }
    } catch (error) {
      console.error('Storage getItem error:', error);
      return null;
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    try {
      if (Platform.OS === 'web') {
        if (typeof globalThis !== 'undefined' && typeof (globalThis as any).localStorage !== 'undefined') {
          (globalThis as any).localStorage.setItem(key, value);
        }
      } else {
        await SecureStore.setItemAsync(key, value);
      }
    } catch (error) {
      console.error('Storage setItem error:', error);
    }
  },
  async removeItem(key: string): Promise<void> {
    try {
      if (Platform.OS === 'web') {
        if (typeof globalThis !== 'undefined' && typeof (globalThis as any).localStorage !== 'undefined') {
          (globalThis as any).localStorage.removeItem(key);
        }
      } else {
        await SecureStore.deleteItemAsync(key);
      }
    } catch (error) {
      console.error('Storage removeItem error:', error);
    }
  }
};

interface AuthContextData {
  token: string | null;
  user: UserProfile | null;
  isLoading: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextData>({} as AuthContextData);

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const segments = useSegments();
  const router = useRouter();

  // This needs to be defined before it's used in useEffect
  const signOut = async () => {
    // Clear the state
    setUser(null);
    setToken(null);
    // Clear the token from the API client
    delete apiClient.defaults.headers.common['Authorization'];
    // Remove the token from storage
    await platformStorage.removeItem(TOKEN_KEY);
  };

  useEffect(() => {
    async function loadAuthData() {
      try {
        const storedToken = await platformStorage.getItem(TOKEN_KEY);
        if (storedToken) {
          apiClient.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
          // --- THIS IS THE CRITICAL FIX ---
          // We wrap the profile fetch in a try/catch. If it fails due
          // to an invalid token, we call signOut() to clear the bad data.
          try {
            const profile = await getMyProfile();
            setUser(profile);
            setToken(storedToken); // Set token only after a successful profile fetch
          } catch (profileError: any) {
            // Check if the error is specifically a credentials error
            if (profileError.message && profileError.message.includes("Could not validate credentials")) {
              console.warn("Stale or invalid token detected. Automatically signing out.");
              await signOut();
            } else {
              console.error("An error occurred while fetching the user profile on initial load:", profileError);
            }
          }
        }
      } catch (e) {
        console.error("Failed to read token from storage:", e);
      } finally {
        setIsLoading(false);
      }
    }
    loadAuthData();
  }, []);

  useEffect(() => {
    if (isLoading) return;
    const inAuthGroup = String(segments[0]) === '(auth)';
    const currentScreen = (segments as string[])[1]; // e.g., 'login', 'register', 'landing'
    
    if (token && inAuthGroup) {
      (router as any).replace('/(main)/home');
    } else if (!token && !inAuthGroup) {
      (router as any).replace('/(auth)/landing');
    } else if (!token && inAuthGroup && currentScreen !== 'landing' && currentScreen !== 'login' && currentScreen !== 'register') {
      // If in auth group but not on a valid auth screen, redirect to landing
      (router as any).replace('/(auth)/landing');
    }
  }, [token, segments, isLoading, router]);
  
  const signIn = async (newToken: string) => {
    setToken(newToken);
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
    await platformStorage.setItem(TOKEN_KEY, newToken);
    const profile = await getMyProfile();
    setUser(profile);
  };

  return (
    <AuthContext.Provider value={{ token, user, isLoading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}