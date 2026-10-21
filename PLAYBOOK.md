# Creator Outreach Pipeline playbook

## 1. Build and confirm the persona

Collect only the essentials: industry/product, target audience and market, platforms, content types, partnership goal, preferences and exclusions. Ask for budget, language, region, audience size or format only when they affect the result. Record supplied links and readable attachments as sources, and mark assumptions.

Write `workspace/persona.md`, rebuild `persona-dashboard.html`, show the result and ask for confirmation. Record the confirmation state, version and timestamp. Do not begin broad discovery while the status is `Draft` or `Needs confirmation`.

## 2. Discover and score creators

Use only the search and browsing capabilities actually available. Record a real profile URL, representative content, evidence date, metric source/definition, public business contact source and missing fields. If a requested number cannot be supported, return the verified count and the shortfall.

Rate the six dimensions from 0–5 only when enough evidence exists:

| Dimension | Weight | Question |
| --- | ---: | --- |
| Audience Fit | 30 | Does the creator reach the confirmed target audience? |
| Content Relevance | 25 | Does recent content directly support the product and campaign topic? |
| Engagement Quality | 20 | Is engagement substantive and credible for the stated measurement window? |
| Audience Size Band | 5 | Does verified size fit the persona’s preferred range? |
| Brand Safety | 15 | Does reviewed evidence support an acceptable risk profile? |
| Collaboration Readiness | 5 | Is there verified evidence of an appropriate collaboration route or fit? |

The weighted result is normalized to 0–100: A ≥ 85, B ≥ 70, C ≥ 50, D < 50. Evidence-incomplete rows remain `Unscored` instead of receiving artificial zeros. A formal score also requires a checkable HTTP(S) evidence URL and a valid checked date; populated public-email and follower-count fields need their own source fields.

## 3. Prepare creator-specific outreach

For each user-selected, eligible creator, provide: fit rationale, suggested format, opening angle, one verified content reference, risks, missing evidence and next step. Save an individual email and DM draft under `workspace/drafts/<creator_id>.md`. Missing evidence must remain visible; do not fake personalization.

Draft creation must not change `outreach.csv` or `activity-log.csv`. Tier D and opted-out creators are not eligible for batch drafts.

## 4. Record actual outreach

Only after the user reports a real send, add/update the creator’s single row in `outreach.csv` and append a unique event to `activity-log.csv`. Record actual channel, first contact, last contact, DM use, current intent, owner and next action. Do not generate intermediate events from a current status.

## 5. Follow up continuously

When the user provides a reply, screenshot, attachment or summary, extract facts and open questions. Append events; update the current outreach row; rebuild the outreach dashboard. Suggestions are not scheduled reminders, sent messages or booked meetings.

## 6. Preserve offers and materials

Each scope/payment combination gets a separate `offer_id`. Store currency, original and negotiated amount, package scope, payment schedule, deposit percentage, rights, disclosure, deliverables, timing, evidence and status. Multiple versions remain visible.

Save authorized files or faithful summaries in `workspace/collaborations/<creator_id>/`. State whether the source was a readable attachment, user-provided text, public URL or inaccessible reference. Commercial terms and content rights require written confirmation.

## 7. Track partnerships and publication

Use these distinct states: `Negotiating`, `Confirmed`, `Published`, `Completed`, `Closed Lost`. Confirmation requires evidence but does not imply publication. Each deliverable has its own ID and `published_at` D0. Build UTM parameters consistently, then separately verify that the final URL and analytics collection work. A Performance row must use the same `utm_campaign` as its partnership record; when `utm_content` is present, it must identify that partnership's creator. A legitimate cross-campaign use is recorded as a separate collaboration and deliverable with its own partnership UTM, rather than being mixed into an existing result series.

## 8. Review cumulative performance

Add D7/D14/D30 rows only after publication and only from user-provided or inspectable evidence. Each row is a cumulative snapshot, not an incremental bucket. Dates are normalized to UTC: a date-only value means 00:00 UTC, and each window must be measured on D0 + 7, 14 or 30 UTC calendar days. Record measurement time, attribution source/definition and verification state. Calculate conversion or cost rates only when numerator, denominator, spend, tracking verification and attribution scope are trustworthy. `spend` is the cumulative amount recorded for the deliverable, not a single-period amount, and must not be summed across windows. It normally cannot decrease. If a verified refund or correction reduces it, record `[Spend adjustment: reason]` in that snapshot's notes; CPD and CPI then use the adjusted cumulative amount. Compare creators only at the same window, attribution definition, metric definition and currency. State small-sample and attribution limitations; do not present correlation as certain causation.

## Safe state transitions

```text
Discovered → Scored → Drafted → Sent → Replied → Negotiating
Negotiating → Confirmed → Published → Completed
Any active stage → Paused / Opted out / Closed Lost
```

No transition is automatic. Preserve the supporting event or source for every external-world status change.
