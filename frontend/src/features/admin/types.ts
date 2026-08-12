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
