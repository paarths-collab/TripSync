// src/components/pooling/ActiveConnectionModal.tsx
import React, { useState } from 'react';
import { View, StyleSheet, Alert } from 'react-native';
import { Text, Button, Portal, Modal } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { Avatar, IconBadge, StatusPill } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

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
  onViewFullProfile
}: ActiveConnectionModalProps) {
  const [endingRide, setEndingRide] = useState(false);

  const handleEndRide = () => {
    Alert.alert(
      'End this ride?',
      'This cancels your ride agreement and disconnects you from your ride partner.',
      [
        { text: 'Keep ride', style: 'cancel' },
        {
          text: 'End ride',
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
      ]
    );
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        dismissable={false}
        style={styles.modalWrapper}
        contentContainerStyle={styles.sheet}
      >
        <View style={styles.handle} />

        <View style={styles.header}>
          <IconBadge icon="checkmark" tone="success" size={48} />
          <Text style={styles.title}>You&apos;re matched</Text>
          <Text style={styles.subtitle}>
            You both agreed to share a taxi. Sort out the pickup point and fare in chat.
          </Text>
        </View>

        <View style={styles.partnerRow}>
          <Avatar name={partner.full_name} size={52} />
          <View style={styles.partnerText}>
            <Text style={styles.partnerName} numberOfLines={1}>
              {partner.full_name}
            </Text>
            {partner.phone_number ? (
              <View style={styles.contactRow}>
                <Ionicons name="call-outline" size={14} color={palette.textMuted} />
                <Text style={styles.contactText}>{partner.phone_number}</Text>
              </View>
            ) : partner.year_of_study ? (
              <Text style={styles.contactText}>{partner.year_of_study}</Text>
            ) : null}
          </View>
          <StatusPill label="Active" tone="success" />
        </View>

        <View style={styles.actions}>
          <Button
            mode="contained"
            onPress={onStartChat}
            style={styles.button}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
            icon={() => <Ionicons name="chatbubbles-outline" size={18} color={palette.onPrimary} />}
          >
            Open chat
          </Button>

          <Button
            mode="outlined"
            onPress={onViewFullProfile}
            style={styles.button}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
          >
            View ride details
          </Button>

          <Button
            mode="text"
            onPress={handleEndRide}
            loading={endingRide}
            disabled={endingRide}
            textColor={palette.danger}
            style={styles.button}
            labelStyle={styles.buttonLabel}
          >
            End ride
          </Button>
        </View>

        <View style={styles.tips}>
          <Text style={styles.tipsTitle}>Before you head out</Text>
          <Text style={styles.tipsText}>
            {'•'} Agree on an exact pickup point{'\n'}
            {'•'} Confirm the time in chat{'\n'}
            {'•'} Decide how you&apos;ll split the fare
          </Text>
        </View>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalWrapper: {
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginTop: space.xs,
    marginBottom: space.lg,
  },
  header: {
    alignItems: 'center',
  },
  title: {
    marginTop: space.sm,
    fontSize: 22,
    fontWeight: font.bold,
    color: palette.text,
  },
  subtitle: {
    marginTop: space.xxs,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
    textAlign: 'center',
  },
  partnerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.lg,
    backgroundColor: palette.surfaceMuted,
  },
  partnerText: {
    flex: 1,
    marginHorizontal: space.sm,
  },
  partnerName: {
    fontSize: 16,
    fontWeight: font.semibold,
    color: palette.text,
  },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xxs,
    marginTop: 2,
  },
  contactText: {
    fontSize: 13,
    color: palette.textMuted,
  },
  actions: {
    marginTop: space.lg,
    gap: space.xs,
  },
  button: {
    borderRadius: radius.md,
  },
  buttonContent: {
    height: 48,
  },
  buttonLabel: {
    fontSize: 15,
    fontWeight: font.semibold,
  },
  tips: {
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: palette.primarySoft,
  },
  tipsTitle: {
    fontSize: 14,
    fontWeight: font.semibold,
    color: palette.primaryDark,
    marginBottom: space.xxs,
  },
  tipsText: {
    fontSize: 13,
    lineHeight: 20,
    color: palette.text,
  },
});
