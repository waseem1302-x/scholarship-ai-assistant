import type { PaginationMeta } from "../catalogue/types";

export type ReviewAction =
  | "publish"
  | "hold_for_review"
  | "flag_conflict"
  | "request_recheck"
  | "resolve_conflict"
  | "expire"
  | "archive";

export interface AdminSource {
  id: string;
  url: string;
  source_type: string;
  title: string;
  relevant_excerpt: string;
  verification_status: string;
  last_verified_at: string | null;
  hash_algorithm: string;
  content_hash: string | null;
}

export interface AdminOpportunity {
  id: string;
  name: string;
  provider_name: string;
  university_name: string | null;
  programme_family_id?: string | null;
  programme_route_id?: string | null;
  catalogue_family_key?: string | null;
  catalogue_route_key?: string | null;
  catalogue_identity_key?: string | null;
  catalogue_identity_policy_version?: string | null;
  country: string;
  degree_level: string;
  degree_levels?: string[];
  application_deadline: string | null;
  application_opening_date: string | null;
  application_timezone: string;
  intake_year: number | null;
  funding_type: string;
  funding_classification: "fully_funded" | "partial" | "unknown";
  funding_summary: string;
  funding_display_label: string;
  funding_policy: string | null;
  tuition_coverage: string | null;
  tuition_coverage_status: string;
  monthly_stipend_amount: number | null;
  monthly_stipend_currency: string | null;
  stipend_coverage_status: string;
  accommodation_coverage: string | null;
  accommodation_coverage_status: string;
  travel_allowance: string | null;
  travel_coverage_status: string;
  health_insurance: string | null;
  insurance_coverage_status: string;
  fees_coverage_status: string;
  application_fee_info: string | null;
  application_fee_status: string;
  field_eligibility: string | null;
  nationality_eligibility: string | null;
  minimum_academic_requirement: string | null;
  english_language_requirement: string | null;
  standardized_test_requirement: string | null;
  required_documents: string[];
  application_method: string | null;
  application_url: string | null;
  eligibility_warnings: string[];
  eligibility_rules: { rule_type: string; value: unknown; required: boolean }[];
  notes: string | null;
  verification_status: string;
  last_verified_at: string | null;
  official_source_url: string;
  application_window_state: string;
  source_is_fresh: boolean;
  verification_freshness: string;
  catalogue_decision_tier: string;
  structured_eligibility_complete: boolean;
  effective_cycle_id: string | null;
  status: string;
  data_confidence: string;
  source: AdminSource;
  sources: AdminSource[];
  publication_readiness?: PublicationReadiness | null;
}

export interface DataQualityIssue {
  code: string;
  severity: "low" | "medium" | "high";
  message: string;
  opportunity_id: string;
  opportunity_name: string;
  source_id: string | null;
}

export interface ReviewQueueItem {
  opportunity: AdminOpportunity;
  reasons: DataQualityIssue[];
  publication_readiness: PublicationReadiness;
}

export interface PublicationReadinessReason {
  field_path: string;
  reason_code: string;
  message: string;
  source_id: string | null;
}

export interface PublicationReadiness {
  ready: boolean;
  blocking_reasons: PublicationReadinessReason[];
  warnings: PublicationReadinessReason[];
  supported_required_count: number;
  required_count: number;
  evaluated_at: string;
  policy_version: string;
  valid_until: string | null;
  field_results: {
    field_path: string;
    state: string;
    supported: boolean;
    source_ids: string[];
  }[];
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  pagination: PaginationMeta;
}

export interface AdminOpportunitySearchResponse {
  items: AdminOpportunity[];
  pagination: PaginationMeta;
}

export interface AdminOpportunityFilters {
  search_query: string;
  country: string;
  degree_level: string;
  status: string;
  verification_status: string;
  needs_review: "" | "true";
}

export const defaultAdminOpportunityFilters: AdminOpportunityFilters = {
  search_query: "",
  country: "",
  degree_level: "",
  status: "",
  verification_status: "",
  needs_review: "",
};

