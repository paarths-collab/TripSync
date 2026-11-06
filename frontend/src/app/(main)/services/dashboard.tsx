import React, { useState, useCallback } from 'react';
import { View, StyleSheet, FlatList, Alert } from 'react-native';
import { Text, SegmentedButtons, Button } from 'react-native-paper';
import { useFocusEffect, useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import { useAuth } from '../../../context/AuthContext';
import { getMyServicePosts, getMyApplications, ServicePost, ServiceApplication } from '../../../services/servicesService';
import { Ionicons } from '@expo/vector-icons';
import { serviceStatusMeta } from '../../../components/services/ServiceCard';
import { Card, StatusPill, SectionTitle, EmptyState, LoadingState } from '../../../components/ui';
import { palette, space, radius, font, Tone } from '../../../constants/theme';

const applicationStatusMeta: Record<ServiceApplication['status'], { label: string; tone: Tone; icon: 'time-outline' | 'checkmark-circle' | 'close-circle' }> = {
    pending: { label: 'Pending', tone: 'warning', icon: 'time-outline' },
    accepted: { label: 'Accepted', tone: 'success', icon: 'checkmark-circle' },
    rejected: { label: 'Rejected', tone: 'danger', icon: 'close-circle' },
};

// Card for the "My Posts" tab
const MyPostCard = ({ post }: { post: ServicePost; index: number }) => {
    const router = useRouter();
    const status = serviceStatusMeta[post.status] ?? { label: post.status, tone: 'neutral' as Tone };

    return (
        <Card style={styles.card}>
            <View style={styles.cardTop}>
                <StatusPill label={status.label} tone={status.tone} />
                <View style={styles.metaItem}>
                    <Ionicons name="people-outline" size={14} color={palette.textMuted} />
                    <Text style={styles.metaText}>Team of {post.team_size}</Text>
                </View>
            </View>
            <Text style={styles.cardTitle} numberOfLines={2}>{post.title}</Text>
            {!!post.description && (
                <Text style={styles.cardBody} numberOfLines={2}>{post.description}</Text>
            )}
            <Button
                mode="contained-tonal"
                icon="account-group-outline"
                onPress={() => router.push(`/(main)/services/applicants/${post.id}` as any)}
                style={styles.cardButton}
                buttonColor={palette.primarySoft}
                textColor={palette.primaryDark}
                labelStyle={styles.cardButtonLabel}
            >
                View applicants
            </Button>
        </Card>
    );
};

// Card for the "My Applications" tab
const MyApplicationCard = ({ application }: { application: ServiceApplication; index: number }) => {
    const router = useRouter();
    const meta = applicationStatusMeta[application.status] ?? { label: application.status, tone: 'neutral' as Tone, icon: 'time-outline' as const };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    };

    return (
        <Card
            style={styles.card}
            onPress={() => router.push(`/(main)/services/${application.service_post.id}` as any)}
        >
            <View style={styles.cardTop}>
                <StatusPill label={meta.label} tone={meta.tone} icon={meta.icon} />
                <Ionicons name="chevron-forward" size={18} color={palette.textFaint} />
            </View>
            <Text style={styles.cardTitle} numberOfLines={2}>{application.service_post.title}</Text>
            <View style={[styles.metaItem, styles.appliedOn]}>
                <Ionicons name="calendar-outline" size={14} color={palette.textMuted} />
                <Text style={styles.metaText}>Applied on {formatDate(application.application_date)}</Text>
            </View>
            {application.cover_letter && (
                <View style={styles.quote}>
                    <Text style={styles.quoteText} numberOfLines={2}>
                        {application.cover_letter}
                    </Text>
                </View>
            )}
        </Card>
    );
};


