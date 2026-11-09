// src/components/pooling/LocationSearchModal.tsx
// Destination search sheet: shows the pickup for context, a search field and
// the results. Place lookups go through the backend proxy (see locationService).
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, View } from 'react-native';
import { Modal, Portal, Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import AutocompleteInput, { PlaceSearchState } from './AutocompleteInput';
import { LatLng, MIN_QUERY_LENGTH, PlaceSuggestion } from '../../services/locationService';
import { Banner, Button, IconButton } from '../ui';
import { palette, radius, shadow, space, type } from '../../constants/theme';

interface LocationSearchModalProps {
  visible: boolean;
  onDismiss: () => void;
  token?: string | null;
  pickupLabel: string;
  near?: LatLng | null;
  /** Shown when the user can switch to choosing the pickup on the map. */
  onAdjustPickup?: () => void;
  onPlaceSelected: (place: PlaceSuggestion) => void;
  /** place_id currently being resolved to coordinates. */
  resolvingPlaceId?: string | null;
  /** Friendly error from resolving the chosen place. */
  selectionError?: string | null;
}

const EMPTY_STATE: PlaceSearchState = { query: '', suggestions: [], loading: false, error: null };

export default function LocationSearchModal({
  visible,
  onDismiss,
  token,
  pickupLabel,
  near,
  onAdjustPickup,
  onPlaceSelected,
  resolvingPlaceId,
  selectionError,
}: LocationSearchModalProps) {
  const insets = useSafeAreaInsets();
  const [search, setSearch] = useState<PlaceSearchState>(EMPTY_STATE);
  const handleStateChange = useCallback((state: PlaceSearchState) => setSearch(state), []);
  const busy = !!resolvingPlaceId;

  const tooShort = search.query.trim().length < MIN_QUERY_LENGTH;
  const showNoResults = !tooShort && !search.loading && !search.error && search.suggestions.length === 0;

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        style={styles.modalWrapper}
        contentContainerStyle={[styles.sheet, { paddingBottom: insets.bottom + space.sm }]}
      >
        {visible ? (
          <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={styles.handle} />

            <View style={styles.header}>
              <Text style={type.title2} accessibilityRole="header">
                Where to?
              </Text>
              <IconButton icon="close" label="Close search" onPress={onDismiss} size={40} round />
            </View>

            <View style={styles.pickupRow}>
              <View style={styles.pickupDot} />
              <View style={styles.flex}>
                <Text style={[type.caption, styles.muted]}>Pick up</Text>
                <Text style={type.bodyStrong} numberOfLines={1}>
                  {pickupLabel}
                </Text>
              </View>
              {onAdjustPickup ? (
                <Button label="Change" variant="ghost" size="sm" fullWidth={false} onPress={onAdjustPickup} />
              ) : null}
            </View>

            <View style={styles.inputWrap}>
              <AutocompleteInput
                token={token}
                near={near}
                onStateChange={handleStateChange}
                placeholder="Search for a destination"
              />
            </View>

            {search.error || selectionError ? (
              <Banner tone="warning" icon="alert-circle" text={(selectionError || search.error) as string} style={styles.banner} />
            ) : null}

            <FlatList
              data={search.suggestions}
              keyExtractor={(item) => item.place_id}
              renderItem={({ item }) => {
                const resolving = resolvingPlaceId === item.place_id;
                return (
                  <Pressable
                    onPress={() => onPlaceSelected(item)}
                    disabled={busy}
                    accessibilityRole="button"
                    accessibilityLabel={item.secondary_text ? `${item.main_text}, ${item.secondary_text}` : item.main_text}
                    accessibilityState={{ disabled: busy, busy: resolving }}
                    style={({ pressed }) => [styles.result, pressed && styles.resultPressed, busy && !resolving && styles.dimmed]}
                  >
                    <View style={styles.resultIcon}>
                      <Ionicons name="location-outline" size={20} color={palette.ink} />
                    </View>
                    <View style={styles.flex}>
                      <Text style={type.bodyStrong} numberOfLines={1}>
                        {item.main_text}
                      </Text>
                      {item.secondary_text ? (
                        <Text style={[type.label, styles.muted]} numberOfLines={1}>
                          {item.secondary_text}
                        </Text>
                      ) : null}
                    </View>
                    {resolving ? <ActivityIndicator size="small" color={palette.ink} /> : null}
                  </Pressable>
                );
              }}
              ItemSeparatorComponent={() => <View style={styles.separator} />}
              ListEmptyComponent={
                search.error ? null : (
                  <Text style={[type.body, styles.hint]}>
                    {tooShort
                      ? 'Type at least 3 letters to search for a place.'
                      : showNoResults
                        ? 'No places found. Try a different name or area.'
                        : ''}
                  </Text>
                )
              }
              style={styles.flex}
              contentContainerStyle={styles.listContent}
              keyboardShouldPersistTaps="handled"
            />
          </KeyboardAvoidingView>
        ) : null}
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalWrapper: {
    justifyContent: 'flex-end',
    marginBottom: 0, // sheet runs to the bottom edge; content pads for the safe area
  },
  sheet: {
    height: '88%',
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    paddingTop: space.xs,
    ...shadow.raised,
  },
  flex: {
    flex: 1,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: palette.border,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
  },
  pickupRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginHorizontal: space.lg,
    marginTop: space.md,
    paddingVertical: space.sm,
    paddingLeft: space.md,
    paddingRight: space.xs,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
  },
  pickupDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: palette.ink,
    borderWidth: 3,
    borderColor: palette.surfaceMuted,
  },
  muted: {
    color: palette.textMuted,
  },
  inputWrap: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
  },
  banner: {
    marginHorizontal: space.lg,
    marginTop: space.sm,
  },
  listContent: {
    paddingTop: space.xs,
    paddingBottom: space.lg,
  },
  result: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 64,
    paddingHorizontal: space.lg,
    paddingVertical: space.xs,
  },
  resultPressed: {
    backgroundColor: palette.surfaceMuted,
  },
  dimmed: {
    opacity: 0.5,
  },
  resultIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.sm,
    backgroundColor: palette.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.border,
    marginLeft: space.lg + 40 + space.sm,
    marginRight: space.lg,
  },
  hint: {
    color: palette.textMuted,
    textAlign: 'center',
    paddingHorizontal: space.xl,
    paddingTop: space.xl,
  },
});
