import type { DegreeLevel, FundingType } from "./types";

export interface HomeSearchState {
  country: string;
  degree_level: DegreeLevel | "";
  funding_type: FundingType | "";
}

export type ActivePopover = "where" | "degree" | "funding" | null;

export interface DestinationOption {
  country: string;
  aliases?: readonly string[];
  hint?: string;
}

export const initialSearch: HomeSearchState = {
  country: "",
  degree_level: "",
  funding_type: "full",
};

export const destinationOptions: readonly DestinationOption[] = [
  { country: "Asia-Pacific Partner Institutions", aliases: ["Asia Pacific"] },
  { country: "Australia" },
  { country: "Azerbaijan" },
  { country: "Brunei Darussalam", aliases: ["Brunei"] },
  { country: "Canada" },
  { country: "China" },
  { country: "France" },
  { country: "Germany" },
  { country: "Indonesia" },
  { country: "IsDB least-developed member countries" },
  { country: "IsDB member countries" },
  { country: "IsDB partner countries" },
  { country: "Japan" },
  { country: "Kazakhstan" },
  { country: "Malaysia" },
  { country: "Multiple European Countries", aliases: ["Europe", "European Union"] },
  { country: "Netherlands", aliases: ["The Netherlands"] },
  { country: "New Zealand" },
  { country: "Saudi Arabia" },
  { country: "Singapore" },
  { country: "South Korea", aliases: ["Korea", "Republic of Korea"] },
  { country: "Sweden" },
  { country: "Switzerland" },
  { country: "Taiwan" },
  { country: "Thailand" },
  { country: "Turkiye", aliases: ["Turkey", "Türkiye"] },
  { country: "United Kingdom", aliases: ["UK", "Great Britain"] },
  { country: "United States", aliases: ["US", "USA", "United States of America"] },
];

const destinationByName = new Map(
  destinationOptions.flatMap((option) =>
    [option.country, ...(option.aliases ?? [])].map((name) => [name.toLocaleLowerCase(), option] as const),
  ),
);

export const popularDestinations: readonly DestinationOption[] = [
  { country: "Germany", hint: "DAAD and public university opportunities" },
  { country: "United States", aliases: ["US", "USA"], hint: "Fulbright and university scholarships" },
  { country: "United Kingdom", aliases: ["UK"], hint: "Chevening and university awards" },
  { country: "Canada", hint: "Government and university funding" },
  { country: "Australia", hint: "Australia Awards and university grants" },
  { country: "Japan", hint: "MEXT and university scholarships" },
];

export const degreeOptions: readonly { label: string; value: DegreeLevel | ""; icon: string; desc: string }[] = [
  { label: "All Degree Levels", value: "", icon: "🌐", desc: "Bachelor's, Master's, PhD" },
  { label: "Bachelor's", value: "bachelors", icon: "🎓", desc: "Undergraduate & freshman grants" },
  { label: "Master's", value: "masters", icon: "📚", desc: "Postgraduate & professional degrees" },
  { label: "PhD / Doctorate", value: "phd", icon: "🔬", desc: "Research fellowships & doctorates" },
  { label: "Postdoc", value: "postdoc", icon: "🧪", desc: "Postdoctoral scientific research" },
  { label: "Short course", value: "short_course", icon: "⚡", desc: "Summer schools & training" },
];

export const fundingOptions: readonly { label: string; value: FundingType | ""; icon: string; desc: string }[] = [
  { label: "All Funding Types", value: "", icon: "💎", desc: "Fully funded, partial, and other awards" },
  { label: "Fully Funded", value: "full", icon: "🏆", desc: "Tuition, living support, and other benefits" },
  { label: "Partial Funding", value: "partial", icon: "💵", desc: "Tuition discount or partial stipend" },
  { label: "Tuition Only", value: "tuition_only", icon: "🏛️", desc: "Tuition waiver coverage" },
  { label: "Stipend Only", value: "stipend_only", icon: "💳", desc: "Living allowance without tuition coverage" },
  { label: "Funding Not Specified", value: "unknown", icon: "◌", desc: "Funding details are not yet classified" },
];

export function filterDestinationOptions(query: string, limit = 8): DestinationOption[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return popularDestinations.slice(0, limit);

  return destinationOptions
    .filter((option) =>
      [option.country, ...(option.aliases ?? [])].some((name) =>
        name.toLocaleLowerCase().includes(normalizedQuery),
      ),
    )
    .slice(0, limit);
}

export function resolveDestinationOption(query: string): DestinationOption | null {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return null;
  return destinationByName.get(normalizedQuery) ?? null;
}
