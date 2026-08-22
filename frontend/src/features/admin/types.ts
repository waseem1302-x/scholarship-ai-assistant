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
}

export interface AdminOpportunity {
  id: string;
  name: string;
  provider_name: string;
  university_name: string | null;
  country: string;
  degree_level: string;
  degree_levels?: string[];
  application_deadline: string | null;
  funding_type: string;
  funding_summary: string;
  verification_status: string;
  last_verified_at: string | null;
  official_source_url: string;
  application_window_state: string;
  source_is_fresh: boolean;
  status: string;
  data_confidence: string;
  source: AdminSource;
  sources: AdminSource[];
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
  aggregate_summary: Record<string, number>;
}

export interface IngestionCandidate {
  id: string;
  status: string;
  proposed_payload: Record<string, unknown> | null;
  validation_errors: string[];
  conflicts: string[];
  opportunity_id: string | null;
  sources: {
    id: string;
    url: string;
    final_url: string | null;
    source_role: "discovered" | "primary" | "supporting" | "crawled";
    is_official: boolean;
    failure_code: string | null;
  }[];
}

export interface IngestionCandidateResponse {
  items: IngestionCandidate[];
  total: number;
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
