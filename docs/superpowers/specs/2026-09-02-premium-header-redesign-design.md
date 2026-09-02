# Premium Header Redesign Design

## Goal

Create a premium, fast scholarship-discovery header inspired by Airbnb's precision and restraint while preserving The Next Scholar's identity, routes, authentication, search query behavior, keyboard access, and responsive navigation.

## Brand direction

The supplied brand plate is authoritative:

- Primary blue: `#2563EB`
- Secondary blue: `#3B82F6`
- Opportunity accent: `#FACC15`
- Text/background navy: `#0F172A`

The header uses blue for identity and primary actions, navy for typography, and yellow only as a small opportunity accent. The logo is a compact vector interpretation of the supplied graduation-cap/N monogram paired with the two-line `The Next` / `Scholar` wordmark.

## Header architecture

`Topbar` remains the state owner. It composes the existing `Brand`, text-first primary navigation, authentication actions, and `ScholarshipSearch`. The expanded desktop header is sticky and remains in document flow. It has a 72px navigation row and an 80px search row; the scrolled state compacts to a 72px row without layout jumps.

The content container is capped at 1440px with 32px desktop gutters. Navigation stays visually centered. The header is white with a subtle boundary only when compact or elevated.

## Search architecture

The desktop search is an 840px by 66px rounded form with three native trigger buttons—Destination, Degree, and Funding—and a separate submit button. Each trigger owns its popover anchor so no inherited transform can displace panels. Labels use 12px semibold text; values use 14px regular text. The primary search action is a 48px blue circle.

Opening a field softens the shell, lifts the active segment, and places a 420px popover 12px below its owning trigger. Existing automatic progression from destination to degree to funding remains. Escape and outside click close the surface.

## Responsive behavior

- `>= 1200px`: full logo, center navigation, account action, 840px search.
- `901px–1199px`: tighter navigation and fluid desktop search.
- `769px–900px`: center navigation and account actions collapse into the existing menu; the three-segment search remains.
- `<= 768px`: desktop search is completely hidden and a single 54px mobile search trigger is shown. The expanded search is a full-height mobile sheet.

The `768px` boundary must never render desktop and mobile search simultaneously. Route content follows the sticky header naturally; no duplicated fixed-header compensation is allowed.

## Accessibility and performance

Search segments are native buttons with `aria-expanded`, `aria-controls`, and popup relationships. Focus-visible styling is consistent. Existing query-string navigation is unchanged. Motion is limited to opacity, transform, color, background, and shadow using an approximately 180ms easing curve; no layout-heavy animation or new dependency is introduced. Reduced-motion users receive effectively immediate transitions.

## Verification

Automated checks cover production search semantics, selection progression, submission behavior, navigation, and the removal of the test-only search duplicate. Browser verification covers 1920, 1440, 1280, 768, and 390 widths, default/hover/open/compact states, popover anchoring, and absence of horizontal overflow. Type checking, tests, and production build must pass before completion.
