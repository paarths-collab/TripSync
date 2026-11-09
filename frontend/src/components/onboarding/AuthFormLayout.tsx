// src/components/onboarding/AuthFormLayout.tsx
// Shared frame for the auth forms: floating back button, yellow icon tile, big
// headline, and a keyboard-aware scrolling body.
import React from 'react';
import { KeyboardAvoidingView, ScrollView, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { palette, radius, space, type } from '../../constants/theme';
import type { IconName } from '../ui';
import RoundBackButton from './RoundBackButton';

export default function AuthFormLayout({
  title,
  subtitle,
  icon,
  onBack,
  children,
}: {
  title: string;
  subtitle?: React.ReactNode;
  icon?: IconName;
  onBack?: () => void;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.screen}>
      <KeyboardAvoidingView style={styles.flex} behavior="padding">
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + (onBack ? 72 : space.xxl), paddingBottom: insets.bottom + space.xl },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.inner}>
            {icon ? (
              <View style={styles.iconTile}>
                <Ionicons name={icon} size={30} color={palette.ink} />
              </View>
            ) : null}
            <Text style={[type.display, styles.title]} accessibilityRole="header">
              {title}
            </Text>
            {subtitle ? (
              typeof subtitle === 'string' ? (
                <Text style={[type.body, styles.subtitle]}>{subtitle}</Text>
              ) : (
                subtitle
              )
            ) : null}
            <View style={styles.body}>{children}</View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
      {onBack ? <RoundBackButton onPress={onBack} style={[styles.back, { top: insets.top + space.xs }]} /> : null}
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
    flexGrow: 1,
    paddingHorizontal: space.xl,
  },
  inner: {
    width: '100%',
    maxWidth: 480,
    alignSelf: 'center',
    flexGrow: 1,
  },
  iconTile: {
    width: 64,
    height: 64,
    borderRadius: radius.lg,
    backgroundColor: palette.yellow,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.lg,
  },
  title: {
    color: palette.text,
  },
  subtitle: {
    color: palette.textMuted,
    marginTop: space.xs,
  },
  body: {
    marginTop: space.xl,
    flexGrow: 1,
  },
  back: {
    position: 'absolute',
    left: space.md,
  },
});
