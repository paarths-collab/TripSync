// src/components/onboarding/FadeToBackground.tsx
// A soft fade from transparent to the screen background, built from thin bands
// so it needs no gradient library (and no native rebuild).
import React from 'react';
import { StyleProp, View, ViewStyle } from 'react-native';
import { palette } from '../../constants/theme';

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export default function FadeToBackground({
  height,
  color = palette.background,
  steps = 28,
  style,
}: {
  height: number;
  color?: string;
  steps?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const [r, g, b] = hexToRgb(color);
  return (
    <View style={[{ position: 'absolute', left: 0, right: 0, bottom: 0, height, pointerEvents: 'none' }, style]}>
      {Array.from({ length: steps }, (_, i) => {
        const t = (i + 1) / steps;
        const alpha = t * t * (3 - 2 * t); // smoothstep: gentle at both ends
        return <View key={i} style={{ flex: 1, backgroundColor: `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})` }} />;
      })}
    </View>
  );
}
