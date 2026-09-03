const pathAustralia = new URL("../../assets/home-journey/path-australia.webp", import.meta.url).href;
const pathCanada = new URL("../../assets/home-journey/path-canada.webp", import.meta.url).href;
const pathEurope = new URL("../../assets/home-journey/path-europe.webp", import.meta.url).href;
const pathGermany = new URL("../../assets/home-journey/path-germany.webp", import.meta.url).href;
const pathGlobal = new URL("../../assets/home-journey/path-global.webp", import.meta.url).href;
const pathJapan = new URL("../../assets/home-journey/path-japan.webp", import.meta.url).href;
const pathUk = new URL("../../assets/home-journey/path-uk.webp", import.meta.url).href;
const pathUs = new URL("../../assets/home-journey/path-us.webp", import.meta.url).href;
const prepareCv = new URL("../../assets/home-journey/prepare-cv.webp", import.meta.url).href;
const prepareDocuments = new URL("../../assets/home-journey/prepare-documents.webp", import.meta.url).href;
const prepareEssay = new URL("../../assets/home-journey/prepare-essay.webp", import.meta.url).href;
const prepareInterview = new URL("../../assets/home-journey/prepare-interview.webp", import.meta.url).href;
const prepareLeadership = new URL("../../assets/home-journey/prepare-leadership.webp", import.meta.url).href;
const preparePlan = new URL("../../assets/home-journey/prepare-plan.webp", import.meta.url).href;
const prepareRecommendation = new URL(
  "../../assets/home-journey/prepare-recommendation.webp",
  import.meta.url,
).href;
const prepareResearch = new URL("../../assets/home-journey/prepare-research.webp", import.meta.url).href;

export type HomepageJourneyCardVariant =
  | "opportunity"
  | "playbook"
  | "preparation"
  | "next-action";

export interface HomepageJourneyCard {
  id: string;
  variant: HomepageJourneyCardVariant;
  eyebrow: string;
  title: string;
  description: string;
  badge: string;
  href: string;
  imageUrl: string;
  imagePosition?: string;
  favoriteId?: string;
  sourceUrl?: string;
  sourceReviewedAt?: string;
}

export interface HomepageJourneySectionContent {
  id: string;
  title: string;
  subtitle: string;
  actionLabel: string;
  actionHref: string;
  cards: HomepageJourneyCard[];
}

function assistantHref(prompt: string) {
  return `/assistant?prompt=${encodeURIComponent(prompt)}`;
}

function playbookHref(programme: string) {
  return assistantHref(
    `Create a preparation plan for ${programme} using only its published selection criteria. Separate confirmed criteria from general advice and tell me what evidence I should prepare.`,
  );
}

function preparationHref(task: string) {
  return assistantHref(
    `Help me prepare my ${task} for a scholarship application. Ask for the evidence you need before giving advice, and do not invent achievements or personal details.`,
  );
}

const sourceReviewedAt = "2026-09-03";

