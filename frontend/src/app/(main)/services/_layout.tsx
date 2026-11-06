import { Stack, useRouter } from 'expo-router';
import { Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { palette, radius, font } from '../../../constants/theme';

export default function ServicesLayout() {
  const router = useRouter();

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: palette.background },
        headerShadowVisible: false,
        headerTintColor: palette.text,
        headerTitleStyle: { fontWeight: font.bold, color: palette.text },
        headerBackButtonDisplayMode: 'minimal', // hides the "Back" label on iOS
        contentStyle: { backgroundColor: palette.background },
      }}
    >
      <Stack.Screen
        name="index"
        options={{
          title: 'Services',
          headerLargeTitle: false,
          headerRight: () => (
            <Pressable
              onPress={() => router.push('/services/dashboard' as any)}
              style={({ pressed }) => [styles.headerAction, pressed && { opacity: 0.7 }]}
              accessibilityRole="button"
              accessibilityLabel="My services"
              hitSlop={8}
            >
              <Ionicons name="briefcase-outline" size={18} color={palette.primary} />
            </Pressable>
          ),
        }}
      />
      <Stack.Screen name="create" options={{ title: 'New service', presentation: 'modal' }} />
      <Stack.Screen name="dashboard" options={{ title: 'My services' }} />
      <Stack.Screen name="applicants/[id]" options={{ title: 'Applicants', headerBackVisible: true }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  headerAction: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
