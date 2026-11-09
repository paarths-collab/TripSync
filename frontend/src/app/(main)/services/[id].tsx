import React, { useState, useEffect, useCallback } from 'react';
import { ScrollView, StyleSheet, View, Alert } from 'react-native';
import { Text } from 'react-native-paper';
import { useLocalSearchParams, useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import { getServicePostById, ServicePost } from '../../../services/servicesService';
import ApplyModal from '../../../components/services/ApplyModal';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../../context/AuthContext';
import { serviceStatusMeta } from '../../../components/services/ServiceCard';
import {
  Button,
  Card,
  Avatar,
  Divider,
  IconButton,
  StatusPill,
  SectionTitle,
  InfoRow,
  EmptyState,
  LoadingState,
} from '../../../components/ui';
import { palette, space, radius, type, fonts, shadow, layout } from '../../../constants/theme';

const formatCompensation = (type: ServicePost['compensation_type'], amount?: number) => {
    switch (type) {
      case 'fixed_price': return `₹${amount || 'N/A'} (Fixed)`;
      case 'hourly_rate': return `₹${amount || 'N/A'} / hour`;
      case 'negotiable': return 'Negotiable';
      default: return 'Volunteer';
    }
};

export default function ServiceDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user, token } = useAuth();
  const [post, setPost] = useState<ServicePost | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalVisible, setIsModalVisible] = useState(false);

  const fetchData = useCallback(async () => {
    if (!id) {
        Alert.alert('Error', 'Service ID is missing.');
        router.back();
        return;
    }
    try {
      const postId = parseInt(id, 10);
      if (isNaN(postId)) throw new Error("Invalid Post ID");
      const fetchedPost = await getServicePostById(postId, token);
      setPost(fetchedPost);
    } catch {
      Alert.alert('Error', 'Could not load service details. It may have been removed.');
      router.back();
    } finally {
      setIsLoading(false);
    }
  }, [id, router, token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleBack = () => {
    if (router.canGoBack()) router.back();
    else router.navigate('/services' as any);
  };

  const topBar = (
    <View style={styles.topBar}>
      <IconButton icon="chevron-back" label="Go back" onPress={handleBack} />
    </View>
  );

  const handleApplicationSuccess = () => {
    setIsModalVisible(false);
    Alert.alert(
      'Application sent',
      'You can follow its status under My services.',
      [{ text: 'OK', onPress: () => router.back() }]
    );
  };

  if (isLoading) {
    return (
      <ScreenWrapper edges={['top', 'left', 'right']}>
        {topBar}
        <LoadingState label="Loading service" style={styles.fill} />
      </ScreenWrapper>
    );
  }

  if (!post) {
    return (
      <ScreenWrapper edges={['top', 'left', 'right']}>
        {topBar}
        <EmptyState icon="alert-circle-outline" title="Service not found" style={styles.fill} />
      </ScreenWrapper>
    );
  }

  const isMyPost = user?.id === post.poster_user_id;
  const status = serviceStatusMeta[post.status] ?? { label: post.status, tone: 'neutral' as const };
  const posterName = post.is_anonymous ? 'Anonymous User' : post.poster?.full_name;

  return (
    <ScreenWrapper edges={['top', 'left', 'right']}>
      {topBar}
      <ScrollView
        contentContainerStyle={[styles.container, !isMyPost && styles.containerWithAction]}
        showsVerticalScrollIndicator={false}
      >
        <StatusPill label={status.label} tone={status.tone} style={styles.statusPill} />
        <Text style={styles.title}>{post.title}</Text>
        <Text style={styles.postedOn}>
          Posted on {new Date(post.created_at).toLocaleDateString()}
        </Text>

        <Card style={styles.section}>
          <SectionTitle title="About this service" />
          <Text style={styles.description}>{post.description}</Text>
        </Card>

        <Card style={styles.section}>
          <SectionTitle title="Details" style={styles.sectionTitleTight} />
          <InfoRow
            icon="cash-outline"
            label="Compensation"
            value={formatCompensation(post.compensation_type, post.compensation_amount)}
          />
          <Divider style={styles.rowDivider} />
          <InfoRow icon="people-outline" label="Team size" value={`${post.team_size} ${post.team_size === 1 ? "person" : "people"}`} />
          <Divider style={styles.rowDivider} />
          <InfoRow
            icon="calendar-outline"
            label="Deadline"
            value={post.deadline ? new Date(post.deadline).toLocaleDateString() : 'N/A'}
          />
        </Card>

        {post.tags.length > 0 && (
          <Card style={styles.section}>
            <SectionTitle title="Required skills" />
            <View style={styles.tagContainer}>
              {post.tags.map(tag => (
                <View key={tag.id} style={styles.tag}>
                  <Text style={styles.tagText}>{tag.name}</Text>
                </View>
              ))}
            </View>
          </Card>
        )}

        <SectionTitle title="Posted by" style={styles.posterHeading} />
        <Card style={styles.posterCard}>
          <Avatar name={post.is_anonymous ? null : posterName} size={44} />
          <View style={styles.posterText}>
            <Text style={styles.posterName}>{posterName}</Text>
            <Text style={styles.metaText}>
              {isMyPost ? 'This is your post' : 'Service poster'}
            </Text>
          </View>
          <Ionicons name="person-circle-outline" size={22} color={palette.textMuted} />
        </Card>
      </ScrollView>

      {!isMyPost && (
        <View style={styles.applyButtonContainer} pointerEvents="box-none">
          <Button
            label="Apply now"
            variant="dark"
            icon="send"
            onPress={() => setIsModalVisible(true)}
            style={styles.applyButton}
          />
        </View>
      )}

      {post && (
        <ApplyModal
            visible={isModalVisible}
            onDismiss={() => setIsModalVisible(false)}
            post={post}
            onApplicationSuccess={handleApplicationSuccess}
        />
      )}
    </ScreenWrapper>
  );
}

const APPLY_BUTTON_HEIGHT = 56;

const styles = StyleSheet.create({
  fill: { flex: 1 },
  topBar: {
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.xs,
    flexDirection: 'row',
  },
  container: {
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
    // Clears the floating tab bar.
    paddingBottom: layout.tabBarSpace,
  },
  // Also clears the floating "Apply now" button that sits above the tab bar.
  containerWithAction: { paddingBottom: layout.tabBarSpace + APPLY_BUTTON_HEIGHT + space.lg },
  statusPill: { marginBottom: space.sm },
  title: {
    ...type.title1,
    color: palette.text,
  },
  postedOn: { ...type.label, marginTop: space.xxs, marginBottom: space.lg, color: palette.textMuted },
  section: { marginBottom: space.md },
  sectionTitleTight: { marginBottom: 0 },
  description: { ...type.body, color: palette.text },
  rowDivider: { marginLeft: 30 },
  tagContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  tag: {
    paddingHorizontal: space.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: palette.yellowSoft,
  },
  tagText: { ...type.label, fontFamily: fonts.semibold, color: palette.ink },
  posterHeading: { marginTop: space.xs },
  posterCard: { flexDirection: 'row', alignItems: 'center' },
  posterText: { flex: 1, marginLeft: space.sm },
  posterName: { ...type.bodyStrong, fontSize: 16, color: palette.text },
  metaText: { ...type.label, marginTop: 2, color: palette.textMuted },
  applyButtonContainer: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    bottom: layout.tabBarSpace,
  },
  applyButton: { ...shadow.floating },
});
