import { ApiError, apiClient } from "../../api/client";
import { emptyProfileDraft, type Application, type ApplicationDocument, type ApplicationEvent, type ApplicationReminder, type ApplicationTask, type CommandCentre, type OpportunityMatch, type ProfileDraft, type StudentProfile } from "./types";

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

export function listFromText(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function optional(value: string): string | null {
  return value.trim() || null;
}

function numeric(value: string): number | null {
  const number = Number(value);
  return value.trim() && Number.isFinite(number) ? number : null;
}

export function draftFromProfile(profile: StudentProfile | null): ProfileDraft {
  if (!profile) return { ...emptyProfileDraft };
  const draft = { ...emptyProfileDraft };
  const mutableDraft = draft as Record<string, string>;
  for (const key of Object.keys(draft) as (keyof ProfileDraft)[]) {
    const profileValue = profile[key as keyof StudentProfile];
    if (Array.isArray(profileValue)) mutableDraft[key] = profileValue.join(", ");
    else if (profileValue !== null && profileValue !== undefined) mutableDraft[key] = String(profileValue);
  }
  return draft;
}

export function profilePayload(draft: ProfileDraft) {
  return {
    nationality: optional(draft.nationality),
    country_of_residence: optional(draft.country_of_residence),
    current_education_level: optional(draft.current_education_level),
    target_degree_level: optional(draft.target_degree_level),
    intended_field: optional(draft.intended_field),
    academic_discipline: optional(draft.academic_discipline),
    cgpa: numeric(draft.cgpa),
    percentage: numeric(draft.percentage),
    grading_scale: numeric(draft.grading_scale),
    english_test_status: draft.english_test_status,
    ielts_score: draft.english_test_status === "taken" ? numeric(draft.ielts_score) : null,
    toefl_score: draft.english_test_status === "taken" ? numeric(draft.toefl_score) : null,
    duolingo_score: draft.english_test_status === "taken" ? numeric(draft.duolingo_score) : null,
    gre_status: draft.gre_status,
    gre_score: draft.gre_status === "taken" ? numeric(draft.gre_score) : null,
    work_experience_months: numeric(draft.work_experience_months),
    research_experience: optional(draft.research_experience),
    publications: listFromText(draft.publications),
    leadership_experience: optional(draft.leadership_experience),
    financial_need: optional(draft.financial_need),
    preferred_destination_countries: listFromText(draft.preferred_destination_countries),
    preferred_study_mode: optional(draft.preferred_study_mode),
    target_intake: optional(draft.target_intake),
    target_intake_year: numeric(draft.target_intake_year),
    application_constraints: optional(draft.application_constraints),
    additional_eligibility_information: optional(draft.additional_eligibility_information),
  };
}

export async function getProfile(signal?: AbortSignal): Promise<StudentProfile | null> {
  return (await apiClient.request<StudentProfile | null>("/profiles/me", { signal })) ?? null;
}

export async function saveProfile(draft: ProfileDraft, currentProfile?: StudentProfile | null): Promise<StudentProfile> {
  const payload = { ...profilePayload(draft), ...(currentProfile ? { expected_version: currentProfile.version } : {}) };
  return apiClient.request<StudentProfile>("/profiles/me", { method: "PUT", body: JSON.stringify(payload) });
}

export async function getMatches(signal?: AbortSignal): Promise<OpportunityMatch[]> {
  const response = await apiClient.request<{ results: OpportunityMatch[] }>("/matches/me", { signal });
  return response.results;
}

export function profileRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 400;
}

export async function createApplication(opportunityId: string): Promise<Application> {
  return apiClient.request<Application>("/applications", { method: "POST", body: JSON.stringify({ opportunity_id: opportunityId }) });
}

export async function getApplications(signal?: AbortSignal): Promise<Application[]> {
  return (await apiClient.request<{ items: Application[] }>("/applications", { signal })).items;
}

export async function getApplication(id: string, signal?: AbortSignal): Promise<Application> {
  return apiClient.request<Application>(`/applications/${id}`, { signal });
}

export async function getApplicationEvents(id: string, signal?: AbortSignal): Promise<ApplicationEvent[]> {
  return apiClient.request<ApplicationEvent[]>(`/applications/${id}/events`, { signal });
}

export async function getCommandCentre(signal?: AbortSignal): Promise<CommandCentre> {
  return apiClient.request<CommandCentre>("/applications/command-centre", { signal });
}

export async function updateApplication(id: string, update: object): Promise<Application> {
  return apiClient.request<Application>(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(update) });
}

export async function updateApplicationTask(applicationId: string, taskId: string, update: object): Promise<Application> {
  await apiClient.request(`/applications/${applicationId}/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(update) });
  return apiClient.request<Application>(`/applications/${applicationId}`);
}

export async function createApplicationTask(applicationId: string, task: object): Promise<ApplicationTask> {
  return apiClient.request<ApplicationTask>(`/applications/${applicationId}/tasks`, { method: "POST", body: JSON.stringify(task) });
}

export async function createApplicationReminder(applicationId: string, reminder: object): Promise<ApplicationReminder> {
  return apiClient.request<ApplicationReminder>(`/applications/${applicationId}/reminders`, { method: "POST", body: JSON.stringify(reminder) });
}

export async function updateApplicationReminder(applicationId: string, reminderId: string, update: object): Promise<ApplicationReminder> {
  return apiClient.request<ApplicationReminder>(`/applications/${applicationId}/reminders/${reminderId}`, { method: "PATCH", body: JSON.stringify(update) });
}

export async function getNotificationPreference(signal?: AbortSignal): Promise<{ in_app_enabled: boolean }> {
  return apiClient.request<{ in_app_enabled: boolean }>("/applications/notification-preferences", { signal });
}

export async function updateNotificationPreference(inAppEnabled: boolean): Promise<{ in_app_enabled: boolean }> {
  return apiClient.request<{ in_app_enabled: boolean }>("/applications/notification-preferences", { method: "PUT", body: JSON.stringify({ in_app_enabled: inAppEnabled }) });
}

export async function createApplicationDocument(applicationId: string, document: object): Promise<ApplicationDocument> {
  return apiClient.request<ApplicationDocument>(`/applications/${applicationId}/documents`, { method: "POST", body: JSON.stringify(document) });
}

export async function updateApplicationDocument(applicationId: string, documentId: string, update: object): Promise<ApplicationDocument> {
  return apiClient.request<ApplicationDocument>(`/applications/${applicationId}/documents/${documentId}`, { method: "PATCH", body: JSON.stringify(update) });
}

export async function exportApplicationData(): Promise<object> {
  return apiClient.request<object>("/applications/export");
}

export async function deleteApplicationData(): Promise<void> {
  return apiClient.request<void>("/applications/data", { method: "DELETE" });
}
