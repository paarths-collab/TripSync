import React, { useState, useCallback } from 'react';
import { FlatList, StyleSheet, View, ScrollView } from 'react-native';
import { FAB, Searchbar, Chip, Text, Snackbar } from 'react-native-paper';
import { useFocusEffect, useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import ServiceCard from '../../../components/services/ServiceCard';
import { getAllServicePosts, deleteServicePost, ServicePost } from '../../../services/servicesService';
import { useDebounce } from '../../../hooks/useDebounce';
import { useAuth } from '../../../context/AuthContext';
import { EmptyState, LoadingState } from '../../../components/ui';
import { palette, space, radius, font, shadow } from '../../../constants/theme';

const POPULAR_TAGS = ['Writing', 'Research', 'Python', 'Design', 'Tutoring', 'Marketing', 'Event Help'];

export default function ServicesScreen() {
  const router = useRouter();
  const { token } = useAuth();
  const [posts, setPosts] = useState<ServicePost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  // Only the first load replaces the screen with a spinner; later searches keep
  // the search box mounted so typing is not interrupted.
  const [hasLoaded, setHasLoaded] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [snackbarVisible, setSnackbarVisible] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarType, setSnackbarType] = useState<'success' | 'error'>('success');
  const debouncedSearchQuery = useDebounce(searchQuery, 500);

  const showSnackbar = (message: string, type: 'success' | 'error' = 'success') => {
    setSnackbarMessage(message);
    setSnackbarType(type);
    setSnackbarVisible(true);
  };

  const hideSnackbar = () => setSnackbarVisible(false);

  const fetchData = useCallback(async () => {
    try {
      const fetchedPosts = await getAllServicePosts(debouncedSearchQuery, selectedTags, token);
      setPosts(fetchedPosts);
    } catch (error) {
      console.error(error);
      showSnackbar("Failed to load services. Please try again.", "error");
    } finally {
      setIsLoading(false);
      setHasLoaded(true);
    }
  }, [debouncedSearchQuery, selectedTags, token]);

  useFocusEffect(useCallback(() => { setIsLoading(true); fetchData(); }, [fetchData]));

  const handleTagPress = (tag: string) => {
    setSelectedTags(currentTags =>
      currentTags.includes(tag)
        ? currentTags.filter(t => t !== tag)
        : [...currentTags, tag]
    );
  };

  const handleDeletePost = async (postId: number) => {
    if (!token) {
      showSnackbar("You must be logged in to delete a post.", "error");
      return;
    }

    try {
      await deleteServicePost(token, postId);
      setPosts(currentPosts => currentPosts.filter(post => post.id !== postId));
      showSnackbar("✓ Post deleted successfully!", "success");
    } catch (error: any) {
      showSnackbar(`Deletion failed: ${error.message}`, "error");
    }
  };

  const ListHeader = (
    <View style={styles.header}>
      <Searchbar
        placeholder="Search by title or skill..."
        onChangeText={setSearchQuery}
        value={searchQuery}
        style={styles.searchbar}
        inputStyle={styles.searchInput}
        iconColor={palette.textMuted}
        placeholderTextColor={palette.textFaint}
        elevation={0}
      />
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipContainer}
        style={styles.chipScroll}
      >
        {POPULAR_TAGS.map(tag => {
          const isSelected = selectedTags.includes(tag);
          return (
            <Chip
              key={tag}
              mode="flat"
              selected={isSelected}
              showSelectedCheck={false}
              onPress={() => handleTagPress(tag)}
              style={[styles.chip, isSelected && styles.chipSelected]}
              textStyle={[styles.chipText, isSelected && styles.chipTextSelected]}
            >
              {tag}
            </Chip>
          );
        })}
      </ScrollView>
    </View>
  );

  if (isLoading && !hasLoaded) {
    return (
      <ScreenWrapper style={styles.center}>
        <LoadingState label="Loading services" />
      </ScreenWrapper>
    );
  }

  return (
    <ScreenWrapper>
      <FlatList
        style={styles.list}
        data={posts}
        keyExtractor={(item) => item.id.toString()}
        renderItem={({ item }) => (
          <ServiceCard post={item} onPostDeleted={handleDeletePost} />
        )}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={ListHeader}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          isLoading ? <LoadingState label="Searching" /> : <EmptyState
            icon="search-outline"
            title="No services found"
            body="Try a different search or clear some filters."
          />
        }
      />

      <FAB
        icon="plus"
        label="New service"
        color={palette.onPrimary}
        style={styles.fab}
        onPress={() => router.push('/services/create' as any)}
        aria-label="Create a new service post"
      />

      <Snackbar
        visible={snackbarVisible}
        onDismiss={hideSnackbar}
        duration={3000}
        style={[
          styles.snackbar,
          { backgroundColor: snackbarType === 'success' ? palette.success : palette.danger },
        ]}
      >
        <Text style={styles.snackbarText}>
          {snackbarMessage}
        </Text>
      </Snackbar>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: palette.background },
  header: { paddingTop: space.xs, backgroundColor: palette.background },
  searchbar: {
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    height: 48,
  },
  searchInput: { fontSize: 15, color: palette.text, minHeight: 0 },
  chipScroll: { marginHorizontal: -space.md },
  chipContainer: { paddingHorizontal: space.md, paddingTop: space.sm, paddingBottom: space.md, gap: space.xs },
  chip: {
    backgroundColor: palette.surface,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
  },
  chipSelected: { backgroundColor: palette.primary, borderColor: palette.primary },
  chipText: { color: palette.text, fontWeight: font.medium },
  chipTextSelected: { color: palette.onPrimary, fontWeight: font.semibold },
  listContent: { paddingHorizontal: space.md, paddingBottom: 96, flexGrow: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.background },
  fab: {
    position: 'absolute',
    right: space.md,
    bottom: space.md,
    backgroundColor: palette.primary,
    borderRadius: radius.lg,
    ...shadow.raised,
  },
  snackbar: { borderRadius: radius.md },
  snackbarText: { color: palette.onPrimary, fontWeight: font.semibold },
});
