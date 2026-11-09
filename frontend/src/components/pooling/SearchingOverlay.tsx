// src/components/pooling/SearchingOverlay.tsx
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';

import { Button, Sheet, Tag } from '../ui';
import { layout, palette, space, type } from '../../constants/theme';

interface SearchingOverlayProps {
  visible: boolean;
  onCancel: () => void;
  destinationName?: string | null;
}

export default function SearchingOverlay({ visible, onCancel, destinationName }: SearchingOverlayProps) {
  if (!visible) return null;

  return (
    <View style={styles.overlay}>
      <Sheet style={styles.sheet}>
        <View style={styles.spinnerWrap}>
          <ActivityIndicator size="large" color={palette.ink} accessibilityLabel="Searching" />
        </View>
        <Tag label="Searching" tone="primary" icon="search" style={styles.tag} />
        <Text style={[type.title2, styles.center]} accessibilityLiveRegion="polite">
          Looking for students going your way
        </Text>
        <Text style={[type.body, styles.body]}>
          {destinationName
            ? `We're checking for students heading towards ${destinationName}. Anyone we find shows up here.`
            : "We're checking for students heading the same way. Anyone we find shows up here."}
        </Text>
        <Button label="Cancel search" variant="outline" onPress={onCancel} style={styles.cancel} />
      </Sheet>
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
    alignItems: 'center',
    paddingTop: space.xs,
    paddingBottom: layout.tabBarSpace,
  },
  spinnerWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: palette.yellowSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  tag: {
    alignSelf: 'center',
    marginTop: space.md,
  },
  center: {
    marginTop: space.sm,
    textAlign: 'center',
  },
  body: {
    marginTop: space.xs,
    color: palette.textMuted,
    textAlign: 'center',
  },
  cancel: {
    marginTop: space.lg,
  },
});
