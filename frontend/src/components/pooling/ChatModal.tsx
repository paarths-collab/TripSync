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
import { palette, space, radius, font } from '../../constants/theme';
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
    } catch (error: any) {
      console.error('Failed to load messages:', error);
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
      // Send via REST API (stores in DB)
      const newMessage = await sendMessage(token, connectionId, messageContent);
      
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
    } catch (error: any) {
      Alert.alert('Error', 'Failed to send message');
      setInputText(messageContent); // Restore message
    } finally {
      setSending(false);
    }
  };

  // Add incoming message from WebSocket
  const addIncomingMessage = (message: Message) => {
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
  };

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
      <View
        style={[
          styles.messageRow,
          isMyMessage ? styles.myMessageRow : styles.theirMessageRow,
        ]}
      >
        <View
          style={[
            styles.messageBubble,
            isMyMessage ? styles.myMessageBubble : styles.theirMessageBubble,
          ]}
        >
          <Text style={[styles.messageText, isMyMessage && styles.myMessageText]}>
            {item.content}
          </Text>
        </View>
        <Text style={[styles.timeText, isMyMessage && styles.myTimeText]}>
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
        contentContainerStyle={styles.modalContainer}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.sheet}
        >
          {/* Header */}
          <View style={[styles.header, { paddingTop: insets.top + space.sm }]}>
            <IconButton icon="chevron-back" label="Close chat" onPress={onDismiss} />
            <View style={styles.headerCenter}>
              <Avatar name={partnerName} size={40} />
              <View style={styles.headerInfo}>
                <Text style={styles.headerTitle} numberOfLines={1}>
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
            onContentSizeChange={() =>
              flatListRef.current?.scrollToEnd({ animated: true })
            }
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
            <TextInput
              placeholder="Message"
              placeholderTextColor={palette.textFaint}
              value={inputText}
              onChangeText={setInputText}
              style={styles.input}
              multiline
              maxLength={500}
              editable={!sending}
              accessibilityLabel="Message"
            />
            <IconButton
              icon="send"
              label="Send message"
              tone={canSend ? 'primary' : 'neutral'}
              size={44}
              onPress={canSend ? handleSendMessage : undefined}
              style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
            />
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    margin: 0,
    padding: 0,
  },
  sheet: {
    flex: 1,
    backgroundColor: palette.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.md,
    paddingBottom: space.sm,
    backgroundColor: palette.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: palette.border,
  },
  headerCenter: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: space.sm,
  },
  headerInfo: {
    flex: 1,
    marginLeft: space.sm,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: font.semibold,
    color: palette.text,
  },
  headerSubtitle: {
    fontSize: 12,
    color: palette.textMuted,
    marginTop: 2,
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
    paddingVertical: space.xs + 2,
    borderRadius: radius.lg,
  },
  myMessageBubble: {
    backgroundColor: palette.primary,
    borderBottomRightRadius: radius.sm / 2,
  },
  theirMessageBubble: {
    backgroundColor: palette.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    borderBottomLeftRadius: radius.sm / 2,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 21,
    color: palette.text,
  },
  myMessageText: {
    color: palette.onPrimary,
  },
  timeText: {
    fontSize: 11,
    marginTop: space.xxs,
    marginHorizontal: space.xxs,
    color: palette.textFaint,
  },
  myTimeText: {
    textAlign: 'right',
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: space.md,
    paddingTop: space.xs,
    backgroundColor: palette.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    paddingHorizontal: space.md,
    paddingTop: space.sm,
    paddingBottom: space.sm,
    backgroundColor: palette.surfaceMuted,
    borderRadius: radius.xl,
    fontSize: 15,
    color: palette.text,
  },
  sendButton: {
    marginLeft: space.xs,
  },
  sendButtonDisabled: {
    opacity: 0.6,
  },
});
