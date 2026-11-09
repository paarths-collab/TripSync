// src/app/(auth)/index.tsx
import { Redirect } from 'expo-router';

export default function AuthIndex() {
  return <Redirect href="/(auth)/welcome" />;
}
