// src/app/index.tsx
// App entry. AuthContext decides where to go once the saved session is checked
// (welcome, verify email, or the main app), so this only fills the gap.
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { palette } from '../constants/theme';

export default function StartPage() {
  return (
    <View style={styles.screen} accessibilityLabel="Loading">
      <ActivityIndicator color={palette.ink} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: palette.background,
  },
});