export default function ServicesDashboard() {
  const { token } = useAuth();
  const [tab, setTab] = useState<'my-posts' | 'my-applications'>('my-posts');
  const [myPosts, setMyPosts] = useState<ServicePost[]>([]);
  const [myApplications, setMyApplications] = useState<ServiceApplication[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // --- THIS IS THE USEEFFECT FIX ---
  // The async logic is defined inside the useEffect callback, which is the correct pattern.
  useFocusEffect(
    useCallback(() => {
      const fetchData = async () => {
        if (!token) {
            Alert.alert("Authentication Error", "You must be logged in to view your dashboard.");
            setIsLoading(false);
            return;
        }
        setIsLoading(true);
        try {
          if (tab === 'my-posts') {
            const posts = await getMyServicePosts(token);
            setMyPosts(posts);
          } else {
            const apps = await getMyApplications(token);
            setMyApplications(apps);
          }
        } catch (error: any) {
          Alert.alert('Error', `Failed to load data: ${error.message}`);
        } finally {
          setIsLoading(false);
        }
      };

      fetchData();
    }, [token, tab]) // The effect re-runs when the token or the selected tab changes
  );

  const renderContent = () => {
    if (isLoading) {
      return (
        <LoadingState
          style={styles.fill}
          label={`Loading your ${tab === 'my-posts' ? 'posts' : 'applications'}...`}
        />
      );
    }

    if (tab === 'my-posts') {
      return (
        <FlatList
          data={myPosts}
          keyExtractor={item => item.id.toString()}
          contentContainerStyle={styles.listContent}
          renderItem={({ item, index }) => <MyPostCard post={item} index={index} />}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={
            myPosts.length > 0 ? (
              <SectionTitle title={`My posts · ${myPosts.length}`} />
            ) : null
          }
          ListEmptyComponent={
            <EmptyState
              icon="document-text-outline"
              title="No service posts yet"
              body="Tap New service on the Services screen to post your first one."
            />
          }
        />
      );
    }

    if (tab === 'my-applications') {
      return (
        <FlatList
          data={myApplications}
          keyExtractor={item => item.id.toString()}
          contentContainerStyle={styles.listContent}
          renderItem={({ item, index }) => <MyApplicationCard application={item} index={index} />}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={
            myApplications.length > 0 ? (
              <SectionTitle title={`My applications · ${myApplications.length}`} />
            ) : null
          }
          ListEmptyComponent={
            <EmptyState
              icon="file-tray-outline"
              title="No applications yet"
              body="Browse open services and apply. Your applications will show up here."
            />
          }
        />
      );
    }
    return null;
  };

  return (
    <ScreenWrapper style={styles.container}>
      <View style={styles.segmentContainer}>
        <SegmentedButtons
          value={tab}
          onValueChange={(value) => setTab(value as any)}
          buttons={[
            {
              value: 'my-posts',
              label: 'My posts',
              icon: 'post-outline',
              style: [styles.segment, tab === 'my-posts' && styles.segmentActive],
              checkedColor: palette.primaryDark,
              uncheckedColor: palette.textMuted,
            },
            {
              value: 'my-applications',
              label: 'My applications',
              icon: 'file-check-outline',
              style: [styles.segment, tab === 'my-applications' && styles.segmentActive],
              checkedColor: palette.primaryDark,
              uncheckedColor: palette.textMuted,
            },
          ]}
          density="regular"
        />
      </View>
      {renderContent()}
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: palette.background },
  fill: { flex: 1 },
  segmentContainer: {
    paddingHorizontal: space.md,
    paddingTop: space.xs,
    paddingBottom: space.sm,
    backgroundColor: palette.background,
  },
  segment: {
    borderColor: palette.border,
    backgroundColor: palette.surface,
  },
  segmentActive: {
    backgroundColor: palette.primarySoft,
  },
  listContent: {
    paddingHorizontal: space.md,
    paddingTop: space.xs,
    paddingBottom: space.xxl,
    flexGrow: 1,
  },
  card: {
    marginBottom: space.sm,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.xs,
  },
  cardTitle: {
    fontSize: 17,
    lineHeight: 23,
    fontWeight: font.semibold,
    color: palette.text,
  },
  cardBody: {
    marginTop: space.xxs,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
  },
  cardButton: {
    marginTop: space.md,
    borderRadius: radius.md,
  },
  cardButtonLabel: {
    fontWeight: font.semibold,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metaText: {
    marginLeft: space.xxs,
    fontSize: 13,
    color: palette.textMuted,
  },
  appliedOn: {
    marginTop: space.xxs,
  },
  quote: {
    marginTop: space.sm,
    paddingVertical: space.xs,
    paddingHorizontal: space.sm,
    borderLeftWidth: 3,
    borderLeftColor: palette.primarySoft,
    backgroundColor: palette.surfaceMuted,
    borderRadius: radius.sm,
  },
  quoteText: {
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
    fontStyle: 'italic',
  },
});
