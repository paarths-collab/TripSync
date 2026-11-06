// src/components/pooling/RouteConfirmationCard.tsx
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { RouteDetails } from '../../services/poolingService';
import { IconBadge, IconButton } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface RouteConfirmationCardProps {
  destinationName: string;
  // Optional: a valid route object or null when the route lookup failed.
  routeDetails: RouteDetails | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function RouteConfirmationCard({
  destinationName,
  routeDetails,
  onConfirm,
  onCancel,
}: RouteConfirmationCardProps) {
  const distanceInKm = routeDetails ? (routeDetails.distance_meters / 1000).toFixed(1) : null;
  const durationInMinutes = routeDetails ? Math.round(routeDetails.duration_seconds / 60) : null;

  return (
    <View style={styles.sheet}>
      <View style={styles.handle} />

      <View style={styles.header}>
        <IconBadge icon="flag" tone="primary" size={44} />
        <View style={styles.headerText}>
          <Text style={styles.eyebrow}>Destination</Text>
          <Text style={styles.title} numberOfLines={2}>
            {destinationName}
          </Text>
        </View>
        <IconButton icon="close" label="Cancel and choose another destination" onPress={onCancel} size={36} />
      </View>

      {routeDetails && (
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Ionicons name="navigate-outline" size={16} color={palette.textMuted} />
            <Text style={styles.statText}>{distanceInKm} km</Text>
          </View>
          <View style={styles.stat}>
            <Ionicons name="time-outline" size={16} color={palette.textMuted} />
            <Text style={styles.statText}>About {durationInMinutes} min</Text>
          </View>
        </View>
      )}

      <Text style={styles.body}>
        We&apos;ll look for other students heading the same way. If you agree to share, you book
        and pay for the taxi yourselves.
      </Text>

      <Button
        mode="contained"
        onPress={onConfirm}
        style={styles.confirmButton}
        contentStyle={styles.buttonContent}
        labelStyle={styles.buttonLabel}
      >
        Find a ride partner
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginTop: space.xs,
    marginBottom: space.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  headerText: {
    flex: 1,
    marginHorizontal: space.sm,
  },
  eyebrow: {
    fontSize: 12,
    color: palette.textMuted,
    marginBottom: 2,
  },
  title: {
    fontSize: 18,
    lineHeight: 24,
    fontWeight: font.semibold,
    color: palette.text,
  },
  statsRow: {
    flexDirection: 'row',
    gap: space.xs,
    marginTop: space.md,
  },
  stat: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xxs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs + 2,
    borderRadius: radius.pill,
    backgroundColor: palette.surfaceMuted,
  },
  statText: {
    fontSize: 13,
    fontWeight: font.medium,
    color: palette.text,
  },
  body: {
    marginTop: space.md,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
  },
  confirmButton: {
    marginTop: space.lg,
    borderRadius: radius.md,
  },
  buttonContent: {
    height: 50,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: font.semibold,
  },
});
