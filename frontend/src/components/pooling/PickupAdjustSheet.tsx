// src/components/pooling/PickupAdjustSheet.tsx
// Shown while the user moves the map to choose a pickup with the centre pin.
// Nothing changes until they press "Confirm pickup".
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';

import { Button, Sheet } from '../ui';
import { layout, palette, radius, space, type } from '../../constants/theme';

interface PickupAdjustSheetProps {
  /** Address under the pin; null while it's being looked up. */
  draftLabel: string | null;
  draftError: string | null;
  canConfirm: boolean;
  canUseCurrentLocation: boolean;
  onConfirm: () => void;
  onUseCurrentLocation: () => void;
  onHeightChange?: (height: number) => void;
}

export default function PickupAdjustSheet({
  draftLabel,
  draftError,
  canConfirm,
  canUseCurrentLocation,
  onConfirm,
  onUseCurrentLocation,
  onHeightChange,
}: PickupAdjustSheetProps) {
  return (
    <View style={styles.wrap} onLayout={(e) => onHeightChange?.(e.nativeEvent.layout.height)}>
      <Sheet
        title="Set your pickup"
        subtitle="Place the pin where you'll wait for your trip partner."
        style={styles.sheet}
      >
        <View style={styles.row}>
          <View style={styles.icon}>
            <View style={styles.dot} />
          </View>
          <View style={styles.text}>
            <Text style={[type.caption, styles.muted]}>Pick up</Text>
            <Text
              style={[type.bodyStrong, !draftLabel && styles.muted]}
              numberOfLines={2}
              accessibilityLiveRegion="polite"
            >
              {draftLabel || (draftError ? 'Pinned location' : 'Finding address…')}
            </Text>
            {draftError ? <Text style={[type.caption, styles.muted]}>{draftError}</Text> : null}
          </View>
        </View>

        <Button label="Confirm pickup" variant="dark" onPress={onConfirm} disabled={!canConfirm} style={styles.confirm} />
        {canUseCurrentLocation ? (
          <Button
            label="Use my current location"
            variant="ghost"
            icon="locate"
            size="md"
            onPress={onUseCurrentLocation}
            style={styles.secondary}
          />
        ) : null}
      </Sheet>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    // Runs to the screen edge; content stays clear of the floating tab bar.
    paddingBottom: layout.tabBarSpace,
  },
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: palette.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: palette.ink,
    borderWidth: 3,
    borderColor: palette.surface,
  },
  text: {
    flex: 1,
  },
  muted: {
    color: palette.textMuted,
  },
  confirm: {
    marginTop: space.md,
  },
  secondary: {
    marginTop: space.xs,
  },
});