const fundedPathCards: ReadonlyArray<Readonly<HomepageJourneyCard>> = [
  {
    id: "daad-epos",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "DAAD EPOS",
    description: "Postgraduate routes for development-focused professionals.",
    badge: "Fully funded",
    href: "/catalogue?country=Germany",
    imageUrl: pathGermany,
    favoriteId: "daad-epos",
  },
  {
    id: "fulbright-foreign-student",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Fulbright Foreign Student Program",
    description: "Academic study and cross-cultural exchange in the United States.",
    badge: "Graduate route",
    href: "/catalogue?country=United%20States",
    imageUrl: pathUs,
    favoriteId: "fulbright-foreign-student",
  },
  {
    id: "chevening-scholarships",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Chevening Scholarships",
    description: "A one-year UK master's route centred on leadership potential.",
    badge: "Fully funded",
    href: "/catalogue?country=United%20Kingdom",
    imageUrl: pathUk,
    favoriteId: "chevening-scholarships",
  },
  {
    id: "vanier-canada-graduate",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Vanier Canada Graduate Scholarships",
    description: "A Canadian route for high-impact doctoral research.",
    badge: "Doctoral funding",
    href: "/catalogue?country=Canada",
    imageUrl: pathCanada,
    favoriteId: "vanier-canada-graduate",
  },
  {
    id: "australia-awards",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Australia Awards",
    description: "Study and development opportunities for eligible partner countries.",
    badge: "Government funded",
    href: "/catalogue?country=Australia",
    imageUrl: pathAustralia,
    favoriteId: "australia-awards",
  },
  {
    id: "erasmus-mundus-joint-masters",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Erasmus Mundus Joint Masters",
    description: "Study across participating European higher-education institutions.",
    badge: "Joint master's",
    href: "/catalogue?funding_type=full",
    imageUrl: pathEurope,
    favoriteId: "erasmus-mundus-joint-masters",
  },
  {
    id: "mext-research",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "MEXT Research Scholarship",
    description: "A Japanese government route for graduate research study.",
    badge: "Government funded",
    href: "/catalogue?country=Japan",
    imageUrl: pathJapan,
    favoriteId: "mext-research",
  },
  {
    id: "commonwealth-masters",
    variant: "opportunity",
    eyebrow: "Check official deadline",
    title: "Commonwealth Master's Scholarships",
    description: "Master's funding connected to sustainable development impact.",
    badge: "Development focused",
    href: "/catalogue?country=United%20Kingdom",
    imageUrl: pathGlobal,
    favoriteId: "commonwealth-masters",
  },
];

const realisticPathCards: ReadonlyArray<Readonly<HomepageJourneyCard>> = [
  {
    id: "fully-funded-masters",
    variant: "opportunity",
    eyebrow: "Master's funding",
    title: "Fully funded master's routes",
    description: "Start with programmes designed to cover major study costs.",
    badge: "Compare funding",
    href: "/catalogue?degree_level=masters&funding_type=full",
    imageUrl: pathGlobal,
  },
  {
    id: "research-degree-funding",
    variant: "opportunity",
    eyebrow: "Research funding",
    title: "Research-degree funding",
    description: "Compare research fit, supervision, and published requirements.",
    badge: "Doctoral route",
    href: "/catalogue?degree_level=phd",
    imageUrl: pathCanada,
  },
  {
    id: "development-professional",
    variant: "opportunity",
    eyebrow: "Professional pathway",
    title: "Development-professional routes",
    description: "Explore programmes that consider professional and development impact.",
    badge: "Experience route",
    href: "/catalogue?q=development",
    imageUrl: pathGermany,
  },
  {
    id: "government-funded",
    variant: "opportunity",
    eyebrow: "Official programmes",
    title: "Government-funded programmes",
    description: "Compare official scholarship routes funded by governments.",
    badge: "Public funding",
    href: "/catalogue?q=government",
    imageUrl: pathAustralia,
  },
  {
    id: "european-joint-degrees",
    variant: "opportunity",
    eyebrow: "Joint study route",
    title: "European joint degrees",
    description: "Explore programmes delivered across participating institutions.",
    badge: "Multi-country",
    href: "/catalogue?q=joint%20masters",
    imageUrl: pathEurope,
  },
  {
    id: "study-routes-germany",
    variant: "opportunity",
    eyebrow: "Destination route",
    title: "Study routes in Germany",
    description: "Compare degree level, funding, and official requirements.",
    badge: "Germany",
    href: "/catalogue?country=Germany",
    imageUrl: pathUk,
  },
  {
    id: "study-routes-canada",
    variant: "opportunity",
    eyebrow: "Destination route",
    title: "Study routes in Canada",
    description: "Inspect graduate and research opportunities before applying.",
    badge: "Canada",
    href: "/catalogue?country=Canada",
    imageUrl: pathUs,
  },
  {
    id: "compare-profile",
    variant: "next-action",
    eyebrow: "Profile step",
    title: "Compare against your profile",
    description: "Use your background to separate alignment from missing information.",
    badge: "Eligibility check",
    href: "/profile",
    imageUrl: pathJapan,
  },
];

