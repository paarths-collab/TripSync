import React, { useState, useEffect } from 'react';
import { ScrollView, StyleSheet, View, Alert, Pressable, KeyboardAvoidingView, Platform } from 'react-native';
import { Text, Switch, Snackbar } from 'react-native-paper';
import { useRouter } from 'expo-router';
import ScreenWrapper from '../../../components/ScreenWrapper';
import { useAuth } from '../../../context/AuthContext';
import { createServicePost, ServicePostCreateData } from '../../../services/servicesService';
import { CompensationType } from '../../../models/serviceModel';
import { Button, Card, Divider, IconButton, ScreenHeader, SectionTitle, SegmentedControl, TextField } from '../../../components/ui';
import { palette, space, radius, type, fonts, layout } from '../../../constants/theme';

const COMPENSATION_OPTIONS: { value: CompensationType; label: string }[] = [
  { value: CompensationType.VOLUNTEER, label: 'Volunteer' },
  { value: CompensationType.FIXED_PRICE, label: 'Fixed price' },
  { value: CompensationType.HOURLY_RATE, label: 'Hourly rate' },
];

const AVAILABLE_TAGS = ['Writing', 'Research', 'Python', 'Graphic Design', 'Tutoring', 'Marketing', 'Event Help', 'Data Entry', 'Video Editing'];

