// src/components/onboarding/RoundBackButton.tsx
// The translucent round back button that floats over onboarding imagery.
import React from 'react';
import { Pressable, StyleProp, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { palette, shadow } from '../../constants/theme';

export default function RoundBackButton({
  onPress,
  label = 'Go back',
  style,
}: {
  onPress: () => void;
  label?: string;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={4}
      style={({ pressed }) => [styles.button, pressed && styles.pressed, style]}
    >
      <Ionicons name="chevron-back" size={24} color={palette.ink} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(22, 20, 15, 0.10)',
    ...shadow.card,
  },
  pressed: {
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
    transform: [{ scale: 0.96 }],
  },
});
