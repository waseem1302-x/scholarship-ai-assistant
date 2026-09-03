# Homepage Conversion Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the five placeholder scholarship rows with five image-led, authentication-aware journey sections that move students from discovery into matching, preparation, and application tracking.

**Architecture:** Keep `HomePage` responsible for authentication and shared favorite state, move all journey copy/data into a typed content module, and replace the scholarship-only carousel with a generic `HomepageJourneySection` plus four card variants. Use local optimized imagery, native overflow/scroll snap, and route every card into an existing product capability without introducing a new backend endpoint.

**Tech Stack:** React 19, TypeScript 5.9, React Router 7, CSS, Vitest, Testing Library, Vite, local WebP/JPEG assets.

**Spec:** `docs/superpowers/specs/2026-09-03-homepage-conversion-sections-design.md`

## Global Constraints

- Preserve the existing header, search surface, hero, footer, and all non-home routes.
- Render exactly five journey sections between the hero and footer.
- Use visitor and signed-in copy without fabricated matches, winners, testimonials, deadlines, progress, or urgency.
- Maximum section width is `1440px`; gutters are `48px`, `32px`, and `24px` at the breakpoints specified in the design.
- Card counts are 7 at 1440px, 6 at 1280px, 4 at 768px, and 2 plus a partial next card at 390px.
- Use repository-local images only, capped at 16 new assets and `180KB` per asset.
- No new runtime or test dependency.
- All new behavior is developed test-first; the full test suite, TypeScript build, and browser checks must pass.

---

## File Structure

- Create `frontend/src/features/home/homepageJourneyContent.ts`: card/section types, visitor/member copy, exact card data, and official playbook sources.
- Create `frontend/src/features/home/homepageJourneyContent.test.ts`: truth, routing, count, and state-copy tests.
- Create `frontend/src/features/home/HomepageJourneySection.tsx`: reusable heading, action, navigation, track, and variant-card renderer.
- Create `frontend/src/features/home/HomepageJourneySection.test.tsx`: semantic, favorite, source, and carousel tests.
- Create `frontend/src/features/home/homepage-journey.css`: exact section, card, breakpoint, interaction, and reduced-motion rules.
- Modify `frontend/src/features/home/HomePage.tsx`: render the content model using authentication state and shared favorites.
- Modify `frontend/src/features/home/HomePage.test.tsx`: verify the five visitor/member sections and removal of the placeholder copy.
- Delete `frontend/src/features/home/ScholarshipCarousel.tsx`, `ScholarshipCarousel.test.tsx`, and `scholarship-carousel.css` after their tested behavior is transferred.
- Create 16 files under `frontend/src/assets/home-journey/`: eight destination scenes and eight preparation/workflow scenes.

---

### Task 1: Create the local editorial image set

**Files:**
- Create: `frontend/src/assets/home-journey/path-europe.webp`
- Create: `frontend/src/assets/home-journey/path-germany.webp`
- Create: `frontend/src/assets/home-journey/path-uk.webp`
- Create: `frontend/src/assets/home-journey/path-us.webp`
- Create: `frontend/src/assets/home-journey/path-canada.webp`
- Create: `frontend/src/assets/home-journey/path-australia.webp`
- Create: `frontend/src/assets/home-journey/path-japan.webp`
- Create: `frontend/src/assets/home-journey/path-global.webp`
- Create: `frontend/src/assets/home-journey/prepare-essay.webp`
- Create: `frontend/src/assets/home-journey/prepare-leadership.webp`
- Create: `frontend/src/assets/home-journey/prepare-cv.webp`
- Create: `frontend/src/assets/home-journey/prepare-recommendation.webp`
- Create: `frontend/src/assets/home-journey/prepare-research.webp`
- Create: `frontend/src/assets/home-journey/prepare-interview.webp`
- Create: `frontend/src/assets/home-journey/prepare-documents.webp`
- Create: `frontend/src/assets/home-journey/prepare-plan.webp`

**Interfaces:**
- Consumes: The imagery and truth constraints in the design spec.
- Produces: Sixteen `1200 × 1140px` local assets imported by `homepageJourneyContent.ts`.

- [ ] **Step 1: Generate eight destination scenes**

Use the image generation skill with one consistent art direction: premium editorial educational travel photography, warm natural daylight, confident but realistic international-student atmosphere, no logos, no visible text, no identifiable university branding, no luxury-travel cues, and safe central/right crop space for badges. Generate Europe, Germany, United Kingdom, United States, Canada, Australia, Japan, and a globally diverse study-planning scene.

