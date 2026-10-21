# Creator Outreach Pipeline playbook

## 1. Build and extend the Creator Database

Start immediately from either input:

- **Product-led discovery:** read the product site, collaboration brief, description or accessible attachment; extract only the search constraints needed to find relevant YouTube creators.
- **Creator-led import:** read YouTube channel URLs, an existing list, CSV or accessible attachment; identify the channels and supplement only public, checkable information.

Do not create a separate Persona file or wait for Persona confirmation. Write every usable result to `01-workspace/creators.csv`.

### Work in durable batches

Do not try to discover and complete a large request in one pass. Choose a batch size that fits the available search and page-reading capability, then:

1. Search or read the supplied channels.
2. Deduplicate by stable Creator ID and normalized channel URL.
3. Save the batch without erasing previous non-empty evidence. When useful, merge a prepared batch with `python3 04-tools/import_creator_batch.py <batch.csv>`.
4. Rebuild `creator-database-dashboard.html` and run daily validation.
5. Report creators saved, Verified records and records that still need completion, then continue from the existing CSV.

If access fails, keep the completed rows and state the shortfall. Ask for channel URLs, a list or a file instead of restarting or filling the quota with invented accounts.

### Core and supplementary data

The durable core is Creator ID, channel name, YouTube channel URL, source URL, verification status and last checked date when a check succeeds. Subscriber count, language/country, category, average views, upload frequency, engagement indicators, relevant videos, public email, other contact routes, fit notes and score are supplementary. A blank or `Unknown` value means not yet available; `0` means a verified zero.

Use these verification states:

- `Verified` — sufficient public evidence supports the record and its score.
- `Partial` — some facts are confirmed, but supplementary or scoring evidence is incomplete.
- `Pending Verification` — a reliable channel check has not yet been completed.

Rate the preserved six dimensions from 0–5 only when supporting evidence exists:

| Dimension | Weight | Question |
| --- | ---: | --- |
| Audience Fit | 30 | Does the creator reach the intended audience described by the user’s product or collaboration input? |
| Content Relevance | 25 | Does recent content directly support the product and collaboration topic? |
| Engagement Quality | 20 | Is public engagement substantive and credible for the stated review window? |
| Audience Size Band | 5 | Does the verified subscriber range fit the stated need? |
| Brand Safety | 15 | Does reviewed evidence support an acceptable risk profile? |
| Collaboration Readiness | 5 | Is there verified evidence of an appropriate collaboration route or fit? |

The weighted result remains normalized to 0–100: A ≥ 85, B ≥ 70, C ≥ 50, D < 50. A score requires all six ratings, a checkable evidence URL and a checked date; populated subscriber and public-email values need their own sources. Missing scoring evidence remains `Unscored` and never becomes an artificial zero.

## 2. Prepare personalised outreach

For each creator the user selects—such as the top 10 eligible records—provide fit rationale, suggested collaboration format, opening angle, one verified content reference, risks, missing evidence and next step. Save one email and DM draft under `01-workspace/drafts/<creator_id>.md`. Missing evidence must remain visible; do not fake personalization.

Draft creation must not create or advance an outreach or activity record. Tier D, opted-out and do-not-contact creators are not eligible for batch drafts.

## 3. Track outreach

`01-workspace/outreach-progress.csv` is the independent relationship-progress table. Only after the user reports a real send, add or update the creator’s single `outreach` row and append a unique `activity` row. Record actual contact route, date, channel, reply, status and next action. Do not generate history from a current state.

When the user provides a reply, screenshot, attachment or summary, extract facts and open questions, append the event, update the current row and rebuild the Outreach Dashboard. Suggestions are not sent messages, scheduled reminders or booked meetings.

## 4. Manage collaborations

Keep each package and payment structure as a separate `offer` row; never overwrite earlier versions. Store scope, currency, amount, payment schedule, rights, disclosure, deliverables, timing, evidence and status. Save authorized files or faithful summaries under `01-workspace/collaborations/<creator_id>/`.

Keep `Negotiating`, `Confirmed`, `Published`, `Completed` and `Closed Lost` distinct. Confirmation does not imply publication. Each published deliverable needs its own ID and `published_at` D0. A Performance UTM campaign must match its partnership record; a legitimate cross-campaign use becomes a separate collaboration and deliverable.

## 5. Track and review performance

Add cumulative D7/D14/D30 records only for published deliverables and only from user-provided or inspectable evidence. Dates are normalized to UTC; each window must be measured on D0 + 7, 14 or 30 UTC calendar days.

Record attribution source, metric definition and verification state. Calculate conversion, CPD or CPI only when numerator, denominator, cumulative spend, tracking verification and attribution scope are trustworthy. Cumulative spend normally cannot decrease; a verified refund or correction requires `[Spend adjustment: reason]` in that snapshot’s notes. Compare creators only when window, attribution, metric definition and currency match.

## Safe state transitions

```text
Discovered → Scored → Drafted → Sent → Replied → Negotiating
Negotiating → Confirmed → Published → Completed
Any active stage → Paused / Opted out / Closed Lost
```

No transition is automatic. Preserve the supporting event or source for every external-world status change.

## Validation modes

During normal use, rebuild the dashboards and run `python3 04-tools/validate_workspace.py`. This checks the Creator Database, scoring, IDs, relationships, UTM attribution and cumulative metrics while allowing partial discovery rows and real business records.

Generated HTML must lead with channel names, collaboration formats, communication summaries and published-content labels. Keep creator, offer, collaboration and deliverable IDs available only as secondary traceability details.

`python3 04-tools/check_public_release.py` is not a daily workflow step. It is reserved for maintainers preparing a blank public template in a separate clean checkout or disposable copy. A failure must never be fixed by deleting user records. If the working folder still has a GitHub or GitLab remote, warn the user that real contacts, pricing, messages and generated dashboards may be committed accidentally.
