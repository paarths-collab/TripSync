// src/components/pooling/ActiveRideView.tsx
// Shown on the Rides tab while the user has an active trip match.
import React, { useState } from 'react';
import { Alert, ScrollView, StyleSheet, View } from 'react-native';
import { Modal, Portal, Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ActiveConnection } from '../../services/poolingService';
import ScreenWrapper from '../ScreenWrapper';
import { Avatar, Button, Card, IconButton, InfoRow, ScreenHeader, SectionTitle, Tag, type IconName } from '../ui';
import { layout, palette, radius, shadow, space, type } from '../../constants/theme';

interface ActiveRideViewProps {
  connection: ActiveConnection;
  onEndRide: () => Promise<void>;
  onStartChat: () => void;
}

export default function ActiveRideView({ connection, onEndRide, onStartChat }: ActiveRideViewProps) {
  const insets = useSafeAreaInsets();
  const [showProfile, setShowProfile] = useState(false);
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

  const partner = connection.partner;
  const matchedAt = new Date(connection.created_at);
  const matchedAtLabel = Number.isNaN(matchedAt.getTime())
    ? null
    : matchedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  return (
    <ScreenWrapper edges={['top']}>
      <ScreenHeader
        title="Your trip match"
        subtitle="You agreed to share a trip"
        right={<Tag label="Active" tone="success" icon="checkmark-circle" />}
      />

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Card style={styles.card}>
          <View style={styles.partnerRow}>
            <Avatar name={partner.full_name} size={56} />
            <View style={styles.partnerText}>
              <Text style={[type.caption, styles.muted]}>Trip partner</Text>
              <Text style={type.title2} numberOfLines={1}>
                {partner.full_name}
              </Text>
              {partner.year_of_study ? (
                <Text style={[type.label, styles.muted]} numberOfLines={1}>
                  {partner.year_of_study}
                </Text>
              ) : null}
            </View>
            <IconButton icon="person-outline" label="View partner details" onPress={() => setShowProfile(true)} size={44} />
          </View>

          <View style={styles.actions}>
            <Button label="Open chat" icon="chatbubbles-outline" onPress={onStartChat} />
            <Button
              label="End match"
              variant="outline"
              size="md"
              icon="close-circle-outline"
              onPress={handleEndRide}
              loading={endingRide}
              accessibilityLabel="End this trip match"
            />
          </View>
        </Card>

        {matchedAtLabel ? (
          <>
            <SectionTitle title="Trip details" style={styles.sectionTitle} />
            <Card style={styles.card}>
              <InfoRow icon="time-outline" label="Matched at" value={matchedAtLabel} />
            </Card>
          </>
        ) : null}

        <SectionTitle title="Before you head out" style={styles.sectionTitle} />
        <Card style={[styles.card, styles.tipsCard]}>
          <Tip icon="location-outline" text="Agree on an exact pickup point" />
          <Tip icon="chatbubble-ellipses-outline" text="Confirm the time in chat" />
          <Tip icon="car-outline" text="Decide which of you arranges the taxi or auto" />
          <Tip icon="wallet-outline" text="Split the fare the way you agreed" />
        </Card>
      </ScrollView>

      <Portal>
        <Modal
          visible={showProfile}
          onDismiss={() => setShowProfile(false)}
          style={styles.modalWrapper}
          contentContainerStyle={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}
        >
          <View style={styles.handle} />
          <View style={styles.sheetHeader}>
            <Text style={type.title2} accessibilityRole="header">
              Partner details
            </Text>
            <IconButton icon="close" label="Close partner details" onPress={() => setShowProfile(false)} size={40} round />
          </View>

          <View style={styles.sheetPartner}>
            <Avatar name={partner.full_name} size={64} />
            <Text style={[type.title3, styles.sheetName]}>{partner.full_name}</Text>
          </View>

          <View style={styles.details}>
            {partner.phone_number ? <InfoRow icon="call-outline" label="Phone" value={partner.phone_number} /> : null}
            {partner.email ? <InfoRow icon="mail-outline" label="Email" value={partner.email} /> : null}
            {partner.year_of_study ? <InfoRow icon="school-outline" label="Year" value={partner.year_of_study} /> : null}
            {partner.bio ? <InfoRow icon="information-circle-outline" label="Bio" value={partner.bio} /> : null}
            {!partner.phone_number && !partner.email && !partner.year_of_study && !partner.bio ? (
              <Text style={[type.body, styles.muted]}>No other details shared yet. Say hello in chat.</Text>
            ) : null}
          </View>
        </Modal>
      </Portal>
    </ScreenWrapper>
  );
}

function Tip({ icon, text }: { icon: IconName; text: string }) {
  return (
    <View style={styles.tipRow}>
      <View style={styles.tipIcon}>
        <Ionicons name={icon} size={18} color={palette.ink} />
      </View>
      <Text style={[type.body, styles.tipText]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingHorizontal: space.lg,
    paddingBottom: layout.tabBarSpace + space.md,
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
    marginHorizontal: space.md,
  },
  muted: {
    color: palette.textMuted,
  },
  actions: {
    marginTop: space.lg,
    gap: space.xs,
  },
  tipsCard: {
    gap: space.sm,
  },
  tipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tipIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: palette.yellowSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tipText: {
    flex: 1,
  },
  modalWrapper: {
    justifyContent: 'flex-end',
    marginBottom: 0, // sheet runs to the bottom edge; content pads for the safe area
  },
  sheet: {
    maxHeight: '80%',
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
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: space.sm,
  },
  sheetPartner: {
    alignItems: 'center',
    marginTop: space.md,
    marginBottom: space.sm,
  },
  sheetName: {
    marginTop: space.sm,
  },
  details: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
    paddingTop: space.xs,
  },
});