export default function CreateServiceScreen() {
  const router = useRouter();
  const { token } = useAuth();

  // Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [teamSize, setTeamSize] = useState('1');
  const [compensationType, setCompensationType] = useState<CompensationType>(CompensationType.VOLUNTEER);
  const [amount, setAmount] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [requiresResume, setRequiresResume] = useState(false);
  const [isAnonymous, setIsAnonymous] = useState(false);

  // New, robust state management for the submission process
  const [submissionStatus, setSubmissionStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [showSuccessSnackbar, setShowSuccessSnackbar] = useState(false);

  // This useEffect hook is the guaranteed fix.
  // It listens for changes in `submissionStatus` and reliably triggers the UI feedback.
  useEffect(() => {
    if (submissionStatus === 'success') {
      setShowSuccessSnackbar(true);
      // Navigate after a short delay to allow user to see the success message
      const timer = setTimeout(() => {
        router.back();
      }, 2000);
      
      // Reset status for the next time the user visits the page
      setSubmissionStatus('idle');
      
      return () => clearTimeout(timer);
    } else if (submissionStatus === 'error') {
      Alert.alert('Post Failed', errorMessage);
      // Reset status so the user can try again
      setSubmissionStatus('idle');
    }
  }, [submissionStatus, errorMessage, router]);

  const handleTagPress = (tag: string) => {
    setSelectedTags(prev => {
      if (prev.includes(tag)) {
        return prev.filter(t => t !== tag);
      }
      if (prev.length < 5) {
        return [...prev, tag];
      }
      Alert.alert("Tag Limit", "You can select a maximum of 5 tags.");
      return prev;
    });
  };
  
  const validateForm = (): boolean => {
    if (title.trim().length < 5) { Alert.alert('Invalid Title', 'Please enter a title with at least 5 characters.'); return false; }
    if (description.trim().length < 15) { Alert.alert('Invalid Description', 'Please provide a more detailed description (at least 15 characters).'); return false; }
    if (teamSize.trim() === '' || parseInt(teamSize, 10) <= 0) { Alert.alert('Invalid Team Size', 'Please enter a number greater than zero for the team size.'); return false; }
    const isPaid = compensationType === CompensationType.FIXED_PRICE || compensationType === CompensationType.HOURLY_RATE;
    if (isPaid) {
      if (amount.trim() === '') { Alert.alert('Amount Required', 'Please enter a price or rate for this service.'); return false; }
      const parsedAmount = parseFloat(amount);
      if (isNaN(parsedAmount) || parsedAmount <= 0) { Alert.alert('Invalid Amount', 'Please enter a valid number greater than zero for the amount.'); return false; }
    }
    return true;
  };

  const handleSubmit = async () => {
    if (submissionStatus === 'loading' || !token || !validateForm()) {
      return;
    }

    setSubmissionStatus('loading');

    const postData: ServicePostCreateData = {
      title: title.trim(),
      description: description.trim(),
      team_size: parseInt(teamSize, 10),
      deadline: undefined,
      compensation_type: compensationType,
      compensation_amount: (compensationType === 'fixed_price' || compensationType === 'hourly_rate') ? parseFloat(amount) : undefined,
      requires_resume: requiresResume,
      requires_cover_letter: true,
      is_anonymous: isAnonymous,
      tags: selectedTags,
    };

    try {
      await createServicePost(token, postData);
      // On success, we just update the state. The useEffect will handle the alert.
      setSubmissionStatus('success');

    } catch (error: any) {
      // On error, we update the state and store the message. useEffect will handle the alert.
      setErrorMessage(error.message || "An unexpected error occurred.");
      setSubmissionStatus('error');
    }
  };

  const handleClose = () => {
    if (router.canGoBack()) router.back();
    else router.navigate('/services' as any);
  };

  const isPaid = compensationType === CompensationType.FIXED_PRICE || compensationType === CompensationType.HOURLY_RATE;

  return (
    <ScreenWrapper edges={['top', 'left', 'right']}>
      <ScreenHeader
        title="New service"
        subtitle="Describe what you need help with."
        right={<IconButton icon="close" label="Close" onPress={handleClose} />}
      />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 0}
      >
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <SectionTitle title="What do you need?" />
          <Card style={styles.section}>
            <TextField
              label="Service title"
              placeholder="e.g. Help with ML project"
              value={title}
              onChangeText={setTitle}
            />
            <TextField
              label="Full description"
              value={description}
              onChangeText={setDescription}
              multiline
              numberOfLines={5}
              style={styles.multiline}
            />
            <TextField
              label="Number of people needed"
              value={teamSize}
              onChangeText={(text) => setTeamSize(text.replace(/[^0-9]/g, ''))}
              keyboardType="number-pad"
              containerStyle={styles.lastField}
            />
          </Card>

          <SectionTitle title="Compensation" />
          <Card style={styles.section}>
            <SegmentedControl
              options={COMPENSATION_OPTIONS}
              value={compensationType}
              onChange={setCompensationType}
            />
            {isPaid && (
              <TextField
                label="Amount (₹)"
                value={amount}
                onChangeText={(text) => setAmount(text.replace(/[^0-9.]/g, ''))}
                keyboardType="decimal-pad"
                containerStyle={styles.amountField}
              />
            )}
          </Card>

          <SectionTitle title="Skills & requirements" />
          <Card style={styles.section}>
            <Text style={styles.helper}>Select up to 5 relevant tags.</Text>
            <View style={styles.chipContainer}>
              {AVAILABLE_TAGS.map(tag => {
                const isSelected = selectedTags.includes(tag);
                return (
                  <Pressable
                    key={tag}
                    onPress={() => handleTagPress(tag)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: isSelected }}
                    style={({ pressed }) => [styles.chip, isSelected && styles.chipSelected, pressed && styles.chipPressed]}
                  >
                    <Text style={[styles.chipText, isSelected && styles.chipTextSelected]}>{tag}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Divider style={styles.switchDivider} />
            <View style={styles.switchContainer}>
              <View style={styles.switchText}>
                <Text style={styles.switchLabel}>Require a resume</Text>
                <Text style={styles.switchHint}>Applicants must attach one to apply.</Text>
              </View>
              <Switch value={requiresResume} onValueChange={setRequiresResume} color={palette.ink} />
            </View>
            <Divider style={styles.switchDivider} />
            <View style={styles.switchContainer}>
              <View style={styles.switchText}>
                <Text style={styles.switchLabel}>Post anonymously</Text>
                <Text style={styles.switchHint}>Your name is hidden on the listing.</Text>
              </View>
              <Switch value={isAnonymous} onValueChange={setIsAnonymous} color={palette.ink} />
            </View>
          </Card>

          <Button
            label="Post service"
            variant="dark"
            iconRight="arrow-forward"
            onPress={handleSubmit}
            loading={submissionStatus === 'loading'}
          />
        </ScrollView>
      </KeyboardAvoidingView>

      <Snackbar
        visible={showSuccessSnackbar}
        onDismiss={() => setShowSuccessSnackbar(false)}
        duration={2000}
        wrapperStyle={styles.snackbarWrapper}
        style={styles.snackbar}
        action={{
          label: 'View',
          textColor: palette.yellow,
          onPress: () => {
            setShowSuccessSnackbar(false);
            router.back();
          },
        }}
      >
        <Text style={styles.snackbarText}>Service posted</Text>
      </Snackbar>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: {
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
    // Clears the floating tab bar where it shows (Android pushes this screen inside the tab).
    paddingBottom: layout.tabBarSpace,
  },
  section: { marginBottom: space.xl },
  multiline: { minHeight: 120, textAlignVertical: 'top' },
  lastField: { marginBottom: 0 },
  amountField: { marginTop: space.md, marginBottom: 0 },
  helper: { ...type.label, color: palette.textMuted, marginBottom: space.sm },
  chipContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  chip: {
    height: 36,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: palette.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipSelected: { backgroundColor: palette.yellow },
  chipPressed: { opacity: 0.85 },
  chipText: { ...type.label, fontFamily: fonts.medium, color: palette.ink },
  chipTextSelected: { fontFamily: fonts.semibold, color: palette.onYellow },
  switchDivider: { marginTop: space.md },
  switchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: space.md,
  },
  switchText: { flex: 1, marginRight: space.sm },
  switchLabel: { ...type.bodyStrong, color: palette.text },
  switchHint: { ...type.label, marginTop: 2, color: palette.textMuted },
  snackbarWrapper: { bottom: layout.tabBarSpace },
  snackbar: { backgroundColor: palette.ink, borderRadius: radius.md },
  snackbarText: { ...type.label, fontFamily: fonts.semibold, color: palette.onPrimary },
});