export interface DataQualityResponse {
  items: DataQualityIssue[];
  pagination: PaginationMeta;
}

export interface ImportResult {
  row_number: number;
  status: string;
  opportunity_id: string | null;
  errors: string[];
  warnings: string[];
}

export interface ImportResponse {
  source_format: "json" | "csv";
  dry_run: boolean;
  total_rows: number;
  imported_count: number;
  duplicate_count: number;
  failed_count: number;
  results: ImportResult[];
}

export interface IngestionRun {
  id: string;
  status: string;
  input_kind: string;
  operator_url: string | null;
  max_candidates: number;
  max_pages_per_candidate: number;
  max_model_calls: number;
  max_input_characters: number;
  max_output_tokens: number;
  max_estimated_cost: number | string;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number | string;
  aggregate_summary: Record<string, number>;
}

export interface DuplicateOpportunitySnapshot {
  id: string;
  name: string;
  provider_name: string;
  programme_family_id: string | null;
  programme_route_id: string | null;
  university_name: string | null;
  country: string;
  degree_level: string;
  cycle_id: string | null;
  catalogue_identity_key: string | null;
  official_source_urls: string[];
}

export interface DuplicateSuggestion {
  id: string;
  opportunity_id: string;
  opportunity_name: string;
  matched_opportunity_id: string;
  matched_opportunity_name: string;
  score: number;
  status: string;
  matching_signals: string[];
  conflicting_fields: Record<string, [string | null, string | null]>;
  opportunity: DuplicateOpportunitySnapshot;
  matched_opportunity: DuplicateOpportunitySnapshot;
  created_at: string;
}

export interface DuplicateSuggestionResponse {
  items: DuplicateSuggestion[];
  pagination: PaginationMeta;
}

export interface AdminOpportunityFamily {
  family_key: string;
  name: string;
  provider_name: string;
  country: string;
  degree_levels: string[];
  variants: ReviewQueueItem[];
}

export interface IngestionSourceArtifact {
  id: string;
  final_url: string;
  content_type: string;
  content_hash: string;
  extraction_method: string;
  byte_count: number;
  character_count: number;
  created_at: string;
}

export interface IngestionCandidateSource {
  id: string;
  url: string;
  final_url: string | null;
  source_role: "discovered" | "primary" | "supporting" | "crawled";
  status: string;
  is_official: boolean;
  trust_tier: number | null;
  classification_reason: string;
  content_type: string | null;
  content_hash: string | null;
  relevant_excerpt: string | null;
  failure_code: string | null;
  fetched_at: string | null;
  artifacts: IngestionSourceArtifact[];
}

export interface IngestionCandidate {
  id: string;
  run_id: string;
  seed_index: number;
  seed_name: string;
  seed_provider: string | null;
  seed_university: string | null;
  seed_country: string | null;
  seed_cycle: string | null;
  seed_intake_year: number | null;
  seed_official_url: string | null;
  identity_hint_is_asserted: boolean;
  seed_keywords: string[];
  status: string;
  proposed_payload: Record<string, unknown> | null;
  acquisition_bundle: Record<string, unknown>;
  validation_errors: string[];
  conflicts: string[];
  duplicate_opportunity_ids: string[];
  failure_code: string | null;
  failure_reason: string | null;
  opportunity_id: string | null;
  sources: IngestionCandidateSource[];
  created_at: string;
  updated_at: string;
}

export interface IngestionCandidateResponse {
  items: IngestionCandidate[];
  total: number;
}

