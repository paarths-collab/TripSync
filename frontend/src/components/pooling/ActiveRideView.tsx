// src/components/pooling/ActiveRideView.tsx
import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, Alert } from 'react-native';
import { Text, Button, Portal, Modal } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { ActiveConnection } from '../../services/poolingService';
import ScreenWrapper from '../ScreenWrapper';
import {
  Avatar,
  Card,
  IconButton,
  InfoRow,
  ScreenHeader,
  SectionTitle,
  StatusPill,
} from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface ActiveRideViewProps {
  connection: ActiveConnection;
  onEndRide: () => Promise<void>;
  onStartChat: () => void;
}

export default function ActiveRideView({ connection, onEndRide, onStartChat }: ActiveRideViewProps) {
  const [showProfile, setShowProfile] = useState(false);
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

  const partner = connection.partner;

  return (
    <ScreenWrapper edges={['top']}>
      <ScreenHeader
        title="Your ride"
        subtitle="You've agreed to share a taxi"
        right={<StatusPill label="Active" tone="success" icon="checkmark-circle" />}
      />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Card style={styles.card}>
          <View style={styles.partnerRow}>
            <Avatar name={partner.full_name} size={56} />
            <View style={styles.partnerText}>
              <Text style={styles.eyebrow}>Ride partner</Text>
              <Text style={styles.partnerName} numberOfLines={1}>
                {partner.full_name}
              </Text>
              {partner.year_of_study ? (
                <Text style={styles.partnerMeta} numberOfLines={1}>
                  {partner.year_of_study}
                </Text>
              ) : null}
            </View>
          </View>

          <Button
            mode="text"
            onPress={() => setShowProfile(true)}
            style={styles.profileLink}
            labelStyle={styles.profileLinkLabel}
            icon={() => <Ionicons name="person-circle-outline" size={18} color={palette.primary} />}
          >
            View profile
          </Button>

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
              onPress={handleEndRide}
              loading={endingRide}
              disabled={endingRide}
              textColor={palette.danger}
              style={[styles.button, styles.dangerOutline]}
              contentStyle={styles.buttonContent}
              labelStyle={styles.buttonLabel}
              icon={() => <Ionicons name="close-circle-outline" size={18} color={palette.danger} />}
            >
              End ride
            </Button>
          </View>
        </Card>

        <SectionTitle title="Ride details" style={styles.sectionTitle} />
        <Card style={styles.card}>
          <InfoRow
            icon="time-outline"
            label="Matched at"
            value={new Date(connection.created_at).toLocaleTimeString()}
          />
        </Card>

        <SectionTitle title="Before you head out" style={styles.sectionTitle} />
        <Card style={[styles.card, styles.tipsCard]}>
          <Tip icon="location-outline" text="Agree on an exact pickup point" />
          <Tip icon="chatbubble-ellipses-outline" text="Confirm the time in chat" />
          <Tip icon="car-outline" text="Decide which of you books the taxi" />
          <Tip icon="wallet-outline" text="Split the fare the way you agreed" />
        </Card>
      </ScrollView>

      {/* Partner profile sheet */}
      <Portal>
        <Modal
          visible={showProfile}
          onDismiss={() => setShowProfile(false)}
          style={styles.modalWrapper}
          contentContainerStyle={styles.sheet}
        >
          <View style={styles.handle} />
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>Partner details</Text>
            <IconButton
              icon="close"
              label="Close partner details"
              onPress={() => setShowProfile(false)}
              size={36}
            />
          </View>

          <View style={styles.sheetPartner}>
            <Avatar name={partner.full_name} size={64} />
            <Text style={styles.sheetName}>{partner.full_name}</Text>
          </View>

          <View style={styles.details}>
            {partner.phone_number && (
              <InfoRow icon="call-outline" label="Phone" value={partner.phone_number} />
            )}
            {partner.email && (
              <InfoRow icon="mail-outline" label="Email" value={partner.email} />
            )}
            {partner.year_of_study && (
              <InfoRow icon="school-outline" label="Year" value={partner.year_of_study} />
            )}
            {partner.bio && (
              <InfoRow icon="information-circle-outline" label="Bio" value={partner.bio} />
            )}
          </View>
        </Modal>
      </Portal>
    </ScreenWrapper>
  );
}

function Tip({ icon, text }: { icon: React.ComponentProps<typeof Ionicons>['name']; text: string }) {
  return (
    <View style={styles.tipRow}>
      <Ionicons name={icon} size={18} color={palette.primary} />
      <Text style={styles.tipText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xxl,
  },
  card: {
    marginBottom: space.md,
  },
  sectionTitle: {
    marginTop: space.xs,
  },
  partnerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  partnerText: {
    flex: 1,
    marginLeft: space.md,
  },
  eyebrow: {
    fontSize: 12,
    color: palette.textMuted,
    marginBottom: 2,
  },
  partnerName: {
    fontSize: 18,
    fontWeight: font.bold,
    color: palette.text,
  },
  partnerMeta: {
    marginTop: 2,
    fontSize: 13,
    color: palette.textMuted,
  },
  profileLink: {
    alignSelf: 'flex-start',
    marginTop: space.xs,
    marginLeft: -space.xs,
  },
  profileLinkLabel: {
    fontSize: 14,
    fontWeight: font.semibold,
  },
  actions: {
    marginTop: space.sm,
    gap: space.sm,
  },
  button: {
    borderRadius: radius.md,
  },
  dangerOutline: {
    borderColor: palette.danger,
  },
  buttonContent: {
    height: 50,
  },
  buttonLabel: {
    fontSize: 15,
    fontWeight: font.semibold,
  },
  tipsCard: {
    gap: space.sm,
  },
  tipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tipText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
    color: palette.text,
  },
  modalWrapper: {
    justifyContent: 'flex-end',
  },
  sheet: {
    maxHeight: '80%',
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
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: space.sm,
  },
  sheetTitle: {
    fontSize: 20,
    fontWeight: font.bold,
    color: palette.text,
  },
  sheetPartner: {
    alignItems: 'center',
    marginTop: space.md,
    marginBottom: space.sm,
  },
  sheetName: {
    marginTop: space.sm,
    fontSize: 18,
    fontWeight: font.semibold,
    color: palette.text,
  },
  details: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
    paddingTop: space.xs,
  },
});
