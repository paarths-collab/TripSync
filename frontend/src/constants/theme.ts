// src/constants/theme.ts
// Single source of truth for TripSync's look. Screens should read colours,
// spacing and radii from here instead of hardcoding values.
import { Platform } from 'react-native';
import { MD3LightTheme as DefaultTheme } from 'react-native-paper';

export const palette = {
  primary: '#5B4BDB',
  primaryDark: '#4335B8',
  primarySoft: '#ECE9FD',
  onPrimary: '#FFFFFF',

  accent: '#F2A93B',
  accentSoft: '#FDF1DD',

  ink: '#16142B',
  text: '#16142B',
  textMuted: '#6B6880',
  textFaint: '#9C99AE',

  background: '#F6F5FB',
  surface: '#FFFFFF',
  surfaceMuted: '#F1F0F7',
  border: '#E6E4F0',

  success: '#1F9D6B',
  successSoft: '#E3F5EC',
  warning: '#B7791F',
  warningSoft: '#FCF1DC',
  danger: '#D64545',
  dangerSoft: '#FBE7E7',
  info: '#2F6FDB',
  infoSoft: '#E5EEFC',

  overlay: 'rgba(22, 20, 43, 0.45)',
};

export const space = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
};

export const font = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

export const shadow = {
  card: Platform.select({
    ios: {
      shadowColor: palette.ink,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.06,
      shadowRadius: 12,
    },
    android: { elevation: 2 },
    default: {
      shadowColor: palette.ink,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.06,
      shadowRadius: 12,
    },
  }) as object,
  raised: Platform.select({
    ios: {
      shadowColor: palette.ink,
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.12,
      shadowRadius: 20,
    },
    android: { elevation: 8 },
    default: {
      shadowColor: palette.ink,
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.12,
      shadowRadius: 20,
    },
  }) as object,
};

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

export const toneColors: Record<Tone, { fg: string; bg: string }> = {
  neutral: { fg: palette.textMuted, bg: palette.surfaceMuted },
  primary: { fg: palette.primary, bg: palette.primarySoft },
  success: { fg: palette.success, bg: palette.successSoft },
  warning: { fg: palette.warning, bg: palette.warningSoft },
  danger: { fg: palette.danger, bg: palette.dangerSoft },
  info: { fg: palette.info, bg: palette.infoSoft },
};

export const theme = {
  ...DefaultTheme,
  roundness: 3, // Paper multiplies this; 3 -> 12px on buttons and inputs
  colors: {
    ...DefaultTheme.colors,
    primary: palette.primary,
    onPrimary: palette.onPrimary,
    primaryContainer: palette.primarySoft,
    onPrimaryContainer: palette.primaryDark,
    secondary: palette.accent,
    secondaryContainer: palette.accentSoft,
    background: palette.background,
    surface: palette.surface,
    surfaceVariant: palette.surfaceMuted,
    onSurface: palette.text,
    onBackground: palette.text,
    onSurfaceVariant: palette.textMuted,
    error: palette.danger,
    errorContainer: palette.dangerSoft,
    outline: palette.border,
    outlineVariant: palette.border,
    backdrop: palette.overlay,
    elevation: {
      ...DefaultTheme.colors.elevation,
      level1: palette.surface,
      level2: palette.surface,
      level3: palette.surface,
    },
    custom: {
      accent: palette.accent,
      secondaryText: palette.textMuted,
      success: palette.success,
      border: palette.border,
      primaryGradient: [palette.primary, palette.primaryDark],
    },
  },
};
