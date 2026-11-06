import React, { useState, useEffect, useCallback } from 'react';
import { ScrollView, StyleSheet, View, Alert } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import { getServicePostById, ServicePost } from '../../../services/servicesService';
import ApplyModal from '../../../components/services/ApplyModal';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../../context/AuthContext';
import { serviceStatusMeta } from '../../../components/services/ServiceCard';
import {
  Card,
  Avatar,
  StatusPill,
  SectionTitle,
  InfoRow,
  EmptyState,
  LoadingState,
} from '../../../components/ui';
import { palette, space, radius, font, shadow } from '../../../constants/theme';

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

  const handleApplicationSuccess = () => {
    setIsModalVisible(false);
    Alert.alert(
      'Application Submitted!',
      'The poster has been notified. You can track the status in your dashboard.',
      [{ text: 'OK', onPress: () => router.back() }]
    );
  };

  if (isLoading) {
    return (
      <ScreenWrapper style={styles.center}>
        <Stack.Screen options={{ title: 'Service' }} />
        <LoadingState label="Loading service" />
      </ScreenWrapper>
    );
  }

  if (!post) {
    return (
      <ScreenWrapper style={styles.center}>
        <Stack.Screen options={{ title: 'Service' }} />
        <EmptyState icon="alert-circle-outline" title="Service not found." />
      </ScreenWrapper>
    );
  }

  const isMyPost = user?.id === post.poster_user_id;
  const status = serviceStatusMeta[post.status] ?? { label: post.status, tone: 'neutral' as const };
  const posterName = post.is_anonymous ? 'Anonymous User' : post.poster?.full_name;

  return (
    <ScreenWrapper style={styles.screenWrapper}>
      <Stack.Screen options={{ title: 'Service' }} />
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
          <View style={styles.rowDivider} />
          <InfoRow icon="people-outline" label="Team size" value={`${post.team_size} ${post.team_size === 1 ? "person" : "people"}`} />
          <View style={styles.rowDivider} />
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
          <Ionicons name="person-circle-outline" size={22} color={palette.textFaint} />
        </Card>
      </ScrollView>

      {!isMyPost && (
        <View style={styles.applyButtonContainer}>
          <Button
            mode="contained"
            onPress={() => setIsModalVisible(true)}
            style={styles.applyButton}
            labelStyle={styles.applyButtonLabel}
            contentStyle={styles.applyButtonContent}
            buttonColor={palette.primary}
            textColor={palette.onPrimary}
            icon="send-outline"
          >
            Apply now
          </Button>
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

const styles = StyleSheet.create({
  screenWrapper: { backgroundColor: palette.background },
  container: { paddingHorizontal: space.md, paddingTop: space.xs, paddingBottom: space.xxl },
  containerWithAction: { paddingBottom: 120 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.background },
  statusPill: { marginBottom: space.sm },
  title: {
    fontSize: 24,
    lineHeight: 30,
    fontWeight: font.bold,
    color: palette.text,
    letterSpacing: -0.2,
  },
  postedOn: { marginTop: space.xxs, marginBottom: space.lg, fontSize: 13, color: palette.textMuted },
  section: { marginBottom: space.md },
  sectionTitleTight: { marginBottom: 0 },
  description: { fontSize: 15, lineHeight: 23, color: palette.text },
  rowDivider: { height: StyleSheet.hairlineWidth, backgroundColor: palette.border, marginLeft: 30 },
  tagContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  tag: {
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs + 2,
    borderRadius: radius.pill,
    backgroundColor: palette.primarySoft,
  },
  tagText: { fontSize: 13, color: palette.primaryDark, fontWeight: font.medium },
  posterHeading: { marginTop: space.xs },
  posterCard: { flexDirection: 'row', alignItems: 'center' },
  posterText: { flex: 1, marginLeft: space.sm },
  posterName: { fontSize: 16, fontWeight: font.semibold, color: palette.text },
  metaText: { marginTop: 2, fontSize: 13, color: palette.textMuted },
  applyButtonContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: space.md,
    paddingTop: space.sm,
    paddingBottom: space.md,
    backgroundColor: palette.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
    ...shadow.raised,
  },
  applyButton: { borderRadius: radius.md },
  applyButtonLabel: { fontWeight: font.semibold, fontSize: 16 },
  applyButtonContent: { paddingVertical: space.xxs + 2 },
});
