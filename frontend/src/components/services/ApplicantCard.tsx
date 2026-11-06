// src/components/services/ApplicantCard.tsx

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { ServiceApplication } from '../../services/servicesService';
import { Card, Avatar, StatusPill } from '../ui';
import { palette, space, radius, font, Tone } from '../../constants/theme';

interface ApplicantCardProps {
  application: ServiceApplication;
  onAccept: (applicationId: number) => void;
  onReject: (applicationId: number) => void;
  /** Disables the actions and shows a spinner on Accept while a status update is in flight. */
  isUpdating?: boolean;
}

const applicationStatusMeta: Record<ServiceApplication['status'], { label: string; tone: Tone; icon: 'time-outline' | 'checkmark-circle' | 'close-circle' }> = {
  pending: { label: 'Pending', tone: 'warning', icon: 'time-outline' },
  accepted: { label: 'Accepted', tone: 'success', icon: 'checkmark-circle' },
  rejected: { label: 'Rejected', tone: 'danger', icon: 'close-circle' },
};

export default function ApplicantCard({ application, onAccept, onReject, isUpdating = false }: ApplicantCardProps) {
  const { applicant, status, cover_letter } = application;
  const meta = applicationStatusMeta[status] ?? { label: status, tone: 'neutral' as Tone, icon: 'time-outline' as const };

  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <Avatar name={applicant.full_name} size={44} />
        <View style={styles.headerText}>
          <Text style={styles.name} numberOfLines={1}>{applicant.full_name}</Text>
          {!!application.application_date && (
            <Text style={styles.date}>
              Applied {new Date(application.application_date).toLocaleDateString()}
            </Text>
          )}
        </View>
        <StatusPill label={meta.label} tone={meta.tone} icon={meta.icon} />
      </View>

      {!!cover_letter && (
        <View style={styles.message}>
          <Text style={styles.messageText}>{cover_letter}</Text>
        </View>
      )}

      {status === 'pending' && (
        <View style={styles.actions}>
          <Button
            mode="outlined"
            onPress={() => onReject(application.id)}
            disabled={isUpdating}
            textColor={palette.danger}
            style={[styles.actionButton, styles.rejectButton]}
            contentStyle={styles.actionContent}
            labelStyle={styles.actionLabel}
            icon="close"
          >
            Reject
          </Button>
          <Button
            mode="contained"
            onPress={() => onAccept(application.id)}
            disabled={isUpdating}
            loading={isUpdating}
            buttonColor={palette.primary}
            textColor={palette.onPrimary}
            style={styles.actionButton}
            contentStyle={styles.actionContent}
            labelStyle={styles.actionLabel}
            icon="check"
          >
            Accept
          </Button>
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    marginBottom: space.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  headerText: {
    flex: 1,
    marginHorizontal: space.sm,
  },
  name: {
    fontSize: 16,
    fontWeight: font.semibold,
    color: palette.text,
  },
  date: {
    marginTop: 2,
    fontSize: 12,
    color: palette.textMuted,
  },
  message: {
    marginTop: space.sm,
    padding: space.sm,
    borderRadius: radius.md,
    backgroundColor: palette.surfaceMuted,
  },
  messageText: {
    fontSize: 14,
    lineHeight: 20,
    color: palette.text,
  },
  actions: {
    flexDirection: 'row',
    gap: space.xs,
    marginTop: space.md,
  },
  actionButton: {
    flex: 1,
    borderRadius: radius.md,
  },
  rejectButton: {
    borderColor: palette.danger,
  },
  actionContent: {
    paddingVertical: 2,
  },
  actionLabel: {
    fontWeight: font.semibold,
  },
});
