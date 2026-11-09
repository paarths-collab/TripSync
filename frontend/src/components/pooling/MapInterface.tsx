// src/components/pooling/MapInterface.tsx
// Everything that floats over the map on the Rides tab: the greeting header
// with the "Where to?" search pill, the locate / 3D buttons and, while the
// pickup is being adjusted, a back button, a hint and the centre pin.
import React, { useEffect, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Avatar, IconButton, SearchBar } from '../ui';
import { palette, radius, shadow, space, type } from '../../constants/theme';

interface MapInterfaceProps {
  userName?: string | null;
  hasDestination: boolean;
  adjustingPickup: boolean;
  /** Locate and 3D buttons only make sense when the map loaded. */
  mapAvailable: boolean;
  mapPitch: 0 | 60;
  onSearchPress: () => void;
  onLocatePress: () => void;
  onTogglePitch: () => void;
  onCancelAdjust: () => void;
  onAvatarPress?: () => void;
  /** Height covered by the header, so the map can keep markers out from under it. */
  onTopInsetChange?: (height: number) => void;
}

export default function MapInterface({
  userName,
  hasDestination,
  adjustingPickup,
  mapAvailable,
  mapPitch,
  onSearchPress,
  onLocatePress,
  onTogglePitch,
  onCancelAdjust,
  onAvatarPress,
  onTopInsetChange,
}: MapInterfaceProps) {
  const insets = useSafeAreaInsets();
  const [headerHeight, setHeaderHeight] = useState(0);
  const name = userName?.trim() || '';
  const firstName = name.split(/\s+/)[0];

  // Android back leaves "Adjust pickup" instead of the tab.
  useEffect(() => {
    if (!adjustingPickup) return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      onCancelAdjust();
      return true;
    });
    return () => subscription.remove();
  }, [adjustingPickup, onCancelAdjust]);

  if (adjustingPickup) {
    const top = insets.top + space.xs;
    return (
      <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
        <CenterPin />
        <View
          style={[styles.adjustBar, { top }]}
          pointerEvents="box-none"
          onLayout={(e) => onTopInsetChange?.(top + e.nativeEvent.layout.height)}
        >
          <IconButton icon="chevron-back" label="Stop adjusting pickup" onPress={onCancelAdjust} size={48} round />
          <View style={styles.hint} accessibilityLiveRegion="polite">
            <Text style={[type.label, styles.hintText]} numberOfLines={2}>
              Move the map to place the pin where you&apos;ll wait
            </Text>
          </View>
          <IconButton icon="locate" label="Go to my location" onPress={onLocatePress} size={48} round />
        </View>
      </View>
    );
  }

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <View
        style={[styles.header, { paddingTop: insets.top + space.sm }]}
        onLayout={(e) => {
          const height = e.nativeEvent.layout.height;
          setHeaderHeight(height);
          onTopInsetChange?.(height);
        }}
      >
        <View style={styles.greetingRow}>
          {name ? (
            onAvatarPress ? (
              <Pressable
                onPress={onAvatarPress}
                accessibilityRole="button"
                accessibilityLabel="Open your profile"
                hitSlop={6}
                style={({ pressed }) => pressed && styles.pressed}
              >
                <Avatar name={name} size={48} />
              </Pressable>
            ) : (
              <Avatar name={name} size={48} />
            )
          ) : null}
          <View style={[styles.greetingText, name ? { marginLeft: space.sm } : null]}>
            <Text style={type.title2} numberOfLines={1} accessibilityRole="header">
              {firstName ? `Hi, ${firstName}` : 'Hi there'}
            </Text>
            <Text style={[type.body, styles.subtitle]} numberOfLines={1}>
              Where are you going?
            </Text>
          </View>
        </View>
        <SearchBar
          placeholder={hasDestination ? 'Change destination' : 'Where to?'}
          onPress={onSearchPress}
          style={styles.search}
        />
      </View>

      {mapAvailable ? (
        <View style={[styles.controls, { top: headerHeight + space.sm }]} pointerEvents="box-none">
          <IconButton icon="locate" label="Go to my location" onPress={onLocatePress} size={44} />
          <IconButton
            icon={mapPitch === 60 ? 'map-outline' : 'cube-outline'}
            label={mapPitch === 60 ? 'Show flat map' : 'Show 3D map'}
            onPress={onTogglePitch}
            size={44}
          />
        </View>
      ) : null}
    </View>
  );
}

/** Pickup pin (ink dot in a white ring on a short stem) whose tip marks the map centre. */
function CenterPin() {
  return (
    <View style={styles.pinLayer} pointerEvents="none">
      <View style={styles.pinGround} />
      <View style={styles.pin} accessibilityLabel="Pickup pin">
        <View style={styles.pinHead}>
          <View style={styles.pinDot} />
        </View>
        <View style={styles.pinStem} />
      </View>
    </View>
  );
}

const PIN_HEAD = 30;
const PIN_STEM = 14;

const styles = StyleSheet.create({
  header: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    backgroundColor: palette.background,
    borderBottomLeftRadius: radius.xxl,
    borderBottomRightRadius: radius.xxl,
    ...shadow.card,
  },
  greetingRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  greetingText: {
    flex: 1,
  },
  subtitle: {
    color: palette.textMuted,
  },
  search: {
    marginTop: space.md,
  },
  pressed: {
    opacity: 0.85,
  },
  controls: {
    position: 'absolute',
    right: space.md,
    gap: space.xs,
  },
  adjustBar: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  hint: {
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: palette.ink,
    ...shadow.card,
  },
  hintText: {
    color: palette.onPrimary,
    textAlign: 'center',
  },
  pinLayer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pinGround: {
    position: 'absolute',
    width: 14,
    height: 6,
    borderRadius: 7,
    backgroundColor: 'rgba(22, 20, 15, 0.25)',
  },
  pin: {
    alignItems: 'center',
    // Lift the pin so the stem's tip sits exactly on the map centre.
    transform: [{ translateY: -(PIN_HEAD + PIN_STEM) / 2 }],
  },
  pinHead: {
    width: PIN_HEAD,
    height: PIN_HEAD,
    borderRadius: PIN_HEAD / 2,
    backgroundColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.floating,
  },
  pinDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: palette.ink,
  },
  pinStem: {
    width: 3,
    height: PIN_STEM,
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
    backgroundColor: palette.ink,
  },
});
