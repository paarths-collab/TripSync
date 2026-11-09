// src/components/onboarding/LinkButton.tsx
// A text-only button ("Forgot password?", "Resend code") with a 44pt touch target.
import React from 'react';
import { Pressable, StyleProp, ViewStyle } from 'react-native';
import { Text } from 'react-native-paper';
import { fonts, palette, type } from '../../constants/theme';

export default function LinkButton({
  label,
  onPress,
  disabled = false,
  muted = false,
  style,
  accessibilityLabel,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  muted?: boolean;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || label}
      accessibilityState={{ disabled }}
      hitSlop={{ left: 8, right: 8 }}
      style={({ pressed }) => [
        { minHeight: 44, justifyContent: 'center', paddingHorizontal: 4, opacity: pressed ? 0.6 : 1 },
        style,
      ]}
    >
      <Text
        style={[
          type.bodyStrong,
          {
            fontFamily: fonts.semibold,
            color: disabled || muted ? palette.textMuted : palette.ink,
            textDecorationLine: disabled || muted ? 'none' : 'underline',
          },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}
