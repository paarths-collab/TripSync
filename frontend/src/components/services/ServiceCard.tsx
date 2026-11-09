import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, IconButton, Menu } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { ServicePost } from '../../services/servicesService';
import { useAuth } from '../../context/AuthContext';
import { Card, Avatar, StatusPill } from '../ui';
import { palette, space, radius, type, fonts, Tone } from '../../constants/theme';

interface ServiceCardProps {
  post: ServicePost;
  onPostDeleted: (postId: number) => void;
}

const formatCompensation = (type: ServicePost['compensation_type'], amount?: number): string => {
  switch (type) {
    case 'fixed_price': return `₹${amount || 'N/A'}`;
    case 'hourly_rate': return `₹${amount || 'N/A'} / hr`;
    case 'negotiable': return 'Negotiable';
    default: return 'Volunteer';
  }
};

const formatPostedDate = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = Math.abs(now.getTime() - date.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  if (diffDays <= 1) return 'Posted today';
  if (diffDays <= 30) return `Posted ${diffDays} days ago`;
  return `Posted on ${date.toLocaleDateString()}`;
};

export const serviceStatusMeta: Record<ServicePost['status'], { label: string; tone: Tone }> = {
  open: { label: 'Open', tone: 'success' },
  in_progress: { label: 'In progress', tone: 'info' },
  completed: { label: 'Completed', tone: 'primary' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
};

export default function ServiceCard({ post, onPostDeleted }: ServiceCardProps) {
  const router = useRouter();
  const { user } = useAuth();

  const [menuVisible, setMenuVisible] = useState(false);
  const openMenu = () => setMenuVisible(true);
  const closeMenu = () => setMenuVisible(false);

  const isMyPost = !!user && user.id === post.poster_user_id;

  const handleCardPress = () => {
    if (!post || typeof post.id !== 'number') { return; }
    router.push(`/services/${post.id}` as any);
  };

  const handleDelete = () => {
    closeMenu();
    onPostDeleted(post.id);
  };

  const posterName = post.is_anonymous ? 'Anonymous User' : post.poster?.full_name || 'User';
  const status = serviceStatusMeta[post.status] ?? { label: post.status, tone: 'neutral' as Tone };
  const isPaid = post.compensation_type === 'fixed_price' || post.compensation_type === 'hourly_rate';

  return (
    <Card style={styles.card} onPress={handleCardPress}>
      <View style={styles.topRow}>
        <StatusPill label={status.label} tone={status.tone} />
        {isMyPost && (
          <Menu
            visible={menuVisible}
            onDismiss={closeMenu}
            contentStyle={styles.menu}
            anchor={
              <IconButton
                icon="dots-horizontal"
                onPress={openMenu}
                size={20}
                iconColor={palette.textMuted}
                style={styles.menuButton}
                accessibilityLabel="Post options"
              />
            }
          >
            <Menu.Item
              onPress={handleDelete}
              title="Delete post"
              leadingIcon="delete-outline"
              titleStyle={styles.menuItemTitle}
            />
          </Menu>
        )}
      </View>

      <Text style={styles.title} numberOfLines={2}>{post.title}</Text>
      {!!post.description && (
        <Text style={styles.description} numberOfLines={2}>{post.description}</Text>
      )}

      {post.tags && post.tags.length > 0 && (
        <View style={styles.tagRow}>
          {post.tags.slice(0, 3).map(tag => (
            <View key={tag.id} style={styles.tag}>
              <Text style={styles.tagText}>{tag.name}</Text>
            </View>
          ))}
          {post.tags.length > 3 && (
            <Text style={styles.moreTags}>+{post.tags.length - 3}</Text>
          )}
        </View>
      )}

      <View style={styles.metaRow}>
        <View style={[styles.price, isPaid && styles.pricePaid]}>
          <Ionicons
            name="cash-outline"
            size={14}
            color={isPaid ? palette.success : palette.textMuted}
          />
          <Text style={[styles.priceText, isPaid && styles.priceTextPaid]}>
            {formatCompensation(post.compensation_type, post.compensation_amount)}
          </Text>
        </View>
        <View style={styles.metaItem}>
          <Ionicons name="people-outline" size={14} color={palette.textMuted} />
          <Text style={styles.metaText}>{post.team_size} {post.team_size === 1 ? "person" : "people"}</Text>
        </View>
        {post.deadline && (
          <View style={styles.metaItem}>
            <Ionicons name="calendar-outline" size={14} color={palette.textMuted} />
            <Text style={styles.metaText}>{new Date(post.deadline).toLocaleDateString()}</Text>
          </View>
        )}
      </View>

      <View style={styles.footer}>
        <Avatar name={post.is_anonymous ? null : posterName} size={32} />
        <View style={styles.footerText}>
          <Text style={styles.posterName} numberOfLines={1}>{posterName}</Text>
          <Text style={styles.date}>{formatPostedDate(post.created_at)}</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={palette.textFaint} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    marginBottom: space.sm,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 28,
    marginBottom: space.xs,
  },
  menuButton: {
    margin: 0,
    marginRight: -space.xs,
  },
  menu: {
    backgroundColor: palette.surface,
    borderRadius: radius.md,
  },
  menuItemTitle: {
    ...type.bodyStrong,
    color: palette.danger,
  },
  title: {
    ...type.title3,
    color: palette.text,
  },
  description: {
    ...type.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: space.xxs,
    color: palette.textMuted,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.xs,
    marginTop: space.sm,
  },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.yellowSoft,
  },
  tagText: {
    ...type.caption,
    fontFamily: fonts.semibold,
    color: palette.ink,
  },
  moreTags: {
    ...type.caption,
    color: palette.textMuted,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.sm,
  },
  price: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.surfaceMuted,
  },
  pricePaid: {
    backgroundColor: palette.successSoft,
  },
  priceText: {
    ...type.label,
    marginLeft: space.xxs,
    fontFamily: fonts.bold,
    color: palette.textMuted,
  },
  priceTextPaid: {
    color: palette.success,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metaText: {
    ...type.label,
    marginLeft: space.xxs,
    color: palette.textMuted,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: space.md,
    paddingTop: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
  },
  footerText: {
    flex: 1,
    marginLeft: space.xs,
  },
  posterName: {
    ...type.label,
    fontFamily: fonts.semibold,
    color: palette.text,
  },
  date: {
    ...type.caption,
    color: palette.textFaint,
  },
});
