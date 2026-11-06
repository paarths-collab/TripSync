import apiClient from './api';

// --- DATA STRUCTURES (INTERFACES) ---

export interface ServiceTag {
  id: number;
  name: string;
}

export interface ServicePoster {
  id: number;
  full_name: string;
}

export interface ServicePost {
  id: number;
  title: string;
  description: string;
  poster_user_id: number | null;
  status: 'open' | 'in_progress' | 'completed' | 'cancelled';
  team_size: number;
  deadline?: string;
  compensation_type: 'volunteer' | 'fixed_price' | 'hourly_rate' | 'negotiable';
  compensation_amount?: number;
  requires_resume: boolean;
  requires_cover_letter: boolean;
  is_anonymous: boolean;
  created_at: string;
  poster?: ServicePoster;
  tags: ServiceTag[];
}

export interface ServicePostCreateData {
  title: string;
  description: string;
  team_size: number;
  deadline?: string;
  compensation_type: 'volunteer' | 'fixed_price' | 'hourly_rate' | 'negotiable';
  compensation_amount?: number;
  requires_resume: boolean;
  // --- THIS IS THE FIX ---
  // This field was missing, causing the button to fail.
  requires_cover_letter: boolean;
  is_anonymous: boolean;
  tags: string[];
}

export interface ServiceApplicationCreateData {
  cover_letter?: string;
  resume_url?: string;
  proposed_rate?: number;
}

export interface ServiceApplication {
  id: number;
  status: 'pending' | 'accepted' | 'rejected';
  applicant: ServicePoster;
  service_post: {
    id: number;
    title: string;
  };
  cover_letter?: string;
  resume_url?: string;
  proposed_rate?: number;
  application_date: string;
}


// --- API COMMUNICATION FUNCTIONS ---

export const getAllServicePosts = async (
  searchQuery?: string,
  tags?: string[],
  token?: string | null,
): Promise<ServicePost[]> => {
  try {
    const params = new URLSearchParams();
    if (searchQuery) {
      params.append('search', searchQuery);
    }
    if (tags && tags.length > 0) {
      tags.forEach(tag => params.append('tags', tag));
    }

    const response = await apiClient.get(`/services?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return response.data;
  } catch (error: any) {
    console.error('Get all service posts failed:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to fetch services.');
  }
};

export const getServicePostById = async (postId: number, token?: string | null): Promise<ServicePost> => {
  try {
    const response = await apiClient.get(`/services/${postId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return response.data;
  } catch (error: any) {
    console.error(`Get service post by ID ${postId} failed:`, error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to fetch service details.');
  }
};

export const createServicePost = async (
  token: string,
  postData: ServicePostCreateData
): Promise<ServicePost> => {
  try {
    const response = await apiClient.post('/services', postData, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch (error: any) {
    console.error('Create service post failed:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to post service.');
  }
};

export const applyForService = async (
  token: string,
  postId: number,
  applicationData: ServiceApplicationCreateData
): Promise<ServiceApplication> => {
  try {
    const response = await apiClient.post(`/services/${postId}/apply`, applicationData, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch (error: any) {
    console.error(`Apply for service ${postId} failed:`, error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to apply for service.');
  }
};

export const deleteServicePost = async (token: string, postId: number): Promise<void> => {
  try {
    await apiClient.delete(`/services/${postId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (error: any) {
    console.error('Delete service post failed:', error.response?.data || error.message);
    throw new Error(error.response?.data?.detail || 'Failed to delete post.');
  }
};

export const getApplicationsForPost = async (token: string, postId: number): Promise<ServiceApplication[]> => {
    try {
        const response = await apiClient.get(`/services/${postId}/applications`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        return response.data;
    } catch (error: any) {
        throw new Error(error.response?.data?.detail || 'Failed to fetch applications.');
    }
};

export const getMyServicePosts = async (token: string): Promise<ServicePost[]> => {
    try {
        const response = await apiClient.get('/profile/me/posts', {
            headers: { Authorization: `Bearer ${token}` },
        });
        return response.data;
    } catch (error: any) {
        throw new Error(error.response?.data?.detail || 'Failed to fetch your posts.');
    }
};

export const getMyApplications = async (token: string): Promise<ServiceApplication[]> => {
    try {
        const response = await apiClient.get('/profile/me/applications', {
             headers: { Authorization: `Bearer ${token}` },
        });
        return response.data;
    } catch (error: any) {
        throw new Error(error.response?.data?.detail || 'Failed to fetch your applications.');
    }
};

export const updateApplicationStatus = async (
    token: string,
    applicationId: number,
    status: 'accepted' | 'rejected'
): Promise<ServiceApplication> => {
    try {
        const response = await apiClient.put(`/services/applications/${applicationId}`, 
            { status },
            {
                headers: { Authorization: `Bearer ${token}` },
            }
        );
        return response.data;
    } catch (error: any) {
        console.error(`Update application ${applicationId} to ${status} failed:`, error.response?.data || error.message);
        throw new Error(error.response?.data?.detail || 'Failed to update application status.');
    }
};
