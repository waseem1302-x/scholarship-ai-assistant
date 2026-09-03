# Homepage Conversion Sections Design

Date: 2026-09-03

## Product position

The Next Scholar is not another scholarship directory. Its homepage must demonstrate a complete winning system:

**Discover a credible opportunity → understand fit → understand what selectors reward → prepare stronger evidence → take and track the next action.**

The header, search surface, hero, and footer remain structurally unchanged. The content between the hero and footer becomes five horizontal, image-led sections. Each section must earn its position by resolving one psychological barrier and sending the student into a core product capability.

## Goals

- Make the homepage feel aspirational without becoming generic study-abroad advertising.
- Move students from browsing into profile, matching, preparation, and tracking workflows.
- Explain why each section matters through one short, concrete subtitle.
- Provide truthful guest and signed-in states; never show fabricated match scores, winners, testimonials, or user progress.
- Preserve the clean Airbnb-inspired horizontal discovery language while giving each row a distinct product purpose.
- Support students with limited access to expert scholarship counselling, especially funding-sensitive international students from South Asia and Africa, without stereotyping or using scarcity manipulation.

## Non-goals

- No winner testimonials or success claims until verified outcomes exist.
- No fake personalization, invented activity, artificial urgency, or generic popularity claims.
- No new backend homepage aggregation endpoint in this iteration.
- No redesign of the header, hero, navigation, footer, catalogue, assistant, or workspace pages.
- No five visually identical rows containing the same scholarships in a different order.

## Audience states

### Visitor

The page creates desire, reduces uncertainty, proves the platform offers more than information, and leads to the first meaningful action: inspect a scholarship, create a profile, or open a preparation tool.

### Signed-in student

The same five positions become a product launchpad. Copy and calls to action lead toward matches, profile, preparation, documents, and applications. Where real personalized data is unavailable, the page uses truthful workflow prompts instead of simulated progress.

An incomplete-profile member receives activation copy such as “Complete your profile to inspect eligibility,” not empty personalized claims.

## Conversion sequence

| Stage | Student belief to create | Primary behavior | Product destination |
| --- | --- | --- | --- |
| Aspiration | “A funded path abroad is possible for me.” | Open a credible opportunity | Catalogue / opportunity detail |
| Feasibility | “I can identify realistic options before wasting time.” | Check eligibility or complete profile | Profile / matches |
| Understanding | “I know what this scholarship evaluates.” | Open a selection playbook | Assistant with scoped prompt |
| Preparation | “I can improve the evidence selectors will score.” | Begin one preparation task | Assistant / document lab |
| Execution | “I know exactly what to do next.” | Save, track, or resume work | Applications / profile / matches |

## Section designs

### 1. Funded paths to your next chapter

**Psychological purpose:** visual self-projection and immediate relevance. The imagery attracts attention, but every card represents a concrete scholarship route rather than a generic destination fantasy.

**Visitor title:** Funded paths to your next chapter  
**Visitor subtitle:** Start with credible opportunities for international students—not another endless directory.  
**Visitor header action:** Explore scholarships

**Signed-in title:** Continue exploring funded opportunities  
**Signed-in subtitle:** Open an opportunity, inspect its criteria, and decide whether it belongs in your plan.  
**Signed-in header action:** View your matches

**Card content:** destination image, truthful funding or verification badge, scholarship name, country, degree level, verified deadline or “Check official deadline,” and save control. No guest match percentage. Cards link to relevant catalogue results until stable opportunity-detail fixture IDs exist.

### 2. Scholarships with a realistic path

**Psychological purpose:** reduce learned helplessness and eligibility anxiety. The row emphasizes opportunities with clear, actionable routes rather than implying that every student qualifies.

**Visitor title:** Scholarships with a realistic path  
**Visitor subtitle:** Compare funding, degree level, deadline, and eligibility before investing weeks in an application.  
**Visitor header action:** Check your eligibility

**Signed-in title:** Turn your profile into better decisions  
**Signed-in subtitle:** Use explainable matching to separate confirmed alignment from missing or uncertain information.  
**Signed-in header action:** Inspect your matches

**Card content:** scholarship image, objective badge such as “Fully funded,” “Verified,” or “Research route,” then a compact eligibility cue such as target degree or published experience requirement. The final card is a profile activation card rather than another scholarship.

### 3. Scholarship winning playbooks

**Psychological purpose:** replace vague hope with clarity and control. These are not winner stories. Each card turns published selection criteria into a practical preparation route.

**Visitor title:** Scholarship winning playbooks  
**Visitor subtitle:** Understand what major scholarships evaluate—and how to prepare evidence before you apply.  
**Visitor header action:** Explore playbooks

**Signed-in title:** Prepare for the scholarships you are targeting  
**Signed-in subtitle:** Turn selection criteria into focused questions, evidence, and application tasks.  
**Signed-in header action:** Open AI coach