- [ ] **Step 2: Generate eight preparation scenes**

Use the same color grade and framing for: essay drafting, leadership evidence mapping, scholarship CV preparation, recommender planning, research proposal development, interview practice, document organization, and application-roadmap planning. Show believable student work rather than floating UI or illegible generated text.

- [ ] **Step 3: Normalize and verify the assets**

Use the bundled image tooling or ImageMagick to export exactly `1200 × 1140px` WebP files. Verify dimensions and size:

```powershell
Get-ChildItem frontend/src/assets/home-journey/*.webp |
  Select-Object Name, Length
```

Expected: 16 files; each file is at most 184320 bytes. Inspect a contact sheet and reject any image containing generated words, logos, watermarks, malformed hands, or misleading official-campus cues.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/assets/home-journey
git commit -m "feat: add homepage journey artwork"
```

---

### Task 2: Define truthful journey content and authentication copy

**Files:**
- Create: `frontend/src/features/home/homepageJourneyContent.ts`
- Create: `frontend/src/features/home/homepageJourneyContent.test.ts`

**Interfaces:**
- Consumes: Sixteen asset URLs from Task 1.
- Produces: `HomepageJourneyCard`, `HomepageJourneySectionContent`, and `getHomepageJourneySections(isAuthenticated: boolean)`.

- [ ] **Step 1: Write failing content tests**

```tsx
import { describe, expect, it } from "vitest";
import { getHomepageJourneySections } from "./homepageJourneyContent";

describe("homepage journey content", () => {
  it("returns five purposeful sections with eight cards in both states", () => {
    for (const authenticated of [false, true]) {
      const sections = getHomepageJourneySections(authenticated);
      expect(sections).toHaveLength(5);
      expect(sections.map((section) => section.id)).toEqual([
        "funded-paths",
        "realistic-paths",
        "winning-playbooks",
        "build-evidence",
        "next-move",
      ]);
      expect(sections.every((section) => section.cards.length === 8)).toBe(true);
      expect(sections.every((section) => section.subtitle.length > 35)).toBe(true);
    }
  });

  it("does not invent personalized claims for visitors", () => {
    const serialized = JSON.stringify(getHomepageJourneySections(false));
    expect(serialized).not.toMatch(/\d+% match|winner story|selected applicant/i);
    expect(serialized).toContain("Check official deadline");
  });

  it("keeps every playbook attached to an official HTTPS source", () => {
    const playbooks = getHomepageJourneySections(false)[2].cards;
    expect(playbooks.every((card) => card.sourceUrl?.startsWith("https://"))).toBe(true);
    expect(playbooks.every((card) => card.sourceReviewedAt === "2026-09-03")).toBe(true);
  });
});
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```powershell
pnpm exec vitest run src/features/home/homepageJourneyContent.test.ts
```

Expected: FAIL because `homepageJourneyContent.ts` does not exist.

- [ ] **Step 3: Add the exact public interfaces**

```ts
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

export function getHomepageJourneySections(
  isAuthenticated: boolean,
): HomepageJourneySectionContent[];
```

- [ ] **Step 4: Add the exact five content groups**

Implement eight cards per group with these titles and routes:

1. `funded-paths`: DAAD EPOS → `/catalogue?country=Germany`; Fulbright Foreign Student Program → `/catalogue?country=United%20States`; Chevening Scholarships → `/catalogue?country=United%20Kingdom`; Vanier Canada Graduate Scholarships → `/catalogue?country=Canada`; Australia Awards → `/catalogue?country=Australia`; Erasmus Mundus Joint Masters → `/catalogue?funding_type=full`; MEXT Research Scholarship → `/catalogue?country=Japan`; Commonwealth Master's Scholarships → `/catalogue?country=United%20Kingdom`. Use objective badges and “Check official deadline.”
2. `realistic-paths`: Fully funded master's routes → `/catalogue?degree_level=masters&funding_type=full`; Research-degree funding → `/catalogue?degree_level=phd`; Development-professional routes → `/catalogue?q=development`; Government-funded programmes → `/catalogue?q=government`; European joint degrees → `/catalogue?q=joint%20masters`; Study routes in Germany → `/catalogue?country=Germany`; Study routes in Canada → `/catalogue?country=Canada`; Compare against your profile → visitor `/profile`, member `/matches`.
3. `winning-playbooks`: Chevening → `https://www.chevening.org/scholarships/guidance/`; Erasmus Mundus → `https://erasmus-plus.ec.europa.eu/opportunities/opportunities-for-individuals/students/erasmus-mundus-joint-masters`; MEXT → `https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/`; DAAD EPOS → `https://www.daad.de/en/studying-in-germany/scholarships/daad-funding-programmes/epos/`; Commonwealth → `https://cscuk.fcdo.gov.uk/scholarships/commonwealth-masters-scholarships/`; Fulbright → `https://foreign.fulbrightonline.org/about/foreign-fulbright`; Australia Awards → `https://www.dfat.gov.au/people-to-people/australia-awards`; Gates Cambridge → `https://www.gatescambridge.org/apply/how-we-select/`. Each `href` is `/assistant?prompt=` plus an encoded prompt naming the programme and asking for a preparation plan based only on published criteria.
4. `build-evidence`: Motivation letter strategy, Leadership evidence, Scholarship CV, Recommender brief, Research proposal, Interview practice, Document readiness, Application narrative. Use `/assistant?prompt=` for coaching tasks, `/document-lab` for CV/research/document tasks, and `/profile` for application narrative evidence.
5. `next-move`: Find scholarships → `/catalogue`; Build profile → `/profile`; Inspect matches → `/matches`; Save opportunities → `/catalogue`; Prepare documents → `/document-lab`; Ask AI coach → `/assistant`; Track applications → `/applications`; Open workspace → `/dashboard`.

Use this exact supporting copy:

| Group | Card | Badge | Description |
| --- | --- | --- | --- |
| Funded paths | DAAD EPOS | Fully funded | Postgraduate routes for development-focused professionals. |
| Funded paths | Fulbright Foreign Student Program | Graduate route | Academic study and cross-cultural exchange in the United States. |
| Funded paths | Chevening Scholarships | Fully funded | A one-year UK master's route centred on leadership potential. |
| Funded paths | Vanier Canada Graduate Scholarships | Doctoral funding | A Canadian route for high-impact doctoral research. |
| Funded paths | Australia Awards | Government funded | Study and development opportunities for eligible partner countries. |
| Funded paths | Erasmus Mundus Joint Masters | Joint master's | Study across participating European higher-education institutions. |
| Funded paths | MEXT Research Scholarship | Government funded | A Japanese government route for graduate research study. |
| Funded paths | Commonwealth Master's Scholarships | Development focused | Master's funding connected to sustainable development impact. |
| Realistic paths | Fully funded master's routes | Compare funding | Start with programmes designed to cover major study costs. |
| Realistic paths | Research-degree funding | Doctoral route | Compare research fit, supervision, and published requirements. |
| Realistic paths | Development-professional routes | Experience route | Explore programmes that consider professional and development impact. |
| Realistic paths | Government-funded programmes | Public funding | Compare official scholarship routes funded by governments. |
| Realistic paths | European joint degrees | Multi-country | Explore programmes delivered across participating institutions. |
| Realistic paths | Study routes in Germany | Germany | Compare degree level, funding, and official requirements. |
| Realistic paths | Study routes in Canada | Canada | Inspect graduate and research opportunities before applying. |
| Realistic paths | Compare against your profile | Eligibility check | Use your background to separate alignment from missing information. |
| Playbooks | Chevening leadership evidence | Published criteria | Turn leadership and networking examples into specific evidence. |
| Playbooks | Erasmus Mundus programme fit | Published criteria | Connect academic direction, motivation, and programme choice. |
| Playbooks | MEXT research preparation | Published criteria | Clarify the research plan and prepare to explain its value. |
| Playbooks | DAAD EPOS development impact | Published criteria | Connect professional experience with a credible development goal. |
| Playbooks | Commonwealth study plan | Published criteria | Align the proposed study plan with development impact. |
| Playbooks | Fulbright academic purpose | Published criteria | Explain academic direction and cross-cultural contribution clearly. |
| Playbooks | Australia Awards contribution | Published criteria | Connect study goals with contribution after returning home. |
| Playbooks | Gates Cambridge selection | Published criteria | Prepare evidence for academic strength, leadership, and improving lives. |
| Build evidence | Motivation letter strategy | Essay | Turn programme fit and personal evidence into a focused narrative. |
| Build evidence | Leadership evidence | Evidence | Replace broad claims with decisions, actions, and measurable outcomes. |
| Build evidence | Scholarship CV | Documents | Prioritize the experience and impact relevant to the application. |
| Build evidence | Recommender brief | Recommendations | Help a referee write a specific, evidence-backed recommendation. |
| Build evidence | Research proposal | Research | Clarify the question, method, feasibility, and expected contribution. |
| Build evidence | Interview practice | Interview | Practise concise answers grounded in real examples. |
| Build evidence | Document readiness | Checklist | Organize required documents before the deadline becomes urgent. |
| Build evidence | Application narrative | Positioning | Connect background, goals, and impact across the whole application. |
| Next move | Find scholarships | Discover | Search verified opportunities by destination, degree, and funding. |
| Next move | Build profile | Profile | Save your background once so matching can inspect real criteria. |
| Next move | Inspect matches | Matching | See confirmed alignment, missing details, and possible mismatches. |
| Next move | Save opportunities | Shortlist | Keep credible options together before comparing them. |
| Next move | Prepare documents | Documents | Review and organize the evidence required for an application. |
| Next move | Ask AI coach | Guidance | Turn one scholarship question into a practical next step. |
| Next move | Track applications | Execution | Keep deadlines, stages, and preparation work in one place. |
| Next move | Open workspace | Continue | Return to the tools that move your applications forward. |

