import { ApiError, apiClient } from "../../api/client";
import { emptyProfileDraft, type OpportunityMatch, type ProfileDraft, type SavedOpportunity, type StudentProfile } from "./types";

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
    application_constraints: optional(draft.application_constraints),
    additional_eligibility_information: optional(draft.additional_eligibility_information),
  };
}

export async function getProfile(): Promise<StudentProfile | null> {
  return (await apiClient.request<StudentProfile | null>("/profiles/me")) ?? null;
}

export async function saveProfile(draft: ProfileDraft): Promise<StudentProfile> {
  return apiClient.request<StudentProfile>("/profiles/me", { method: "PUT", body: JSON.stringify(profilePayload(draft)) });
}

export async function getMatches(): Promise<OpportunityMatch[]> {
  const response = await apiClient.request<{ results: OpportunityMatch[] }>("/matches/me");
  return response.results;
}

export function profileRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 400;
}

export async function getSaved(): Promise<SavedOpportunity[]> {
  return apiClient.request<SavedOpportunity[]>("/saved-opportunities");
}

export async function saveOpportunity(opportunityId: string): Promise<SavedOpportunity> {
  return apiClient.request<SavedOpportunity>("/saved-opportunities", { method: "POST", body: JSON.stringify({ opportunity_id: opportunityId, status: "interested" }) });
}

export async function updateSaved(id: string, update: object): Promise<SavedOpportunity> {
  return apiClient.request<SavedOpportunity>(`/saved-opportunities/${id}`, { method: "PATCH", body: JSON.stringify(update) });
}

export async function deleteSaved(id: string): Promise<void> {
  return apiClient.request<void>(`/saved-opportunities/${id}`, { method: "DELETE" });
}
