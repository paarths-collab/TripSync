// src/components/ui/index.tsx
// Shared building blocks so every screen looks like the same app.
import React, { forwardRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Pressable,
  ViewStyle,
  TextStyle,
  StyleProp,
  ActivityIndicator,
  TextInput,
  TextInputProps,
  Platform,
} from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons } from '@expo/vector-icons';
import { palette, space, radius, shadow, fonts, type, toneColors, Tone } from '../../constants/theme';

export type IconName = React.ComponentProps<typeof Ionicons>['name'];

/* ---------- Button ---------- */

type ButtonVariant = 'primary' | 'dark' | 'secondary' | 'outline' | 'danger' | 'ghost';

const buttonColors: Record<ButtonVariant, { bg: string; fg: string; pressed: string; border?: string }> = {
  primary: { bg: palette.yellow, fg: palette.onYellow, pressed: palette.yellowPressed },
  dark: { bg: palette.ink, fg: palette.onPrimary, pressed: palette.ink2 },
  secondary: { bg: palette.surfaceMuted, fg: palette.ink, pressed: palette.border },
  outline: { bg: 'transparent', fg: palette.ink, pressed: palette.surfaceMuted, border: palette.borderStrong },
  danger: { bg: palette.dangerSolid, fg: palette.onPrimary, pressed: palette.danger },
  ghost: { bg: 'transparent', fg: palette.ink, pressed: palette.surfaceMuted },
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'lg',
  icon,
  iconRight,
  loading = false,
  disabled = false,
  fullWidth = true,
  style,
  accessibilityLabel,
}: {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  size?: 'lg' | 'md' | 'sm';
  icon?: IconName;
  iconRight?: IconName;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
}) {
  const c = buttonColors[variant];
  const height = size === 'lg' ? 56 : size === 'md' ? 48 : 36;
  const inactive = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || label}
      accessibilityState={{ disabled: inactive, busy: loading }}
      style={({ pressed }) => [
        styles.button,
        {
          height,
          paddingHorizontal: size === 'sm' ? space.sm : space.xl,
          backgroundColor: pressed ? c.pressed : c.bg,
          borderColor: c.border ?? 'transparent',
          borderWidth: c.border ? 1.5 : 0,
          alignSelf: fullWidth ? 'stretch' : 'flex-start',
          opacity: disabled ? 0.45 : 1,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={c.fg} />
      ) : (
        <>
          {icon ? <Ionicons name={icon} size={size === 'sm' ? 16 : 20} color={c.fg} style={{ marginRight: 8 }} /> : null}
          <Text style={[size === 'sm' ? type.label : type.button, { color: c.fg, fontFamily: fonts.semibold }]}>
            {label}
          </Text>
          {iconRight ? <Ionicons name={iconRight} size={size === 'sm' ? 16 : 20} color={c.fg} style={{ marginLeft: 8 }} /> : null}
        </>
      )}
    </Pressable>
  );
}

/* ---------- Card ---------- */

export function Card({
  children,
  style,
  onPress,
  padded = true,
  accessibilityLabel,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  padded?: boolean;
  accessibilityLabel?: string;
}) {
  const content = [styles.card, padded && styles.cardPadded, style];
  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [...content, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
      >
        {children}
      </Pressable>
    );
  }
  return <View style={content}>{children}</View>;
}

/* ---------- Sheet (static bottom sheet container) ---------- */

export function Sheet({
  children,
  title,
  subtitle,
  right,
  style,
  handle = true,
}: {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  right?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  handle?: boolean;
}) {
  return (
    <View style={[styles.sheet, style]}>
      {handle ? <View style={styles.handle} /> : null}
      {title ? (
        <View style={styles.sheetHeader}>
          <View style={{ flex: 1 }}>
            <Text style={type.title2}>{title}</Text>
            {subtitle ? <Text style={[type.body, { color: palette.textMuted, marginTop: 2 }]}>{subtitle}</Text> : null}
          </View>
          {right}
        </View>
      ) : null}
      {children}
    </View>
  );
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
      {onBack ? <IconButton icon="chevron-back" onPress={onBack} label="Go back" style={styles.headerBack} /> : null}
      <View style={styles.headerText}>
        <Text style={type.title1} numberOfLines={1} accessibilityRole="header">
          {title}
        </Text>
        {subtitle ? (
          <Text style={[type.body, { color: palette.textMuted, marginTop: 2 }]} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ? <View style={styles.headerRight}>{right}</View> : null}
    </View>
  );
}

/* ---------- IconButton (rounded square, as in the references) ---------- */