Use these exact state headers from the spec. Export no mutable arrays; return cloned section/card records so callers cannot alter module state.

Build assistant destinations with these exact helpers so links are encoded consistently:

```ts
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
```

- [ ] **Step 5: Verify official source URLs**

Open each of the eight source URLs in the browser. Keep the card only when the page is an official programme/government domain and visibly supports the playbook topic. Replace a broken URL with the official programme’s current criteria/guidance URL; do not substitute a blog or aggregator.

- [ ] **Step 6: Run content tests to verify GREEN**

```powershell
pnpm exec vitest run src/features/home/homepageJourneyContent.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/features/home/homepageJourneyContent.ts frontend/src/features/home/homepageJourneyContent.test.ts
git commit -m "feat: define homepage journey content"
```

---

### Task 3: Build the generic journey section and card variants

**Files:**
- Create: `frontend/src/features/home/HomepageJourneySection.tsx`
- Create: `frontend/src/features/home/HomepageJourneySection.test.tsx`
- Read: `frontend/src/features/home/ScholarshipCarousel.tsx`
- Read: `frontend/src/features/home/ScholarshipCarousel.test.tsx`

**Interfaces:**
- Consumes: `HomepageJourneySectionContent` and `HomepageJourneyCard` from Task 2.
- Produces: `HomepageJourneySection({ section, savedFavorites, onToggleFavorite })`.

- [ ] **Step 1: Write failing component tests**

Create tests that render one opportunity card, one playbook, one preparation card, and one next-action card. Use exact assertions:

```tsx
expect(screen.getByRole("region", { name: section.title })).toBeInTheDocument();
expect(screen.getByText(section.subtitle)).toBeInTheDocument();
expect(screen.getByRole("link", { name: section.actionLabel })).toHaveAttribute("href", section.actionHref);
expect(screen.getByRole("button", { name: "Save DAAD EPOS" })).toHaveAttribute("aria-pressed", "false");
expect(screen.getByRole("link", { name: "Official criteria for Chevening" })).toHaveAttribute(
  "href",
  "https://www.chevening.org/scholarships/guidance/",
);
expect(screen.queryAllByRole("button", { name: /save/i })).toHaveLength(1);
```

Port the existing scroll test and keep `clientWidth = 600`, `scrollWidth = 1200`, and the expectation that one Next activation calls `scrollBy({ left: 600, behavior: "smooth" })` and updates disabled states.

- [ ] **Step 2: Run component tests to verify RED**

```powershell
pnpm exec vitest run src/features/home/HomepageJourneySection.test.tsx
```

Expected: FAIL because `HomepageJourneySection.tsx` does not exist.

- [ ] **Step 3: Implement the reusable section shell**

Use this public signature:

```tsx
interface HomepageJourneySectionProps {
  section: HomepageJourneySectionContent;
  savedFavorites: Set<string>;
  onToggleFavorite: (id: string) => void;
}

export function HomepageJourneySection({
  section,
  savedFavorites,
  onToggleFavorite,
}: HomepageJourneySectionProps) {}
```

The header contains a non-linked `h2`, subtitle, contextual `NavLink`, and previous/next buttons. The `ul` retains native horizontal scrolling, named-list semantics, `aria-controls`, and scroll-boundary state from `ScholarshipCarousel`.

- [ ] **Step 4: Implement variant-specific card output**

