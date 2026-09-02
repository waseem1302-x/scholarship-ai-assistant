import type { OpportunitySummary } from "../catalogue/types";

export type TestStatus = "unknown" | "not_taken" | "planned" | "taken" | "not_required";

export interface StudentProfile {
  id: string;
  user_id: string;
  nationality: string | null;
  nationality_code: string | null;
  country_of_residence: string | null;
  country_of_residence_code: string | null;
  current_education_level: string | null;
  target_degree_level: string | null;
  intended_field: string | null;
  intended_field_taxonomy: string | null;
  intended_field_detail: string | null;
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
  preferred_destination_country_codes: string[];
  preferred_study_mode: string | null;
  target_intake: string | null;
  target_intake_year: number | null;
  application_constraints: string | null;
  additional_eligibility_information: string | null;
  profile_completeness: number;
  missing_recommended_fields: string[];
  completeness_context: string;
  version: number;
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
  fit_band: string;
  display_label: string;
  eligibility_status: string;
  fit_score: number | null;
  preference_fit: number | null;
  evidence_completeness: number;
  profile_completeness: number;
  confidence: string;
  confidence_factors: string[];
  eligibility_failures: string[];
  preference_mismatches: string[];
  missing_information: string[];
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

export type CommandLifecycle = "saved" | "preparing" | "ready_to_submit" | "submitted" | "decision_received" | "accepted" | "declined" | "withdrawn";
export type TaskStatus = "todo" | "in_progress" | "blocked" | "completed" | "dismissed";
export type DeadlineUrgency = "upcoming" | "due_soon" | "overdue" | "deadline_changed" | "deadline_uncertain";

export interface ApplicationTask {
  id: string; category: string; title: string; status: TaskStatus; priority: string;
  due_at: string | null; source_id: string | null; source_excerpt_id: string | null;
  is_generated: boolean; completion_evidence: string | null; completed_at: string | null; notes: string | null;
}
export interface ApplicationReminder { id: string; task_id: string | null; scheduled_at: string; timezone: string; message: string | null; status: string; delivered_at: string | null; read_at: string | null; }
export interface ApplicationDocument {
  id: string; task_id: string | null; name: string; is_required: boolean; file_name: string | null;
  content_type: string | null; size_bytes: number | null; version_label: string | null;
  expires_at: string | null; reviewed_at: string | null; is_complete: boolean;
}
export interface ApplicationEvent { id: string; event_type: string; metadata_json: Record<string, unknown>; created_at: string; }
export interface Application {
  id: string; lifecycle: CommandLifecycle; official_deadline: string | null; official_deadline_timezone: string; official_deadline_state: "known" | "changed" | "uncertain";
  personal_deadline: string | null; personal_deadline_timezone: string; deadline_urgency: DeadlineUrgency;
  notes: string | null; submitted_at: string | null; version: number; opportunity: OpportunitySummary;
  tasks: ApplicationTask[]; reminders: ApplicationReminder[]; documents: ApplicationDocument[];
}
export interface CommandCentre { urgent_tasks: ApplicationTask[]; blocked_tasks: ApplicationTask[]; blocked_applications: Application[]; approaching_deadlines: Application[]; submitted_applications: Application[]; upcoming_reminders: ApplicationReminder[]; recently_changed_opportunities: Application[]; }

export const emptyProfileDraft: ProfileDraft = {
  nationality: "", country_of_residence: "", current_education_level: "", target_degree_level: "", intended_field: "", academic_discipline: "", cgpa: "", percentage: "", grading_scale: "", english_test_status: "unknown", ielts_score: "", toefl_score: "", duolingo_score: "", gre_status: "unknown", gre_score: "", work_experience_months: "", research_experience: "", publications: "", leadership_experience: "", financial_need: "", preferred_destination_countries: "", preferred_study_mode: "", target_intake: "", target_intake_year: "", application_constraints: "", additional_eligibility_information: "",
};
