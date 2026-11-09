// src/components/services/ApplicantCard.tsx

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import { ServiceApplication } from '../../services/servicesService';
import { Button, Card, Avatar, StatusPill } from '../ui';
import { palette, space, radius, type, Tone } from '../../constants/theme';

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
            label="Reject"
            variant="secondary"
            size="md"
            icon="close"
            onPress={() => onReject(application.id)}
            disabled={isUpdating}
            style={styles.actionButton}
          />
          <Button
            label="Accept"
            variant="dark"
            size="md"
            icon="checkmark"
            onPress={() => onAccept(application.id)}
            loading={isUpdating}
            style={styles.actionButton}
          />
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
    ...type.bodyStrong,
    fontSize: 16,
    color: palette.text,
  },
  date: {
    ...type.caption,
    marginTop: 2,
    color: palette.textMuted,
  },
  message: {
    marginTop: space.sm,
    padding: space.sm,
    borderRadius: radius.md,
    backgroundColor: palette.surfaceMuted,
  },
  messageText: {
    ...type.body,
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
  },
});
