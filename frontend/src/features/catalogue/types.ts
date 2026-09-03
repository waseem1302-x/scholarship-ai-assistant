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

export interface OpportunityDetail extends OpportunitySummary {
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
