import React, { useState } from 'react';
import { View, StyleSheet, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { Modal, Portal, Text, Button, TextInput } from 'react-native-paper';
import { useAuth } from '../../context/AuthContext';
import { applyForService, ServiceApplicationCreateData, ServicePost } from '../../services/servicesService';
import { IconBadge } from '../ui';
import { palette, space, radius, font, shadow } from '../../constants/theme';

interface ApplyModalProps {
  visible: boolean;
  onDismiss: () => void;
  post: ServicePost;
  onApplicationSuccess: () => void;
}

export default function ApplyModal({ visible, onDismiss, post, onApplicationSuccess }: ApplyModalProps) {
  const { token } = useAuth();
  const [coverLetter, setCoverLetter] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async () => {
    if (!token) {
      Alert.alert('Authentication Error', 'You must be logged in to apply.');
      return;
    }
    if (post.requires_cover_letter && coverLetter.trim().length < 10) {
      Alert.alert('Message Required', 'Please provide a brief message (at least 10 characters) explaining your interest.');
      return;
    }

    setIsLoading(true);
    try {
      const applicationData: ServiceApplicationCreateData = {
        cover_letter: coverLetter,
      };
      await applyForService(token, post.id, applicationData);
      onApplicationSuccess();
    } catch (error: any) {
      Alert.alert('Application Failed', error.message || 'An unknown error occurred.');
      // Only set loading to false on error, so the user can try again
      setIsLoading(false);
    }
  };

  const handleDismiss = () => {
    setCoverLetter('');
    setIsLoading(false);
    onDismiss();
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={handleDismiss}
        style={styles.modal}
        contentContainerStyle={styles.container}
      >
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <IconBadge icon="document-text-outline" size={44} />
            <View style={styles.headerText}>
              <Text style={styles.title}>Apply for service</Text>
              <Text style={styles.postTitle} numberOfLines={1}>{post.title}</Text>
            </View>
          </View>

          <Text style={styles.subtitle}>
            {post.requires_cover_letter
              ? "The poster requires a message for this service."
              : "You can include an optional message to the poster."}
          </Text>

          <TextInput
            label="Your message"
            value={coverLetter}
            onChangeText={setCoverLetter}
            mode="outlined"
            multiline
            numberOfLines={6}
            style={styles.input}
            outlineStyle={styles.inputOutline}
            outlineColor={palette.border}
            activeOutlineColor={palette.primary}
            placeholder="Introduce yourself and your relevant skills..."
          />

          <Button
            mode="contained"
            onPress={handleSubmit}
            loading={isLoading}
            disabled={isLoading}
            style={styles.button}
            contentStyle={styles.buttonContent}
            labelStyle={styles.buttonLabel}
            buttonColor={palette.primary}
            textColor={palette.onPrimary}
            icon="send-outline"
          >
            Submit application
          </Button>
          <Button
            onPress={handleDismiss}
            disabled={isLoading}
            style={styles.cancelButton}
            textColor={palette.textMuted}
          >
            Cancel
          </Button>
        </KeyboardAvoidingView>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modal: {
    justifyContent: 'flex-end',
  },
  container: {
    backgroundColor: palette.surface,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.xxl,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    marginBottom: space.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: space.md,
  },
  headerText: {
    flex: 1,
    marginLeft: space.sm,
  },
  title: {
    fontSize: 20,
    fontWeight: font.bold,
    color: palette.text,
  },
  postTitle: {
    marginTop: 2,
    fontSize: 14,
    color: palette.textMuted,
  },
  subtitle: {
    marginBottom: space.md,
    fontSize: 14,
    lineHeight: 20,
    color: palette.textMuted,
  },
  input: {
    marginBottom: space.lg,
    backgroundColor: palette.surface,
    minHeight: 132,
  },
  inputOutline: {
    borderRadius: radius.md,
  },
  button: {
    borderRadius: radius.md,
  },
  buttonContent: {
    paddingVertical: space.xxs + 2,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: font.semibold,
  },
  cancelButton: {
    marginTop: space.xs,
    borderRadius: radius.md,
  },
});
