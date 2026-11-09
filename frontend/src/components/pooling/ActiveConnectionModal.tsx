// src/components/pooling/ActiveConnectionModal.tsx
import React, { useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { Modal, Portal, Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Avatar, Button, IconBadge, Tag } from '../ui';
import { palette, radius, shadow, space, type } from '../../constants/theme';

interface Partner {
  id: number;
  full_name: string;
  phone_number?: string | null;
  email?: string | null;
  year_of_study?: string | null;
  bio?: string | null;
}

interface ActiveConnectionModalProps {
  visible: boolean;
  partner: Partner;
  onStartChat: () => void;
  onEndRide: () => Promise<void>;
  onViewFullProfile: () => void;
}

export default function ActiveConnectionModal({
  visible,
  partner,
  onStartChat,
  onEndRide,
  onViewFullProfile,
}: ActiveConnectionModalProps) {
  const insets = useSafeAreaInsets();
  const [endingRide, setEndingRide] = useState(false);

  const handleEndRide = () => {
    Alert.alert('End this match?', 'This cancels your shared-trip match and lets your trip partner know.', [
      { text: 'Keep match', style: 'cancel' },
      {
        text: 'End match',
        style: 'destructive',
        onPress: async () => {
          setEndingRide(true);
          try {
            await onEndRide();
          } finally {
            setEndingRide(false);
          }
        },
      },
    ]);
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        dismissable={false}
        style={styles.modalWrapper}
        contentContainerStyle={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}
      >
        <View style={styles.handle} />

        <View style={styles.header}>
          <IconBadge icon="checkmark" tone="success" size={52} />
          <Text style={[type.title1, styles.title]} accessibilityRole="header">
            You&apos;re matched
          </Text>
          <Text style={[type.body, styles.subtitle]}>
            You both agreed to share a trip. Agree on the pickup point, time and how you&apos;ll split the fare in
            chat.
          </Text>
        </View>

        <View style={styles.partnerRow}>
          <Avatar name={partner.full_name} size={52} />
          <View style={styles.partnerText}>
            <Text style={type.title3} numberOfLines={1}>
              {partner.full_name}
            </Text>
            {partner.phone_number ? (
              <View style={styles.contactRow}>
                <Ionicons name="call-outline" size={14} color={palette.textMuted} />
                <Text style={[type.label, styles.muted]}>{partner.phone_number}</Text>
              </View>
            ) : partner.year_of_study ? (
              <Text style={[type.label, styles.muted]}>{partner.year_of_study}</Text>
            ) : null}
          </View>
          <Tag label="Matched" tone="success" icon="checkmark-circle" />
        </View>

        <View style={styles.actions}>
          <Button label="Open chat" icon="chatbubbles-outline" onPress={onStartChat} />
          <Button label="View trip details" variant="secondary" size="md" onPress={onViewFullProfile} />
          <Button
            label="End match"
            variant="ghost"
            size="md"
            onPress={handleEndRide}
            loading={endingRide}
            accessibilityLabel="End this trip match"
          />
        </View>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalWrapper: {
    justifyContent: 'flex-end',
    marginBottom: 0, // sheet runs to the bottom edge; content pads for the safe area
  },
  sheet: {
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: palette.border,
    marginBottom: space.lg,
  },
  header: {
    alignItems: 'center',
  },
  title: {
    marginTop: space.sm,
    textAlign: 'center',
  },
  subtitle: {
    marginTop: space.xxs,
    color: palette.textMuted,
    textAlign: 'center',
  },
  partnerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.lg,
    backgroundColor: palette.background,
  },
  partnerText: {
    flex: 1,
    marginHorizontal: space.sm,
  },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xxs,
    marginTop: 2,
  },
  muted: {
    color: palette.textMuted,
  },
  actions: {
    marginTop: space.lg,
    gap: space.xs,
  },
});
