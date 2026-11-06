// src/components/ScreenWrapper.tsx
// Safe-area aware screen container with the app background colour.
import React from 'react';
import { View, StyleSheet, ViewStyle, StyleProp } from 'react-native';
import { SafeAreaView, Edge } from 'react-native-safe-area-context';
import { palette } from '../constants/theme';

interface ScreenWrapperProps {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Which safe-area edges to inset. Defaults to all edges. */
  edges?: Edge[];
  /** Override the screen background (defaults to palette.background). */
  backgroundColor?: string;
}

export default function ScreenWrapper({
  children,
  style,
  edges,
  backgroundColor = palette.background,
}: ScreenWrapperProps) {
  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor }]} edges={edges}>
      <View style={[styles.container, style]}>{children}</View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
  container: {
    flex: 1,
  },
});
