// src/app/(auth)/_layout.tsx
// Onboarding and sign-in screens. Each screen draws its own back button, so the
// stack header is hidden.
import React from 'react';
import { Stack } from 'expo-router';
import { APP_NAME } from '../../constants/brand';
import { palette } from '../../constants/theme';

export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: palette.background },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="index" options={{ animation: 'none' }} />
      <Stack.Screen name="welcome" options={{ animation: 'fade', title: APP_NAME }} />
      <Stack.Screen name="landing" options={{ animation: 'none' }} />
      <Stack.Screen name="login" options={{ title: 'Log in' }} />
      <Stack.Screen name="register" options={{ title: 'Create account' }} />
      <Stack.Screen name="verify-email" options={{ title: 'Verify email' }} />
      <Stack.Screen name="forgot-password" options={{ title: 'Forgot password' }} />
      <Stack.Screen name="reset-password" options={{ title: 'Reset password' }} />
      <Stack.Screen name="location" options={{ animation: 'fade', gestureEnabled: false, title: 'Location' }} />
    </Stack>
  );
}