Use one `HomepageJourneyCardView` helper. Every card has one primary image link, title, description, and badge. Only cards with `favoriteId` render the heart and `aria-pressed`. Only cards with `sourceUrl` render a secondary official-source link using `target="_blank"` and `rel="noreferrer"`. Add `loading="lazy"` and `decoding="async"` to every image.

- [ ] **Step 5: Run component tests to verify GREEN**

```powershell
pnpm exec vitest run src/features/home/HomepageJourneySection.test.tsx
```

Expected: all semantic, variant, favorite, source, and navigation tests pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/home/HomepageJourneySection.tsx frontend/src/features/home/HomepageJourneySection.test.tsx
git commit -m "feat: build homepage journey carousel"
```

---

### Task 4: Apply the exact premium visual system

**Files:**
- Create: `frontend/src/features/home/homepage-journey.css`
- Modify: `frontend/src/features/home/HomepageJourneySection.tsx`

**Interfaces:**
- Consumes: stable BEM class names from `HomepageJourneySection`.
- Produces: the measured desktop/tablet/mobile geometry defined by the spec.

- [ ] **Step 1: Add the section and typography tokens**

Implement these exact rules as the foundation:

```css
.tns-home-journey-section {
  width: min(1440px, 100%);
  margin: 48px auto 0;
  color: #222222;
}