export function IconButton({
  icon,
  onPress,
  label,
  tone = 'neutral',
  size = 48,
  round = false,
  style,
}: {
  icon: IconName;
  onPress?: () => void;
  label: string;
  tone?: Tone | 'dark';
  size?: number;
  round?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const colors =
    tone === 'neutral'
      ? { fg: palette.ink, bg: palette.surface }
      : tone === 'dark'
        ? { fg: palette.onPrimary, bg: palette.ink }
        : toneColors[tone];
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={6}
      style={({ pressed }) => [
        styles.iconButton,
        {
          width: size,
          height: size,
          borderRadius: round ? size / 2 : Math.round(size * 0.36),
          backgroundColor: colors.bg,
        },
        tone === 'neutral' && shadow.card,
        pressed && styles.pressed,
        style,
      ]}
    >
      <Ionicons name={icon} size={Math.round(size * 0.46)} color={colors.fg} />
    </Pressable>
  );
}

/* ---------- IconBadge ---------- */

export function IconBadge({ icon, tone = 'primary', size = 44 }: { icon: IconName; tone?: Tone; size?: number }) {
  const c = toneColors[tone];
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.34,
        backgroundColor: c.bg,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Ionicons name={icon} size={Math.round(size * 0.5)} color={c.fg} />
    </View>
  );
}

/* ---------- Tag / StatusPill ---------- */

export function Tag({
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
      <Text style={[type.caption, { color: c.fg, fontFamily: fonts.semibold }]}>{label}</Text>
    </View>
  );
}

export const StatusPill = Tag;

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
      <Text style={type.title3} accessibilityRole="header">
        {title}
      </Text>
      {action}
    </View>
  );
}

/* ---------- CategoryTile (vehicle / service tiles) ---------- */

export function CategoryTile({
  icon,
  label,
  caption,
  selected = false,
  onPress,
  style,
}: {
  icon: IconName;
  label: string;
  caption?: string;
  selected?: boolean;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={caption ? `${label}, ${caption}` : label}
      style={({ pressed }) => [
        styles.tile,
        selected ? { backgroundColor: palette.ink } : shadow.card,
        pressed && styles.pressed,
        style,
      ]}
    >
      <Ionicons name={icon} size={28} color={selected ? palette.yellow : palette.ink} />
      <Text style={[type.label, { marginTop: space.xs, color: selected ? palette.onPrimary : palette.ink, fontFamily: fonts.semibold }]}>
        {label}
      </Text>
      {caption ? (
        <Text style={[type.caption, { color: selected ? palette.onDarkMuted : palette.textMuted, marginTop: 2 }]} numberOfLines={1}>
          {caption}
        </Text>
      ) : null}
    </Pressable>
  );
}

/* ---------- ListRow ---------- */

export function ListRow({
  title,
  subtitle,
  icon,
  leading,
  trailing,
  onPress,
  chevron = !!onPress,
  style,
}: {
  title: string;
  subtitle?: string;
  icon?: IconName;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  onPress?: () => void;
  chevron?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const body = (
    <>
      {leading ?? (icon ? <IconBadge icon={icon} tone="neutral" size={40} /> : null)}
      <View style={{ flex: 1, marginLeft: leading || icon ? space.sm : 0 }}>
        <Text style={type.bodyStrong} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={[type.label, { color: palette.textMuted }]} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {trailing}
      {chevron ? <Ionicons name="chevron-forward" size={18} color={palette.textMuted} style={{ marginLeft: space.xs }} /> : null}
    </>
  );
  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        style={({ pressed }) => [styles.listRow, pressed && { backgroundColor: palette.surfaceMuted }, style]}
      >
        {body}
      </Pressable>
    );
  }
  return <View style={[styles.listRow, style]}>{body}</View>;
}

/* ---------- TextField ---------- */

// The field draws its own focus border; drop the browser's default outline on web.
const webNoOutline = (Platform.OS === 'web' ? { outlineStyle: 'none' } : null) as unknown as TextStyle;

export const TextField = forwardRef<
  TextInput,
  TextInputProps & {
    label?: string;
    error?: string | null;
    hint?: string;
    icon?: IconName;
    right?: React.ReactNode;
    containerStyle?: StyleProp<ViewStyle>;
  }
>(function TextField({ label, error, hint, icon, right, containerStyle, style, onFocus, onBlur, ...props }, ref) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={[{ marginBottom: space.md }, containerStyle]}>
      {label ? <Text style={[type.label, { color: palette.textMuted, marginBottom: 6 }]}>{label}</Text> : null}
      <View
        style={[
          styles.field,
          { borderColor: error ? palette.danger : focused ? palette.ink : palette.borderStrong },
          focused && { borderWidth: 2 },
        ]}
      >
        {icon ? <Ionicons name={icon} size={20} color={palette.textMuted} style={{ marginRight: space.xs }} /> : null}
        <TextInput
          ref={ref}
          placeholderTextColor={palette.textMuted}
          accessibilityLabel={label}
          style={[styles.fieldInput, webNoOutline, style as StyleProp<TextStyle>]}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...props}
        />
        {right}
      </View>
      {error ? (
        <Text style={[type.caption, { color: palette.danger, marginTop: 4 }]} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : hint ? (
        <Text style={[type.caption, { color: palette.textMuted, marginTop: 4 }]}>{hint}</Text>
      ) : null}
    </View>
  );
});

