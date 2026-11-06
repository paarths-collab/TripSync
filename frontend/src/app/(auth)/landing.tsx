// src/app/(auth)/landing.tsx

import React from 'react';
import { View, StyleSheet, ScrollView, StatusBar } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import ScreenWrapper from '../../components/ScreenWrapper';
import { Card, IconBadge } from '../../components/ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

const FEATURES: { icon: IconName; title: string; description: string }[] = [
  {
    icon: 'time-outline',
    title: 'Match by departure time',
    description: 'Find students from your college heading the same way around the same time.',
  },
  {
    icon: 'people-outline',
    title: 'Agree a shared ride together',
    description: 'Settle on a taxi plan as a group, then book and split it yourselves.',
  },
  {
    icon: 'chatbubbles-outline',
    title: 'Chat while your plan is active',
    description: 'Coordinate pickup details with your group in one place.',
  },
  {
    icon: 'storefront-outline',
    title: 'Campus services board',
    description: 'Offer or find small services within your campus community.',
  },
];

export default function LandingScreen() {
  const router = useRouter();

  return (
    <ScreenWrapper>
      <StatusBar barStyle="dark-content" />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Hero */}
        <View style={styles.hero}>
          <View style={styles.logoBadge}>
            <Ionicons name="car-sport" size={40} color={palette.onPrimary} />
          </View>
          <Text style={styles.title} accessibilityRole="header">
            TripSync
          </Text>
          <Text style={styles.tagline}>
            Plan shared taxi rides with students from your college.
          </Text>
        </View>

        {/* Features */}
        <Card style={styles.featuresCard}>
          {FEATURES.map((f, i) => (
            <View
              key={f.title}
              style={[styles.featureRow, i < FEATURES.length - 1 && styles.featureDivider]}
            >
              <IconBadge icon={f.icon} size={40} />
              <View style={styles.featureText}>
                <Text style={styles.featureTitle}>{f.title}</Text>
                <Text style={styles.featureDescription}>{f.description}</Text>
              </View>
            </View>
          ))}
        </Card>

        <View style={styles.spacer} />

        {/* Actions */}
        <View style={styles.actions}>
          <Button
            mode="contained"
            onPress={() => router.push('/(auth)/register')}
            style={styles.primaryButton}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
          >
            Create account
          </Button>
          <Button
            mode="text"
            onPress={() => router.push('/(auth)/login')}
            style={styles.secondaryButton}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
          >
            I already have an account
          </Button>
          <Text style={styles.footnote}>
            TripSync records ride agreements between students. You book and pay for the taxi yourselves.
          </Text>
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: space.xl,
    paddingTop: space.xxl,
    paddingBottom: space.xl,
  },
  hero: {
    alignItems: 'center',
    marginBottom: space.xxl,
  },
  logoBadge: {
    width: 80,
    height: 80,
    borderRadius: radius.xl,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.lg,
    ...shadow.raised,
  },
  title: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: font.bold,
    color: palette.text,
    letterSpacing: -0.5,
    textAlign: 'center',
  },
  tagline: {
    marginTop: space.xs,
    fontSize: 16,
    lineHeight: 22,
    color: palette.textMuted,
    textAlign: 'center',
    maxWidth: 300,
  },
  featuresCard: {
    paddingVertical: space.xs,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  featureDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: palette.border,
  },
  featureText: {
    flex: 1,
    marginLeft: space.md,
  },
  featureTitle: {
    fontSize: 15,
    fontWeight: font.semibold,
    color: palette.text,
  },
  featureDescription: {
    marginTop: 2,
    fontSize: 13,
    lineHeight: 18,
    color: palette.textMuted,
  },
  spacer: {
    flexGrow: 1,
    minHeight: space.xl,
  },
  actions: {
    gap: space.xs,
  },
  primaryButton: {
    borderRadius: radius.md,
  },
  secondaryButton: {
    borderRadius: radius.md,
  },
  buttonContent: {
    height: 52,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: font.semibold,
  },
  footnote: {
    marginTop: space.xs,
    fontSize: 12,
    lineHeight: 17,
    color: palette.textFaint,
    textAlign: 'center',
  },
});
