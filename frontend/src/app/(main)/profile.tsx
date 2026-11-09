// src/app/(main)/profile.tsx
import { useState, useCallback, useRef } from 'react';
import { Alert, StyleSheet, ScrollView, View, Pressable } from 'react-native';
import { Text } from 'react-native-paper';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import ScreenWrapper from '../../components/ScreenWrapper';
import { getMyProfile, updateMyProfile, UserProfile } from '../../services/profileService';
import { useAuth } from '../../context/AuthContext';
import { palette, space, radius, type, fonts, layout } from '../../constants/theme';
import {
  Avatar,
  Button,
  Card,
  Divider,
  EmptyState,
  InfoRow,
  LoadingState,
  ScreenHeader,
  SectionTitle,
  Tag,
  TextField,
} from '../../components/ui';

// Outlined destructive action. The shared Button has no outlined-danger variant.
function LogoutButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="Log out"
      style={({ pressed }) => [styles.logoutButton, pressed && styles.logoutButtonPressed]}
    >
      <Ionicons name="log-out-outline" size={20} color={palette.danger} style={styles.logoutIcon} />
      <Text style={styles.logoutLabel}>Log out</Text>
    </Pressable>
  );
}

export default function ProfileScreen() {
  const { signOut } = useAuth();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const hasLoadedRef = useRef(false);

  // State for editable fields
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [bio, setBio] = useState('');
  const [yearOfStudy, setYearOfStudy] = useState('');

  const fillForm = useCallback((data: UserProfile) => {
    setFullName(data.full_name);
    setUsername(data.username || '');
    setPhoneNumber(data.phone_number || '');
    setBio(data.bio || '');
    setYearOfStudy(data.year_of_study || '');
  }, []);

  const fetchProfile = useCallback(async () => {
    try {
      // Only the first load replaces the screen with a spinner.
      if (!hasLoadedRef.current) setIsLoading(true);
      const profileData = await getMyProfile();
      hasLoadedRef.current = true;
      setProfile(profileData);
      fillForm(profileData);
    } catch (error: any) {
      Alert.alert("Couldn't load your profile", error.message);
    } finally {
      setIsLoading(false);
    }
  }, [fillForm]);

  useFocusEffect(
    useCallback(() => {
      fetchProfile();
    }, [fetchProfile])
  );

  // Returns true when the profile was saved.
  const handleSaveChanges = async (): Promise<boolean> => {
    setIsSaving(true);
    try {
      const updatedProfile = await updateMyProfile({
        full_name: fullName,
        username,
        phone_number: phoneNumber,
        bio,
        year_of_study: yearOfStudy,
      });
      setProfile(updatedProfile);
      fillForm(updatedProfile);
      Alert.alert('Saved', 'Your profile has been updated.');
      return true;
    } catch (error: any) {
      Alert.alert("Couldn't save", error.message);
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const handleSavePress = async () => {
    const saved = await handleSaveChanges();
    if (saved) setIsEditing(false);
  };

  // Discard unsaved edits and go back to the saved values.
  const handleCancelEdit = () => {
    if (profile) fillForm(profile);
    setIsEditing(false);
  };

  if (isLoading) {
    return (
      <ScreenWrapper edges={['top', 'left', 'right']}>
        <LoadingState label="Loading your profile…" style={styles.fill} />
      </ScreenWrapper>
    );
  }

  if (!profile) {
    return (
      <ScreenWrapper edges={['top', 'left', 'right']}>
        <EmptyState
          icon="person-circle-outline"
          title="Couldn't load your profile"
          body="Check your connection and try again."
          style={styles.fill}
          action={<Button label="Try again" variant="dark" onPress={fetchProfile} />}
        />
      </ScreenWrapper>
    );
  }

  return (
    <ScreenWrapper edges={['top', 'left', 'right']}>
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
        showsVerticalScrollIndicator={false}
      >
        <ScreenHeader title="Profile" style={styles.screenHeader} />

        {/* Identity card */}
        <Card style={styles.identityCard}>
          <View style={styles.identityTop}>
            <Avatar name={profile.full_name} size={72} />
            <View style={styles.identityText}>
              <Text style={styles.name} numberOfLines={2}>
                {profile.full_name}
              </Text>
              {profile.username ? (
                <Text style={styles.handle} numberOfLines={1}>
                  @{profile.username}
                </Text>
              ) : null}
            </View>
          </View>

          <View style={styles.metaRow}>
            <Ionicons name="school-outline" size={16} color={palette.textMuted} />
            <Text style={styles.metaText} numberOfLines={2}>
              {profile.college_name}
            </Text>
          </View>
          <View style={styles.metaRow}>
            <Ionicons name="mail-outline" size={16} color={palette.textMuted} />
            <Text style={styles.metaText} numberOfLines={1}>
              {profile.email}
            </Text>
          </View>

          {/* Only shown when the server says so; missing means unknown. */}
          {profile.email_verified === true ? (
            <Tag label="College email confirmed" tone="success" icon="checkmark-circle" style={styles.confirmedTag} />
          ) : null}
        </Card>

        {/* Details / edit */}
        <SectionTitle
          title={isEditing ? 'Edit details' : 'Details'}
          style={styles.sectionTitle}
          action={
            isEditing ? null : (
              <Button
                label="Edit"
                variant="ghost"
                size="sm"
                icon="create-outline"
                fullWidth={false}
                onPress={() => setIsEditing(true)}
                accessibilityLabel="Edit details"
              />
            )
          }
        />

        {isEditing ? (
          <Card style={styles.formCard}>
            <TextField label="Full name" icon="person-outline" value={fullName} onChangeText={setFullName} />
            <TextField
              label="Username"
              icon="at-outline"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TextField
              label="Phone number"
              icon="call-outline"
              value={phoneNumber}
              onChangeText={setPhoneNumber}
              keyboardType="phone-pad"
            />
            <TextField label="Year of study" icon="calendar-outline" value={yearOfStudy} onChangeText={setYearOfStudy} />
            <TextField
              label="Bio"
              icon="document-text-outline"
              value={bio}
              onChangeText={setBio}
              multiline
              numberOfLines={4}
              style={styles.bioInput}
            />

            <View style={styles.editActions}>
              <Button
                label="Cancel"
                variant="secondary"
                size="md"
                onPress={handleCancelEdit}
                disabled={isSaving}
                style={styles.editActionButton}
              />
              <Button
                label="Save changes"
                variant="dark"
                size="md"
                onPress={handleSavePress}
                loading={isSaving}
                style={styles.editActionButton}
              />
            </View>
          </Card>
        ) : (
          <Card style={styles.detailsCard}>
            <InfoRow icon="person-outline" label="Full name" value={profile.full_name} />
            <Divider style={styles.divider} />
            <InfoRow icon="at-outline" label="Username" value={profile.username} />
            <Divider style={styles.divider} />
            <InfoRow icon="call-outline" label="Phone number" value={profile.phone_number} />
            <Divider style={styles.divider} />
            <InfoRow icon="calendar-outline" label="Year of study" value={profile.year_of_study} />
            <Divider style={styles.divider} />
            <InfoRow icon="document-text-outline" label="Bio" value={profile.bio} />
          </Card>
        )}

        <LogoutButton onPress={signOut} />
      </ScrollView>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  container: {
    paddingHorizontal: space.lg,
    // Keeps the log-out button scrollable above the floating tab bar.
    paddingBottom: layout.tabBarSpace,
  },
  screenHeader: {
    paddingHorizontal: 0,
  },
  identityCard: {
    padding: space.lg,
    marginTop: space.xs,
  },
  identityTop: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: space.sm,
  },
  identityText: {
    flex: 1,
    marginLeft: space.md,
  },
  name: {
    ...type.title2,
    color: palette.text,
  },
  handle: {
    ...type.label,
    fontFamily: fonts.semibold,
    color: palette.goldText,
    marginTop: 2,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    marginTop: space.xs,
  },
  metaText: {
    ...type.label,
    flex: 1,
    color: palette.textMuted,
  },
  confirmedTag: {
    marginTop: space.sm,
  },
  sectionTitle: {
    marginTop: space.xl,
    marginBottom: space.xs,
  },
  detailsCard: {
    paddingVertical: space.xs,
  },
  formCard: {
    paddingTop: space.md,
    paddingBottom: space.sm,
  },
  divider: {
    marginLeft: 18 + space.sm,
  },
  bioInput: {
    minHeight: 96,
    textAlignVertical: 'top',
  },
  editActions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.xs,
    marginBottom: space.xs,
  },
  editActionButton: {
    flex: 1,
  },
  logoutButton: {
    marginTop: space.xxl,
    height: 56,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: palette.danger,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoutButtonPressed: {
    backgroundColor: palette.dangerSoft,
  },
  logoutIcon: {
    marginRight: space.xs,
  },
  logoutLabel: {
    ...type.button,
    color: palette.danger,
  },
});
