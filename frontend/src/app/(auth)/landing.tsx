// src/app/(auth)/landing.tsx
// Old entry point, kept so existing links still work. The intro lives in welcome.tsx.
import { Redirect } from 'expo-router';

export default function LandingRedirect() {
  return <Redirect href="/(auth)/welcome" />;
}
