// src/components/pooling/ChatModal.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Alert,
  TextInput,
} from 'react-native';
import { Text, Portal, Modal } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Message, getMessages, sendMessage, markMessagesAsRead } from '../../services/chatService';
import { palette, space, radius, type, fonts, shadow } from '../../constants/theme';
import { Avatar, EmptyState, IconButton } from '../ui';

interface ChatModalProps {
  visible: boolean;
  onDismiss: () => void;
  connectionId: number;
  partnerId: number;
  partnerName: string;
  currentUserId: number;
  token: string;
  onSendMessageViaWebSocket?: (message: any) => void;
}

export default function ChatModal({
  visible,
  onDismiss,
  connectionId,
  partnerId,
  partnerName,
  currentUserId,
  token,
  onSendMessageViaWebSocket,
}: ChatModalProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const insets = useSafeAreaInsets();

  // Load messages when modal opens
  const loadMessages = useCallback(async () => {
    try {
      const fetchedMessages = await getMessages(token, connectionId);
      setMessages(fetchedMessages);

      // Mark messages as read
      await markMessagesAsRead(token, connectionId);

      // Scroll to bottom
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    } catch {
      console.error('Failed to load messages');
    }
  }, [token, connectionId]);

  useEffect(() => {
    if (visible) {
      loadMessages();
    }
  }, [visible, loadMessages]);

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;

    const messageContent = inputText.trim();
    setInputText('');
    setSending(true);

    try {
      // Send via REST API (stores in DB). The API addresses messages by
      // receiver, so this must be the partner's user id.
      const newMessage = await sendMessage(token, partnerId, messageContent);

      // Add to local state
      setMessages((prev) => [...prev, newMessage]);

      // Send via WebSocket for real-time delivery
      if (onSendMessageViaWebSocket) {
        onSendMessageViaWebSocket({
          type: 'chat_message',
          connection_id: connectionId,
          content: messageContent,
          receiver_id: partnerId,
          created_at: new Date().toISOString(),
        });
      }

      // Scroll to bottom
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    } catch {
      Alert.alert("Couldn't send", 'Your message was not sent. Check your connection and try again.');
      setInputText(messageContent); // Restore message
    } finally {
      setSending(false);
    }
  };

  // Add incoming message from WebSocket
  const addIncomingMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      // Avoid duplicates
      if (prev.some((m) => m.id === message.id)) {
        return prev;
      }
      return [...prev, message];
    });

    setTimeout(() => {
      flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, []);

  // Expose method to parent
  useEffect(() => {
    if (visible) {
      (ChatModal as any).addIncomingMessage = addIncomingMessage;
    }
  }, [visible, addIncomingMessage]);

  const canSend = inputText.trim().length > 0 && !sending;

  const renderMessage = ({ item }: { item: Message }) => {
    const isMyMessage = item.sender_id === currentUserId;

    return (
      <View style={[styles.messageRow, isMyMessage ? styles.myMessageRow : styles.theirMessageRow]}>
        <View style={[styles.messageBubble, isMyMessage ? styles.myMessageBubble : styles.theirMessageBubble]}>
          <Text style={styles.messageText}>{item.content}</Text>
        </View>
        <Text style={styles.timeText}>
          {new Date(item.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </Text>
      </View>
    );
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        style={styles.modalWrapper}
        contentContainerStyle={styles.modalContainer}
      >
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.sheet}>
          {/* Header */}
          <View style={[styles.headerWrap, { paddingTop: insets.top + space.xs }]}>
            <View style={styles.headerCard}>
              <IconButton
                icon="chevron-back"
                label="Close chat"
                size={44}
                onPress={onDismiss}
                style={styles.backButton}
              />
              <Avatar name={partnerName} size={44} />
              <View style={styles.headerInfo}>
                <Text style={styles.headerTitle} numberOfLines={1} accessibilityRole="header">
                  {partnerName}
                </Text>
                <Text style={styles.headerSubtitle} numberOfLines={1}>
                  Ride chat
                </Text>
              </View>
            </View>
          </View>

          {/* Messages */}
          <FlatList
            ref={flatListRef}
            style={styles.list}
            data={messages}
            keyExtractor={(item) => item.id.toString()}
            renderItem={renderMessage}
            contentContainerStyle={styles.messagesList}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="interactive"
            onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
            ListEmptyComponent={
              <EmptyState
                icon="chatbubbles-outline"
                title="No messages yet"
                body={`Say hi to ${partnerName} and sort out where to meet.`}
                style={styles.list}
              />
            }
          />

          {/* Composer */}
          <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, space.sm) }]}>
            <View style={styles.inputPill}>
              <TextInput
                placeholder="Message"
                placeholderTextColor={palette.textMuted}
                value={inputText}
                onChangeText={setInputText}
                style={styles.input}
                multiline
                maxLength={500}
                editable={!sending}
                accessibilityLabel="Message"
              />
            </View>
            <View style={!canSend && styles.sendDisabled} pointerEvents={canSend ? 'auto' : 'none'}>
              <IconButton
                icon="send"
                label="Send message"
                tone="dark"
                size={48}
                onPress={canSend ? handleSendMessage : undefined}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  // Full screen: the header and composer pad for the safe area themselves.
  modalWrapper: {
    marginTop: 0,
    marginBottom: 0,
  },
  modalContainer: {
    flex: 1,
    margin: 0,
    padding: 0,
  },
  sheet: {
    flex: 1,
    backgroundColor: palette.background,
  },
  headerWrap: {
    paddingHorizontal: space.md,
    paddingBottom: space.xs,
  },
  headerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: space.xs,
    paddingRight: space.md,
    backgroundColor: palette.surface,
    borderRadius: radius.xl,
    ...shadow.card,
  },
  backButton: {
    backgroundColor: palette.surfaceMuted,
    marginRight: space.sm,
  },
  headerInfo: {
    flex: 1,
    marginLeft: space.sm,
  },
  headerTitle: {
    ...type.title3,
    color: palette.text,
  },
  headerSubtitle: {
    ...type.caption,
    color: palette.textMuted,
  },
  list: {
    flex: 1,
  },
  messagesList: {
    paddingHorizontal: space.md,
    paddingTop: space.md,
    paddingBottom: space.xs,
    flexGrow: 1,
  },
  messageRow: {
    marginBottom: space.sm,
    maxWidth: '80%',
  },
  myMessageRow: {
    alignSelf: 'flex-end',
    alignItems: 'flex-end',
  },
  theirMessageRow: {
    alignSelf: 'flex-start',
    alignItems: 'flex-start',
  },
  messageBubble: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.lg,
  },
  myMessageBubble: {
    backgroundColor: palette.yellowSoft,
    borderBottomRightRadius: 6,
  },
  theirMessageBubble: {
    backgroundColor: palette.surface,
    borderBottomLeftRadius: 6,
    ...shadow.card,
  },
  messageText: {
    ...type.body,
    color: palette.ink,
  },
  timeText: {
    ...type.caption,
    fontSize: 11,
    marginTop: space.xxs,
    marginHorizontal: space.xxs,
    color: palette.textFaint,
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: space.md,
    paddingTop: space.xs,
    gap: space.xs,
  },
  inputPill: {
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
    backgroundColor: palette.surface,
    borderRadius: radius.xl,
    ...shadow.card,
  },
  input: {
    maxHeight: 120,
    paddingHorizontal: space.lg,
    paddingTop: 13,
    paddingBottom: 13,
    fontFamily: fonts.regular,
    fontSize: 15,
    color: palette.text,
  },
  sendDisabled: {
    opacity: 0.4,
  },
});
