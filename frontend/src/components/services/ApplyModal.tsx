import React, { useState } from 'react';
import { View, StyleSheet, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { Modal, Portal, Text } from 'react-native-paper';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { applyForService, ServiceApplicationCreateData, ServicePost } from '../../services/servicesService';
import { Button, IconBadge, TextField } from '../ui';
import { palette, space, radius, type, shadow } from '../../constants/theme';

interface ApplyModalProps {
  visible: boolean;
  onDismiss: () => void;
  post: ServicePost;
  onApplicationSuccess: () => void;
}

export default function ApplyModal({ visible, onDismiss, post, onApplicationSuccess }: ApplyModalProps) {
  const { token } = useAuth();
  const insets = useSafeAreaInsets();
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
        contentContainerStyle={[styles.container, { paddingBottom: Math.max(insets.bottom, space.md) + space.md }]}
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

          <TextField
            label="Your message"
            value={coverLetter}
            onChangeText={setCoverLetter}
            multiline
            numberOfLines={6}
            style={styles.input}
            containerStyle={styles.inputContainer}
            placeholder="Introduce yourself and your relevant skills…"
          />

          <Button
            label="Send application"
            variant="dark"
            icon="send"
            onPress={handleSubmit}
            loading={isLoading}
          />
          <Button
            label="Cancel"
            variant="ghost"
            size="md"
            onPress={handleDismiss}
            disabled={isLoading}
            style={styles.cancelButton}
          />
        </KeyboardAvoidingView>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modal: {
    justifyContent: 'flex-end',
    // Paper insets the modal by the safe area; let the sheet reach the bottom edge
    // and pad its content instead.
    marginBottom: 0,
  },
  container: {
    backgroundColor: palette.surface,
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    ...shadow.raised,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 5,
    borderRadius: 3,
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
    ...type.title2,
    color: palette.text,
  },
  postTitle: {
    ...type.label,
    marginTop: 2,
    color: palette.textMuted,
  },
  subtitle: {
    ...type.body,
    fontSize: 14,
    lineHeight: 20,
    marginBottom: space.md,
    color: palette.textMuted,
  },
  inputContainer: {
    marginBottom: space.lg,
  },
  input: {
    minHeight: 120,
    textAlignVertical: 'top',
  },
  cancelButton: {
    marginTop: space.xs,
  },
});
