import 'react-native-paper';

declare global {
  namespace ReactNativePaper {
    interface MD3Colors {
      custom: {
        accent: string;
        secondaryText: string;
        success: string;
        border: string;
        primaryGradient: string[];
      };
    }
  }
}