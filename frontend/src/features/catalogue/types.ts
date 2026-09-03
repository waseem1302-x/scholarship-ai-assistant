export type DegreeLevel = "bachelors" | "masters" | "phd" | "postdoc" | "short_course";
export type FundingType = "full" | "partial" | "tuition_only" | "stipend_only" | "unknown";
export type CatalogueAvailability = "open" | "upcoming" | "all";

export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
  count: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface OpportunitySummary {
  id: string;
  name: string;
  provider_name: string;
  university_name: string | null;
  country: string;
  degree_level: DegreeLevel;
  degree_levels?: DegreeLevel[];
  application_deadline: string | null;
  application_opening_date: string | null;
  application_timezone: string;
  effective_cycle_id: string | null;
  funding_type: FundingType;
  funding_classification?: "fully_funded" | "partial" | "unknown";
  funding_summary: string;
  verification_status: "officially_verified";
  last_verified_at: string | null;
  official_source_url: string;
  application_window_state: "upcoming" | "open" | "closed" | "rolling" | "deadline_unknown";
  source_is_fresh: boolean;
  verification_freshness: "recent" | "recheck_recommended" | "historical";
  funding_display_label: string;
  catalogue_decision_tier: "decision_ready" | "informational_only";
  structured_eligibility_complete: boolean;
}

export type DecisionSummaryState =
  | "confirmed"
  | "unknown"
  | "not_applicable"
  | "stale"
  | "conflicting";

export interface PublicFactScope {
  cycle_id: string | null;
  track_id: string | null;
  institution_id: string | null;
  programme_id: string | null;
  scholarship_programme_id: string | null;
}

export interface PublicEvidenceReference {
  id: string;
  entity_type: string;
  entity_id: string;
  field_path: string;
  source_snapshot_id: string;
  source_title: string;
  source_url: string;
  content_hash: string;
  excerpt: string;
  excerpt_start: number;
  excerpt_end: number;
  last_verified_at: string | null;
  verification_status: "officially_verified";
}

export interface PublicScopedFact {
  id: string;
  scope: PublicFactScope;
  evidence_ids: string[];
}

export interface PublicCycle extends PublicScopedFact {
  label: string | null;
  intake_year: number | null;
  application_opening_date: string | null;
  application_deadline: string | null;
  status: string | null;
  timezone: string | null;
  is_rolling: boolean | null;
}

export interface PublicTrack extends PublicScopedFact {
  code: string;
  parent_track_id: string | null;
  name: string | null;
  track_type: string | null;
  application_method: string | null;
  application_url: string | null;
  status: string | null;
  display_order: number;
}

export interface PublicProgramme extends PublicScopedFact {
  programme_key: string;
  name: string | null;
  programme_type: string | null;
  degree_levels: string[];
  fields_of_study: string[];
  duration: string | null;
  description: string | null;
  application_route_keys: string[];
  display_order: number;
}

export interface PublicEligibility extends PublicScopedFact {
  rule_key: string;
  rule_type: string | null;
  operator: string | null;
  value: Record<string, unknown> | null;
  unit: string | null;
  required: boolean | null;
  condition: string | null;
  is_exclusion: boolean | null;
  critical: boolean | null;
  original_text: string | null;
  notes: string | null;
  display_order: number;
}

export interface PublicDeadline extends PublicScopedFact {
  deadline_type: string | null;
  deadline_at: string | null;
  deadline_text: string | null;
  local_date: string | null;
  precision: string | null;
  timezone: string | null;
  varies_by: string | null;
  label: string | null;
  notes: string | null;
}

export interface PublicFunding extends PublicScopedFact {
  component_type: string | null;
  coverage_status: string | null;
  amount: number | string | null;
  currency: string | null;
  frequency: string | null;
  unit: string | null;
  qualifier: string | null;
  original_text: string | null;
  description: string | null;
}

