// src/components/pooling/AutocompleteInput.tsx
// Search field for places. Debounces typing (300 ms), cancels and ignores
// stale requests, and reports results, loading and a friendly error to the
// parent, which renders the list.
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  LatLng,
  MIN_QUERY_LENGTH,
  PlaceSuggestion,
  searchPlaces,
  toPlacesError,
} from '../../services/locationService';
import { palette, radius, space, type } from '../../constants/theme';

export const SEARCH_DEBOUNCE_MS = 300;

export interface PlaceSearchState {
  query: string;
  suggestions: PlaceSuggestion[];
  loading: boolean;
  error: string | null;
}

interface AutocompleteInputProps {
  token?: string | null;
  /** Optional bias so nearby places rank first. */
  near?: LatLng | null;
  onStateChange: (state: PlaceSearchState) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

export default function AutocompleteInput({
  token,
  near,
  onStateChange,
  placeholder = 'Search for a place',
  autoFocus = true,
}: AutocompleteInputProps) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<Omit<PlaceSearchState, 'query'>>({ suggestions: [], loading: false, error: null });
  const latestRequest = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const nearRef = useRef(near);
  nearRef.current = near;

  useEffect(() => {
    const trimmed = query.trim();
    const requestId = ++latestRequest.current;
    controller.current?.abort();
    controller.current = null;

    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResult({ suggestions: [], loading: false, error: null });
      return;
    }

    setResult((previous) => ({ ...previous, loading: true, error: null }));
    const timer = setTimeout(async () => {
      const abort = new AbortController();
      controller.current = abort;
      try {
        const suggestions = await searchPlaces(trimmed, { token, near: nearRef.current, signal: abort.signal });
        if (requestId !== latestRequest.current) return; // a newer query is in flight
        setResult({ suggestions, loading: false, error: null });
      } catch (error) {
        if (requestId !== latestRequest.current) return;
        const placesError = toPlacesError(error);
        if (placesError.code === 'cancelled') return;
        setResult({ suggestions: [], loading: false, error: placesError.message });
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [query, token]);

  // Cancel anything in flight when the sheet closes.
  useEffect(
    () => () => {
      latestRequest.current++;
      controller.current?.abort();
    },
    [],
  );

  useEffect(() => {
    onStateChange({ query, ...result });
  }, [query, result, onStateChange]);

  return (
    <View style={styles.field}>
      <Ionicons name="search" size={20} color={palette.ink} />
      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder={placeholder}
        placeholderTextColor={palette.textMuted}
        autoFocus={autoFocus}
        autoCorrect={false}
        autoCapitalize="words"
        returnKeyType="search"
        accessibilityLabel={placeholder}
        style={styles.input}
      />
      {result.loading ? (
        <ActivityIndicator size="small" color={palette.ink} accessibilityLabel="Searching" />
      ) : query ? (
        <Pressable onPress={() => setQuery('')} accessibilityRole="button" accessibilityLabel="Clear search" hitSlop={8}>
          <Ionicons name="close-circle" size={20} color={palette.textMuted} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: palette.surfaceMuted,
    paddingHorizontal: space.md,
    gap: space.xs,
  },
  input: {
    flex: 1,
    ...type.body,
    color: palette.text,
    paddingVertical: 0,
  },
});