.tns-home-journey-section:first-child { margin-top: 56px; }
.tns-home-journey-header { padding-inline: 48px; }
.tns-home-journey-title { font-size: 22px; font-weight: 650; line-height: 28px; }
.tns-home-journey-subtitle { max-width: 640px; margin-top: 4px; color: #6a6a6a; font-size: 14px; line-height: 20px; }
.tns-home-journey-track { gap: 12px; margin-top: 16px; overflow-x: auto; scroll-snap-type: inline mandatory; scrollbar-width: none; }
```

- [ ] **Step 2: Add card geometry and variant surfaces**

Use `aspect-ratio: 20 / 19`, `20px` visual radius, `10px` artwork-to-copy spacing, `14px/18px` titles, `12px/17px` support copy, `36px` favorite target, and the exact badge/focus/hover rules in the spec. Opportunity and playbook cards use photographic artwork; preparation and next-action cards add restrained variant tints without changing geometry.

- [ ] **Step 3: Add responsive column rules**

```css
@media (min-width: 1440px) {
  .tns-home-journey-track { grid-auto-columns: calc(14.2857% - 10.2857px); margin-inline: 44px; }
}
@media (max-width: 1439px) {
  .tns-home-journey-header { padding-inline: 32px; }
  .tns-home-journey-track { grid-auto-columns: calc(16.6667% - 10px); margin-inline: 28px; }
}
@media (max-width: 900px) {
  .tns-home-journey-header { padding-inline: 24px; }
  .tns-home-journey-track { grid-auto-columns: calc(25% - 9px); margin-inline: 20px; }
}
@media (max-width: 743px) {
  .tns-home-journey-section { margin-top: 32px; }
  .tns-home-journey-title { font-size: 19px; line-height: 24px; }
  .tns-home-journey-navigation { display: none; }
  .tns-home-journey-track { grid-auto-columns: calc(50% - 6px); margin-inline: 0; padding-inline: 24px; }
}
```

- [ ] **Step 4: Add interaction and motion safeguards**

Add hover image scale `1.02` over `240ms`, button scale `1.06`, visible `2px` focus ring with `3px` offset, hidden scrollbars, `overscroll-behavior-x: contain`, and a reduced-motion block that disables transforms/transitions.

- [ ] **Step 5: Run the component tests and build**

```powershell
pnpm exec vitest run src/features/home/HomepageJourneySection.test.tsx
pnpm build
```

Expected: tests and build pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/home/HomepageJourneySection.tsx frontend/src/features/home/homepage-journey.css
git commit -m "style: refine homepage journey sections"
```

---

### Task 5: Integrate the five-stage journey into `HomePage`

**Files:**
- Modify: `frontend/src/features/home/HomePage.tsx:1-130,273-286`
- Modify: `frontend/src/features/home/HomePage.test.tsx:74-132`
- Delete: `frontend/src/features/home/ScholarshipCarousel.tsx`
- Delete: `frontend/src/features/home/ScholarshipCarousel.test.tsx`
- Delete: `frontend/src/features/home/scholarship-carousel.css`

**Interfaces:**
- Consumes: `getHomepageJourneySections(Boolean(user))` and `HomepageJourneySection`.
- Produces: five visitor/member homepage sections connected to existing routes.

- [ ] **Step 1: Replace the integration tests with failing outcome tests**

For a guest, assert these region names:

```tsx
[
  "Funded paths to your next chapter",
  "Scholarships with a realistic path",
  "Scholarship winning playbooks",
  "Build what selectors score",
  "Start from where you are",
]
```

For a signed-in student, assert these region names:

```tsx
[
  "Continue exploring funded opportunities",
  "Turn your profile into better decisions",
  "Prepare for the scholarships you are targeting",
  "Strengthen your application evidence",
  "Your next best move",
]
```

For both states, assert exactly five regions and eight articles per region. Assert guest content contains no `/\d+% match/i`, each section subtitle is present, “Scholarship winning playbooks” contains an official-source link, and the header/hero/footer tests remain unchanged.

- [ ] **Step 2: Run the homepage tests to verify RED**

```powershell
pnpm exec vitest run src/features/home/HomePage.test.tsx
```

Expected: FAIL because the existing placeholder section titles still render.

- [ ] **Step 3: Replace scholarship-only data and rendering**

In `HomePage`, remove `featuredScholarshipsData` and `scholarshipCarouselSections`. Add:

```tsx
const journeySections = getHomepageJourneySections(Boolean(user));

<div className="tns-home-journey" aria-label="Your scholarship journey">
  {journeySections.map((section) => (
    <HomepageJourneySection
      key={section.id}
      section={section}
      savedFavorites={savedFavorites}
      onToggleFavorite={toggleFavorite}
    />
  ))}
</div>
```

Keep the hero and footer JSX byte-for-byte except for import movement required by the new component.

- [ ] **Step 4: Remove the superseded component files**

Delete `ScholarshipCarousel.tsx`, its test, and `scholarship-carousel.css` only after the new homepage and component tests pass. Confirm no references remain:

```powershell
rg -n "ScholarshipCarousel|scholarship-carousel" frontend/src
```

Expected: no matches.

- [ ] **Step 5: Run focused tests and build**

```powershell
pnpm exec vitest run src/features/home/HomePage.test.tsx src/features/home/HomepageJourneySection.test.tsx src/features/home/homepageJourneyContent.test.ts
pnpm build
```

Expected: focused tests and production build pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/features/home
git commit -m "feat: connect homepage to scholarship journey"
```

---

### Task 6: Verify responsive behavior and production readiness

**Files:**
- Modify only when a test or browser check reveals a defect in the files from Tasks 2-5.

**Interfaces:**
- Consumes: the complete homepage journey implementation.
- Produces: a verified, clean branch ready for user review.

- [ ] **Step 1: Run the full automated suite from a cold cache**

```powershell
pnpm exec vitest --clearCache
pnpm test
pnpm build
git diff --check main...HEAD
```

Expected: all test files pass, TypeScript and Vite build pass, and `git diff --check` emits no errors.

- [ ] **Step 2: Start the local frontend**

```powershell
pnpm dev --host 127.0.0.1 --port 4173
```

- [ ] **Step 3: Verify exact browser geometry**

At 1440px, 1280px, 768px, and 390px, measure the first track and assert:

```text
1440: 7 complete cards, navigation visible
1280: 6 complete cards, navigation visible
768: 4 complete cards, navigation visible
390: 2 complete cards plus next-card preview, navigation hidden
```

At every width confirm `document.documentElement.scrollWidth <= window.innerWidth`, artwork maintains `20/19`, subtitles do not overlap actions, and the footer begins after the final section’s specified spacing.

- [ ] **Step 4: Verify interactions and both auth states**

Use the browser to click Next/Previous, save/unsave one opportunity, open one official source, open one assistant prompt, and verify native touch-style scrolling at 390px. Inspect visitor and signed-in fixtures; confirm neither state presents unsupported match percentages, live deadlines, winners, or progress.

- [ ] **Step 5: Review the visual system**

Capture desktop and mobile screenshots. Reject the result if rows look duplicated, imagery includes generated text/logos, the first row resembles a travel-booking page without scholarship context, or core action rows feel visually weaker than opportunity rows.

- [ ] **Step 6: Request code review and resolve findings**

Dispatch the code-reviewer with the approved spec, this plan, the base commit, and the final commit. Fix all Critical and Important findings, then rerun Steps 1-5.

- [ ] **Step 7: Commit verification fixes when needed**

```powershell
git add frontend/src/features/home frontend/src/assets/home-journey
git commit -m "fix: complete homepage journey verification"
```

Skip this commit when verification required no code or asset changes.