export interface CandidateReviewFact {
  entity_type: string;
  entity_key: string;
  field_path: string;
  value: Record<string, unknown>;
  scope: {
    cycle_key: string | null;
    track_key: string | null;
    institution_key: string | null;
    programme_key: string | null;
    country_code: string | null;
    programme_family_key: string | null;
  };
  source_title: string;
  source_url: string;
  source_checked_at: string | null;
  source_role: IngestionCandidateSource["source_role"];
  source_content_role: string | null;
  authority_tier: "T0" | "T1" | "T2" | "T3" | "unresolved";
  extraction: {
    objective: string;
    schema_version: string;
    prompt_hash: string;
    provider: string;
    model: string;
  } | null;
  evidence: {
    artifact_id: string;
    block_id: string;
    canonicalization_version: string;
    start_offset: number;
    end_offset: number;
    locator: Record<string, number>;
    text: string;
    text_format: "plain_text";
  };
}

export interface CandidateReviewSource {
  id: string;
  title: string;
  url: string;
  final_url: string | null;
  source_role: IngestionCandidateSource["source_role"];
  status: string;
  is_official: boolean;
  trust_tier: number | null;
  failure_code: string | null;
  checked_at: string | null;
  artifacts: {
    id: string;
    final_url: string;
    content_type: string;
    content_hash: string;
    extraction_method: string;
    parser_version: string | null;
    page_count: number | null;
    byte_count: number;
    character_count: number;
    evidence_block_count: number;
    canonicalization_versions: string[];
    ocr_decision: string;
    ocr_reason: string;
    browser_decision: string;
    browser_reason: string;
    acquisition_role: string;
    acquisition_role_classifier_version: string | null;
    acquisition_role_requires_manual_review: boolean;
  }[];
  routing: {
    role: string;
    cycle: string;
    authority_tier: string;
    classifier_version: string;
    deterministic_signals: string[];
    ambiguity_reason: string | null;
    requires_manual_review: boolean;
    applicable_objectives: string[];
  }[];
}

export interface CandidateExtractionAttempt {
  id: string;
  source_id: string;
  provider: string;
  model: string;
  schema_version: string;
  prompt_hash: string;
  status: string;
  error_code: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number | string;
  latency_ms: number;
  created_at: string;
}

export interface CandidateReviewProjection {
  candidate_id: string;
  candidate_status: string;
  proposed_facts: CandidateReviewFact[];
  conflicts: string[];
  rejected_claims: string[];
  missing_mandatory_objectives: string[];
  objective_coverage: Record<string, string>;
  readiness: {
    ready: boolean;
    supported_mandatory_count: number;
    mandatory_count: number;
    blockers: string[];
    warnings: string[];
    source_freshness: "fresh" | "stale" | "unknown";
    evaluated_at: string;
  };
  warnings: string[];
  acquisition_bundle: Record<string, unknown>;
  sources: CandidateReviewSource[];
  extraction_attempts: CandidateExtractionAttempt[];
  duplicate_opportunity_ids: string[];
  decision_history: {
    proposal_hash: string;
    schema_version: string;
    action: string;
    actor_user_id: string;
    reason: string;
    prior_candidate_status: string;
    created_at: string;
  }[];
  audit_history: {
    action: string;
    actor_user_id: string | null;
    reason: string | null;
    created_at: string;
    integrity_hash: string;
  }[];
}

export interface AcquiredCandidateReview {
  candidate: IngestionCandidate;
  projection: CandidateReviewProjection;
}

export interface GraphCitation {
  id: string;
  entity_type: string;
  entity_id: string;
  field_path: string;
  source_title: string;
  source_url: string;
  content_hash: string;
  excerpt: string;
  validator_status: string;
}

export interface OpportunityGraph {
  opportunity_id: string;
  intake_year: number | null;
  degree_levels: string[];
  tracks: { id: string; code: string; name: string; track_type: string }[];
  institutions: { id: string; canonical_name: string; institution_type: string }[];
  institution_participations: {
    id: string;
    track_id: string;
    institution_id: string;
    role: string;
    participation_status: string | null;
    application_url: string | null;
    source_id: string | null;
  }[];
  funding: { id: string; component_type: string; coverage_status: string; description: string | null }[];
  documents: { id: string; name: string; required: boolean }[];
  steps: { id: string; title: string; description: string | null }[];
  citations: GraphCitation[];
}