export interface PublicDocument extends PublicScopedFact {
  document_key: string;
  name: string | null;
  required: boolean | null;
  condition: string | null;
  submission_stage: string | null;
  original_count: number | null;
  copy_count: number | null;
  translation_requirement: string | null;
  certification_requirement: string | null;
  form_year: number | null;
  notes: string | null;
  display_order: number;
}

export interface PublicApplicationStep extends PublicScopedFact {
  step_code: string;
  title: string | null;
  stage_type: string | null;
  required: boolean | null;
  actor_type: string | null;
  actor_name: string | null;
  outcome: string | null;
  original_text: string | null;
  description: string | null;
  application_url: string | null;
  display_order: number;
}

export interface PublicEvent extends PublicScopedFact {
  event_key: string;
  event_type: string | null;
  starts_at: string | null;
  ends_at: string | null;
  date_text: string | null;
  precision: string | null;
  timezone: string | null;
  label: string | null;
  notes: string | null;
  display_order: number;
}

export interface PublicResource extends PublicScopedFact {
  resource_key: string;
  title: string | null;
  resource_type: string | null;
  url: string | null;
  contact_type: string | null;
  organization: string | null;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  original_text: string | null;
  required: boolean | null;
  notes: string | null;
  display_order: number;
}

export interface DecisionSummaryBlock {
  text: string;
  evidence_ids: string[];
  state: DecisionSummaryState;
}

export interface ScholarshipDecisionSummary {
  overview: DecisionSummaryBlock;
  funding: DecisionSummaryBlock;
  eligibility: DecisionSummaryBlock;
  application_route: DecisionSummaryBlock;
}

export interface PublicScholarshipProjection {
  cycle: PublicCycle | null;
  tracks: PublicTrack[];
  programmes: PublicProgramme[];
  eligibility: PublicEligibility[];
  deadlines: PublicDeadline[];
  funding: PublicFunding[];
  documents: PublicDocument[];
  steps: PublicApplicationStep[];
  events: PublicEvent[];
  resources: PublicResource[];
  evidence: PublicEvidenceReference[];
  known_unknowns: string[];
  summary: ScholarshipDecisionSummary | null;
}

export interface OpportunityDetail extends OpportunitySummary {
  projection: PublicScholarshipProjection;
  field_eligibility: string | null;
  nationality_eligibility: string | null;
  intake_year: number | null;
  tuition_coverage: string | null;
  funding_policy?: string | null;
  tuition_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  stipend_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  accommodation_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  travel_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  insurance_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  fees_coverage_status?: "confirmed" | "partial" | "not_covered" | "unknown";
  application_fee_status?: "not_required" | "required" | "waiver_available" | "unknown";
  monthly_stipend_amount: number | null;
  monthly_stipend_currency: string | null;
  accommodation_coverage: string | null;
  travel_allowance: string | null;
  health_insurance: string | null;
  application_fee_info: string | null;
  english_language_requirement: string | null;
  standardized_test_requirement: string | null;
  minimum_academic_requirement: string | null;
  required_documents: string[];
  application_method: string | null;
  application_url: string | null;
  data_confidence: "low" | "medium" | "high";
  notes: string | null;
  eligibility_warnings: string[];
  source: {
    id: string;
    url: string;
    source_type: string;
    title: string;
    relevant_excerpt: string;
    verification_status: "officially_verified";
    last_verified_at: string | null;
  };
}

export interface OpportunitySearchResponse {
  items: OpportunitySummary[];
  pagination: PaginationMeta;
}

export interface CatalogueFilters {
  q: string;
  availability: CatalogueAvailability;
  country: string;
  degree_level: DegreeLevel | "";
  funding_type: FundingType | "";
  field: string;
  nationality: string;
  limit: "10" | "20" | "50";
}

export const defaultCatalogueFilters: CatalogueFilters = {
  q: "",
  availability: "all",
  country: "",
  degree_level: "",
  funding_type: "",
  field: "",
  nationality: "",
  limit: "10",
};
