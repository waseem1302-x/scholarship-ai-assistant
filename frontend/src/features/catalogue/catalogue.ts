import { ApiError, apiClient } from "../../api/client";

import {
  defaultCatalogueFilters,
  type CatalogueAvailability,
  type CatalogueFilters,
  type OpportunityDetail,
  type OpportunityFamily,
  type OpportunitySearchResponse,
} from "./types";

export function filtersFromSearch(search: URLSearchParams): CatalogueFilters {
  const limit = search.get("limit");
  const availability = search.get("availability");
  const degreeLevel = search.get("degree_level");
  const fundingType = search.get("funding_type");
  return {
    availability:
      availability === "open" || availability === "upcoming" || availability === "all"
        ? availability
        : defaultCatalogueFilters.availability,
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
  const params = new URLSearchParams({
    availability: filters.availability,
    limit: filters.limit,
    offset: String(offset),
  });
  if (filters.availability === "open") {
    params.set("open_now", "true");
  }
  if (filters.availability === "upcoming") {
    params.set("application_window_state", "upcoming");
  }
  for (const [key, value] of Object.entries(filters)) {
    if (key !== "availability" && key !== "limit" && value) {
      params.set(key, value);
    }
  }
  return params;
}

export function availabilityLabel(availability: CatalogueAvailability): string {
  if (availability === "open") return "open opportunities";
  if (availability === "upcoming") return "upcoming opportunities";
  return "verified opportunities";
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

export async function searchOpportunities(filters: CatalogueFilters, offset: number, signal?: AbortSignal) {
  return apiClient.request<OpportunitySearchResponse>(`/opportunities?${catalogueSearch(filters, offset)}`, { signal });
}

export async function getOpportunity(id: string, signal?: AbortSignal) {
  return apiClient.request<OpportunityDetail>(`/opportunities/${id}`, { signal });
}

export async function getOpportunityFamily(id: string, signal?: AbortSignal) {
  return apiClient.request<OpportunityFamily>(`/opportunities/${id}/family`, { signal });
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