/* ---------- SearchBar (pill) ---------- */

export function SearchBar({
  value,
  onChangeText,
  placeholder = 'Search',
  onPress,
  style,
  autoFocus,
}: {
  value?: string;
  onChangeText?: (t: string) => void;
  placeholder?: string;
  onPress?: () => void; // when set, the bar acts as a button (e.g. opens a search screen)
  style?: StyleProp<ViewStyle>;
  autoFocus?: boolean;
}) {
  if (onPress) {
    return (
      <Pressable onPress={onPress} accessibilityRole="search" style={({ pressed }) => [styles.search, pressed && styles.pressed, style]}>
        <Text style={[type.body, { flex: 1, color: palette.textMuted }]}>{placeholder}</Text>
        <Ionicons name="search" size={20} color={palette.ink} />
      </Pressable>
    );
  }
  return (
    <View style={[styles.search, style]}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={palette.textMuted}
        autoFocus={autoFocus}
        accessibilityLabel={placeholder}
        style={[type.body, { flex: 1, color: palette.text, paddingVertical: 0 }]}
      />
      <Ionicons name="search" size={20} color={palette.ink} />
    </View>
  );
}

/* ---------- SegmentedControl ---------- */

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  style,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.segment, style]} accessibilityRole="tablist">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            style={[styles.segmentItem, active && styles.segmentItemActive]}
          >
            <Text style={[type.label, { fontFamily: fonts.semibold, color: active ? palette.onPrimary : palette.textMuted }]}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/* ---------- Banner ---------- */

export function Banner({
  text,
  tone = 'info',
  icon = 'information-circle',
  action,
  style,
}: {
  text: string;
  tone?: Tone;
  icon?: IconName;
  action?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const c = toneColors[tone];
  return (
    <View style={[styles.banner, { backgroundColor: c.bg }, style]} accessibilityRole="alert">
      <Ionicons name={icon} size={18} color={c.fg} style={{ marginTop: 1 }} />
      <Text style={[type.label, { color: c.fg, flex: 1, marginLeft: space.xs }]}>{text}</Text>
      {action}
    </View>
  );
}

/* ---------- Divider ---------- */

export function Divider({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[{ height: StyleSheet.hairlineWidth, backgroundColor: palette.border }, style]} />;
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
      <Text style={[type.title3, { marginTop: space.md, textAlign: 'center' }]}>{title}</Text>
      {body ? <Text style={[type.body, styles.emptyBody]}>{body}</Text> : null}
      {action ? <View style={{ marginTop: space.md, alignSelf: 'stretch' }}>{action}</View> : null}
    </View>
  );
}

/* ---------- LoadingState ---------- */

export function LoadingState({ label, style }: { label?: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.empty, style]}>
      <ActivityIndicator size="large" color={palette.ink} />
      {label ? <Text style={[type.body, styles.emptyBody, { marginTop: space.sm }]}>{label}</Text> : null}
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
        <Text style={[type.caption, { color: palette.textMuted, marginBottom: 2 }]}>{label}</Text>
        <Text style={type.bodyStrong}>{value || '—'}</Text>
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
        borderRadius: size * 0.36,
        backgroundColor: palette.yellowSoft,
        alignItems: 'center',
        justifyContent: 'center',
      }}
      accessibilityLabel={name ? `${name}'s avatar` : 'Avatar'}
    >
      <Text style={{ color: palette.ink, fontFamily: fonts.bold, fontSize: size * 0.38 }}>{initials}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.xl,
    ...shadow.card,
  },
  cardPadded: {
    padding: space.md,
  },
  pressed: {
    opacity: 0.88,
    transform: [{ scale: 0.99 }],
  },
  sheet: {
    backgroundColor: palette.surface,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    paddingHorizontal: space.lg,
    paddingBottom: space.lg,
    paddingTop: space.xs,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: palette.border,
    marginBottom: space.sm,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: space.md,
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
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  section: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.sm,
  },
  tile: {
    width: 84,
    height: 96,
    borderRadius: radius.lg,
    backgroundColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xs,
  },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    minHeight: 56,
  },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 56,
    borderRadius: radius.md,
    borderWidth: 1.5,
    backgroundColor: palette.surface,
    paddingHorizontal: space.md,
  },
  fieldInput: {
    flex: 1,
    ...type.body,
    color: palette.text,
    paddingVertical: space.sm,
  },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: palette.surface,
    paddingHorizontal: space.lg,
    ...shadow.card,
  },
  segment: {
    flexDirection: 'row',
    backgroundColor: palette.surfaceMuted,
    borderRadius: radius.pill,
    padding: 4,
  },
  segmentItem: {
    flex: 1,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentItemActive: {
    backgroundColor: palette.ink,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    borderRadius: radius.md,
    padding: space.sm,
  },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xxl,
    paddingVertical: space.xxxl,
  },
  emptyBody: {
    marginTop: space.xs,
    color: palette.textMuted,
    textAlign: 'center',
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: space.sm,
  },
});
