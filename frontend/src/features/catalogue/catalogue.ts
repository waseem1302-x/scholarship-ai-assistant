import { ApiError, apiClient } from "../../api/client";

import {
  defaultCatalogueFilters,
  type CatalogueAvailability,
  type CatalogueFilters,
  type OpportunityDetail,
  type OpportunitySearchResponse,
  type OpportunitySummary,
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

export function getDestinationImage(country?: string | null, name?: string | null): string {
  const normCountry = (country || "").toLowerCase();
  const normName = (name || "").toLowerCase();

  if (normName.includes("chevening") || normCountry.includes("united kingdom") || normCountry === "uk") {
    return "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=600&q=80"; // Big Ben / London
  }
  if (normName.includes("daad") || normCountry.includes("germany")) {
    return "https://images.unsplash.com/photo-1560969184-10fe8719e047?auto=format&fit=crop&w=600&q=80"; // Brandenburg Gate / Berlin
  }
  if (normName.includes("erasmus") || normCountry.includes("europe") || normCountry.includes("eu")) {
    return "https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=600&q=80"; // European architecture
  }
  if (normName.includes("mext") || normCountry.includes("japan")) {
    return "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=600&q=80"; // Mount Fuji / Japan
  }
  if (normName.includes("fulbright") || normCountry.includes("united states") || normCountry === "usa" || normCountry === "us") {
    return "https://images.unsplash.com/photo-1501446529957-6226bd447c46?auto=format&fit=crop&w=600&q=80"; // USA Capitol / Washington
  }
  if (normCountry.includes("australia")) {
    return "https://images.unsplash.com/photo-1506973035872-a4ec16b8e8d9?auto=format&fit=crop&w=600&q=80"; // Sydney Opera House
  }
  if (normCountry.includes("canada")) {
    return "https://images.unsplash.com/photo-1503614472-8c93d56e92ce?auto=format&fit=crop&w=600&q=80"; // Canada / Banff
  }
  if (normCountry.includes("singapore")) {
    return "https://images.unsplash.com/photo-1525625293386-3f8f99389edd?auto=format&fit=crop&w=600&q=80"; // Singapore Marina Bay
  }
  if (normCountry.includes("france")) {
    return "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=600&q=80"; // Paris Eiffel Tower
  }
  if (normCountry.includes("netherlands")) {
    return "https://images.unsplash.com/photo-1512470876302-972faa2aa9a4?auto=format&fit=crop&w=600&q=80"; // Amsterdam Canal
  }
  if (normCountry.includes("china")) {
    return "https://images.unsplash.com/photo-1508804185872-d7badad00f7d?auto=format&fit=crop&w=600&q=80"; // Great Wall / China
  }
  if (normCountry.includes("korea") || normCountry.includes("south korea")) {
    return "https://images.unsplash.com/photo-1538485399081-7191377e8241?auto=format&fit=crop&w=600&q=80"; // Seoul Korea
  }
  // Default university campus / academic aesthetic
  return "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=600&q=80";
}

export interface CardBadges {
  fundingBadge: { label: string; tier: "full" | "partial" };
  highlightBadge?: { label: string; style: "top" | "popular" | "new" };
}

export function getOpportunityBadges(opportunity: OpportunitySummary): CardBadges {
  const isFull = opportunity.funding_type === "full" || opportunity.funding_classification === "fully_funded";
  const nameLower = (opportunity.name + " " + (opportunity.provider_name || "")).toLowerCase();
  
  let highlight: CardBadges["highlightBadge"] = undefined;
  if (nameLower.includes("chevening") || nameLower.includes("fulbright") || nameLower.includes("rhodes")) {
    highlight = { label: "Top opportunity", style: "top" };
  } else if (nameLower.includes("daad") || nameLower.includes("erasmus") || nameLower.includes("australia awards")) {
    highlight = { label: "Popular", style: "popular" };
  } else if (opportunity.source_is_fresh || nameLower.includes("mext") || opportunity.verification_freshness === "recent") {
    highlight = { label: "New", style: "new" };
  }

  return {
    fundingBadge: {
      label: isFull ? "Fully Funded" : "Partial Funding",
      tier: isFull ? "full" : "partial",
    },
    highlightBadge: highlight,
  };
}

export function getInclusionsSummary(opportunity: OpportunitySummary): string {
  const text = (opportunity.funding_summary || opportunity.funding_display_label || "").toLowerCase();
  if (text.includes("travel") && text.includes("living") && text.includes("tuition")) {
    return "Tuition, living costs, travel";
  }
  if (text.includes("stipend") && text.includes("tuition")) {
    return "Tuition, stipend, travel";
  }
  if (text.includes("allowance") || text.includes("living")) {
    return "Tuition, living allowance, insurance";
  }
  if (text.includes("waiver") || opportunity.funding_type === "tuition_only") {
    return "Tuition waiver, monthly allowance";
  }
  if (opportunity.funding_type === "full" || opportunity.funding_classification === "fully_funded") {
    return "Tuition, living costs, travel";
  }
  return "Tuition waiver & academic stipend";
}

export function formatCardDeadline(dateStr: string | null): string {
  if (!dateStr) return "Open Now";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "Open Now";
    return d.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return "Open Now";
  }
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
