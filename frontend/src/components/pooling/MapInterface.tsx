// src/components/pooling/MapInterface.tsx
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Card, IconButton } from '../ui';
import { palette, space, font, shadow } from '../../constants/theme';

interface MapInterfaceProps {
  pickupLocationName: string;
  destinationName?: string;
  onWhereToPress: () => void;
  onRecenterPress: () => void;
  onTogglePitch: () => void;
  mapPitch: 0 | 60;
}

export default function MapInterface({
  pickupLocationName,
  destinationName,
  onWhereToPress,
  onRecenterPress,
  onTogglePitch,
  mapPitch,
}: MapInterfaceProps) {
  const insets = useSafeAreaInsets();

  return (
    <>
      {/* Centre pin: the map centre is the pickup point */}
      <View style={styles.pinContainer} pointerEvents="none">
        <Ionicons name="location" size={40} color={palette.primary} style={styles.pinShadow} />
      </View>

      <View
        style={[styles.topArea, { top: insets.top + space.xs }]}
        pointerEvents="box-none"
      >
        <Card
          onPress={onWhereToPress}
          padded={false}
          style={styles.topCard}
        >
          <View style={styles.locationRow}>
            <View style={[styles.dot, styles.pickupDot]} />
            <View style={styles.rowText}>
              <Text style={styles.rowLabel}>Pickup</Text>
              <Text style={styles.locationText} numberOfLines={1}>
                {pickupLocationName}
              </Text>
            </View>
          </View>
          <View style={styles.divider} />
          <View style={styles.locationRow}>
            <View style={[styles.dot, styles.destinationDot]} />
            <View style={styles.rowText}>
              <Text style={styles.rowLabel}>Destination</Text>
              {destinationName ? (
                <Text style={styles.locationText} numberOfLines={1}>
                  {destinationName}
                </Text>
              ) : (
                <Text style={styles.placeholderText}>Where to?</Text>
              )}
            </View>
            <Ionicons name="search" size={18} color={palette.textMuted} />
          </View>
        </Card>

        <View style={styles.mapButtons} pointerEvents="box-none">
          <IconButton
            icon={mapPitch === 60 ? 'map-outline' : 'cube-outline'}
            label={mapPitch === 60 ? 'Switch to flat map' : 'Switch to 3D map'}
            onPress={onTogglePitch}
            size={44}
            style={styles.mapButton}
          />
          <IconButton
            icon="locate"
            label="Recenter on my location"
            onPress={onRecenterPress}
            size={44}
            style={styles.mapButton}
          />
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  pinContainer: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: [{ translateX: -20 }, { translateY: -40 }],
  },
  pinShadow: {
    textShadowColor: 'rgba(22, 20, 43, 0.35)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 4,
  },
  topArea: {
    position: 'absolute',
    left: space.md,
    right: space.md,
  },
  topCard: {
    paddingVertical: space.xxs,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  pickupDot: {
    backgroundColor: palette.success,
  },
  destinationDot: {
    backgroundColor: palette.primary,
  },
  rowText: {
    flex: 1,
    marginLeft: space.sm,
    marginRight: space.xs,
  },
  rowLabel: {
    fontSize: 12,
    color: palette.textMuted,
    marginBottom: 2,
  },
  locationText: {
    fontSize: 15,
    color: palette.text,
    fontWeight: font.medium,
  },
  placeholderText: {
    fontSize: 15,
    color: palette.textFaint,
    fontWeight: font.medium,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.border,
    marginLeft: space.md + 10 + space.sm,
    marginRight: space.md,
  },
  mapButtons: {
    alignItems: 'flex-end',
    marginTop: space.sm,
    gap: space.xs,
  },
  mapButton: {
    ...shadow.card,
  },
});
