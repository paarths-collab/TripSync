import React, { useState, useCallback } from 'react';
import { StyleSheet, FlatList } from 'react-native';
import { Snackbar } from 'react-native-paper';
import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import ScreenWrapper from '../../../../components/ScreenWrapper';
import { useAuth } from '../../../../context/AuthContext';
// --- IMPORT THE NEW UPDATE FUNCTION ---
import { getApplicationsForPost, ServiceApplication, updateApplicationStatus } from '../../../../services/servicesService';
import ApplicantCard from '../../../../components/services/ApplicantCard';
import { EmptyState, LoadingState, SectionTitle, StatusPill } from '../../../../components/ui';
import { palette, space, radius } from '../../../../constants/theme';

export default function ViewApplicantsScreen() {
    const { id } = useLocalSearchParams<{ id: string }>();
    const { token } = useAuth();
    
    const [applications, setApplications] = useState<ServiceApplication[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [updatingApplicationId, setUpdatingApplicationId] = useState<number | null>(null);
    const [snackbar, setSnackbar] = useState({ visible: false, message: '' });

    const fetchData = useCallback(async () => {
        if (!token || !id) return;
        setIsLoading(true);
        try {
            const postId = parseInt(id, 10);
            const fetchedApplications = await getApplicationsForPost(token, postId);
            setApplications(fetchedApplications);
        } catch (error: any) {
            setSnackbar({ visible: true, message: `Error: ${error.message}` });
        } finally {
            setIsLoading(false);
        }
    }, [token, id]);

    useFocusEffect(useCallback(() => {
        fetchData();
    }, [fetchData]));

    const handleStatusChange = async (applicationId: number, status: 'accepted' | 'rejected') => {
        if (!token || updatingApplicationId !== null) return;

        setUpdatingApplicationId(applicationId);
        try {
            await updateApplicationStatus(token, applicationId, status);
            
            // Update the local state to reflect the change
            setApplications(prevApps => 
                prevApps.map(app => 
                    app.id === applicationId 
                        ? { ...app, status } 
                        : app
                )
            );
            
            setSnackbar({ 
                visible: true, 
                message: `Application ${status === 'accepted' ? 'accepted' : 'rejected'} successfully!` 
            });
        } catch (error: any) {
            setSnackbar({ 
                visible: true, 
                message: `Failed to ${status} application: ${error.message}` 
            });
        } finally {
            setUpdatingApplicationId(null);
        }
    };
    
    if (isLoading) {
        return (
            <ScreenWrapper style={styles.center}>
                <LoadingState label="Loading applicants" />
            </ScreenWrapper>
        );
    }

    const pendingCount = applications.filter(app => app.status === 'pending').length;

    return (
        <ScreenWrapper style={styles.container}>
            <FlatList
                data={applications}
                keyExtractor={item => item.id.toString()}
                renderItem={({ item }) => (
                    <ApplicantCard
                        application={item}
                        onAccept={(appId) => handleStatusChange(appId, 'accepted')}
                        onReject={(appId) => handleStatusChange(appId, 'rejected')}
                        isUpdating={updatingApplicationId === item.id}
                    />
                )}
                contentContainerStyle={styles.listContent}
                showsVerticalScrollIndicator={false}
                ListHeaderComponent={
                    applications.length > 0 ? (
                        <SectionTitle
                            title={`${applications.length} ${applications.length === 1 ? 'applicant' : 'applicants'}`}
                            action={
                                pendingCount > 0 ? (
                                    <StatusPill label={`${pendingCount} pending`} tone="warning" />
                                ) : undefined
                            }
                        />
                    ) : null
                }
                ListEmptyComponent={
                    <EmptyState
                        icon="people-outline"
                        title="No applicants yet"
                        body="When users apply to your service, they will appear here."
                    />
                }
            />
            <Snackbar
                visible={snackbar.visible}
                onDismiss={() => setSnackbar({ ...snackbar, visible: false })}
                duration={3000}
                style={styles.snackbar}
            >
                {snackbar.message}
            </Snackbar>
        </ScreenWrapper>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: palette.background },
    listContent: { paddingHorizontal: space.md, paddingTop: space.xs, paddingBottom: space.xxl, flexGrow: 1 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.background },
    snackbar: { borderRadius: radius.md, backgroundColor: palette.ink },
});
