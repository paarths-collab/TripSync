import React, { useState, useEffect } from 'react';
import { ScrollView, StyleSheet, View, Alert, TouchableOpacity, KeyboardAvoidingView, Platform } from 'react-native';
import { Text, TextInput, Button, Switch, Chip, Snackbar } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import ScreenWrapper from '../../../components/ScreenWrapper';
import { useAuth } from '../../../context/AuthContext';
import { createServicePost, ServicePostCreateData } from '../../../services/servicesService';
import { CompensationType } from '../../../models/serviceModel';
import { Card, SectionTitle } from '../../../components/ui';
import { palette, space, radius, font } from '../../../constants/theme';

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

  const ToggleButton = ({ label, selected, onPress }: { label: string, selected: boolean, onPress: () => void }) => (
    <TouchableOpacity
      style={[styles.toggleButton, selected && styles.toggleButtonSelected]}
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
    >
      <Ionicons
        name={selected ? "checkmark-circle" : "ellipse-outline"}
        size={20}
        color={selected ? palette.primary : palette.textFaint}
      />
      <Text style={[styles.toggleButtonText, selected && styles.toggleButtonTextSelected]}>{label}</Text>
    </TouchableOpacity>
  );

  const inputProps = {
    mode: 'outlined' as const,
    style: styles.input,
    outlineStyle: styles.inputOutline,
    outlineColor: palette.border,
    activeOutlineColor: palette.primary,
  };

  return (
    <ScreenWrapper>
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
          <Text style={styles.intro}>Fill out the details below to find the help you need.</Text>

          <SectionTitle title="What do you need?" />
          <Card style={styles.section}>
            <TextInput label="Service title" placeholder="e.g. Help with ML project" value={title} onChangeText={setTitle} {...inputProps} />
            <TextInput label="Full description" value={description} onChangeText={setDescription} multiline numberOfLines={5} {...inputProps} style={[styles.input, styles.multiline]} />
            <TextInput
              label="Number of people needed"
              value={teamSize}
              onChangeText={(text) => setTeamSize(text.replace(/[^0-9]/g, ''))}
              keyboardType="number-pad"
              {...inputProps}
              style={[styles.input, styles.lastInput]}
            />
          </Card>

          <SectionTitle title="Compensation" />
          <Card style={styles.section}>
            <View style={styles.compensationContainer}>
              <ToggleButton label="Volunteer" selected={compensationType === CompensationType.VOLUNTEER} onPress={() => setCompensationType(CompensationType.VOLUNTEER)} />
              <ToggleButton label="Fixed price" selected={compensationType === CompensationType.FIXED_PRICE} onPress={() => setCompensationType(CompensationType.FIXED_PRICE)} />
              <ToggleButton label="Hourly rate" selected={compensationType === CompensationType.HOURLY_RATE} onPress={() => setCompensationType(CompensationType.HOURLY_RATE)} />
            </View>
            {(compensationType === CompensationType.FIXED_PRICE || compensationType === CompensationType.HOURLY_RATE) && (
              <TextInput
                label="Amount (₹)"
                value={amount}
                onChangeText={(text) => setAmount(text.replace(/[^0-9.]/g, ''))}
                keyboardType="decimal-pad"
                {...inputProps}
                style={[styles.input, styles.amountInput]}
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
                  <Chip
                    key={tag}
                    mode="flat"
                    selected={isSelected}
                    showSelectedCheck={false}
                    onPress={() => handleTagPress(tag)}
                    style={[styles.chip, isSelected && styles.chipSelected]}
                    textStyle={[styles.chipText, isSelected && styles.chipTextSelected]}
                  >
                    {tag}
                  </Chip>
                );
              })}
            </View>

            <View style={styles.switchContainer}>
              <View style={styles.switchText}>
                <Text style={styles.switchLabel}>Require a resume</Text>
                <Text style={styles.switchHint}>Applicants must attach one to apply.</Text>
              </View>
              <Switch value={requiresResume} onValueChange={setRequiresResume} color={palette.primary} />
            </View>
            <View style={styles.switchContainer}>
              <View style={styles.switchText}>
                <Text style={styles.switchLabel}>Post anonymously</Text>
                <Text style={styles.switchHint}>Your name is hidden on the listing.</Text>
              </View>
              <Switch value={isAnonymous} onValueChange={setIsAnonymous} color={palette.primary} />
            </View>
          </Card>

          <Button
            mode="contained"
            onPress={handleSubmit}
            loading={submissionStatus === 'loading'}
            disabled={submissionStatus === 'loading'}
            style={styles.button}
            buttonColor={palette.primary}
            textColor={palette.onPrimary}
            labelStyle={styles.buttonLabel}
            icon="arrow-right"
            contentStyle={styles.buttonContent}
          >
            Post service
          </Button>
        </ScrollView>
      </KeyboardAvoidingView>

      <Snackbar
        visible={showSuccessSnackbar}
        onDismiss={() => setShowSuccessSnackbar(false)}
        duration={2000}
        style={styles.snackbar}
        action={{
          label: 'View',
          textColor: palette.onPrimary,
          onPress: () => {
            setShowSuccessSnackbar(false);
            router.back();
          },
        }}
      >
        <Text style={styles.snackbarText}>
          ✓ Service posted successfully!
        </Text>
      </Snackbar>
    </ScreenWrapper>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { paddingHorizontal: space.md, paddingTop: space.xs, paddingBottom: space.xxxl },
  intro: { fontSize: 14, lineHeight: 20, color: palette.textMuted, marginBottom: space.lg },
  section: { marginBottom: space.xl },
  input: { backgroundColor: palette.surface, marginBottom: space.sm },
  inputOutline: { borderRadius: radius.md },
  multiline: { minHeight: 120 },
  lastInput: { marginBottom: 0 },
  amountInput: { marginTop: space.sm, marginBottom: 0 },
  compensationContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  toggleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.sm,
    flexGrow: 1,
    flexBasis: '45%',
  },
  toggleButtonSelected: { borderColor: palette.primary, backgroundColor: palette.primarySoft },
  toggleButtonText: { marginLeft: space.xs, fontSize: 14, fontWeight: font.medium, color: palette.text },
  toggleButtonTextSelected: { color: palette.primaryDark, fontWeight: font.semibold },
  helper: { fontSize: 13, color: palette.textMuted, marginBottom: space.sm },
  chipContainer: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  chip: {
    backgroundColor: palette.surfaceMuted,
    borderRadius: radius.pill,
  },
  chipSelected: { backgroundColor: palette.primary },
  chipText: { color: palette.text, fontWeight: font.medium },
  chipTextSelected: { color: palette.onPrimary, fontWeight: font.semibold },
  switchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: space.md,
    marginTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.border,
  },
  switchText: { flex: 1, marginRight: space.sm },
  switchLabel: { fontSize: 15, fontWeight: font.medium, color: palette.text },
  switchHint: { marginTop: 2, fontSize: 13, color: palette.textMuted },
  button: { borderRadius: radius.md },
  buttonContent: { flexDirection: 'row-reverse', paddingVertical: space.xs },
  buttonLabel: { fontWeight: font.semibold, fontSize: 16 },
  snackbar: { backgroundColor: palette.success, borderRadius: radius.md },
  snackbarText: { color: palette.onPrimary, fontWeight: font.semibold },
});
