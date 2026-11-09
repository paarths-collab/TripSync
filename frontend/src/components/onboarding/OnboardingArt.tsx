// src/components/onboarding/OnboardingArt.tsx
// Illustrated panels for onboarding, drawn with plain Views and icon glyphs in
// the kaali-peeli palette (we have no licensed photos). Each panel fills the
// top of the screen and fades into the background at the bottom.
import React from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import { Text } from 'react-native-paper';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { fonts, palette, shadow, type } from '../../constants/theme';
import FadeToBackground from './FadeToBackground';

export type ArtVariant = 'commute' | 'lift' | 'college' | 'location';

type McIcon = React.ComponentProps<typeof MaterialCommunityIcons>['name'];
type Stage = { W: number; top: number; H: number; s: number };

const TAN_12 = Math.tan((12 * Math.PI) / 180);

export default function OnboardingArt({
  variant,
  height,
  topInset = 0,
}: {
  variant: ArtVariant;
  height: number;
  topInset?: number;
}) {
  const { width: windowWidth } = useWindowDimensions();
  const fade = Math.round(height * 0.3);
  const W = Math.min(windowWidth, 520);
  const H = Math.max(160, height - topInset - fade * 0.35);
  const s = Math.max(0.7, Math.min(1.15, H / 340));
  const stage: Stage = { W, top: topInset, H, s };

  return (
    <View
      style={[styles.frame, { height }]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <View style={[styles.stage, { width: W, left: (windowWidth - W) / 2 }]}>
        <Decor stage={stage} />
        {variant === 'commute' ? <Commute stage={stage} /> : null}
        {variant === 'lift' ? <Lift stage={stage} /> : null}
        {variant === 'college' ? <College stage={stage} /> : null}
        {variant === 'location' ? <LocationMap stage={stage} /> : null}
      </View>
      <FadeToBackground height={fade} />
    </View>
  );
}

function Decor({ stage: { W, top, H } }: { stage: Stage }) {
  const big = W * 0.95;
  const small = W * 0.5;
  return (
    <>
      <View
        style={[
          styles.circle,
          {
            width: big,
            height: big,
            top: top - big * 0.42,
            right: -big * 0.3,
            backgroundColor: 'rgba(255, 255, 255, 0.22)',
          },
        ]}
      />
      <View
        style={[
          styles.circle,
          {
            width: small,
            height: small,
            top: top + H * 0.5,
            left: -small * 0.42,
            backgroundColor: 'rgba(242, 183, 5, 0.55)',
          },
        ]}
      />
    </>
  );
}

function Chip({
  icon,
  label,
  dark = false,
}: {
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  label: string;
  dark?: boolean;
}) {
  const fg = dark ? palette.onPrimary : palette.ink;
  return (
    <View style={[styles.chip, { backgroundColor: dark ? palette.ink : palette.surface }]}>
      {icon ? (
        <Ionicons name={icon} size={14} color={dark ? palette.yellow : palette.ink} style={{ marginRight: 6 }} />
      ) : null}
      <Text style={[type.caption, { color: fg, fontFamily: fonts.semibold }]}>{label}</Text>
    </View>
  );
}

/** A marker centred on (x, y). */
function At({ x, y, size, children }: { x: number; y: number; size: number; children: React.ReactNode }) {
  return (
    <View style={{ position: 'absolute', left: x - size / 2, top: y - size / 2, width: size, height: size }}>
      {children}
    </View>
  );
}

/* Slide 1: a road from home to college with a shared auto on it. */
function Commute({ stage: { W, top, H, s } }: { stage: Stage }) {
  const roadH = 84 * s;
  const cy = top + H * 0.6;
  const yAt = (x: number) => cy - (x - W / 2) * TAN_12;
  const vehicle = 78 * s;
  return (
    <>
      <View
        style={[
          styles.road,
          { left: -W * 0.3, width: W * 1.6, top: cy - roadH / 2, height: roadH, borderRadius: roadH / 2 },
        ]}
      >
        {Array.from({ length: 18 }, (_, i) => (
          <View
            key={i}
            style={{
              width: 24 * s,
              height: 6 * s,
              borderRadius: 3 * s,
              backgroundColor: palette.yellow,
              marginHorizontal: 10 * s,
            }}
          />
        ))}
      </View>

      <At x={W * 0.15} y={yAt(W * 0.15)} size={58 * s}>
        <View style={[styles.fill, styles.round, styles.whiteTile, { borderRadius: 29 * s }]}>
          <Ionicons name="location" size={28 * s} color={palette.ink} />
        </View>
      </At>

      <At x={W * 0.85} y={yAt(W * 0.85)} size={64 * s}>
        <View style={[styles.fill, styles.whiteTile, { borderRadius: 20 * s }]}>
          <Ionicons name="school" size={32 * s} color={palette.ink} />
        </View>
      </At>

      <At x={W * 0.5} y={cy} size={vehicle}>
        <View style={[styles.fill, styles.vehicle, { borderRadius: 24 * s, borderWidth: 4 * s }]}>
          <MaterialCommunityIcons name="rickshaw" size={44 * s} color={palette.ink} />
        </View>
      </At>

      <View style={[styles.row, { top: cy - vehicle / 2 - 52 }]}>
        <View style={styles.chip}>
          {[0, 1, 2].map((i) => (
            <View key={i} style={[styles.avatar, { marginLeft: i ? -8 : 0 }]}>
              <Ionicons name="person" size={12} color={palette.ink} />
            </View>
          ))}
          <Text style={[type.caption, { color: palette.ink, fontFamily: fonts.semibold, marginLeft: 8 }]}>
            Going your way
          </Text>
        </View>
      </View>
    </>
  );
}

/* Slide 2: an auto to split, with scooter, bike and car lifts around it. */
function Lift({ stage: { W, top, H, s } }: { stage: Stage }) {
  const cx = W / 2;
  const cy = top + H * 0.5;
  const core = 120 * s;
  const ring = 236 * s;
  const lifts: { icon: McIcon; label: string; x: number; y: number }[] = [
    { icon: 'moped', label: 'Scooter', x: cx - W * 0.31, y: cy - 78 * s },
    { icon: 'motorbike', label: 'Bike', x: cx + W * 0.31, y: cy - 60 * s },
    { icon: 'car-side', label: 'Car', x: cx + W * 0.31, y: cy + 76 * s },
  ];
  const tile = 74 * s;
  return (
    <>
      <At x={cx} y={cy} size={ring}>
        <View
          style={[
            styles.fill,
            styles.round,
            { borderRadius: ring / 2, borderWidth: 2, borderStyle: 'dashed', borderColor: 'rgba(22, 20, 15, 0.28)' },
          ]}
        />
      </At>
      {lifts.map((l) => (
        <At key={l.label} x={l.x} y={l.y} size={tile}>
          <View style={[styles.fill, styles.whiteTile, { borderRadius: 22 * s }]}>
            <MaterialCommunityIcons name={l.icon} size={40 * s} color={palette.ink} />
          </View>
          <Text style={[type.caption, styles.tileLabel]}>{l.label}</Text>
        </At>
      ))}
      <At x={cx} y={cy} size={core}>
        <View style={[styles.fill, styles.inkTile, { borderRadius: 34 * s }]}>
          <MaterialCommunityIcons name="rickshaw" size={66 * s} color={palette.yellow} />
        </View>
      </At>
      <View style={[styles.row, { top: cy + core / 2 + 12 }]}>
        <Chip icon="people" label="Split an auto" />
      </View>
    </>
  );
}

/* Slide 3: college email sign-up and a chat with your match. */
function College({ stage: { W, top, H, s } }: { stage: Stage }) {
  const cardW = Math.min(W * 0.68, 300);
  const pad = 16 * s;
  return (
    <View style={[styles.row, { top: top + H * 0.14 }]}>
      <View
        style={[styles.card, { width: cardW, padding: pad, borderRadius: 28 * s, transform: [{ rotate: '-4deg' }] }]}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={[styles.softTile, { width: 46 * s, height: 46 * s, borderRadius: 14 * s }]}>
            <Ionicons name="school" size={24 * s} color={palette.ink} />
          </View>
          <View style={{ marginLeft: 12 * s, flex: 1 }}>
            <View style={{ width: '80%', height: 10 * s, borderRadius: 5 * s, backgroundColor: palette.ink }} />
            <View
              style={{
                width: '50%',
                height: 8 * s,
                borderRadius: 4 * s,
                backgroundColor: palette.surfaceMuted,
                marginTop: 6 * s,
              }}
            />
          </View>
        </View>

        <View style={[styles.emailRow, { marginTop: 14 * s, height: 40 * s, borderRadius: 12 * s }]}>
          <Ionicons name="mail" size={16} color={palette.ink} />
          <Text style={[type.caption, { color: palette.ink, flex: 1, marginLeft: 8 }]} numberOfLines={1}>
            you@college.ac.in
          </Text>
          <Ionicons name="checkmark-circle" size={18} color={palette.success} />
        </View>

        <View style={[styles.bubble, styles.bubbleMine, { marginTop: 16 * s }]}>
          <Text style={[type.caption, { color: palette.onPrimary, fontFamily: fonts.semibold }]}>Leaving at 8:30?</Text>
        </View>
        <View style={[styles.bubble, styles.bubbleTheirs, { marginTop: 8 * s }]}>
          <Text style={[type.caption, { color: palette.ink, fontFamily: fonts.semibold }]}>
            Works for me, see you at the gate
          </Text>
        </View>

        <View
          style={[styles.badge, { width: 54 * s, height: 54 * s, borderRadius: 27 * s, top: -20 * s, right: -20 * s }]}
        >
          <Ionicons name="chatbubbles" size={24 * s} color={palette.yellow} />
        </View>
      </View>
    </View>
  );
}

/* Location primer: a street map with your pickup point and a route to college. */
function LocationMap({ stage: { W, top, H, s } }: { stage: Stage }) {
  const street = 'rgba(255, 255, 255, 0.55)';
  const px = W * 0.4;
  const py = top + H * 0.62;
  const sx = W * 0.8;
  const sy = top + H * 0.2;
  const dx = sx - px;
  const dy = sy - py;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const rings = [196 * s, 128 * s];
  return (
    <>
      <View
        style={[styles.street, { left: 0, right: 0, top: top + H * 0.3, height: 10 * s, backgroundColor: street }]}
      />
      <View
        style={[styles.street, { left: 0, right: 0, top: top + H * 0.82, height: 12 * s, backgroundColor: street }]}
      />
      <View style={[styles.street, { top: 0, bottom: 0, left: W * 0.18, width: 10 * s, backgroundColor: street }]} />
      <View style={[styles.street, { top: 0, bottom: 0, left: W * 0.66, width: 12 * s, backgroundColor: street }]} />
      <View
        style={[
          styles.street,
          {
            left: -W * 0.2,
            width: W * 1.4,
            top: top + H * 0.5,
            height: 14 * s,
            backgroundColor: street,
            transform: [{ rotate: '-28deg' }],
          },
        ]}
      />

      <View
        style={{
          position: 'absolute',
          left: (px + sx) / 2 - length / 2,
          top: (py + sy) / 2 - 3 * s,
          width: length,
          height: 6 * s,
          borderRadius: 3 * s,
          backgroundColor: palette.ink,
          transform: [{ rotate: `${angle}deg` }],
        }}
      />

      <At x={sx} y={sy} size={54 * s}>
        <View style={[styles.fill, styles.whiteTile, { borderRadius: 16 * s }]}>
          <Ionicons name="school" size={26 * s} color={palette.ink} />
        </View>
      </At>

      {rings.map((r, i) => (
        <At key={r} x={px} y={py} size={r}>
          <View
            style={[
              styles.fill,
              { borderRadius: r / 2, backgroundColor: i === 0 ? 'rgba(22, 20, 15, 0.07)' : 'rgba(22, 20, 15, 0.11)' },
            ]}
          />
        </At>
      ))}
      <At x={px} y={py} size={68 * s}>
        <View
          style={[
            styles.fill,
            styles.inkTile,
            { borderRadius: 34 * s, borderWidth: 4 * s, borderColor: palette.surface },
          ]}
        >
          <Ionicons name="navigate" size={28 * s} color={palette.yellow} />
        </View>
      </At>
      <View style={[styles.row, { top: py + 44 * s + 6 }]}>
        <Chip icon="location" label="Pickup point" />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  frame: {
    width: '100%',
    overflow: 'hidden',
    pointerEvents: 'none',
    backgroundColor: palette.yellow,
  },
  stage: {
    position: 'absolute',
    top: 0,
    bottom: 0,
  },
  circle: {
    position: 'absolute',
    borderRadius: 9999,
  },
  road: {
    position: 'absolute',
    backgroundColor: palette.ink,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    transform: [{ rotate: '-12deg' }],
  },
  street: {
    position: 'absolute',
    borderRadius: 8,
  },
  fill: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  round: {
    overflow: 'hidden',
  },
  whiteTile: {
    backgroundColor: palette.surface,
    ...shadow.floating,
  },
  inkTile: {
    backgroundColor: palette.ink,
    ...shadow.floating,
  },
  softTile: {
    backgroundColor: palette.yellowSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  vehicle: {
    backgroundColor: palette.yellow,
    borderColor: palette.surface,
    ...shadow.floating,
  },
  row: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 36,
    paddingHorizontal: 12,
    borderRadius: 18,
    backgroundColor: palette.surface,
    ...shadow.floating,
  },
  avatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: palette.yellowSoft,
    borderWidth: 2,
    borderColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileLabel: {
    position: 'absolute',
    bottom: -20,
    left: -20,
    right: -20,
    textAlign: 'center',
    color: palette.ink,
    fontFamily: fonts.semibold,
  },
  card: {
    backgroundColor: palette.surface,
    ...shadow.floating,
  },
  emailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    backgroundColor: palette.surfaceMuted,
  },
  bubble: {
    maxWidth: '86%',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
  },
  bubbleMine: {
    alignSelf: 'flex-end',
    backgroundColor: palette.ink,
    borderBottomRightRadius: 4,
  },
  bubbleTheirs: {
    alignSelf: 'flex-start',
    backgroundColor: palette.yellowSoft,
    borderBottomLeftRadius: 4,
  },
  badge: {
    position: 'absolute',
    backgroundColor: palette.ink,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.floating,
  },
});
