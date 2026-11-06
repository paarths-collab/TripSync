// src/app/(main)/chats.tsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, StyleSheet, FlatList, Pressable, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Text, Searchbar } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { useAuth } from '../../context/AuthContext';
import { getRecentConversations, Conversation } from '../../services/chatService';
import { useFocusEffect } from '@react-navigation/native';
import { palette, space, radius, font } from '../../constants/theme';
import { Avatar, EmptyState, LoadingState, ScreenHeader } from '../../components/ui';

interface ChatItem {
  id: number;
  connectionId: number;
  partnerId: number;
  partnerName: string;
  lastMessage: string;
  timestamp: string;
  unreadCount: number;
  isOnline: boolean;
}

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

      // Convert to ChatItem format
      const chatItems: ChatItem[] = conversations.map((conv: Conversation) => ({
        id: conv.conversation_id,
        connectionId: conv.conversation_id, // Keep for compatibility, but it's actually conversation_id
        partnerId: conv.partner.id,
        partnerName: conv.partner.full_name,
        lastMessage: conv.last_message?.content || 'No messages yet',
        timestamp: formatTimestamp(conv.last_message?.created_at),
        unreadCount: conv.unread_count,
        isOnline: false, // TODO: Add online status if needed
      }));

      setChats(chatItems);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
      isFetchingRef.current = false;
    }
  }, [token]);

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

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Refetch when screen comes into focus
  useFocusEffect(
    useCallback(() => {
      fetchConversations();

      const intervalId = setInterval(() => {
        fetchConversations();
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
        conversationId: chat.connectionId.toString(), // This is actually conversation_id
        partnerId: chat.partnerId.toString(),
        partnerName: chat.partnerName,
      },
    });
  };

  const renderChatItem = ({ item }: { item: ChatItem }) => {
    const unread = item.unreadCount > 0;
    return (
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
                <Text style={styles.unreadCount}>
                  {item.unreadCount > 99 ? '99+' : item.unreadCount}
                </Text>
              </View>
            )}
          </View>
        </View>
      </Pressable>
    );
  };

  const filteredChats = chats.filter((chat) =>
    chat.partnerName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
      <ScreenHeader title="Chats" subtitle="Messages with students you've connected with" />

      <View style={styles.searchContainer}>
        <Searchbar
          placeholder="Search by name"
          onChangeText={setSearchQuery}
          value={searchQuery}
          style={styles.searchBar}
          inputStyle={styles.searchInput}
          iconColor={palette.textMuted}
          placeholderTextColor={palette.textFaint}
        />
      </View>

      {loading ? (
        <LoadingState label="Loading conversations…" style={styles.fill} />
      ) : (
        <FlatList
          data={filteredChats}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderChatItem}
          contentContainerStyle={[
            styles.chatList,
            filteredChats.length === 0 && styles.chatListEmpty,
          ]}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={[palette.primary]}
              tintColor={palette.primary}
            />
          }
          ListEmptyComponent={
            searchQuery.trim() && chats.length > 0 ? (
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
            )
          }
        />
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
    paddingBottom: space.sm,
  },
  searchBar: {
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    elevation: 0,
    shadowOpacity: 0,
  },
  searchInput: {
    fontSize: 15,
    color: palette.text,
  },
  chatList: {
    marginHorizontal: space.lg,
    marginTop: space.xs,
    marginBottom: space.xl,
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    overflow: 'hidden',
  },
  chatListEmpty: {
    flexGrow: 1,
    justifyContent: 'center',
    backgroundColor: 'transparent',
    borderWidth: 0,
  },
  chatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    backgroundColor: palette.surface,
  },
  chatItemPressed: {
    backgroundColor: palette.surfaceMuted,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.border,
    marginLeft: space.md + 48 + space.sm,
  },
  chatContent: {
    flex: 1,
    marginLeft: space.sm,
  },
  chatHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.xxs,
  },
  chatName: {
    flex: 1,
    fontSize: 16,
    fontWeight: font.semibold,
    color: palette.text,
    marginRight: space.xs,
  },
  chatNameUnread: {
    fontWeight: font.bold,
  },
  timestamp: {
    fontSize: 12,
    color: palette.textFaint,
  },
  timestampUnread: {
    color: palette.primary,
    fontWeight: font.semibold,
  },
  chatFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  lastMessage: {
    flex: 1,
    fontSize: 14,
    color: palette.textMuted,
  },
  unreadMessage: {
    fontWeight: font.semibold,
    color: palette.text,
  },
  unreadBadge: {
    backgroundColor: palette.primary,
    borderRadius: radius.pill,
    minWidth: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: space.xs - 2,
    marginLeft: space.xs,
  },
  unreadCount: {
    color: palette.onPrimary,
    fontSize: 11,
    fontWeight: font.bold,
  },
});
