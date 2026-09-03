import { searchOpportunities } from "../catalogue/catalogue";
import {
  defaultCatalogueFilters,
  type OpportunitySummary,
} from "../catalogue/types";

const pathAustralia = new URL("../../assets/home-journey/path-australia.webp", import.meta.url).href;
const pathCanada = new URL("../../assets/home-journey/path-canada.webp", import.meta.url).href;
const pathEurope = new URL("../../assets/home-journey/path-europe.webp", import.meta.url).href;
const pathGermany = new URL("../../assets/home-journey/path-germany.webp", import.meta.url).href;
const pathGlobal = new URL("../../assets/home-journey/path-global.webp", import.meta.url).href;
const pathJapan = new URL("../../assets/home-journey/path-japan.webp", import.meta.url).href;
const pathUk = new URL("../../assets/home-journey/path-uk.webp", import.meta.url).href;
const pathUs = new URL("../../assets/home-journey/path-us.webp", import.meta.url).href;

export interface HomepageOpportunityRowItem {
  opportunityId: string;
  title: string;
  providerName: string;
  description: string;
  badge: string;
  href: string;
  imageUrl: string;
  country: string;
  degreeLevel: string;
  applicationWindowState: OpportunitySummary["application_window_state"];
}

export interface HomepageOpportunityRows {
  verified: HomepageOpportunityRowItem[];
  open: HomepageOpportunityRowItem[];
  funded: HomepageOpportunityRowItem[];
}

function destinationImage(country: string, name: string): string {
  const destination = `${country} ${name}`.toLowerCase();
  if (destination.includes("australia")) return pathAustralia;
  if (destination.includes("canada")) return pathCanada;
  if (destination.includes("europe") || destination.includes("erasmus")) return pathEurope;
  if (destination.includes("germany") || destination.includes("daad")) return pathGermany;
  if (destination.includes("japan") || destination.includes("mext")) return pathJapan;
  if (destination.includes("united kingdom") || destination.includes("chevening")) return pathUk;
  if (destination.includes("united states") || destination.includes("fulbright")) return pathUs;
  return pathGlobal;
}

function degreeLabel(level: OpportunitySummary["degree_level"]): string {
  return {
    bachelors: "Bachelor's",
    masters: "Master's",
    phd: "Doctoral",
    postdoc: "Postdoctoral",
    short_course: "Short course",
  }[level];
}

function toHomepageRow(opportunity: OpportunitySummary): HomepageOpportunityRowItem {
  const levels = opportunity.degree_levels?.length
    ? opportunity.degree_levels
    : [opportunity.degree_level];

  return {
    opportunityId: opportunity.id,
    title: opportunity.name,
    providerName: opportunity.provider_name,
    description: opportunity.funding_summary,
    badge: opportunity.funding_display_label,
    href: `/catalogue/${opportunity.id}`,
    imageUrl: destinationImage(opportunity.country, opportunity.name),
    country: opportunity.country,
    degreeLevel: levels.map(degreeLabel).join(", "),
    applicationWindowState: opportunity.application_window_state,
  };
}

export async function loadHomepageOpportunityRows(
  signal?: AbortSignal,
): Promise<HomepageOpportunityRows> {
  const [verified, open, funded] = await Promise.all([
    searchOpportunities({ ...defaultCatalogueFilters, limit: "10" }, 0, signal),
    searchOpportunities(
      { ...defaultCatalogueFilters, availability: "open", limit: "10" },
      0,
      signal,
    ),
    searchOpportunities(
      { ...defaultCatalogueFilters, funding_type: "full", limit: "10" },
      0,
      signal,
    ),
  ]);

  return {
    verified: verified.items.map(toHomepageRow),
    open: open.items
      .filter((opportunity) => opportunity.application_window_state === "open")
      .map(toHomepageRow),
    funded: funded.items.map(toHomepageRow),
  };
}
