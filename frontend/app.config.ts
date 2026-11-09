// app.config.ts
// Expo config. Name and store identifiers come from environment variables so the
// rename and the move to the owner's Apple/Google/EAS accounts need no code change.
// Set these before any store build: APP_NAME, APP_SLUG, APP_SCHEME, IOS_BUNDLE_ID,
// ANDROID_PACKAGE, EAS_PROJECT_ID.
import type { ExpoConfig } from 'expo/config';

const name = process.env.APP_NAME || process.env.EXPO_PUBLIC_APP_NAME || 'TripSync';
const slug = process.env.APP_SLUG || 'campus-commute';
const scheme = process.env.APP_SCHEME || 'campuscommute';
const iosBundleId = process.env.IOS_BUNDLE_ID || 'com.example.campuscommute';
const androidPackage = process.env.ANDROID_PACKAGE || 'com.example.campuscommute';
const easProjectId = process.env.EAS_PROJECT_ID;

const config: ExpoConfig = {
  name,
  slug,
  scheme,
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/images/icon.png',
  userInterfaceStyle: 'light',
  newArchEnabled: true,
  ios: {
    supportsTablet: false,
    bundleIdentifier: iosBundleId,
    infoPlist: {
      ITSAppUsesNonExemptEncryption: false,
      NSLocationWhenInUseUsageDescription:
        'Your location sets your pickup point and shows lifts heading your way.',
    },
  },
  android: {
    package: androidPackage,
    adaptiveIcon: {
      foregroundImage: './assets/images/adaptive-icon.png',
      backgroundColor: '#F7F4EC',
    },
    edgeToEdgeEnabled: true,
    permissions: ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION'],
  },
  web: {
    bundler: 'metro',
    output: 'static',
    favicon: './assets/images/favicon.png',
  },
  plugins: [
    'expo-router',
    [
      'expo-splash-screen',
      {
        image: './assets/images/splash-icon.png',
        imageWidth: 200,
        resizeMode: 'contain',
        backgroundColor: '#F7F4EC',
      },
    ],
    'expo-secure-store',
    'expo-font',
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'Your location sets your pickup point and shows lifts heading your way.',
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    router: {},
    ...(easProjectId ? { eas: { projectId: easProjectId } } : {}),
  },
};

export default config;
