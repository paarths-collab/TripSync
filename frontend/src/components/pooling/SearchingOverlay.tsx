// src/components/pooling/SearchingOverlay.tsx
import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ActivityIndicator, Button, Text } from 'react-native-paper';
import { StatusPill } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface SearchingOverlayProps {
  visible: boolean;
  onCancel: () => void;
}

export default function SearchingOverlay({ visible, onCancel }: SearchingOverlayProps) {
  // Render nothing if the overlay is not supposed to be visible.
  if (!visible) {
    return null;
  }

  return (
    <View style={styles.overlay}>
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.spinnerWrap}>
          <ActivityIndicator size="large" color={palette.primary} />
        </View>
        <StatusPill label="Searching" tone="primary" icon="search" style={styles.pill} />
        <Text style={styles.title}>Looking for a ride partner</Text>
        <Text style={styles.body}>
          We&apos;re checking for students heading the same way. This can take a moment — we&apos;ll
          show you anyone we find here.
        </Text>
        <Button
          mode="outlined"
          onPress={onCancel}
          textColor={palette.danger}
          style={styles.cancelButton}
          contentStyle={styles.buttonContent}
          labelStyle={styles.buttonLabel}
        >
          Cancel search
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: palette.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.xl,
    paddingBottom: space.xl,
    alignItems: 'center',
    ...shadow.raised,
  },
  handle: {
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginTop: space.xs,
    marginBottom: space.lg,
  },
  spinnerWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pill: {
    alignSelf: 'center',
    marginTop: space.md,
  },
  title: {
    marginTop: space.sm,
    fontSize: 20,
    fontWeight: font.bold,
    color: palette.text,
    textAlign: 'center',
  },
  body: {
    marginTop: space.xs,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
    textAlign: 'center',
  },
  cancelButton: {
    alignSelf: 'stretch',
    marginTop: space.lg,
    borderRadius: radius.md,
    borderColor: palette.danger,
  },
  buttonContent: {
    height: 48,
  },
  buttonLabel: {
    fontSize: 15,
    fontWeight: font.semibold,
  },
});
