# QA and capability record

## Automated checks

- Six-dimension weighting and A/B/C/D boundaries.
- Evidence-incomplete creators remain unscored.
- Duplicate stable IDs and normalized YouTube channel URLs are deduplicated or rejected when they conflict.
- User-controlled content is HTML-escaped.
- Exactly three dashboard files are generated for each data root.
- Exactly three CSV data tables are exposed in `01-workspace/` and the isolated fixture: creators, outreach progress and performance.
- Draft files do not create outreach or activity records.
- Event IDs are unique and history is never synthesized from current state.
- Multiple offers for one creator remain separate.
- Confirmation and publication states remain distinct.
- Performance accepts only published deliverables; UTM campaign and creator attribution must match the partnership record.
- Cumulative D7/D14/D30 values do not decrease. A lower cumulative spend requires a structured refund/correction explanation in notes.
- Performance creator IDs, offer ownership and collaboration/deliverable references must agree across tables.
- Confirmation precedes publication; published timestamps agree; D7/D14/D30 measurement dates match UTC D0 windows.
- `Verified` candidates without complete scoring evidence are downgraded safely; Partial and Pending Verification records remain usable without false certainty.
- Spend, cost per download and cost per install return `N/A` when spend, outcome or attribution scope is insufficient.
- Cross-creator comparison requires the same observation window, attribution source, metric definition and currency.
- CSV references and displayed dashboard summaries remain consistent.
- Consolidated progress rows retain separate outreach, activity, offer and partnership record types with stable IDs.
- Creator Database tier/subscriber charts, outreach stage/tier charts and performance trend/comparison charts are derived from configuration or validated CSV rows.
- Empty workspaces render chart Empty States; performance totals use only the latest cumulative snapshot per deliverable.

## Environment-dependent checks

| Capability | Status | Notes |
| --- | --- | --- |
| Standard browser rendering | Tested locally | Generated HTML is self-contained and uses no remote assets. |
| puppyone Desktop HTML preview | Not verified in this repository build | Paths are printed in each page so clickable links are not required. |
| Cross-Agent file handoff | Supported by file contract; live client handoff not verified | A new Agent must read `AGENTS.md`, `PLAYBOOK.md` and `01-workspace/`. |
| Conversation attachment persistence | Not assumed | Save an authorized source or summary into the project when the active Agent can access it. |
| Email/DM delivery | Not included | Draft-only unless the user gives separate action-specific authorization and a connected tool is available. |
| Live platform discovery and analytics | Not included | Agents use available browsing/tools and record evidence; the template never claims automatic sync. |

## Validation modes

Normal user work runs the dashboard build, `04-tools/validate_workspace.py`, and the automated suite. Partial Creator Database rows and populated business tables are valid inputs. Release-specific tests construct a clean temporary fixture and do not copy the user's working records.

## Release checks

Only in a separate clean release copy, run the blank-workspace build, isolated-fixture build, validation, `04-tools/check_public_release.py`, tests, `git diff --check`, and a search for real internal case names or private business data. Fixtures must use reserved domains and never appear in the user workspace or root Dashboards. `.gitignore` does not protect tracked workspace CSV/MD or root dashboards; review their `git status` and diff before every public commit. Never clear a user's workspace to make this mode pass.

## Latest run — 2026-10-21

- Blank-workspace and isolated-fixture dashboard builds: passed.
- Workspace relationship validation: passed.
- Public-release data boundary: passed; blank workspace, blank-derived root dashboards, reserved fixture domains and public Markdown/CSV/HTML/JSON scanning confirmed. Non-Git release copies report the Git check as skipped rather than clean.
- Unit tests: 31 passed, including cross-creator/cross-offer references, timestamp mismatches, early/wrong-window measurements, incomplete scoring evidence, missing/zero cost inputs and attribution-scope comparison.
- Standard-browser review: updated Performance Dashboard rendered correctly with spend, CPD, CPI, comparable-results empty state and evidence-bounded next actions.

## Final-fix verification on 2026-10-21

- Full automated suite: 43/43 passed.
- Attribution exceptions: a mismatched `utm_campaign` or creator `utm_content` is blocked before performance data can be used.
- Spend exceptions: an unexplained cumulative decrease is blocked; a documented adjustment is accepted and the adjusted amount is used by cost metrics.
- Release exceptions: simulated sensitive text and unredacted labeled commercial terms are blocked, while isolated fixture values remain allowed; a release copy without `.git` reports `Skipped — Not a Git Repository`.
- Blank workspace and isolated fixture validation: passed.
- Root and fixture dashboards: regenerated; exactly three dashboard types in each location.
- Data-table consolidation: passed; only `creators.csv`, `outreach-progress.csv` and `performance.csv` remain in each data root.
- Ordered directories: passed; numbered top-level workflow folders are present and legacy unnumbered paths are absent.
- Mode separation: 10 populated Creator Database rows pass daily validation and dashboard generation. Release checks run against an independent clean fixture; a populated release fixture is blocked without deleting or reverting its data.
- `git diff --check`, privacy scan and lowercase-brand scan: passed.
- puppyone Desktop preview, end-to-end live creator discovery, cross-Agent attachment persistence, delivery integrations and live analytics remain `Not verified`.

## Dashboard-visualization verification on 2026-10-21

- Full automated suite: 49/49 passed.
- Blank workspace and isolated fixture validation: passed; all six generated dashboard files were rebuilt.
- Creator Database: score tiers and subscriber bands render from creator rows without changing the scoring model.
- Outreach: each creator is counted once in the current-stage donut; A/B/C/D bars exclude and separately label unscored creators.
- Performance: KPIs use the latest snapshot per deliverable, D7/D14/D30 trend lines retain exact values, and creator bars appear only for like-for-like records.
- Empty State checks: passed; blank Workspace dashboards do not create synthetic chart marks.
- Responsive review: passed in a standard desktop viewport and a 600 px-wide browser viewport; no remote assets or CDN requests are used.

## v2.2 discovery-flow verification on 2026-10-21

- Automated suite: 56/56 passed.
- Product-brief path: a simulated 20-channel request saved in two batches, preserved the first batch and rebuilt the database view.
- Channel-link path: five partially verified channel records entered the database without requiring subscriber, email or performance fields.
- Missing-data path: blank supplementary fields stayed blank, produced no fabricated score and did not interrupt validation.
- Resume path: normalized duplicate channel URLs merged into the existing stable ID, enriched non-empty fields and preserved prior evidence.
- Downstream regression: drafts, events, offers, partnerships, UTM attribution and both later dashboards remained valid against the isolated fixture.
- External limit: live YouTube search, page accessibility, authenticated metrics and public contact availability still depend on the active Agent and platform access.

## Clean-start and name-first verification — 2026-10-21

- The three root Dashboards contain no preloaded creator, outreach, offer, partnership or performance records and show useful Empty States.
- Fixture data lives only under `05-tests/fixtures/` and does not appear in the starting workspace or root Dashboards.
- Channel names precede Creator IDs; collaboration formats precede Offer IDs; communication summaries remain human-readable; published content labels precede Deliverable IDs.