const playbookCards: ReadonlyArray<Readonly<HomepageJourneyCard>> = [
  {
    id: "chevening-playbook",
    variant: "playbook",
    eyebrow: "Chevening",
    title: "Chevening leadership evidence",
    description: "Turn leadership and networking examples into specific evidence.",
    badge: "Published criteria",
    href: playbookHref("Chevening"),
    imageUrl: pathUk,
    sourceUrl: "https://www.chevening.org/resource-hub/guidance/",
    sourceReviewedAt,
  },
  {
    id: "erasmus-mundus-playbook",
    variant: "playbook",
    eyebrow: "Erasmus Mundus",
    title: "Erasmus Mundus programme fit",
    description: "Connect academic direction, motivation, and programme choice.",
    badge: "Published criteria",
    href: playbookHref("Erasmus Mundus"),
    imageUrl: pathEurope,
    sourceUrl:
      "https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters",
    sourceReviewedAt,
  },
  {
    id: "mext-playbook",
    variant: "playbook",
    eyebrow: "MEXT",
    title: "MEXT research preparation",
    description: "Clarify the research plan and prepare to explain its value.",
    badge: "Published criteria",
    href: playbookHref("MEXT"),
    imageUrl: pathJapan,
    sourceUrl: "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
    sourceReviewedAt,
  },
  {
    id: "daad-epos-playbook",
    variant: "playbook",
    eyebrow: "DAAD EPOS",
    title: "DAAD EPOS development impact",
    description: "Connect professional experience with a credible development goal.",
    badge: "Published criteria",
    href: playbookHref("DAAD EPOS"),
    imageUrl: pathGermany,
    sourceUrl:
      "https://www.daad.de/en/information-services-for-higher-education-institutions/further-information-on-daad-programmes/epos/",
    sourceReviewedAt,
  },
  {
    id: "commonwealth-playbook",
    variant: "playbook",
    eyebrow: "Commonwealth",
    title: "Commonwealth study plan",
    description: "Align the proposed study plan with development impact.",
    badge: "Published criteria",
    href: playbookHref("Commonwealth"),
    imageUrl: pathGlobal,
    sourceUrl: "https://cscuk.fcdo.gov.uk/scholarships/commonwealth-masters-scholarships/",
    sourceReviewedAt,
  },
  {
    id: "fulbright-playbook",
    variant: "playbook",
    eyebrow: "Fulbright",
    title: "Fulbright academic purpose",
    description: "Explain academic direction and cross-cultural contribution clearly.",
    badge: "Published criteria",
    href: playbookHref("Fulbright"),
    imageUrl: pathUs,
    sourceUrl: "https://foreign.fulbrightonline.org/about/foreign-student-program",
    sourceReviewedAt,
  },
  {
    id: "australia-awards-playbook",
    variant: "playbook",
    eyebrow: "Australia Awards",
    title: "Australia Awards contribution",
    description: "Connect study goals with contribution after returning home.",
    badge: "Published criteria",
    href: playbookHref("Australia Awards"),
    imageUrl: pathAustralia,
    sourceUrl: "https://www.dfat.gov.au/people-to-people/australia-awards",
    sourceReviewedAt,
  },
  {
    id: "gates-cambridge-playbook",
    variant: "playbook",
    eyebrow: "Gates Cambridge",
    title: "Gates Cambridge selection",
    description: "Prepare evidence for academic strength, leadership, and improving lives.",
    badge: "Published criteria",
    href: playbookHref("Gates Cambridge"),
    imageUrl: pathCanada,
    sourceUrl: "https://www.gatescambridge.org/apply/how-we-select/",
    sourceReviewedAt,
  },
];

