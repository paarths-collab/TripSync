// src/components/pooling/SearchingView.tsx
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { ActivityIndicator, Button, Text } from 'react-native-paper';
import ScreenWrapper from '../ScreenWrapper';
import { StatusPill } from '../ui';
import { palette, space, radius, font } from '../../constants/theme';

interface SearchingViewProps {
  onCancel: () => void;
}

export default function SearchingView({ onCancel }: SearchingViewProps) {
  return (
    <ScreenWrapper style={styles.container}>
      <View style={styles.spinnerWrap}>
        <ActivityIndicator size="large" color={palette.primary} />
      </View>
      <StatusPill label="Searching" tone="primary" icon="search" style={styles.pill} />
      <Text style={styles.title}>Looking for a ride partner</Text>
      <Text style={styles.body}>
        We&apos;re checking for students heading the same way. This can take a moment.
      </Text>
      <Button
        mode="outlined"
        onPress={onCancel}
        textColor={palette.danger}
        style={styles.button}
        contentStyle={styles.buttonContent}
      >
        Cancel search
      </Button>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: space.xl },
  spinnerWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pill: { alignSelf: 'center', marginTop: space.md },
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
  button: { alignSelf: 'stretch', marginTop: space.lg, borderRadius: radius.md, borderColor: palette.danger },
  buttonContent: { height: 48 },
});
