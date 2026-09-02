# Premium Header Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved premium, brand-accurate and responsive The Next Scholar header and scholarship search.

**Architecture:** Keep `Topbar` as the state owner and preserve existing application behavior. Replace the logo SVG, make production search triggers native controls with locally anchored popovers, and consolidate header/search styling into the dedicated stylesheet while removing only conflicting legacy rules and test-only duplication.

**Tech Stack:** React 19, TypeScript, React Router, CSS, Vitest, Testing Library, Vite

**Spec:** `docs/superpowers/specs/2026-09-02-premium-header-redesign-design.md`

## Global Constraints

- Preserve routing, authentication, query-string search behavior, filters, keyboard navigation, and responsive bottom navigation.
- Use brand colors `#2563EB`, `#3B82F6`, `#FACC15`, and `#0F172A` from the supplied logo plate.
- Add no dependency.
- Keep motion limited to compositor-friendly properties where possible and respect reduced-motion preferences.
- Do not merge into `main`.

---

### Task 1: Brand-accurate header identity

**Files:**
- Modify: `frontend/src/components/BrandLogo.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: existing `<Brand showDomain? onClick? />` API.
- Produces: the same API with a blue cap/N monogram and two-line wordmark markup.

- [ ] **Step 1: Write a failing brand test**

Assert that the home link exposes `The Next Scholar home`, contains separate `The Next` and `Scholar` wordmark lines, and includes the opportunity accent element.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pnpm test src/App.test.tsx`

Expected: FAIL because the current brand renders one title string and a burgundy droplet.

- [ ] **Step 3: Implement the brand SVG and wordmark**

Replace the droplet paths with the cap/N/tassel geometry and retain the existing `Brand` props and home link behavior.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `pnpm test src/App.test.tsx`

- [ ] **Step 5: Commit**

Run: `git add frontend/src/components/BrandLogo.tsx frontend/src/App.test.tsx && git commit -m "feat: align header brand with visual identity"`

### Task 2: Production search semantics and behavior

**Files:**
- Modify: `frontend/src/components/ScholarshipSearch.tsx`
- Modify: `frontend/src/features/home/HomePage.test.tsx`

**Interfaces:**
- Consumes: `HomeSearchState`, `ActivePopover`, `onSearchChange`, and `onPopoverChange`.
- Produces: unchanged search query navigation with native desktop trigger buttons and local popover anchors.

- [ ] **Step 1: Point tests at the production component**

Replace `SearchPillHarness` with `ScholarshipSearchHarness` importing `ScholarshipSearch`. Assert that Destination, Degree, and Funding are buttons with `aria-expanded` and `aria-controls`, and that choosing a destination advances to Degree.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pnpm test src/features/home/HomePage.test.tsx`

Expected: FAIL because production desktop segments are currently `div role="button"`, lack popup IDs, and popovers are hosted in a shared displaced layer.

- [ ] **Step 3: Implement native field triggers and anchored popovers**

Render each field as a wrapper containing a native trigger and its conditional dialog. Keep the search submit button a sibling and keep existing value selection and query serialization.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pnpm test src/features/home/HomePage.test.tsx`

- [ ] **Step 5: Commit**

Run: `git add frontend/src/components/ScholarshipSearch.tsx frontend/src/features/home/HomePage.test.tsx && git commit -m "refactor: make scholarship search accessible and anchored"`

### Task 3: Consolidated premium responsive styling

**Files:**
- Modify: `frontend/src/premium-header.css`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: existing header state classes and search component class names.
- Produces: a sticky in-flow expanded header, compact scroll state, single-mode responsive search, and correctly anchored panels.

- [ ] **Step 1: Add a failing layout contract test**

Extend `App.test.tsx` to assert the header uses the production search once and exposes the mobile trigger without duplicating the desktop search landmark.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pnpm test src/App.test.tsx`

- [ ] **Step 3: Replace the header override layer**

Define the approved brand tokens, 1440px container, 72/80px header rows, 840×66px search geometry, active/hover states, compact mode, popup elevation, and non-overlapping `769px`/`768px` responsive contract in `premium-header.css`.

- [ ] **Step 4: Remove conflicting legacy selectors**

Delete only the old `.tns-*` header/search blocks and duplicated route-stage compensation from `styles.css`; preserve unrelated page and workspace styling. Keep `Topbar` behavior intact while removing obsolete layout coupling in `App.tsx` if needed.

- [ ] **Step 5: Run focused and full tests**

Run: `pnpm test src/App.test.tsx src/features/home/HomePage.test.tsx`

Run: `pnpm test`

- [ ] **Step 6: Commit**

Run: `git add frontend/src/App.tsx frontend/src/styles.css frontend/src/premium-header.css frontend/src/App.test.tsx && git commit -m "feat: deliver premium responsive scholarship header"`

### Task 4: Remove the duplicate search implementation

**Files:**
- Modify: `frontend/src/features/home/HomePage.tsx`
- Modify: `frontend/src/features/home/HomePage.test.tsx`

**Interfaces:**
- Consumes: the production `ScholarshipSearch` owned by `Topbar`.
- Produces: one tested search implementation and shared option data/types.

- [ ] **Step 1: Verify no runtime caller uses `SearchPill`**

Run: `rg -n "SearchPill" frontend/src`

Expected: only the declaration and obsolete test references.

- [ ] **Step 2: Remove the duplicate component**

Delete `SearchPill` while preserving `initialSearch`, `HomeSearchState`, `ActivePopover`, destinations, degree options, funding options, and `HomePage`.

- [ ] **Step 3: Run tests and type checking**

Run: `pnpm test`

Run: `pnpm typecheck`

- [ ] **Step 4: Commit**

Run: `git add frontend/src/features/home/HomePage.tsx frontend/src/features/home/HomePage.test.tsx && git commit -m "refactor: remove duplicate scholarship search"`

### Task 5: Browser and production verification

**Files:**
- Modify only if verification exposes a requirement defect.

**Interfaces:**
- Consumes: completed header implementation.
- Produces: evidence for visual, interaction, responsive, build, and repository-state completion.

- [ ] **Step 1: Start the application**

Run: `pnpm dev --host 127.0.0.1`

- [ ] **Step 2: Inspect desktop states in Browser**

At 1920, 1440, and 1280 verify logo proportions, optical centering, 840×66px search, hover/active transitions, popover anchoring, focus-visible styling, and compact-on-scroll behavior.

- [ ] **Step 3: Inspect tablet and mobile states in Browser**

At 768 and 390 verify only the mobile trigger is visible, the full-height search sheet opens, controls remain keyboard-accessible, route content is not offset twice, and no horizontal overflow exists.

- [ ] **Step 4: Run fresh automated verification**

Run: `pnpm test`

Run: `pnpm typecheck`

Run: `pnpm build`

- [ ] **Step 5: Review the complete branch diff**

Run: `git diff main...HEAD --check`

Run: `git status --short --branch`

- [ ] **Step 6: Commit any verified corrections**

Commit only corrections required by the approved design and leave the branch unmerged.
