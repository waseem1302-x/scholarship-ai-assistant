import type {
  HomepageOpportunityRowItem,
  HomepageOpportunityRows,
} from "./homepageJourney";

const prepareCv = new URL("../../assets/home-journey/prepare-cv.webp", import.meta.url).href;
const preparePlan = new URL("../../assets/home-journey/prepare-plan.webp", import.meta.url).href;
const prepareResearch = new URL("../../assets/home-journey/prepare-research.webp", import.meta.url).href;
const prepareRecommendation = new URL(
  "../../assets/home-journey/prepare-recommendation.webp",
  import.meta.url,
).href;
const prepareLeadership = new URL(
  "../../assets/home-journey/prepare-leadership.webp",
  import.meta.url,
).href;

export type HomepageJourneyCardVariant =
  | "opportunity"
  | "playbook"
  | "preparation"
  | "next-action";

interface HomepageJourneyCardBase {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  badge: string;
  href: string;
  imageUrl: string;
  imagePosition?: string;
  sourceUrl?: string;
  sourceReviewedAt?: string;
}

export interface HomepageJourneyOpportunityCard extends HomepageJourneyCardBase {
  variant: "opportunity";
  country: string;
  degreeLevel: string;
  opportunityId?: string;
  applicationWindowState?: HomepageOpportunityRowItem["applicationWindowState"];
}

interface HomepageJourneySupportingCard extends HomepageJourneyCardBase {
  variant: Exclude<HomepageJourneyCardVariant, "opportunity">;
  country?: never;
  degreeLevel?: never;
}

export type HomepageJourneyCard =
  | HomepageJourneyOpportunityCard
  | HomepageJourneySupportingCard;

export interface HomepageJourneySectionContent {
  id: string;
  title: string;
  subtitle: string;
  actionLabel: string;
  actionHref: string;
  cards: HomepageJourneyCard[];
  isCatalogueRow?: boolean;
}

function opportunityCard(
  item: HomepageOpportunityRowItem,
  sectionId: string,
): HomepageJourneyOpportunityCard {
  return {
    id: `${sectionId}-opportunity-${item.opportunityId}`,
    opportunityId: item.opportunityId,
    applicationWindowState: item.applicationWindowState,
    variant: "opportunity",
    eyebrow: item.providerName,
    title: item.title,
    description: item.description,
    badge: item.badge,
    href: item.href,
    imageUrl: item.imageUrl,
    country: item.country,
    degreeLevel: item.degreeLevel,
  };
}

const matchingCards: HomepageJourneyCard[] = [
  {
    id: "build-profile",
    variant: "next-action",
    eyebrow: "Profile",
    title: "Build your profile",
    description: "Record your background for eligibility matching.",
    badge: "Profile",
    href: "/profile",
    imageUrl: prepareCv,
  },
  {
    id: "review-matches",
    variant: "next-action",
    eyebrow: "Matching",
    title: "Review opportunity matches",
    description: "Compare your saved profile with published criteria.",
    badge: "Matches",
    href: "/matches",
    imageUrl: preparePlan,
  },
  {
    id: "browse-catalogue",
    variant: "next-action",
    eyebrow: "Catalogue",
    title: "Browse verified scholarships",
    description: "Search the public catalogue by destination, degree, and funding.",
    badge: "Catalogue",
    href: "/catalogue",
    imageUrl: prepareResearch,
  },
];

const planningCards: HomepageJourneyCard[] = [
  {
    id: "track-applications",
    variant: "next-action",
    eyebrow: "Applications",
    title: "Track your applications",
    description: "Save opportunities and organize active applications.",
    badge: "Applications",
    href: "/applications",
    imageUrl: prepareRecommendation,
  },
  {
    id: "open-dashboard",
    variant: "next-action",
    eyebrow: "Dashboard",
    title: "Open your dashboard",
    description: "Return to your current scholarship workflow.",
    badge: "Dashboard",
    href: "/dashboard",
    imageUrl: prepareLeadership,
  },
];

const catalogueSections = [
  {
    id: "verified-opportunities",
    row: "verified" as const,
    title: "Verified scholarships worth exploring",
    subtitle: "Browse opportunities published from the reviewed public catalogue.",
    actionLabel: "View all scholarships",
    actionHref: "/catalogue",
  },
  {
    id: "open-opportunities",
    row: "open" as const,
    title: "Applications open now",
    subtitle: "Review opportunities with a published application window that is open.",
    actionLabel: "View open scholarships",
    actionHref: "/catalogue?availability=open",
  },
  {
    id: "funded-study-paths",
    row: "funded" as const,
    title: "Explore funded study paths",
    subtitle: "Compare published funding opportunities across destinations and study levels.",
    actionLabel: "View funded scholarships",
    actionHref: "/catalogue?funding_type=full",
  },
];

const workflowSections: HomepageJourneySectionContent[] = [
  {
    id: "profile-matching",
    title: "Check which opportunities fit you",
    subtitle: "Build a profile, review matches, or continue exploring the public catalogue.",
    actionLabel: "Build your profile",
    actionHref: "/profile",
    cards: matchingCards,
  },
  {
    id: "application-planning",
    title: "Save and build your application plan",
    subtitle: "Keep selected opportunities and application work in one place.",
    actionLabel: "Track applications",
    actionHref: "/applications",
    cards: planningCards,
  },
];

export function getHomepageJourneySections(
  rows: HomepageOpportunityRows,
  includeEmptyCatalogueRows = false,
): HomepageJourneySectionContent[] {
  const dynamicSections = catalogueSections
    .filter((section) => includeEmptyCatalogueRows || rows[section.row].length > 0)
    .map((section) => ({
      id: section.id,
      title: section.title,
      subtitle: section.subtitle,
      actionLabel: section.actionLabel,
      actionHref: section.actionHref,
      cards: rows[section.row].map((item) => opportunityCard(item, section.id)),
      isCatalogueRow: true,
    }));

  return [
    ...dynamicSections,
    ...workflowSections.map((section) => ({
      ...section,
      cards: section.cards.map((card) => ({ ...card })),
    })),
  ];
}
