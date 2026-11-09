// src/constants/theme.ts
// Single source of truth for the app's look: black and yellow like Mumbai's
// kaali-peeli taxis and autos, on warm off-white. Screens should read colours,
// type, spacing, radii and shadows from here instead of hardcoding values.
import { configureFonts, MD3LightTheme as DefaultTheme } from 'react-native-paper';

export const palette = {
  // Brand
  yellow: '#FFC629',
  yellowPressed: '#F2B705',
  yellowSoft: '#FFF0C2',
  yellowTint: '#FFF8E0',
  goldText: '#7A5A00', // "yellow" text on light surfaces (yellow itself fails contrast)
  onYellow: '#16140F', // never put white on yellow

  ink: '#16140F',
  ink2: '#2B2822',
  onDarkMuted: '#B8B1A3',

  // Kept names so existing screens map onto the new scheme
  primary: '#16140F', // black pill CTAs, active states
  primaryDark: '#2B2822',
  primarySoft: '#FFF0C2',
  onPrimary: '#FFFFFF',
  accent: '#FFC629',
  accentSoft: '#FFF8E0',

  text: '#16140F',
  textMuted: '#6A6458',
  textFaint: '#736C60', // still passes 4.5:1 on background and surface

  background: '#F7F4EC',
  surface: '#FFFFFF',
  surfaceMuted: '#F0ECE2',
  border: '#E6E0D2', // decorative only
  borderStrong: '#8C8576', // input outlines (3:1 non-text)

  success: '#17734A',
  successSoft: '#E1F3E9',
  online: '#22A35A',
  warning: '#8F5B00',
  warningSoft: '#FFF0D4',
  danger: '#B3261E',
  dangerSoft: '#FDE7E3',
  dangerSolid: '#D7322A',
  info: '#2259B8',
  infoSoft: '#E5EDFB',

  overlay: 'rgba(22, 20, 15, 0.45)',
  mapRoute: '#16140F',
};

// Space reserved at the bottom of tab screens so content scrolls above the floating tab bar.
export const layout = {
  tabBarSpace: 104,
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
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 28,
  pill: 999,
};

// Font families. On Android, fontWeight is ignored for custom fonts, so pick the
// weight through fontFamily (e.g. fonts.bold) rather than fontWeight.
export const fonts = {
  regular: 'PlusJakartaSans_400Regular',
  medium: 'PlusJakartaSans_500Medium',
  semibold: 'PlusJakartaSans_600SemiBold',
  bold: 'PlusJakartaSans_700Bold',
  extrabold: 'PlusJakartaSans_800ExtraBold',
};

// Legacy weight tokens (still used by some styles). Prefer `type` or `fonts`.
export const font = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
};

export const type = {
  display: { fontFamily: fonts.extrabold, fontSize: 32, lineHeight: 38, letterSpacing: -0.6 },
  title1: { fontFamily: fonts.bold, fontSize: 26, lineHeight: 32, letterSpacing: -0.4 },
  title2: { fontFamily: fonts.bold, fontSize: 20, lineHeight: 26, letterSpacing: -0.2 },
  title3: { fontFamily: fonts.semibold, fontSize: 17, lineHeight: 22 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 22 },
  bodyStrong: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 22 },
  label: { fontFamily: fonts.medium, fontSize: 13, lineHeight: 18 },
  caption: { fontFamily: fonts.medium, fontSize: 12, lineHeight: 16 },
  button: { fontFamily: fonts.semibold, fontSize: 16, lineHeight: 20 },
  price: { fontFamily: fonts.bold, fontSize: 17, lineHeight: 22 },
};

// React Native 0.81 (New Architecture) supports CSS-style boxShadow on iOS,
// Android and web. Shadows are tinted with ink, never pure black.
export const shadow = {
  card: { boxShadow: '0px 4px 16px rgba(22, 20, 15, 0.06)' } as object,
  raised: { boxShadow: '0px -6px 28px rgba(22, 20, 15, 0.10)' } as object,
  floating: { boxShadow: '0px 10px 30px rgba(22, 20, 15, 0.14)' } as object,
  button: { boxShadow: '0px 6px 14px rgba(22, 20, 15, 0.12)' } as object,
};

export type Tone = 'neutral' | 'primary' | 'brand' | 'success' | 'warning' | 'danger' | 'info';

export const toneColors: Record<Tone, { fg: string; bg: string }> = {
  neutral: { fg: palette.textMuted, bg: palette.surfaceMuted },
  primary: { fg: palette.ink, bg: palette.yellowSoft },
  brand: { fg: palette.ink, bg: palette.yellow },
  success: { fg: palette.success, bg: palette.successSoft },
  warning: { fg: palette.warning, bg: palette.warningSoft },
  danger: { fg: palette.danger, bg: palette.dangerSoft },
  info: { fg: palette.info, bg: palette.infoSoft },
};

const paperFonts = configureFonts({ config: { fontFamily: fonts.regular } });

export const theme = {
  ...DefaultTheme,
  roundness: 4, // Paper multiplies this; 4 -> 16px on inputs
  fonts: paperFonts,
  colors: {
    ...DefaultTheme.colors,
    primary: palette.ink,
    onPrimary: palette.onPrimary,
    primaryContainer: palette.yellowSoft,
    onPrimaryContainer: palette.ink,
    secondary: palette.yellow,
    onSecondary: palette.onYellow,
    secondaryContainer: palette.yellowTint,
    background: palette.background,
    surface: palette.surface,
    surfaceVariant: palette.surfaceMuted,
    onSurface: palette.text,
    onBackground: palette.text,
    onSurfaceVariant: palette.textMuted,
    error: palette.danger,
    errorContainer: palette.dangerSoft,
    outline: palette.borderStrong,
    outlineVariant: palette.border,
    backdrop: palette.overlay,
    elevation: {
      ...DefaultTheme.colors.elevation,
      level1: palette.surface,
      level2: palette.surface,
      level3: palette.surface,
    },
    custom: {
      accent: palette.yellow,
      secondaryText: palette.textMuted,
      success: palette.success,
      border: palette.border,
      primaryGradient: [palette.yellow, palette.yellowPressed],
    },
  },
};
