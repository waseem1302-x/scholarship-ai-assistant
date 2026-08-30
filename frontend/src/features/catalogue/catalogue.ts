import { ApiError, apiClient } from "../../api/client";

import {
  defaultCatalogueFilters,
  type CatalogueAvailability,
  type CatalogueFilters,
  type OpportunityDetail,
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
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "Deadline varies";
  }
  const days = Math.ceil((timestamp - Date.now()) / 86_400_000);
  if (days < 0) {
    return `Closed ${formatDate(value)}`;
  }
  if (days <= 30) {
    return `${days} days left`;
  }
  return `Deadline ${formatDate(value)}`;
}

export type UrgencyTier = "critical" | "soon" | "comfortable" | "relaxed" | "closed" | "varies";

export interface DeadlineUrgency {
  label: string;
  tier: UrgencyTier;
  icon: string;
}

export function getDeadlineUrgency(value: string | null): DeadlineUrgency {
  if (!value) {
    return { label: "Deadline varies", tier: "varies", icon: "🗓️" };
  }
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return { label: "Deadline varies", tier: "varies", icon: "🗓️" };
  }
  const days = Math.ceil((timestamp - Date.now()) / 86_400_000);
  if (days < 0) {
    return { label: `Closed ${formatDate(value)}`, tier: "closed", icon: "⚫" };
  }
  if (days === 0) {
    return { label: "Closes today", tier: "critical", icon: "⏰" };
  }
  if (days === 1) {
    return { label: "1 day left", tier: "critical", icon: "⏰" };
  }
  if (days <= 7) {
    return { label: `${days} days left`, tier: "critical", icon: "⏰" };
  }
  if (days <= 30) {
    return { label: `${days} days left`, tier: "soon", icon: "⚠" };
  }
  const months = Math.max(1, Math.round(days / 30));
  if (months <= 3) {
    return { label: `${months} ${months === 1 ? "month" : "months"} left`, tier: "comfortable", icon: "🟢" };
  }
  return { label: `${months} months left`, tier: "relaxed", icon: "🟢" };
}

export function getCountryFlag(country: string | null | undefined): string {
  if (!country) return "🌐";
  const normalized = country.toLowerCase();
  if (normalized.includes("united kingdom") || normalized === "uk" || normalized.includes("britain")) return "🇬🇧";
  if (normalized.includes("japan")) return "🇯🇵";
  if (normalized.includes("malaysia")) return "🇲🇾";
  if (normalized.includes("australia")) return "🇦🇺";
  if (normalized.includes("united states") || normalized === "usa" || normalized === "us") return "🇺🇸";
  if (normalized.includes("germany")) return "🇩🇪";
  if (normalized.includes("canada")) return "🇨🇦";
  if (normalized.includes("europe") || normalized.includes("eu") || normalized.includes("erasmus")) return "🇪🇺";
  if (normalized.includes("singapore")) return "🇸🇬";
  if (normalized.includes("france")) return "🇫🇷";
  if (normalized.includes("netherlands")) return "🇳🇱";
  if (normalized.includes("china")) return "🇨🇳";
  if (normalized.includes("korea")) return "🇰🇷";
  if (normalized.includes("pakistan")) return "🇵🇰";
  return "🌐";
}

export async function searchOpportunities(filters: CatalogueFilters, offset: number, signal?: AbortSignal) {
  return apiClient.request<OpportunitySearchResponse>(`/opportunities?${catalogueSearch(filters, offset)}`, { signal });
}

export async function getOpportunity(id: string, signal?: AbortSignal) {
  return apiClient.request<OpportunityDetail>(`/opportunities/${id}`, { signal });
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