**Initial playbooks:**

- Chevening: leadership and networking evidence
- Erasmus Mundus: motivation, programme fit, and academic story
- MEXT: research proposal clarity and interview readiness
- DAAD EPOS: professional experience and development impact
- Commonwealth: development impact and study-plan coherence
- Fulbright: academic purpose and cross-cultural contribution
- Australia Awards: development contribution and return-home impact
- Gates Cambridge: academic excellence, leadership, and improving lives

**Card content:** editorial programme/destination image, “Based on published criteria” badge, programme name, one selector-facing outcome, an official criteria source URL, a reviewed date, and a direct assistant link with a programme-specific starter prompt. A playbook is omitted unless its official source is recorded. Wording must say “prepare,” “evaluate,” or “published criteria”; it must not promise selection or claim access to private selection rubrics.

### 4. Build what selectors score

**Psychological purpose:** convert educational interest into productive tool use. The section makes the invisible work of a strong application tangible.

**Visitor title:** Build what selectors score  
**Visitor subtitle:** Strengthen the essays, evidence, documents, and interview answers behind a serious application.  
**Visitor header action:** Start preparing

**Signed-in title:** Strengthen your application evidence  
**Signed-in subtitle:** Continue with the highest-impact part of your application instead of guessing what to do next.  
**Signed-in header action:** Open document lab

**Initial cards:** motivation letter strategy, leadership evidence, scholarship CV, recommender brief, research proposal, interview practice, document checklist, and application narrative.

**Card content:** premium editorial artwork or a truthful document/workflow preview, task badge, task name, concrete outcome, and destination route. Essay/interview tasks link to scoped assistant prompts; document tasks link to the document lab; profile-evidence tasks link to the profile.

### 5. Your next best move

**Psychological purpose:** remove decision paralysis and create an implementation intention. This is the bridge from the homepage into activation and retention.

**Visitor title:** Start from where you are  
**Visitor subtitle:** Choose your current stage and go directly to the tool that moves your application forward.  
**Visitor header action:** Build your plan

**Signed-in title:** Your next best move  
**Signed-in subtitle:** Resume your profile, matches, documents, or applications from one clear starting point.  
**Signed-in header action:** Open workspace

**Initial cards:** find scholarships, build profile, inspect matches, save opportunities, prepare documents, practise with the assistant, track applications, and review deadlines.

**Card content:** visually distinct workflow artwork, short stage label, outcome-focused title, one sentence of context, and a route to the relevant core capability. This row does not claim that a task is incomplete unless real state confirms it.

## Section header copy pattern

Every section header contains:

1. A sentence-case title that names the desired outcome.
2. A one-line subtitle explaining why the row is useful.
3. One contextual text action describing what happens after the click.
4. Previous and next controls on desktop/tablet.

Avoid marketing adjectives such as “amazing,” “exclusive,” “best,” and “life-changing” inside supporting copy. Confidence comes from specificity.

## Visual system and exact measurements

### Page and rhythm

- Maximum section width: `1440px`.
- Desktop gutters at 1440px and above: `48px`.
- Desktop gutters below 1440px: `32px`.
- Tablet gutters at 901px and below: `24px`.
- Mobile gutters at 743px and below: `24px`, with the carousel allowed to continue beyond the right edge.
- First section starts `56px` after the hero.
- Section-to-section top spacing: `48px` desktop, `40px` tablet, `32px` mobile.
- Final section bottom spacing before footer: `64px` desktop, `48px` mobile.

### Header

- Title: `22px/28px`, weight `650` desktop; `19px/24px`, weight `650` mobile.
- Subtitle: `14px/20px`, weight `400`, color `#6A6A6A`, maximum width `640px`.
- Title-to-subtitle gap: `4px`.
- Header-to-carousel gap: `16px` desktop, `14px` mobile.
- Contextual header action: `13px/18px`, weight `600`, minimum target height `32px`.
- Arrow buttons: `32px` circle, `4px` gap, `#F2F2F2` surface, `1.06` hover scale, clear disabled state.

### Carousel geometry

- Horizontal gap: `12px` at every breakpoint.
- 1440px viewport: 7 complete cards.
- 1280px viewport: 6 complete cards.
- 768px viewport: 4 complete cards.
- 390px viewport: 2 complete cards plus a visible portion of the next card.
- Track uses native horizontal overflow and `scroll-snap-type: inline mandatory`.
- Arrow activation scrolls one visible track width and naturally clamps at the end.
- Desktop/tablet arrows disable at boundaries; mobile arrows are hidden and touch scrolling remains native.

### Card geometry

