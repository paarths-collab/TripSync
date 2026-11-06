// src/components/ui/index.tsx
// Small shared building blocks so every screen looks like the same app.
import React from 'react';
import {
  View,
  StyleSheet,
  Pressable,
  ViewStyle,
  StyleProp,
  ActivityIndicator,
} from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { palette, space, radius, shadow, font, toneColors, Tone } from '../../constants/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

/* ---------- Card ---------- */

export function Card({
  children,
  style,
  onPress,
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  padded?: boolean;
}) {
  const content = [styles.card, padded && styles.cardPadded, style];
  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [...content, pressed && styles.pressed]}
        accessibilityRole="button"
      >
        {children}
      </Pressable>
    );
  }
  return <View style={content}>{children}</View>;
}

/* ---------- ScreenHeader ---------- */

export function ScreenHeader({
  title,
  subtitle,
  onBack,
  right,
  style,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.header, style]}>
      {onBack ? (
        <IconButton icon="chevron-back" onPress={onBack} label="Go back" style={styles.headerBack} />
      ) : null}
      <View style={styles.headerText}>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.headerSubtitle} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ? <View style={styles.headerRight}>{right}</View> : null}
    </View>
  );
}

/* ---------- IconButton ---------- */

export function IconButton({
  icon,
  onPress,
  label,
  tone = 'neutral',
  size = 40,
  style,
}: {
  icon: IconName;
  onPress?: () => void;
  label: string;
  tone?: Tone;
  size?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const colors = tone === 'neutral' ? { fg: palette.text, bg: palette.surface } : toneColors[tone];
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={6}
      style={({ pressed }) => [
        styles.iconButton,
        { width: size, height: size, borderRadius: size / 2, backgroundColor: colors.bg },
        tone === 'neutral' && styles.iconButtonBorder,
        pressed && styles.pressed,
        style,
      ]}
    >
      <Ionicons name={icon} size={Math.round(size * 0.5)} color={colors.fg} />
    </Pressable>
  );
}

/* ---------- IconBadge ---------- */

export function IconBadge({
  icon,
  tone = 'primary',
  size = 44,
}: {
  icon: IconName;
  tone?: Tone;
  size?: number;
}) {
  const c = toneColors[tone];
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.32,
        backgroundColor: c.bg,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Ionicons name={icon} size={Math.round(size * 0.5)} color={c.fg} />
    </View>
  );
}

/* ---------- StatusPill ---------- */

export function StatusPill({
  label,
  tone = 'neutral',
  icon,
  style,
}: {
  label: string;
  tone?: Tone;
  icon?: IconName;
  style?: StyleProp<ViewStyle>;
}) {
  const c = toneColors[tone];
  return (
    <View style={[styles.pill, { backgroundColor: c.bg }, style]}>
      {icon ? <Ionicons name={icon} size={12} color={c.fg} style={{ marginRight: 4 }} /> : null}
      <Text style={[styles.pillText, { color: c.fg }]}>{label}</Text>
    </View>
  );
}

/* ---------- SectionTitle ---------- */

export function SectionTitle({
  title,
  action,
  style,
}: {
  title: string;
  action?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.section, style]}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {action}
    </View>
  );
}

/* ---------- EmptyState ---------- */

export function EmptyState({
  icon,
  title,
  body,
  action,
  style,
}: {
  icon: IconName;
  title: string;
  body?: string;
  action?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.empty, style]}>
      <IconBadge icon={icon} size={64} />
      <Text style={styles.emptyTitle}>{title}</Text>
      {body ? <Text style={styles.emptyBody}>{body}</Text> : null}
      {action ? <View style={{ marginTop: space.md }}>{action}</View> : null}
    </View>
  );
}

/* ---------- LoadingState ---------- */

export function LoadingState({ label, style }: { label?: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.empty, style]}>
      <ActivityIndicator size="large" color={palette.primary} />
      {label ? <Text style={[styles.emptyBody, { marginTop: space.sm }]}>{label}</Text> : null}
    </View>
  );
}

/* ---------- InfoRow ---------- */

export function InfoRow({
  icon,
  label,
  value,
  style,
}: {
  icon: IconName;
  label: string;
  value?: string | null;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.infoRow, style]}>
      <Ionicons name={icon} size={18} color={palette.textMuted} style={{ marginTop: 2 }} />
      <View style={{ flex: 1, marginLeft: space.sm }}>
        <Text style={styles.infoLabel}>{label}</Text>
        <Text style={styles.infoValue}>{value || '—'}</Text>
      </View>
    </View>
  );
}

/* ---------- Avatar ---------- */

export function Avatar({ name, size = 44 }: { name?: string | null; size?: number }) {
  const initials =
    (name || '?')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join('') || '?';
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: palette.primarySoft,
        alignItems: 'center',
        justifyContent: 'center',
      }}
      accessibilityLabel={name ? `${name}'s avatar` : 'Avatar'}
    >
      <Text style={{ color: palette.primaryDark, fontWeight: font.bold, fontSize: size * 0.38 }}>
        {initials}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    ...shadow.card,
  },
  cardPadded: {
    padding: space.md,
  },
  pressed: {
    opacity: 0.85,
    transform: [{ scale: 0.99 }],
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingTop: space.md,
    paddingBottom: space.sm,
  },
  headerBack: {
    marginRight: space.sm,
  },
  headerText: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: font.bold,
    color: palette.text,
    letterSpacing: -0.3,
  },
  headerSubtitle: {
    marginTop: 2,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
  },
  headerRight: {
    marginLeft: space.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  iconButton: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonBorder: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  pillText: {
    fontSize: 12,
    fontWeight: font.semibold,
    letterSpacing: 0.2,
  },
  section: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.sm,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: font.semibold,
    color: palette.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xxl,
    paddingVertical: space.xxxl,
  },
  emptyTitle: {
    marginTop: space.md,
    fontSize: 18,
    fontWeight: font.semibold,
    color: palette.text,
    textAlign: 'center',
  },
  emptyBody: {
    marginTop: space.xs,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
    textAlign: 'center',
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: space.sm,
  },
  infoLabel: {
    fontSize: 12,
    color: palette.textMuted,
    marginBottom: 2,
  },
  infoValue: {
    fontSize: 15,
    color: palette.text,
    fontWeight: font.medium,
  },
});