const preparationCards: ReadonlyArray<Readonly<HomepageJourneyCard>> = [
  {
    id: "motivation-letter-strategy",
    variant: "preparation",
    eyebrow: "Writing task",
    title: "Motivation letter strategy",
    description: "Turn programme fit and personal evidence into a focused narrative.",
    badge: "Essay",
    href: preparationHref("motivation letter strategy"),
    imageUrl: prepareEssay,
  },
  {
    id: "leadership-evidence",
    variant: "preparation",
    eyebrow: "Evidence task",
    title: "Leadership evidence",
    description: "Replace broad claims with decisions, actions, and measurable outcomes.",
    badge: "Evidence",
    href: preparationHref("leadership evidence"),
    imageUrl: prepareLeadership,
  },
  {
    id: "scholarship-cv",
    variant: "preparation",
    eyebrow: "Document task",
    title: "Scholarship CV",
    description: "Prioritize the experience and impact relevant to the application.",
    badge: "Documents",
    href: "/document-lab",
    imageUrl: prepareCv,
  },
  {
    id: "recommender-brief",
    variant: "preparation",
    eyebrow: "Referee task",
    title: "Recommender brief",
    description: "Help a referee write a specific, evidence-backed recommendation.",
    badge: "Recommendations",
    href: preparationHref("recommender brief"),
    imageUrl: prepareRecommendation,
  },
  {
    id: "research-proposal",
    variant: "preparation",
    eyebrow: "Document task",
    title: "Research proposal",
    description: "Clarify the question, method, feasibility, and expected contribution.",
    badge: "Research",
    href: "/document-lab",
    imageUrl: prepareResearch,
  },
  {
    id: "interview-practice",
    variant: "preparation",
    eyebrow: "Practice task",
    title: "Interview practice",
    description: "Practise concise answers grounded in real examples.",
    badge: "Interview",
    href: preparationHref("interview practice"),
    imageUrl: prepareInterview,
  },
  {
    id: "document-readiness",
    variant: "preparation",
    eyebrow: "Organization task",
    title: "Document readiness",
    description: "Organize required documents before the deadline becomes urgent.",
    badge: "Checklist",
    href: "/document-lab",
    imageUrl: prepareDocuments,
  },
  {
    id: "application-narrative",
    variant: "preparation",
    eyebrow: "Profile task",
    title: "Application narrative",
    description: "Connect background, goals, and impact across the whole application.",
    badge: "Positioning",
    href: "/profile",
    imageUrl: preparePlan,
  },
];

const nextMoveCards: ReadonlyArray<Readonly<HomepageJourneyCard>> = [
  {
    id: "find-scholarships",
    variant: "next-action",
    eyebrow: "Explore options",
    title: "Find scholarships",
    description: "Search verified opportunities by destination, degree, and funding.",
    badge: "Discover",
    href: "/catalogue",
    imageUrl: prepareResearch,
  },
  {
    id: "build-profile",
    variant: "next-action",
    eyebrow: "Record evidence",
    title: "Build profile",
    description: "Save your background once so matching can inspect real criteria.",
    badge: "Profile",
    href: "/profile",
    imageUrl: prepareCv,
  },
  {
    id: "inspect-matches",
    variant: "next-action",
    eyebrow: "Compare fit",
    title: "Inspect matches",
    description: "See confirmed alignment, missing details, and possible mismatches.",
    badge: "Matching",
    href: "/matches",
    imageUrl: preparePlan,
  },
  {
    id: "save-opportunities",
    variant: "next-action",
    eyebrow: "Compare options",
    title: "Save opportunities",
    description: "Keep credible options together before comparing them.",
    badge: "Shortlist",
    href: "/catalogue",
    imageUrl: prepareLeadership,
  },
  {
    id: "prepare-documents",
    variant: "next-action",
    eyebrow: "Organize evidence",
    title: "Prepare documents",
    description: "Review and organize the evidence required for an application.",
    badge: "Documents",
    href: "/document-lab",
    imageUrl: prepareDocuments,
  },
  {
    id: "ask-ai-coach",
    variant: "next-action",
    eyebrow: "Get guidance",
    title: "Ask AI coach",
    description: "Turn one scholarship question into a practical next step.",
    badge: "Guidance",
    href: "/assistant",
    imageUrl: prepareInterview,
  },
  {
    id: "track-applications",
    variant: "next-action",
    eyebrow: "Manage progress",
    title: "Track applications",
    description: "Keep deadlines, stages, and preparation work in one place.",
    badge: "Execution",
    href: "/applications",
    imageUrl: prepareRecommendation,
  },
  {
    id: "open-workspace",
    variant: "next-action",
    eyebrow: "Resume work",
    title: "Open workspace",
    description: "Return to the tools that move your applications forward.",
    badge: "Continue",
    href: "/dashboard",
    imageUrl: prepareEssay,
  },
];

