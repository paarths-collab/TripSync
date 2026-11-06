// src/components/pooling/MatchFoundModal.tsx
import React, { useCallback } from 'react';
import { View, StyleSheet, FlatList } from 'react-native';
import { Text, Button, Portal, Modal } from 'react-native-paper';
import { MatchedUser } from '../../services/poolingService';
import MatchedUserCard from './MatchedUserCard';
import { EmptyState, IconButton, StatusPill } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

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
  const hasMatches = matches.length > 0;
  const title = hasMatches
    ? `${matches.length} ${matches.length === 1 ? 'person' : 'people'} heading your way`
    : 'No one found yet';

  const handleClose = useCallback(() => {
    console.log('MatchFoundModal - Close button pressed');
    onNewSearch();
  }, [onNewSearch]);

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={handleClose}
        dismissable={true}
        style={styles.modalWrapper}
        contentContainerStyle={styles.sheet}
      >
        <View style={styles.handle} />

        <View style={styles.header}>
          <View style={styles.headerText}>
            <StatusPill
              label={hasMatches ? 'Matched' : 'No matches'}
              tone={hasMatches ? 'success' : 'neutral'}
              icon={hasMatches ? 'people' : 'search'}
            />
            <Text style={styles.title}>{title}</Text>
            {hasMatches ? (
              <Text style={styles.subtitle}>
                Send a request to agree on sharing a taxi. You book and pay for it together.
              </Text>
            ) : null}
          </View>
          <IconButton icon="close" label="Close and start over" onPress={handleClose} size={36} />
        </View>

        {hasMatches ? (
          <FlatList
            data={matches}
            keyExtractor={(item) => item.id.toString()}
            renderItem={({ item }) => (
              <MatchedUserCard
                user={item}
                onSendRequest={onSendRequest}
                onApprove={onApprove}
                onReject={onReject}
              />
            )}
            contentContainerStyle={styles.listContent}
            style={styles.list}
            showsVerticalScrollIndicator={false}
          />
        ) : (
          <EmptyState
            icon="people-outline"
            title="No students on this route right now"
            body="Try searching again in a few minutes."
            style={styles.empty}
          />
        )}

        <View style={styles.footer}>
          <Button
            mode="outlined"
            onPress={onNewSearch}
            style={styles.button}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
          >
            Start a new search
          </Button>
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
    maxHeight: '85%',
    backgroundColor: palette.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
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
    fontSize: 20,
    lineHeight: 26,
    fontWeight: font.bold,
    color: palette.text,
  },
  subtitle: {
    marginTop: space.xxs,
    fontSize: 14,
    lineHeight: 20,
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
});
