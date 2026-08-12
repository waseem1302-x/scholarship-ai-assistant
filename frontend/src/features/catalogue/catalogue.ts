import { ApiError, apiClient } from "../../api/client";

import {
  defaultCatalogueFilters,
  type CatalogueFilters,
  type OpportunityDetail,
  type OpportunitySearchResponse,
} from "./types";

export function filtersFromSearch(search: URLSearchParams): CatalogueFilters {
  const limit = search.get("limit");
  const degreeLevel = search.get("degree_level");
  const fundingType = search.get("funding_type");
  return {
    country: search.get("country") ?? defaultCatalogueFilters.country,
    degree_level:
      degreeLevel === "bachelors" || degreeLevel === "masters" || degreeLevel === "phd" || degreeLevel === "postdoc" || degreeLevel === "short_course"
        ? degreeLevel
        : "",
    funding_type:
      fundingType === "full" || fundingType === "partial" || fundingType === "tuition_only" || fundingType === "stipend_only" || fundingType === "unknown"
        ? fundingType
        : "",
    field: search.get("field") ?? defaultCatalogueFilters.field,
    nationality: search.get("nationality") ?? defaultCatalogueFilters.nationality,
    limit: limit === "20" || limit === "50" ? limit : "10",
  };
}

export function catalogueSearch(filters: CatalogueFilters, offset = 0): URLSearchParams {
  const params = new URLSearchParams({ open_now: "true", limit: filters.limit, offset: String(offset) });
  for (const [key, value] of Object.entries(filters)) {
    if (key !== "limit" && value) {
      params.set(key, value);
    }
  }
  return params;
}

export function readableValue(value: string): string {
  return value.replaceAll("_", " ");
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "Not stated";
  }
  return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(
    new Date(value),
  );
}

export function deadlineLabel(value: string | null): string {
  if (!value) {
    return "Deadline varies";
  }
  const days = Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000);
  if (days < 0) {
    return `Closed ${formatDate(value)}`;
  }
  if (days <= 30) {
    return `${days} days left`;
  }
  return `Deadline ${formatDate(value)}`;
}

export async function searchOpportunities(filters: CatalogueFilters, offset: number) {
  return apiClient.request<OpportunitySearchResponse>(`/opportunities?${catalogueSearch(filters, offset)}`);
}

export async function getOpportunity(id: string) {
  return apiClient.request<OpportunityDetail>(`/opportunities/${id}`);
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
