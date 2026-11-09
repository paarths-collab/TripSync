// src/app/(auth)/welcome.tsx
// First screen for signed-out users: a three-slide intro with the sign-up and
// log-in buttons always in reach.
import React, { useCallback, useRef, useState } from 'react';
import {
  Animated,
  FlatList,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { Text } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import OnboardingArt, { ArtVariant } from '../../components/onboarding/OnboardingArt';
import { Button } from '../../components/ui';
import { APP_NAME } from '../../constants/brand';
import { fonts, palette, radius, space, type } from '../../constants/theme';

type Slide = { key: string; art: ArtVariant; title: string; body: string };

const SLIDES: Slide[] = [
  {
    key: 'share',
    art: 'commute',
    title: 'Share the ride to college',
    body: `${APP_NAME} matches you with students from your college who are heading the same way, around the same time.`,
  },
  {
    key: 'lift',
    art: 'lift',
    title: 'Find a lift or split an auto',
    body: 'Catch a scooter, bike or car lift with a student on your commute, or team up to split an auto. You arrange and pay for the trip together.',
  },
  {
    key: 'college',
    art: 'college',
    title: 'Travel with your college',
    body: 'Sign up with your college email so your matches are students from your campus. Chat with your match before you head out.',
  },
];

export default function WelcomeScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const listRef = useRef<FlatList<Slide>>(null);
  const scrollX = useRef(new Animated.Value(0)).current;
  const indexRef = useRef(0);
  const [index, setIndex] = useState(0);

  // Imagery takes the top ~55%, but never squeezes the copy and buttons below it.
  const artHeight = Math.round(Math.max(220, Math.min(height * 0.55, height - 380 - insets.bottom)));
  const isLast = index === SLIDES.length - 1;

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const x = e.nativeEvent.contentOffset.x;
      scrollX.setValue(x);
      const next = Math.max(0, Math.min(SLIDES.length - 1, Math.round(x / Math.max(1, width))));
      if (next !== indexRef.current) {
        indexRef.current = next;
        setIndex(next);
      }
    },
    [scrollX, width],
  );

  const skip = () => listRef.current?.scrollToIndex({ index: SLIDES.length - 1, animated: true });

  return (
    <View style={styles.screen}>
      <FlatList
        ref={listRef}
        data={SLIDES}
        keyExtractor={(s) => s.key}
        horizontal
        pagingEnabled
        bounces={false}
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
        style={styles.flex}
        renderItem={({ item }) => (
          <View style={{ width }}>
            <OnboardingArt variant={item.art} height={artHeight} topInset={insets.top} />
            <View style={styles.copy}>
              <Text style={[type.display, styles.title]} accessibilityRole="header">
                {item.title}
              </Text>
              <Text style={[type.body, styles.body]}>{item.body}</Text>
            </View>
          </View>
        )}
      />

      <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
        <View
          style={styles.dots}
          accessible
          accessibilityRole="text"
          accessibilityLabel={`Slide ${index + 1} of ${SLIDES.length}`}
        >
          {SLIDES.map((s, i) => {
            const inputRange = [(i - 1) * width, i * width, (i + 1) * width];
            return (
              <Animated.View
                key={s.key}
                style={[
                  styles.dot,
                  {
                    width: scrollX.interpolate({ inputRange, outputRange: [8, 24, 8], extrapolate: 'clamp' }),
                    opacity: scrollX.interpolate({ inputRange, outputRange: [0.25, 1, 0.25], extrapolate: 'clamp' }),
                  },
                ]}
              />
            );
          })}
        </View>
        <Button label="Create account" variant="dark" onPress={() => router.push('/(auth)/register')} />
        <Button
          label="Log in"
          variant="secondary"
          onPress={() => router.push('/(auth)/login')}
          style={{ marginTop: space.sm }}
        />
      </View>

      {!isLast ? (
        <Pressable
          onPress={skip}
          accessibilityRole="button"
          accessibilityLabel="Skip intro"
          hitSlop={6}
          style={({ pressed }) => [styles.skip, { top: insets.top + space.xs }, pressed && styles.skipPressed]}
        >
          <Text style={[type.label, { color: palette.ink, fontFamily: fonts.semibold }]}>Skip</Text>
        </Pressable>
      ) : null}
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
  copy: {
    paddingHorizontal: space.xl,
    paddingTop: space.xs,
    alignItems: 'center',
  },
  title: {
    color: palette.text,
    textAlign: 'center',
    maxWidth: 420,
  },
  body: {
    color: palette.textMuted,
    textAlign: 'center',
    marginTop: space.sm,
    maxWidth: 420,
  },
  footer: {
    paddingHorizontal: space.xl,
    paddingTop: space.sm,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  dots: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 6,
    height: 24,
    marginBottom: space.md,
  },
  dot: {
    height: 8,
    borderRadius: 4,
    backgroundColor: palette.ink,
  },
  skip: {
    position: 'absolute',
    right: space.md,
    minHeight: 44,
    minWidth: 64,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
  },
  skipPressed: {
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
  },
});
