import React, { useState, useCallback } from 'react';
import { FlatList, StyleSheet, View, ScrollView, Pressable } from 'react-native';
import { Text, Snackbar } from 'react-native-paper';
import { useFocusEffect, useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import ServiceCard from '../../../components/services/ServiceCard';
import { getAllServicePosts, deleteServicePost, ServicePost } from '../../../services/servicesService';
import { useDebounce } from '../../../hooks/useDebounce';
import { useAuth } from '../../../context/AuthContext';
import { Button, EmptyState, IconButton, LoadingState, ScreenHeader, SearchBar } from '../../../components/ui';
import { palette, space, radius, type, fonts, shadow, layout } from '../../../constants/theme';

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
      showSnackbar("Couldn't load services. Please try again.", 'error');
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
      showSnackbar('You must be logged in to delete a post.', 'error');
      return;
    }

    try {
      await deleteServicePost(token, postId);
      setPosts(currentPosts => currentPosts.filter(post => post.id !== postId));
      showSnackbar('Post deleted.', 'success');
    } catch (error: any) {
      showSnackbar(`Couldn't delete the post: ${error.message}`, 'error');
    }
  };

  const header = (
    <ScreenHeader
      title="Services"
      subtitle="Get help with projects, or lend a hand"
      right={
        <IconButton
          icon="briefcase-outline"
          label="My services"
          onPress={() => router.push('/services/dashboard' as any)}
        />
      }
    />
  );

  const ListHeader = (
    <View style={styles.listHeader}>
      <SearchBar
        placeholder="Search by title or skill"
        value={searchQuery}
        onChangeText={setSearchQuery}
      />
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.chipContainer}
        style={styles.chipScroll}
      >
        {POPULAR_TAGS.map(tag => {
          const isSelected = selectedTags.includes(tag);
          return (
            <Pressable
              key={tag}
              onPress={() => handleTagPress(tag)}
              accessibilityRole="button"
              accessibilityState={{ selected: isSelected }}
              accessibilityLabel={`Filter by ${tag}`}
              style={({ pressed }) => [styles.chip, isSelected && styles.chipSelected, pressed && styles.chipPressed]}
            >
              <Text style={[styles.chipText, isSelected && styles.chipTextSelected]}>{tag}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );

  if (isLoading && !hasLoaded) {
    return (
      <ScreenWrapper edges={['top', 'left', 'right']}>
        {header}
        <LoadingState label="Loading services" style={styles.fill} />
      </ScreenWrapper>
    );
  }

  return (
    <ScreenWrapper edges={['top', 'left', 'right']}>
      {header}
      <FlatList
        style={styles.fill}
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

      <Button
        label="New service"
        icon="add"
        variant="primary"
        size="md"
        fullWidth={false}
        onPress={() => router.push('/services/create' as any)}
        accessibilityLabel="Create a new service post"
        style={styles.fab}
      />

      <Snackbar
        visible={snackbarVisible}
        onDismiss={hideSnackbar}
        duration={3000}
        wrapperStyle={styles.snackbarWrapper}
        style={[
          styles.snackbar,
          { backgroundColor: snackbarType === 'success' ? palette.ink : palette.dangerSolid },
        ]}
      >
        <Text style={styles.snackbarText}>{snackbarMessage}</Text>
      </Snackbar>
    </ScreenWrapper>
  );
}

const FAB_HEIGHT = 48;

const styles = StyleSheet.create({
  fill: { flex: 1 },
  listHeader: { paddingTop: space.xxs },
  chipScroll: { marginHorizontal: -space.lg },
  chipContainer: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.md,
    gap: space.xs,
  },
  chip: {
    height: 36,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.card,
  },
  chipSelected: { backgroundColor: palette.yellow },
  chipPressed: { opacity: 0.85 },
  chipText: { ...type.label, fontFamily: fonts.medium, color: palette.ink },
  chipTextSelected: { fontFamily: fonts.semibold, color: palette.onYellow },
  listContent: {
    paddingHorizontal: space.lg,
    // Room for the floating "New service" button above the floating tab bar.
    paddingBottom: layout.tabBarSpace + FAB_HEIGHT + space.lg,
    flexGrow: 1,
  },
  fab: {
    position: 'absolute',
    right: space.lg,
    bottom: layout.tabBarSpace,
    ...shadow.floating,
  },
  snackbarWrapper: { bottom: layout.tabBarSpace },
  snackbar: { borderRadius: radius.md },
  snackbarText: { ...type.label, fontFamily: fonts.semibold, color: palette.onPrimary },
});
