// src/components/pooling/MatchFoundModal.tsx
import React from 'react';
import { FlatList, StyleSheet, View } from 'react-native';
import { Modal, Portal, Text } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MatchedUser } from '../../services/poolingService';
import MatchedUserCard from './MatchedUserCard';
import { Button, EmptyState, IconButton, Tag } from '../ui';
import { palette, radius, shadow, space, type } from '../../constants/theme';

interface MatchFoundModalProps {
  visible: boolean;
  matches: MatchedUser[];
  onNewSearch: () => void;
  onSendRequest: (requestId: number) => Promise<void>;
  onApprove: (connectionId: number) => Promise<void>;
  onReject: (connectionId: number) => Promise<void>;
}

export default function MatchFoundModal({
  visible,
  matches,
  onNewSearch,
  onSendRequest,
  onApprove,
  onReject,
}: MatchFoundModalProps) {
  const insets = useSafeAreaInsets();
  const hasMatches = matches.length > 0;
  const title = hasMatches
    ? `${matches.length} ${matches.length === 1 ? 'student' : 'students'} going your way`
    : 'No one found yet';

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onNewSearch}
        dismissable
        style={styles.modalWrapper}
        contentContainerStyle={[styles.sheet, { paddingBottom: insets.bottom + space.md }]}
      >
        <View style={styles.handle} />

        <View style={styles.header}>
          <View style={styles.headerText}>
            <Tag
              label={hasMatches ? 'Matches' : 'No matches'}
              tone={hasMatches ? 'brand' : 'neutral'}
              icon={hasMatches ? 'people' : 'search'}
            />
            <Text style={[type.title2, styles.title]} accessibilityRole="header">
              {title}
            </Text>
            {hasMatches ? (
              <Text style={[type.label, styles.subtitle]}>
                Send a request to agree on sharing the trip. You arrange and pay for travel together.
              </Text>
            ) : null}
          </View>
          <IconButton icon="close" label="Close and start over" onPress={onNewSearch} size={40} round />
        </View>

        {hasMatches ? (
          <FlatList
            data={matches}
            keyExtractor={(item) => item.id.toString()}
            renderItem={({ item }) => (
              <MatchedUserCard user={item} onSendRequest={onSendRequest} onApprove={onApprove} onReject={onReject} />
            )}
            contentContainerStyle={styles.listContent}
            style={styles.list}
            showsVerticalScrollIndicator={false}
          />
        ) : (
          <EmptyState
            icon="people-outline"
            title="No students on this route right now"
            body="Try again in a few minutes. New requests appear as students search."
            style={styles.empty}
          />
        )}

        <View style={styles.footer}>
          <Button label="Start a new search" variant="outline" size="md" onPress={onNewSearch} />
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
    maxHeight: '88%',
    backgroundColor: palette.background,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
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
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.sm,
  },
  headerText: {
    flex: 1,
    marginRight: space.sm,
  },
  title: {
    marginTop: space.xs,
  },
  subtitle: {
    marginTop: space.xxs,
    color: palette.textMuted,
  },
  list: {
    flexGrow: 0,
  },
  listContent: {
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
  },
  empty: {
    paddingVertical: space.xl,
  },
  footer: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
  },
});
