// src/app/(main)/chat.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Message, getMessages, sendMessage, markMessagesAsRead, findOrCreateConversation } from '../../services/chatService';
import { useAuth } from '../../context/AuthContext';
import { palette, space, radius, font } from '../../constants/theme';
import { Avatar, EmptyState, IconButton, LoadingState } from '../../components/ui';

export default function ChatScreen() {
  const router = useRouter();
  const { token, user } = useAuth();
  const params = useLocalSearchParams<{
    conversationId?: string;
    partnerId: string;
    partnerName: string;
  }>();
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const flatListRef = useRef<FlatList>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const partnerId = parseInt(params.partnerId || '0');
  const partnerName = params.partnerName || 'Partner';
  const initialConversationId = params.conversationId ? parseInt(params.conversationId) : null;

  // Find or create conversation on mount
  useEffect(() => {
    const initializeConversation = async () => {
      if (!token || !user || !partnerId) {
        setLoading(false);
        return;
      }

      try {
        let convId = initialConversationId;
        
        // If no conversation ID provided, find or create one
        if (!convId) {
          const conversation = await findOrCreateConversation(token, partnerId);
          convId = conversation.conversation_id;
        }
        
        setConversationId(convId);
        setLoading(false);
      } catch (error) {
        console.error('Failed to initialize conversation:', error);
        setLoading(false);
      }
    };

    initializeConversation();
  }, [token, user, partnerId, initialConversationId]);

  // Load messages function
  const loadMessages = useCallback(async () => {
    if (!token || !conversationId) return;
    
    try {
      const fetchedMessages = await getMessages(token, conversationId);
      setMessages(fetchedMessages);
      await markMessagesAsRead(token, conversationId);
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: false });
      }, 100);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  }, [token, conversationId]);

  // Load messages when conversation is ready
  useEffect(() => {
    if (conversationId) {
      loadMessages();
    }
  }, [conversationId, loadMessages]);

  // Polling: Fetch messages every 2 seconds when screen is focused
  useFocusEffect(
    useCallback(() => {
      if (!conversationId) return;

      // Load immediately
      loadMessages();

      // Set up polling every 2 seconds
      pollingIntervalRef.current = setInterval(() => {
        loadMessages();
      }, 2000);

      // Cleanup on unmount or when screen loses focus
      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      };
    }, [conversationId, loadMessages])
  );

  const handleSendMessage = async (messageText?: string) => {
    const messageContent = messageText || inputText.trim();
    if (!messageContent || !token || !user || !partnerId) return;

    setInputText('');
    setSending(true);

    try {
      const newMessage = await sendMessage(token, partnerId, messageContent);
      
      // Update conversation ID if it was just created
      if (!conversationId && newMessage.conversation_id) {
        setConversationId(newMessage.conversation_id);
      }
      
      setMessages((prev) => [...prev, newMessage]);

      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    } catch (error) {
      console.error('Failed to send message:', error);
      if (!messageText) {
        setInputText(messageContent);
      }
    } finally {
      setSending(false);
    }
  };

  const quickMessages = [
    "Where are you?",
    "I'm on my way",
    "See you soon",
    "Running late",
    "I'm here"
  ];

  const canSend = inputText.trim().length > 0 && !sending;

  const renderMessage = ({ item }: { item: Message }) => {
    if (!user) return null;
    const isMyMessage = item.sender_id === user.id;

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

  const header = (
    <View style={styles.header}>
      <IconButton
        icon="chevron-back"
        label="Back to chats"
        onPress={() => router.push('/(main)/chats')}
      />
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
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
        {header}
        <LoadingState label="Loading conversation…" style={styles.fill} />
      </SafeAreaView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.fill}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
        {header}

        <FlatList
          ref={flatListRef}
          style={styles.fill}
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
              style={styles.fill}
            />
          }
        />

        {/* Quick Message Pills */}
        {inputText.length === 0 && (
          <View style={styles.quickMessagesContainer}>
            <FlatList
              data={quickMessages}
              horizontal
              showsHorizontalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={styles.quickMessagesList}
              keyExtractor={(item, index) => `quick-${index}`}
              renderItem={({ item }) => (
                <Pressable
                  style={({ pressed }) => [
                    styles.quickMessagePill,
                    (pressed || sending) && styles.quickMessagePillDim,
                  ]}
                  onPress={() => handleSendMessage(item)}
                  disabled={sending}
                  accessibilityRole="button"
                  accessibilityLabel={`Send quick message: ${item}`}
                >
                  <Text style={styles.quickMessageText}>{item}</Text>
                </Pressable>
              )}
            />
          </View>
        )}

        {/* Composer */}
        <View style={styles.composer}>
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
            onPress={canSend ? () => handleSendMessage() : undefined}
            style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          />
        </View>
      </SafeAreaView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  container: {
    flex: 1,
    backgroundColor: palette.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
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
  quickMessagesContainer: {
    paddingVertical: space.xs,
    backgroundColor: palette.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
  },
  quickMessagesList: {
    paddingHorizontal: space.md,
    gap: space.xs,
  },
  quickMessagePill: {
    paddingHorizontal: space.sm,
    paddingVertical: space.xs - 2,
    backgroundColor: palette.primarySoft,
    borderRadius: radius.pill,
  },
  quickMessagePillDim: {
    opacity: 0.6,
  },
  quickMessageText: {
    fontSize: 13,
    color: palette.primaryDark,
    fontWeight: font.medium,
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: space.md,
    paddingTop: space.xs,
    paddingBottom: space.sm,
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
