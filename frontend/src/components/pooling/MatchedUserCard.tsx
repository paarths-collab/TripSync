// src/components/pooling/MatchedUserCard.tsx
import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { MatchedUser } from '../../services/poolingService';
import { Avatar, Card, StatusPill } from '../ui';
import { palette, space, radius, font, Tone } from '../../constants/theme';

interface MatchedUserCardProps {
  user: MatchedUser;
  onSendRequest: (requestId: number) => Promise<void>;
  onApprove: (connectionId: number) => Promise<void>;
  onReject: (connectionId: number) => Promise<void>;
}

const STATUS_PILL: Record<string, { label: string; tone: Tone } | undefined> = {
  pending_sent: { label: 'Request sent', tone: 'info' },
  pending_received: { label: 'Wants to share', tone: 'warning' },
  approved: { label: 'Matched', tone: 'success' },
  rejected: { label: 'Declined', tone: 'danger' },
};

export default function MatchedUserCard({ user, onSendRequest, onApprove, onReject }: MatchedUserCardProps) {
  const [loading, setLoading] = useState(false);

  const handleSendRequest = async () => {
    console.log('MatchedUserCard - Send request button pressed for user:', user.id, 'request_id:', user.request_id);
    setLoading(true);
    try {
      await onSendRequest(user.request_id);
      console.log('MatchedUserCard - Request sent successfully');
    } catch (error) {
      console.error('MatchedUserCard - Error sending request:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!user.connection_id) return;
    setLoading(true);
    try {
      await onApprove(user.connection_id);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!user.connection_id) return;
    setLoading(true);
    try {
      await onReject(user.connection_id);
    } finally {
      setLoading(false);
    }
  };

  const status = user.connection_status || 'none';
  const pill = STATUS_PILL[status];

  const renderActions = () => {
    if (status === 'none' || status === 'rejected') {
      return (
        <Button
          mode="contained"
          onPress={handleSendRequest}
          loading={loading}
          disabled={loading}
          style={styles.button}
          contentStyle={styles.buttonContent}
          labelStyle={styles.buttonLabel}
          icon={() => <Ionicons name="paper-plane" size={16} color={palette.onPrimary} />}
        >
          Send request
        </Button>
      );
    }

    if (status === 'pending_sent') {
      return (
        <Button
          mode="outlined"
          disabled
          style={styles.button}
          contentStyle={styles.buttonContent}
          labelStyle={styles.buttonLabel}
          icon={() => <Ionicons name="time-outline" size={16} color={palette.textMuted} />}
        >
          Waiting for a reply
        </Button>
      );
    }

    if (status === 'pending_received') {
      return (
        <View>
          <View style={styles.notice}>
            <Ionicons name="notifications-outline" size={16} color={palette.primaryDark} />
            <Text style={styles.noticeText}>
              {user.full_name} asked to share a ride with you
            </Text>
          </View>
          <View style={styles.buttonRow}>
            <Button
              mode="contained"
              onPress={handleApprove}
              loading={loading}
              disabled={loading}
              style={[styles.button, styles.rowButton]}
              contentStyle={styles.buttonContent}
              labelStyle={styles.buttonLabel}
              icon={() => <Ionicons name="checkmark" size={16} color={palette.onPrimary} />}
            >
              Accept
            </Button>
            <Button
              mode="outlined"
              onPress={handleReject}
              loading={loading}
              disabled={loading}
              textColor={palette.danger}
              style={[styles.button, styles.rowButton, styles.dangerOutline]}
              contentStyle={styles.buttonContent}
              labelStyle={styles.buttonLabel}
              icon={() => <Ionicons name="close" size={16} color={palette.danger} />}
            >
              Decline
            </Button>
          </View>
        </View>
      );
    }

    if (status === 'approved') {
      return (
        <View style={styles.approvedRow}>
          <Ionicons name="checkmark-circle" size={18} color={palette.success} />
          <Text style={styles.approvedText}>You both agreed to share this ride.</Text>
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
          <Text style={styles.name} numberOfLines={1}>
            {user.full_name}
          </Text>
          {user.year_of_study ? (
            <Text style={styles.meta} numberOfLines={1}>
              {user.year_of_study}
            </Text>
          ) : null}
        </View>
        {pill ? <StatusPill label={pill.label} tone={pill.tone} /> : null}
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
  name: {
    fontSize: 16,
    fontWeight: font.semibold,
    color: palette.text,
  },
  meta: {
    marginTop: 2,
    fontSize: 13,
    color: palette.textMuted,
  },
  actions: {
    marginTop: space.md,
  },
  button: {
    borderRadius: radius.md,
  },
  buttonContent: {
    height: 44,
  },
  buttonLabel: {
    fontSize: 14,
    fontWeight: font.semibold,
  },
  dangerOutline: {
    borderColor: palette.danger,
  },
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    backgroundColor: palette.primarySoft,
    paddingHorizontal: space.sm,
    paddingVertical: space.sm,
    borderRadius: radius.sm,
    marginBottom: space.sm,
  },
  noticeText: {
    flex: 1,
    fontSize: 13,
    fontWeight: font.medium,
    color: palette.primaryDark,
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
    fontSize: 14,
    fontWeight: font.medium,
    color: palette.success,
  },
});