type SectionHeader = Omit<HomepageJourneySectionContent, "id" | "cards">;

const visitorHeaders: Readonly<Record<string, Readonly<SectionHeader>>> = {
  "funded-paths": {
    title: "Funded paths to your next chapter",
    subtitle: "Start with credible opportunities for international students—not another endless directory.",
    actionLabel: "Explore scholarships",
    actionHref: "/catalogue",
  },
  "realistic-paths": {
    title: "Scholarships with a realistic path",
    subtitle: "Compare funding, degree level, deadline, and eligibility before investing weeks in an application.",
    actionLabel: "Check your eligibility",
    actionHref: "/profile",
  },
  "winning-playbooks": {
    title: "Scholarship winning playbooks",
    subtitle: "Understand what major scholarships evaluate—and how to prepare evidence before you apply.",
    actionLabel: "Explore playbooks",
    actionHref: "/assistant",
  },
  "build-evidence": {
    title: "Build what selectors score",
    subtitle: "Strengthen the essays, evidence, documents, and interview answers behind a serious application.",
    actionLabel: "Start preparing",
    actionHref: "/assistant",
  },
  "next-move": {
    title: "Start from where you are",
    subtitle: "Choose your current stage and go directly to the tool that moves your application forward.",
    actionLabel: "Build your plan",
    actionHref: "/profile",
  },
};

const memberHeaders: Readonly<Record<string, Readonly<SectionHeader>>> = {
  "funded-paths": {
    title: "Continue exploring funded opportunities",
    subtitle: "Open an opportunity, inspect its criteria, and decide whether it belongs in your plan.",
    actionLabel: "View your matches",
    actionHref: "/matches",
  },
  "realistic-paths": {
    title: "Turn your profile into better decisions",
    subtitle: "Use explainable matching to separate confirmed alignment from missing or uncertain information.",
    actionLabel: "Inspect your matches",
    actionHref: "/matches",
  },
  "winning-playbooks": {
    title: "Prepare for the scholarships you are targeting",
    subtitle: "Turn selection criteria into focused questions, evidence, and application tasks.",
    actionLabel: "Open AI coach",
    actionHref: "/assistant",
  },
  "build-evidence": {
    title: "Strengthen your application evidence",
    subtitle: "Continue with the highest-impact part of your application instead of guessing what to do next.",
    actionLabel: "Open document lab",
    actionHref: "/document-lab",
  },
  "next-move": {
    title: "Your next best move",
    subtitle: "Resume your profile, matches, documents, or applications from one clear starting point.",
    actionLabel: "Open workspace",
    actionHref: "/dashboard",
  },
};

const sectionCards: ReadonlyArray<
  readonly [string, ReadonlyArray<Readonly<HomepageJourneyCard>>]
> = [
  ["funded-paths", fundedPathCards],
  ["realistic-paths", realisticPathCards],
  ["winning-playbooks", playbookCards],
  ["build-evidence", preparationCards],
  ["next-move", nextMoveCards],
];

export function getHomepageJourneySections(
  isAuthenticated: boolean,
): HomepageJourneySectionContent[] {
  const headers = isAuthenticated ? memberHeaders : visitorHeaders;

  return sectionCards.map(([id, cards]) => ({
    id,
    ...headers[id],
    cards: cards.map((card) => ({
      ...card,
      ...(id === "realistic-paths" && card.id === "compare-profile"
        ? { href: isAuthenticated ? "/matches" : "/profile" }
        : {}),
    })),
  }));
}
