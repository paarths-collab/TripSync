// src/app/(main)/services/_layout.tsx
// Each services screen draws its own header (ScreenHeader with a rounded-square
// back button) so the section matches the rest of the app.
import { Stack } from 'expo-router';
import { palette } from '../../../constants/theme';

export default function ServicesLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: palette.background },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Services' }} />
      <Stack.Screen name="[id]" options={{ title: 'Service' }} />
      <Stack.Screen name="create" options={{ title: 'New service', presentation: 'modal' }} />
      <Stack.Screen name="dashboard" options={{ title: 'My services' }} />
      <Stack.Screen name="applicants/[id]" options={{ title: 'Applicants' }} />
    </Stack>
  );
}