- Visual ratio: `20 / 19` for all card artwork surfaces.
- Visual radius: `20px` desktop, `18px` mobile.
- Card background: transparent; no generic card shadow.
- Artwork background fallback: `#F2F2F2`.
- Copy starts `10px` below artwork and uses `4px` horizontal inset.
- Eyebrow/badge: `11px/14px`, weight `650`.
- Card title: `14px/18px`, weight `600`, maximum two lines.
- Supporting copy: `12px/17px`, weight `400`, color `#6A6A6A`, maximum two lines.
- Badge position: `12px` top and left; favorite/action position: `8px` top and right.
- Badge surface: 84% white with `8px` backdrop blur and subtle layered shadow.
- Favorite target: `36px`; heart glyph: `24px`; saved color: `#E11D48`.
- Hover: artwork scales to `1.02` over `240ms`; copy and card do not jump.
- Keyboard focus: `2px` visible focus ring with `3px` offset.

### Imagery

- Use repository-local images only; do not hotlink third-party files.
- Create distinct, premium editorial destination or preparation imagery rather than repeating the same photograph.
- Limit the initial image set to 16 optimized assets: eight destination/campus scenes and eight preparation/workflow scenes. An image may reappear in another section only with a different semantic crop and never twice in the same row.
- Export card imagery at `1200 × 1140px`, WebP or progressive JPEG, with a target maximum of `180KB` per asset.
- Destination images may suggest region and aspiration but must not pretend to depict a specific university or official scholarship campus.
- Preparation cards use document, writing, interview, and planning imagery so the page does not become a travel-photo gallery.
- Images are decorative when the adjacent title conveys the destination; use empty alt text, `loading="lazy"`, and `decoding="async"`.

## Component architecture

### `HomePage`

- Owns authentication-aware section configuration.
- Preserves the existing hero and footer.
- Selects visitor or signed-in copy and destinations.
- Owns shared favorite state until persistent saved-opportunity data is integrated.

### `HomepageJourneySection`

- Reusable section shell for heading, explanatory subtitle, contextual action, arrows, and carousel track.
- Accepts a section ID, copy, action, card list, card renderer/variant, and optional favorite behavior.
- Owns scroll-boundary state and page scrolling behavior.

### Card variants

- `opportunity`: image, badge, favorite, title, scholarship metadata.
- `playbook`: image, source-trust badge, programme, selector outcome.
- `preparation`: image/artwork, task category, task, concrete output.
- `next-action`: image/artwork, stage, outcome, short explanation.

Variants share the same visual frame and typography tokens but do not show irrelevant controls. Playbooks and preparation tasks do not receive favorite hearts.

## Routing

- Opportunity cards → `/catalogue` with relevant filters until stable detail IDs are available.
- Eligibility and profile actions → `/profile` or `/matches` depending on authentication.
- Playbooks and preparation actions → `/assistant?prompt=<scoped prompt>`.
- Document actions → `/document-lab`.
- Application actions → `/applications`.
- Workspace action → `/dashboard`.

Every header and card link must name the destination or outcome. Generic “Learn more” calls to action are not allowed.

## Truth and trust rules

- “Match,” percentage, or eligibility language appears only when supported by actual user and scholarship data.
- Guest opportunity cards use objective badges such as “Fully funded,” “Verified,” or “Check eligibility.”
- Playbooks must explicitly state that they are based on published criteria and retain an official criteria URL plus reviewed date in their data.
- No invented winner names, quotations, acceptance rates, popularity counts, or deadlines.
- Current fixture deadlines are omitted or labelled “Check official deadline” unless backed by a reviewed official source; the UI must not present demonstrative metadata as live or personalized.

## Accessibility and interaction

- Each section is a named `region`; each track is a named list; each card is an article or descriptive link.
- Favorite controls expose `aria-pressed` and an action-specific label.
- Navigation buttons expose the controlled track ID and accurate disabled state.
- Headings preserve a logical `h1 → h2 → h3` hierarchy.
- Touch scrolling works without JavaScript; keyboard users can tab through cards and controls.
- Reduced-motion preferences remove image and arrow animation.
- Text and controls meet WCAG AA contrast; no critical meaning is encoded only by color.

## Measurement of success

The implementation should make these events separately measurable when analytics is introduced:

- Section 1: opportunity open rate.
- Section 2: profile start/completion and matches open rate.
- Section 3: playbook open and assistant-start rate.
- Section 4: preparation-tool activation rate.
- Section 5: application/tracker open rate and signed-in return rate.

The homepage succeeds when more visitors enter the winning workflow, not when they merely scroll farther.

## Testing and verification

- Unit tests cover five-section rendering, visitor/signed-in copy, truthful guest badges, card variants, favorites, navigation boundaries, and destination routes.
- Full frontend test suite and TypeScript production build must pass.
- Browser verification at 1440px, 1280px, 768px, and 390px confirms card counts, overflow, no page-level horizontal scroll, typography, section rhythm, mobile touch affordance, and footer separation.
- Visual review checks that every row has distinct imagery and that repeated content does not make the page appear duplicated.
