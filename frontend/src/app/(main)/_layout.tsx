// src/app/(main)/_layout.tsx
// Floating pill tab bar (reference R1): white pill with a black rounded-square
// active tab and a yellow icon.

import React from 'react';
import { Tabs } from 'expo-router';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { palette, radius, shadow, space, type, fonts } from '../../constants/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

const TAB_ICONS: Record<string, string> = {
  home: 'car-sport',
  chats: 'chatbubbles',
  services: 'grid',
  profile: 'person',
};

function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const routes = state.routes.filter((r) => TAB_ICONS[r.name]);
  const focusedName = state.routes[state.index]?.name;
  // The single-chat screen is hidden from the bar; keep "Chats" highlighted there.
  const activeName = focusedName === 'chat' ? 'chats' : focusedName;

  return (
    <View
      pointerEvents="box-none"
      style={[styles.wrap, { paddingBottom: Math.max(insets.bottom, Platform.OS === 'ios' ? 16 : 12) }]}
    >
      <View style={styles.bar}>
        {routes.map((route) => {
          const focused = route.name === activeName;
          const { options } = descriptors[route.key];
          const label = (options.title as string) ?? route.name;
          const icon = TAB_ICONS[route.name];
          return (
            <Pressable
              key={route.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={label}
              onPress={() => {
                const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
                if (!focused && !event.defaultPrevented) navigation.navigate(route.name as never);
              }}
              style={[styles.item, focused && styles.itemActive]}
            >
              <Ionicons
                name={(focused ? icon : `${icon}-outline`) as IconName}
                size={22}
                color={focused ? palette.yellow : palette.textMuted}
              />
              {focused ? (
                <Text style={[type.caption, { color: palette.onPrimary, fontFamily: fonts.semibold, marginLeft: 6 }]}>
                  {label}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export default function MainLayout() {
  return (
    <Tabs
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        tabBarHideOnKeyboard: true,
        sceneStyle: { backgroundColor: palette.background },
      }}
    >
      <Tabs.Screen name="home" options={{ title: 'Rides' }} />
      <Tabs.Screen name="chats" options={{ title: 'Chats' }} />
      <Tabs.Screen name="services" options={{ title: 'Services' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
      <Tabs.Screen name="chat" options={{ href: null }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
  },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: palette.surface,
    borderRadius: radius.xxl,
    padding: 6,
    gap: 4,
    ...shadow.floating,
  },
  item: {
    height: 48,
    minWidth: 52,
    paddingHorizontal: space.sm,
    borderRadius: radius.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  itemActive: {
    backgroundColor: palette.ink,
    paddingHorizontal: space.md,
  },
});
