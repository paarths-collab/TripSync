// src/app/(main)/chats.tsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, AppState } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Text } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { getRecentConversations, Conversation } from '../../services/chatService';
import { useFocusEffect } from '@react-navigation/native';
import { palette, space, radius, type, fonts, layout } from '../../constants/theme';
import { Avatar, Card, Divider, EmptyState, LoadingState, ScreenHeader, SearchBar } from '../../components/ui';

interface ChatItem {
  id: number;
  connectionId: number;
  partnerId: number;
  partnerName: string;
  lastMessage: string;
  timestamp: string;
  unreadCount: number;
}

const formatTimestamp = (timestamp: string | undefined) => {
  if (!timestamp) return '';

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
};

export default function ChatsScreen() {
  const router = useRouter();
  const { token } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [chats, setChats] = useState<ChatItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const isFetchingRef = useRef(false);

  const fetchConversations = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    if (isFetchingRef.current) {
      return;
    }

    isFetchingRef.current = true;

    try {
      const conversations = await getRecentConversations(token);

      const chatItems: ChatItem[] = conversations.map((conv: Conversation) => ({
        id: conv.conversation_id,
        connectionId: conv.conversation_id, // Kept for compatibility; this is the conversation id
        partnerId: conv.partner.id,
        partnerName: conv.partner.full_name,
        lastMessage: conv.last_message?.content || 'No messages yet',
        timestamp: formatTimestamp(conv.last_message?.created_at),
        unreadCount: conv.unread_count,
      }));

      setChats(chatItems);
    } catch {
      console.error('Failed to fetch conversations');
    } finally {
      setLoading(false);
      setRefreshing(false);
      isFetchingRef.current = false;
    }
  }, [token]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Refetch when the screen is focused, and poll while it stays focused.
  // Polls are skipped while the app is in the background.
  useFocusEffect(
    useCallback(() => {
      fetchConversations();

      const intervalId = setInterval(() => {
        if (AppState.currentState === 'active') fetchConversations();
      }, 2000);

      return () => {
        clearInterval(intervalId);
      };
    }, [fetchConversations])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchConversations();
  };

  const handleChatPress = (chat: ChatItem) => {
    router.push({
      pathname: '/(main)/chat',
      params: {
        conversationId: chat.connectionId.toString(), // This is the conversation id
        partnerId: chat.partnerId.toString(),
        partnerName: chat.partnerName,
        from: 'chats', // lets the chat screen's back button return here
      },
    });
  };

  const renderChatItem = (item: ChatItem, index: number) => {
    const unread = item.unreadCount > 0;
    return (
      <React.Fragment key={item.id}>
        {index > 0 ? <Divider style={styles.separator} /> : null}
        <Pressable
          style={({ pressed }) => [styles.chatItem, pressed && styles.chatItemPressed]}
          onPress={() => handleChatPress(item)}
          accessibilityRole="button"
          accessibilityLabel={`Open chat with ${item.partnerName}${unread ? `, ${item.unreadCount} unread` : ''}`}
        >
          <Avatar name={item.partnerName} size={48} />

          <View style={styles.chatContent}>
            <View style={styles.chatHeader}>
              <Text style={[styles.chatName, unread && styles.chatNameUnread]} numberOfLines={1}>
                {item.partnerName}
              </Text>
              <Text style={[styles.timestamp, unread && styles.timestampUnread]}>{item.timestamp}</Text>
            </View>
            <View style={styles.chatFooter}>
              <Text style={[styles.lastMessage, unread && styles.unreadMessage]} numberOfLines={1}>
                {item.lastMessage}
              </Text>
              {unread && (
                <View style={styles.unreadBadge}>
                  <Text style={styles.unreadCount}>{item.unreadCount > 99 ? '99+' : item.unreadCount}</Text>
                </View>
              )}
            </View>
          </View>
        </Pressable>
      </React.Fragment>
    );
  };

  const filteredChats = chats.filter((chat) =>
    chat.partnerName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
      <ScreenHeader title="Chats" subtitle="Messages with students you've connected with" />

      <View style={styles.searchContainer}>
        <SearchBar placeholder="Search by name" value={searchQuery} onChangeText={setSearchQuery} />
      </View>

      {loading ? (
        <LoadingState label="Loading conversations…" style={styles.fill} />
      ) : (
        <ScrollView
          style={styles.fill}
          contentContainerStyle={[styles.listContent, filteredChats.length === 0 && styles.listContentEmpty]}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={[palette.ink]}
              tintColor={palette.ink}
            />
          }
        >
          {filteredChats.length > 0 ? (
            <Card padded={false} style={styles.listCard}>
              {filteredChats.map(renderChatItem)}
            </Card>
          ) : searchQuery.trim() && chats.length > 0 ? (
            <EmptyState
              icon="search-outline"
              title="No matches"
              body={`No conversations match “${searchQuery.trim()}”.`}
            />
          ) : (
            <EmptyState
              icon="chatbubbles-outline"
              title="No conversations yet"
              body="When you connect with another student for a ride, your chat with them will show up here."
            />
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: palette.background,
  },
  fill: {
    flex: 1,
  },
  searchContainer: {
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
    paddingBottom: space.md,
  },
  listContent: {
    paddingHorizontal: space.lg,
    paddingTop: space.xxs,
    // Keeps the last row scrollable above the floating tab bar.
    paddingBottom: layout.tabBarSpace,
  },
  listContentEmpty: {
    flexGrow: 1,
    justifyContent: 'center',
  },
  listCard: {
    paddingVertical: space.xs,
  },
  chatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: space.xs,
    paddingHorizontal: space.xs,
    paddingVertical: space.sm,
    borderRadius: radius.lg,
  },
  chatItemPressed: {
    backgroundColor: palette.surfaceMuted,
  },
  separator: {
    marginLeft: space.md + 48 + space.sm,
    marginRight: space.md,
  },
  chatContent: {
    flex: 1,
    marginLeft: space.sm,
  },
  chatHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  chatName: {
    ...type.bodyStrong,
    flex: 1,
    fontSize: 16,
    color: palette.text,
    marginRight: space.xs,
  },
  chatNameUnread: {
    fontFamily: fonts.bold,
  },
  timestamp: {
    ...type.caption,
    color: palette.textFaint,
  },
  timestampUnread: {
    color: palette.ink,
    fontFamily: fonts.semibold,
  },
  chatFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  lastMessage: {
    ...type.label,
    fontFamily: fonts.regular,
    fontSize: 14,
    flex: 1,
    color: palette.textMuted,
  },
  unreadMessage: {
    fontFamily: fonts.semibold,
    color: palette.text,
  },
  unreadBadge: {
    backgroundColor: palette.yellow,
    borderRadius: radius.pill,
    minWidth: 22,
    height: 22,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
    marginLeft: space.xs,
  },
  unreadCount: {
    ...type.caption,
    fontSize: 11,
    lineHeight: 14,
    fontFamily: fonts.bold,
    color: palette.onYellow,
  },
});
