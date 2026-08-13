# Phase 9 accessibility smoke checklist

Run this in staging with a keyboard and a screen reader before each cohort.
Record browser, assistive technology, release digest, tester, findings, and
remediation in the release evidence. A keyboard trap, inaccessible primary
flow, or incorrect announcement of an error is a beta no-go.

## Required flows

- [ ] Sign in, invitation registration, terms/privacy checkbox, email
  verification/activation, and password reset: labels, errors, focus order,
  and success announcements work without a mouse.
- [ ] Catalogue filters, opportunity source links, profile, matching, and
  application workspace: heading order, visible focus, form errors, and route
  changes remain understandable.
- [ ] Assistant consent, send, citation links, feedback, and unavailable state
  work by keyboard and explain that results are decision support.
- [ ] If enabled, Document Lab consent, file selection, upload/scan status,
  export/delete confirmation, and provider-unavailable state are announced.
- [ ] If enabled, Community join, post/reply/report/moderation controls are
  keyboard reachable and report/suspension states are announced.
- [ ] Administrator passkey registration, MFA step-up, and one-time invitation
  display explain browser support, cancellation, error, and code-copy risks.

## Automated complement

The browser regression suite verifies keyboard reachability for authentication
and primary navigation. Use the semantic controls in the React client as the
baseline, then run the manual smoke above; automated checks do not prove the
screen-reader experience or passkey-browser integration.
