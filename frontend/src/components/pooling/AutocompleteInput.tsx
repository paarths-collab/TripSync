// src/components/pooling/AutocompleteInput.tsx
import React, { useState, useMemo } from 'react';
import { TextInput } from 'react-native-paper';
import debounce from 'lodash.debounce';
import { getAutocompleteSuggestions, AutocompleteSuggestion } from '../../services/locationService';
import { palette, radius } from '../../constants/theme';

interface AutocompleteInputProps {
  label: string;
  onPlaceSelected: (place: AutocompleteSuggestion) => void;
  /** Optional: callers that render their own suggestion list pass this. */
  onSuggestionsChange?: (suggestions: AutocompleteSuggestion[]) => void;
}

export default function AutocompleteInput({
  label,
  onPlaceSelected,
  onSuggestionsChange,
}: AutocompleteInputProps) {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const debouncedFetchSuggestions = useMemo(
    () =>
      debounce(async (text: string) => {
        if (text.length < 3) {
          onSuggestionsChange?.([]); // Inform parent to clear suggestions
          setIsLoading(false);
          return;
        }
        setIsLoading(true);
        console.log('Fetching suggestions for:', text);
        try {
          const results = await getAutocompleteSuggestions(text);
          console.log('Suggestions received:', results.length, 'results');
          onSuggestionsChange?.(results); // Pass results to parent
        } catch (error) {
          console.error('Error fetching autocomplete suggestions:', error);
          onSuggestionsChange?.([]);
        } finally {
          setIsLoading(false);
        }
      }, 300),
    [onSuggestionsChange]
  );

  const handleTextChange = (text: string) => {
    setQuery(text);
    debouncedFetchSuggestions(text);
  };

  return (
    <TextInput
      label={label || undefined}
      mode="outlined"
      value={query}
      onChangeText={handleTextChange}
      left={<TextInput.Icon icon="magnify" color={palette.textMuted} />}
      right={isLoading ? <TextInput.Icon icon="timer-sand" color={palette.textMuted} /> : null}
      autoFocus={true}
      placeholder="Search for a destination"
      placeholderTextColor={palette.textFaint}
      outlineColor={palette.border}
      activeOutlineColor={palette.primary}
      outlineStyle={{ borderRadius: radius.md }}
      style={{ backgroundColor: palette.surface, fontSize: 15 }}
    />
  );
}
