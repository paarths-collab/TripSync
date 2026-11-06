// src/app/(main)/profile.tsx
import { useState, useCallback } from 'react';
import { Alert, StyleSheet, ScrollView, View, StatusBar } from 'react-native';
import { Text, TextInput, Button } from 'react-native-paper';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import ScreenWrapper from '../../components/ScreenWrapper';
import { getMyProfile, updateMyProfile, UserProfile } from '../../services/profileService';
import { useAuth } from '../../context/AuthContext';
import { palette, space, radius, font } from '../../constants/theme';
import {
  Avatar,
  Card,
  EmptyState,
  InfoRow,
  LoadingState,
  ScreenHeader,
  SectionTitle,
} from '../../components/ui';

export default function ProfileScreen() {
  const { signOut } = useAuth();
  
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // State for editable fields
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [bio, setBio] = useState('');
  const [yearOfStudy, setYearOfStudy] = useState('');

  const fetchProfile = useCallback(async () => {
    try {
      if (!profile) setIsLoading(true);
      const profileData = await getMyProfile();
      setProfile(profileData);
      setFullName(profileData.full_name);
      setUsername(profileData.username || '');
      setPhoneNumber(profileData.phone_number || '');
      setBio(profileData.bio || '');
      setYearOfStudy(profileData.year_of_study || '');
    } catch (error: any) {
      Alert.alert('Error Fetching Profile', error.message);
    } finally {
      setIsLoading(false);
    }
  }, [profile]);

  useFocusEffect(useCallback(() => { fetchProfile(); }, []));
  
  const handleSaveChanges = async () => {
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
        Alert.alert('Success', 'Profile updated successfully!');
    } catch (error: any) {
        Alert.alert('Save Failed', error.message);
    } finally {
        setIsSaving(false);
    }
  };

  // Discard unsaved edits and go back to the saved values.
  const handleCancelEdit = () => {
    if (profile) {
      setFullName(profile.full_name);
      setUsername(profile.username || '');
      setPhoneNumber(profile.phone_number || '');
      setBio(profile.bio || '');
      setYearOfStudy(profile.year_of_study || '');
    }
    setIsEditing(false);
  };

  if (isLoading) {
    return (
      <ScreenWrapper>
        <LoadingState label="Loading your profile…" style={styles.fill} />
      </ScreenWrapper>
    );
  }

  if (!profile) {
    return (
      <ScreenWrapper>
        <EmptyState
          icon="person-circle-outline"
          title="Couldn't load your profile"
          body="Check your connection and try again."
          style={styles.fill}
          action={
            <Button mode="contained" onPress={fetchProfile}>
              Try again
            </Button>
          }
        />
      </ScreenWrapper>
    );
  }

  const inputProps = {
    mode: 'outlined' as const,
    style: styles.input,
    outlineColor: palette.border,
    activeOutlineColor: palette.primary,
    outlineStyle: styles.inputOutline,
  };

  return (
    <ScreenWrapper>
      <StatusBar barStyle="dark-content" backgroundColor={palette.background} />
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <ScreenHeader title="Profile" style={styles.screenHeader} />

        {/* Identity card */}
        <Card style={styles.identityCard}>
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
            <View style={styles.metaRow}>
              <Ionicons name="mail-outline" size={14} color={palette.textMuted} />
              <Text style={styles.metaText} numberOfLines={1}>
                {profile.email}
              </Text>
            </View>
            <View style={styles.metaRow}>
              <Ionicons name="school-outline" size={14} color={palette.textMuted} />
              <Text style={styles.metaText} numberOfLines={2}>
                {profile.college_name}
              </Text>
            </View>
          </View>
        </Card>

        {/* Details / edit */}
        <SectionTitle
          title={isEditing ? 'Edit details' : 'Details'}
          style={styles.sectionTitle}
          action={
            isEditing ? null : (
              <Button
                mode="text"
                compact
                onPress={() => setIsEditing(true)}
                icon={({ size, color }) => <Ionicons name="create-outline" size={size} color={color} />}
              >
                Edit
              </Button>
            )
          }
        />

        {isEditing ? (
          <Card style={styles.card}>
            <TextInput
              label="Full name"
              value={fullName}
              onChangeText={setFullName}
              left={<TextInput.Icon icon="account-outline" color={palette.textMuted} />}
              {...inputProps}
            />
            <TextInput
              label="Username"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              left={<TextInput.Icon icon="at" color={palette.textMuted} />}
              {...inputProps}
            />
            <TextInput
              label="Phone number"
              value={phoneNumber}
              onChangeText={setPhoneNumber}
              keyboardType="phone-pad"
              left={<TextInput.Icon icon="phone-outline" color={palette.textMuted} />}
              {...inputProps}
            />
            <TextInput
              label="Year of study"
              value={yearOfStudy}
              onChangeText={setYearOfStudy}
              left={<TextInput.Icon icon="calendar-outline" color={palette.textMuted} />}
              {...inputProps}
            />
            <TextInput
              label="Bio"
              value={bio}
              onChangeText={setBio}
              multiline
              numberOfLines={4}
              left={<TextInput.Icon icon="text" color={palette.textMuted} />}
              {...inputProps}
            />

            <View style={styles.editActions}>
              <Button
                mode="outlined"
                onPress={handleCancelEdit}
                disabled={isSaving}
                style={styles.editActionButton}
                contentStyle={styles.buttonContent}
                textColor={palette.textMuted}
              >
                Cancel
              </Button>
              <Button
                mode="contained"
                onPress={handleSaveChanges}
                loading={isSaving}
                disabled={isSaving}
                style={styles.editActionButton}
                contentStyle={styles.buttonContent}
                labelStyle={styles.buttonLabel}
              >
                Save changes
              </Button>
            </View>
          </Card>
        ) : (
          <Card style={styles.card}>
            <InfoRow icon="person-outline" label="Full name" value={profile.full_name} />
            <View style={styles.divider} />
            <InfoRow icon="at-outline" label="Username" value={profile.username} />
            <View style={styles.divider} />
            <InfoRow icon="call-outline" label="Phone number" value={profile.phone_number} />
            <View style={styles.divider} />
            <InfoRow icon="calendar-outline" label="Year of study" value={profile.year_of_study} />
            <View style={styles.divider} />
            <InfoRow icon="document-text-outline" label="Bio" value={profile.bio} />
          </Card>
        )}

        <Button
          mode="outlined"
          onPress={signOut}
          style={styles.logoutButton}
          contentStyle={styles.buttonContent}
          labelStyle={styles.buttonLabel}
          textColor={palette.danger}
          icon={({ size }) => <Ionicons name="log-out-outline" size={size} color={palette.danger} />}
        >
          Log out
        </Button>
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
    paddingBottom: space.xxxl,
  },
  screenHeader: {
    paddingHorizontal: 0,
  },
  identityCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: space.lg,
    marginTop: space.xs,
  },
  identityText: {
    flex: 1,
    marginLeft: space.md,
  },
  name: {
    fontSize: 20,
    lineHeight: 26,
    fontWeight: font.bold,
    color: palette.text,
  },
  handle: {
    fontSize: 14,
    color: palette.primary,
    fontWeight: font.medium,
    marginTop: 2,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xxs + 2,
    marginTop: space.xxs + 2,
  },
  metaText: {
    flex: 1,
    fontSize: 13,
    color: palette.textMuted,
  },
  sectionTitle: {
    marginTop: space.xl,
    marginBottom: space.xs,
  },
  card: {
    paddingVertical: space.xs,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.border,
    marginLeft: 18 + space.sm,
  },
  input: {
    marginVertical: space.xs,
    backgroundColor: palette.surface,
  },
  inputOutline: {
    borderRadius: radius.md,
  },
  editActions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.sm,
    marginBottom: space.xs,
  },
  editActionButton: {
    flex: 1,
    borderRadius: radius.md,
  },
  logoutButton: {
    marginTop: space.xxl,
    borderRadius: radius.md,
    borderColor: palette.danger,
    borderWidth: 1,
  },
  buttonContent: {
    height: 48,
  },
  buttonLabel: {
    fontSize: 15,
    fontWeight: font.semibold,
  },
});
