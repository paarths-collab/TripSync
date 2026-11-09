// src/components/pooling/MatchedUserCard.tsx
import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';

import { MatchedUser } from '../../services/poolingService';
import { Avatar, Button, Card, Tag } from '../ui';
import { palette, radius, space, type, Tone } from '../../constants/theme';

interface MatchedUserCardProps {
  user: MatchedUser;
  onSendRequest: (requestId: number) => Promise<void>;
  onApprove: (connectionId: number) => Promise<void>;
  onReject: (connectionId: number) => Promise<void>;
}

const STATUS_TAG: Record<string, { label: string; tone: Tone } | undefined> = {
  pending_sent: { label: 'Request sent', tone: 'info' },
  pending_received: { label: 'Wants to share', tone: 'primary' },
  approved: { label: 'Matched', tone: 'success' },
  rejected: { label: 'Declined', tone: 'danger' },
};

export default function MatchedUserCard({ user, onSendRequest, onApprove, onReject }: MatchedUserCardProps) {
  const [loading, setLoading] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setLoading(true);
    try {
      await action();
    } catch {
      // The screen shows the error; just stop the spinner here.
    } finally {
      setLoading(false);
    }
  };

  const status = user.connection_status || 'none';
  const tag = STATUS_TAG[status];

  const renderActions = () => {
    if (status === 'none' || status === 'rejected') {
      return (
        <Button
          label={status === 'rejected' ? 'Send another request' : 'Send request'}
          icon="paper-plane"
          size="md"
          onPress={() => run(() => onSendRequest(user.request_id))}
          loading={loading}
        />
      );
    }

    if (status === 'pending_sent') {
      return <Button label="Waiting for a reply" icon="time-outline" variant="secondary" size="md" disabled />;
    }

    if (status === 'pending_received') {
      return (
        <View>
          <View style={styles.notice}>
            <Ionicons name="notifications-outline" size={16} color={palette.ink} />
            <Text style={[type.label, styles.noticeText]}>{user.full_name} asked to share a trip with you</Text>
          </View>
          <View style={styles.buttonRow}>
            <Button
              label="Accept"
              icon="checkmark"
              variant="dark"
              size="md"
              onPress={() => user.connection_id && run(() => onApprove(user.connection_id as number))}
              loading={loading}
              style={styles.rowButton}
            />
            <Button
              label="Decline"
              variant="outline"
              size="md"
              onPress={() => user.connection_id && run(() => onReject(user.connection_id as number))}
              disabled={loading}
              style={styles.rowButton}
            />
          </View>
        </View>
      );
    }

    if (status === 'approved') {
      return (
        <View style={styles.approvedRow}>
          <Ionicons name="checkmark-circle" size={18} color={palette.success} />
          <Text style={[type.label, styles.approvedText]}>You both agreed to share this trip.</Text>
        </View>
      );
    }

    return null;
  };

  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <Avatar name={user.full_name} size={48} />
        <View style={styles.headerText}>
          <Text style={type.title3} numberOfLines={1}>
            {user.full_name}
          </Text>
          {user.year_of_study ? (
            <Text style={[type.label, styles.meta]} numberOfLines={1}>
              {user.year_of_study}
            </Text>
          ) : null}
        </View>
        {tag ? <Tag label={tag.label} tone={tag.tone} /> : null}
      </View>
      <View style={styles.actions}>{renderActions()}</View>
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
  meta: {
    marginTop: 2,
    color: palette.textMuted,
  },
  actions: {
    marginTop: space.md,
  },
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: palette.yellowTint,
    paddingHorizontal: space.sm,
    paddingVertical: space.sm,
    borderRadius: radius.sm,
    marginBottom: space.sm,
  },
  noticeText: {
    flex: 1,
    color: palette.ink,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: space.xs,
  },
  rowButton: {
    flex: 1,
  },
  approvedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.sm,
    paddingHorizontal: space.sm,
    borderRadius: radius.sm,
    backgroundColor: palette.successSoft,
  },
  approvedText: {
    flex: 1,
    color: palette.success,
  },
});
