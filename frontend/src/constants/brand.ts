// src/constants/brand.ts
// The app's name lives here and only here, so a rename is a one-line change.
// app.config.ts reads the same values through environment variables.
export const APP_NAME = process.env.EXPO_PUBLIC_APP_NAME || 'TripSync';
export const APP_TAGLINE = 'Share the ride to college';
export const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL || '';
