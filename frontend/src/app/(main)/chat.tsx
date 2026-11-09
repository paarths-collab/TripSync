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
  AppState,
  BackHandler,
  Keyboard,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Message, getMessages, sendMessage, markMessagesAsRead, findOrCreateConversation } from '../../services/chatService';
import { useAuth } from '../../context/AuthContext';
import { palette, space, radius, type, fonts, shadow } from '../../constants/theme';
import { Avatar, EmptyState, IconButton, LoadingState } from '../../components/ui';

const QUICK_MESSAGES = ["Where are you?", "I'm on my way", 'See you soon', 'Running late', "I'm here"];

export default function ChatScreen() {
  const router = useRouter();
  const { token, user } = useAuth();
  const userId = user?.id;
  const params = useLocalSearchParams<{
    conversationId?: string;
    partnerId: string;
    partnerName: string;
    from?: string;
  }>();

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const insets = useSafeAreaInsets();
  const flatListRef = useRef<FlatList>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const partnerId = parseInt(params.partnerId || '0');
  const partnerName = params.partnerName || 'Partner';
  const initialConversationId = params.conversationId ? parseInt(params.conversationId) : null;
  const cameFromChats = params.from === 'chats';

  // This screen lives in the tab navigator, whose back action returns to the
  // first tab. Go back to the chat list when we were opened from it; otherwise
  // go back (e.g. to the ride screen), falling back to the chat list.
  const handleBack = useCallback(() => {
    if (!cameFromChats && router.canGoBack()) {
      router.back();
    } else {
      router.navigate('/(main)/chats');
    }
  }, [cameFromChats, router]);

  // Android hardware back follows the same rule as the on-screen button.
  useFocusEffect(
    useCallback(() => {
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        handleBack();
        return true;
      });
      return () => sub.remove();
    }, [handleBack])
  );

  // Track the keyboard so the composer can sit above the floating tab bar
  // when the keyboard is closed.
  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const showSub = Keyboard.addListener(showEvent, () => setKeyboardVisible(true));
    const hideSub = Keyboard.addListener(hideEvent, () => setKeyboardVisible(false));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  // Find or create the conversation whenever the chat partner changes. The tab
  // keeps this screen mounted, so clear the previous partner's messages first.
  useEffect(() => {
    setMessages([]);
    setConversationId(null);
    setLoading(true);

    const initializeConversation = async () => {
      if (!token || !userId || !partnerId) {
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
      } catch {
        console.error('Failed to initialize conversation');
        setLoading(false);
      }
    };

    initializeConversation();
  }, [token, userId, partnerId, initialConversationId]);

  const loadMessages = useCallback(async () => {
    if (!token || !conversationId) return;

    try {
      const fetchedMessages = await getMessages(token, conversationId);
      setMessages(fetchedMessages);
      await markMessagesAsRead(token, conversationId);
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: false });
      }, 100);
    } catch {
      console.error('Failed to load messages');
    }
  }, [token, conversationId]);

  // Load messages when conversation is ready
  useEffect(() => {
    if (conversationId) {
      loadMessages();
    }
  }, [conversationId, loadMessages]);

  // Polling: fetch messages every 2 seconds while the screen is focused.
  // Stops when the screen loses focus; polls are skipped while the app is in
  // the background.
  useFocusEffect(
    useCallback(() => {
      if (!conversationId) return;

      loadMessages();

      pollingIntervalRef.current = setInterval(() => {
        if (AppState.currentState === 'active') loadMessages();
      }, 2000);

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
    } catch {
      console.error('Failed to send message');
      if (!messageText) {
        setInputText(messageContent);
      }
    } finally {
      setSending(false);
    }
  };

  const canSend = inputText.trim().length > 0 && !sending;

  const renderMessage = ({ item }: { item: Message }) => {
    if (!user) return null;
    const isMyMessage = item.sender_id === user.id;

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

  const header = (
    <View style={styles.headerWrap}>
      <View style={styles.headerCard}>
        <IconButton
          icon="chevron-back"
          label="Go back"
          size={44}
          onPress={handleBack}
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
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
        {header}
        <LoadingState label="Loading conversation…" style={styles.fill} />
      </SafeAreaView>
    );
  }

  // The tab bar is hidden on this screen, so the composer only needs the safe area.
  const composerBottom = keyboardVisible ? space.sm : Math.max(insets.bottom, space.sm);

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
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

        {/* Quick replies */}
        {inputText.length === 0 && (
          <FlatList
            data={QUICK_MESSAGES}
            horizontal
            style={styles.quickMessages}
            showsHorizontalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.quickMessagesList}
            keyExtractor={(item) => item}
            renderItem={({ item }) => (
              <Pressable
                style={({ pressed }) => [styles.quickMessagePill, (pressed || sending) && styles.quickMessagePillDim]}
                onPress={() => handleSendMessage(item)}
                disabled={sending}
                accessibilityRole="button"
                accessibilityLabel={`Send quick message: ${item}`}
              >
                <Text style={styles.quickMessageText}>{item}</Text>
              </Pressable>
            )}
          />
        )}

        {/* Composer */}
        <View style={[styles.composer, { paddingBottom: composerBottom }]}>
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
              onPress={canSend ? () => handleSendMessage() : undefined}
            />
          </View>
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
  headerWrap: {
    paddingHorizontal: space.md,
    paddingTop: space.xs,
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
  quickMessages: {
    flexGrow: 0,
  },
  quickMessagesList: {
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    gap: space.xs,
  },
  quickMessagePill: {
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    backgroundColor: palette.surface,
    borderRadius: radius.pill,
    ...shadow.card,
  },
  quickMessagePillDim: {
    opacity: 0.6,
  },
  quickMessageText: {
    ...type.label,
    fontFamily: fonts.semibold,
    color: palette.ink,
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
