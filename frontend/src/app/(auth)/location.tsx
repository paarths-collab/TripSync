// src/app/(auth)/location.tsx
// Shown once per install after sign-up or the first log-in: explains why the app
// asks for location before the system prompt appears.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BackHandler, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import { Text } from 'react-native-paper';
import { useRouter } from 'expo-router';
import * as Location from 'expo-location';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import OnboardingArt from '../../components/onboarding/OnboardingArt';
import { Button, Card, IconBadge, IconName } from '../../components/ui';
import { palette, space, type } from '../../constants/theme';
import { useAuth } from '../../context/AuthContext';

const FEATURES: { icon: IconName; title: string; body: string }[] = [
  { icon: 'navigate', title: 'Quick pickup point', body: 'Start from where you are, no typing.' },
  { icon: 'people', title: 'Lifts heading your way', body: 'See students leaving from near you.' },
];

export default function LocationPrimerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const { markLocationPrimerSeen } = useAuth();
  const [requesting, setRequesting] = useState(false);
  const leaving = useRef(false);

  const artHeight = Math.round(Math.max(200, Math.min(height * 0.5, height - 520 - insets.bottom)));

  const finish = useCallback(async () => {
    if (leaving.current) return;
    leaving.current = true;
    await markLocationPrimerSeen();
    router.replace('/(main)/home');
  }, [markLocationPrimerSeen, router]);

  // Permission already granted (say, from an earlier install): nothing to explain.
  useEffect(() => {
    Location.getForegroundPermissionsAsync()
      .then((p) => {
        if (p.granted) finish();
      })
      .catch(() => {});
  }, [finish]);

  // Android back acts like Skip rather than returning to the sign-in screens.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      finish();
      return true;
    });
    return () => sub.remove();
  }, [finish]);

  const allowLocation = async () => {
    setRequesting(true);
    try {
      await Location.requestForegroundPermissionsAsync();
    } catch {
      // Whatever the answer, the app works; location can be allowed later.
    }
    await finish();
  };

  return (
    <View style={styles.screen}>
      <OnboardingArt variant="location" height={artHeight} topInset={insets.top} />
      <ScrollView style={styles.flex} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={[type.display, styles.title]} accessibilityRole="header">
          Your ride, powered by location
        </Text>
        <Text style={[type.body, styles.body]}>
          We use your location to set your pickup point and show lifts heading your way. It’s only used while you have
          the app open.
        </Text>
        <View style={styles.cards}>
          {FEATURES.map((f) => (
            <Card key={f.title} style={styles.card}>
              <IconBadge icon={f.icon} size={40} />
              <View style={styles.cardText}>
                <Text style={[type.bodyStrong, { color: palette.text }]}>{f.title}</Text>
                <Text style={[type.label, { color: palette.textMuted }]}>{f.body}</Text>
              </View>
            </Card>
          ))}
        </View>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
        <Button label="Use my location" variant="dark" icon="navigate" onPress={allowLocation} loading={requesting} />
        <Button
          label="Skip for now"
          variant="secondary"
          onPress={finish}
          disabled={requesting}
          style={{ marginTop: space.sm }}
        />
        <Text style={[type.caption, styles.note]}>You can change this at any time in your phone’s settings.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: palette.background,
  },
  flex: {
    flex: 1,
  },
  content: {
    paddingHorizontal: space.xl,
    paddingTop: space.xs,
    paddingBottom: space.md,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  title: {
    color: palette.text,
    textAlign: 'center',
  },
  body: {
    color: palette.textMuted,
    textAlign: 'center',
    marginTop: space.sm,
  },
  cards: {
    gap: space.xs,
    marginTop: space.lg,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  cardText: {
    flex: 1,
    marginLeft: space.sm,
  },
  footer: {
    paddingHorizontal: space.xl,
    paddingTop: space.sm,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  note: {
    color: palette.textMuted,
    textAlign: 'center',
    marginTop: space.sm,
  },
});
