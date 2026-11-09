// src/services/profileService.ts

import apiClient from './api';

// This interface matches the Profile schema from our backend
export interface UserProfile {
  id: number;
  full_name: string;
  email: string;
  college_name: string;
  username?: string;
  phone_number?: string;
  bio?: string;
  year_of_study?: string;
  has_resume: boolean;
  /** True once the college email has been confirmed. Missing or null means unknown. */
  email_verified?: boolean | null;
}

// This interface matches the ProfileUpdate schema
export interface ProfileUpdateData {
    username?: string;
    full_name?: string;
    phone_number?: string;
    bio?: string;
    year_of_study?: string;
}

export const getMyProfile = async (): Promise<UserProfile> => {
  try {
    const response = await apiClient.get('/profile/me');
    return response.data;
  } catch (error: any) {
    console.error('Get profile failed:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to fetch profile.');
  }
};

export const updateMyProfile = async (profileData: ProfileUpdateData): Promise<UserProfile> => {
    try {
        const response = await apiClient.put('/profile/me', profileData);
        return response.data;
    } catch (error: any) {
        console.error('Update profile failed:', error.response?.data || error.message);
        throw new Error(error.response?.data?.detail || 'Failed to update profile.');
    }
};
