// src/app/(main)/_layout.tsx

import React from 'react';
import { Tabs, useSegments } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Platform, View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { palette, radius, font } from '../../constants/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function TabIcon({ focused, icon }: { focused: boolean; icon: string }) {
  return (
    <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
      <Ionicons
        name={(focused ? icon : `${icon}-outline`) as IconName}
        size={22}
        color={focused ? palette.primary : palette.textFaint}
      />
    </View>
  );
}

export default function MainLayout() {
  const segments = useSegments();
  const insets = useSafeAreaInsets();
  // The single-chat screen is hidden from the tab bar; keep "Chats" highlighted there.
  const onChatScreen = (segments as string[]).includes('chat');
  const bottomPad = Math.max(insets.bottom, Platform.OS === 'ios' ? 20 : 10);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.primary,
        tabBarInactiveTintColor: palette.textFaint,
        tabBarStyle: {
          backgroundColor: palette.surface,
          borderTopColor: palette.border,
          borderTopWidth: StyleSheet.hairlineWidth,
          height: 60 + bottomPad,
          paddingTop: 8,
          paddingBottom: bottomPad,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: font.semibold,
          marginTop: 2,
        },
        tabBarHideOnKeyboard: Platform.OS !== 'ios',
        animation: 'shift',
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: 'Rides',
          tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon="car-sport" />,
        }}
      />
      <Tabs.Screen
        name="chats"
        options={{
          title: 'Chats',
          tabBarIcon: ({ focused }) => <TabIcon focused={focused || onChatScreen} icon="chatbubbles" />,
        }}
      />
      <Tabs.Screen
        name="services"
        options={{
          title: 'Services',
          tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon="grid" />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon="person" />,
        }}
      />
      <Tabs.Screen name="chat" options={{ href: null }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  iconWrap: {
    width: 48,
    height: 28,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrapActive: {
    backgroundColor: palette.primarySoft,
  },
});
