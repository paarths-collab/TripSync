// src/components/pooling/RouteConfirmationCard.tsx
// The route card at the bottom of the Rides tab: Pick up and Destination rows,
// a route summary once a destination is chosen, and the main CTA. It runs to
// the bottom edge with enough padding that its content clears the floating
// tab bar.
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';

import { RouteDetails } from '../../services/poolingService';
import { Button, Divider, Sheet, Tag } from '../ui';
import { layout, palette, radius, space, type } from '../../constants/theme';

export type PickupState = 'locating' | 'ready' | 'unavailable';
export type RouteState = 'idle' | 'loading' | 'ready' | 'unavailable';

interface RouteConfirmationCardProps {
  pickupLabel: string | null;
  pickupSource: 'gps' | 'manual' | null;
  pickupState: PickupState;
  canAdjustPickup: boolean;
  onAdjustPickup: () => void;
  destinationName: string | null;
  destinationAddress?: string | null;
  onDestinationPress: () => void;
  onClearDestination: () => void;
  routeDetails: RouteDetails | null;
  routeState: RouteState;
  onConfirm: () => void;
  confirmDisabled: boolean;
  /** Full height of the card, so the map can frame the route above it. */
  onHeightChange?: (height: number) => void;
}

export default function RouteConfirmationCard({
  pickupLabel,
  pickupSource,
  pickupState,
  canAdjustPickup,
  onAdjustPickup,
  destinationName,
  destinationAddress,
  onDestinationPress,
  onClearDestination,
  routeDetails,
  routeState,
  onConfirm,
  confirmDisabled,
  onHeightChange,
}: RouteConfirmationCardProps) {
  const pickupCaption =
    pickupState === 'ready' ? (pickupSource === 'manual' ? 'Pick up · pinned on map' : 'Pick up · your location') : 'Pick up';
  const pickupValue =
    pickupState === 'locating'
      ? 'Finding your location…'
      : pickupState === 'unavailable'
        ? 'Location unavailable'
        : pickupLabel || 'Current location';

  const distanceKm = routeDetails ? (routeDetails.distance_meters / 1000).toFixed(1) : null;
  const minutes = routeDetails ? Math.max(1, Math.round(routeDetails.duration_seconds / 60)) : null;

  return (
    <View style={styles.wrap} onLayout={(e) => onHeightChange?.(e.nativeEvent.layout.height)}>
      <Sheet style={styles.sheet}>
        <View style={styles.rows}>
          <View style={styles.row}>
            <View style={[styles.rowIcon, styles.pickupIcon]}>
              <View style={styles.pickupDot} />
            </View>
            <View style={styles.rowText}>
              <Text style={[type.caption, styles.rowLabel]}>{pickupCaption}</Text>
              <Text
                style={[type.bodyStrong, pickupState !== 'ready' && styles.mutedValue]}
                numberOfLines={1}
                accessibilityLiveRegion="polite"
              >
                {pickupValue}
              </Text>
            </View>
            {canAdjustPickup ? (
              <Button
                label={pickupState === 'unavailable' ? 'Set on map' : 'Adjust'}
                variant="secondary"
                size="sm"
                fullWidth={false}
                onPress={onAdjustPickup}
                accessibilityLabel={pickupState === 'unavailable' ? 'Set pickup on the map' : 'Adjust pickup on the map'}
              />
            ) : null}
          </View>

          <Divider style={styles.divider} />

          <Pressable
            onPress={onDestinationPress}
            accessibilityRole="button"
            accessibilityLabel={destinationName ? `Destination ${destinationName}. Change destination` : 'Choose a destination'}
            style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
          >
            <View style={[styles.rowIcon, styles.destinationIcon]}>
              <Ionicons name="location" size={18} color={palette.onYellow} />
            </View>
            <View style={styles.rowText}>
              <Text style={[type.caption, styles.rowLabel]}>Destination</Text>
              <Text style={[type.bodyStrong, !destinationName && styles.mutedValue]} numberOfLines={1}>
                {destinationName || 'Where to?'}
              </Text>
              {destinationName && destinationAddress && destinationAddress !== destinationName ? (
                <Text style={[type.caption, styles.rowLabel]} numberOfLines={1}>
                  {destinationAddress}
                </Text>
              ) : null}
            </View>
            {destinationName ? (
              <Pressable
                onPress={onClearDestination}
                accessibilityRole="button"
                accessibilityLabel="Clear destination"
                hitSlop={8}
                style={({ pressed }) => [styles.clear, pressed && styles.rowPressed]}
              >
                <Ionicons name="close" size={18} color={palette.ink} />
              </Pressable>
            ) : (
              <Ionicons name="chevron-forward" size={18} color={palette.textMuted} />
            )}
          </Pressable>
        </View>

        {destinationName ? (
          <View style={styles.tags}>
            {routeState === 'loading' ? <Tag label="Getting route…" icon="hourglass-outline" /> : null}
            {routeState === 'ready' && routeDetails ? (
              <>
                <Tag label={`${distanceKm} km`} icon="navigate-outline" />
                <Tag label={`About ${minutes} min by road`} icon="time-outline" />
              </>
            ) : null}
            {routeState === 'unavailable' ? (
              <Tag label="Route preview unavailable" icon="alert-circle-outline" tone="warning" />
            ) : null}
          </View>
        ) : null}

        <Text style={[type.caption, styles.note]}>
          We match you with students heading the same way. You arrange and pay for the trip yourselves.
        </Text>

        <Button
          label="Find students going your way"
          icon="people"
          onPress={onConfirm}
          disabled={confirmDisabled}
          style={styles.cta}
        />
      </Sheet>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
  },
  sheet: {
    paddingTop: space.xs,
    // Runs to the screen edge; content stays clear of the floating tab bar.
    paddingBottom: layout.tabBarSpace,
  },
  rows: {
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: space.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 64,
    paddingVertical: space.xs,
    gap: space.sm,
  },
  rowPressed: {
    opacity: 0.7,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pickupIcon: {
    backgroundColor: palette.surfaceMuted,
  },
  pickupDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: palette.ink,
    borderWidth: 3,
    borderColor: palette.surface,
  },
  destinationIcon: {
    backgroundColor: palette.yellow,
  },
  rowText: {
    flex: 1,
  },
  rowLabel: {
    color: palette.textMuted,
  },
  mutedValue: {
    color: palette.textMuted,
  },
  divider: {
    marginLeft: 36 + space.sm,
  },
  clear: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: palette.surfaceMuted,
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.xs,
    marginTop: space.sm,
  },
  note: {
    marginTop: space.sm,
    color: palette.textMuted,
  },
  cta: {
    marginTop: space.md,
  },
});
