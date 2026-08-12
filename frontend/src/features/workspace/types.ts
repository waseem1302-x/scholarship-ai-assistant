import type { OpportunitySummary } from "../catalogue/types";

export type TestStatus = "unknown" | "not_taken" | "planned" | "taken" | "not_required";
export type ApplicationStatus =
  | "interested"
  | "researching"
  | "preparing_documents"
  | "waiting_for_recommendation"
  | "ready_to_apply"
  | "submitted"
  | "interview_stage"
  | "accepted"
  | "rejected"
  | "withdrawn"
  | "expired";

export interface StudentProfile {
  id: string;
  user_id: string;
  nationality: string | null;
  country_of_residence: string | null;
  current_education_level: string | null;
  target_degree_level: string | null;
  intended_field: string | null;
  academic_discipline: string | null;
  cgpa: number | null;
  percentage: number | null;
  grading_scale: number | null;
  english_test_status: TestStatus;
  ielts_score: number | null;
  toefl_score: number | null;
  duolingo_score: number | null;
  gre_status: TestStatus;
  gre_score: number | null;
  work_experience_months: number | null;
  research_experience: string | null;
  publications: string[];
  leadership_experience: string | null;
  financial_need: string | null;
  preferred_destination_countries: string[];
  preferred_study_mode: string | null;
  target_intake: string | null;
  target_intake_year: number | null;
  application_constraints: string | null;
  additional_eligibility_information: string | null;
  profile_completeness: number;
  missing_recommended_fields: string[];
}

export interface ProfileDraft {
  nationality: string;
  country_of_residence: string;
  current_education_level: string;
  target_degree_level: string;
  intended_field: string;
  academic_discipline: string;
  cgpa: string;
  percentage: string;
  grading_scale: string;
  english_test_status: TestStatus;
  ielts_score: string;
  toefl_score: string;
  duolingo_score: string;
  gre_status: TestStatus;
  gre_score: string;
  work_experience_months: string;
  research_experience: string;
  publications: string;
  leadership_experience: string;
  financial_need: string;
  preferred_destination_countries: string;
  preferred_study_mode: string;
  target_intake: string;
  target_intake_year: string;
  application_constraints: string;
  additional_eligibility_information: string;
}

export interface OpportunityMatch {
  opportunity: OpportunitySummary;
  match_score: number;
  score_label: string;
  eligibility_status: string;
  fit_score: number | null;
  evidence_completeness: number;
  confidence: string;
  failed_criteria: string[];
  unknown_criteria: string[];
  warnings: string[];
  matcher_version: string;
  explanation: {
    satisfied: string[];
    missing: string[];
    uncertain: string[];
    next_steps: string[];
  };
  disclaimer: string;
}

export interface MatchListResponse {
  profile_id: string;
  results: OpportunityMatch[];
}

export interface ChecklistItem {
  name: string;
  is_complete: boolean;
  notes: string | null;
}

export interface SavedOpportunity {
  id: string;
  status: ApplicationStatus;
  personal_notes: string | null;
  personal_deadline: string | null;
  document_checklist: ChecklistItem[];
  recommendation_letters: ChecklistItem[];
  test_requirements: ChecklistItem[];
  submitted_at: string | null;
  outcome_notes: string | null;
  opportunity: OpportunitySummary;
}

export const applicationStatuses: ApplicationStatus[] = [
  "interested", "researching", "preparing_documents", "waiting_for_recommendation", "ready_to_apply",
  "submitted", "interview_stage", "accepted", "rejected", "withdrawn", "expired",
];

export const emptyProfileDraft: ProfileDraft = {
  nationality: "", country_of_residence: "", current_education_level: "", target_degree_level: "", intended_field: "", academic_discipline: "", cgpa: "", percentage: "", grading_scale: "", english_test_status: "unknown", ielts_score: "", toefl_score: "", duolingo_score: "", gre_status: "unknown", gre_score: "", work_experience_months: "", research_experience: "", publications: "", leadership_experience: "", financial_need: "", preferred_destination_countries: "", preferred_study_mode: "", target_intake: "", target_intake_year: "", application_constraints: "", additional_eligibility_information: "",
};
