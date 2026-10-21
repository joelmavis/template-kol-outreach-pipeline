# QA and capability record

## Automated checks

- Six-dimension weighting and A/B/C/D boundaries.
- Evidence-incomplete creators remain unscored.
- Duplicate stable IDs and duplicate platform/profile identities fail.
- User-controlled content is HTML-escaped.
- Exactly three dashboard files are generated for each data root.
- Exactly three CSV data tables are exposed in both `01-workspace/` and the Example: creators, outreach progress and performance.
- Draft files do not create outreach or activity records.
- Event IDs are unique and history is never synthesized from current state.
- Multiple offers for one creator remain separate.
- Confirmation and publication states remain distinct.
- Performance accepts only published deliverables; UTM campaign and creator attribution must match the partnership record.
- Cumulative D7/D14/D30 values do not decrease. A lower cumulative spend requires a structured refund/correction explanation in notes.
- Performance creator IDs, offer ownership and collaboration/deliverable references must agree across tables.
- Confirmation precedes publication; published timestamps agree; D7/D14/D30 measurement dates match UTC D0 windows.
- `Verified` candidates without an evidence URL or checked date remain unscored.
- Spend, cost per download and cost per install return `N/A` when spend, outcome or attribution scope is insufficient.
- Cross-creator comparison requires the same observation window, attribution source, metric definition and currency.
- CSV references and displayed dashboard summaries remain consistent.
- Consolidated progress rows retain separate outreach, activity, offer and partnership record types with stable IDs.
- Persona weight, outreach stage, score-tier, cumulative trend and creator-comparison charts are derived from configuration or validated CSV rows.
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

Normal user work runs the dashboard build, `04-tools/validate_workspace.py`, and the automated suite. A confirmed Persona and populated workspace are valid inputs. Release-specific tests construct a clean temporary fixture and do not copy the user's working records.

## Release checks

Only in a separate clean release copy, run both blank-workspace and example builds, validation, `04-tools/check_public_release.py`, tests, `git diff --check`, and a search for real internal case names or private business data. The public example must use reserved domains and visibly state that all data is illustrative. `.gitignore` does not protect tracked workspace CSV/MD or root dashboards; review their `git status` and diff before every public commit. Never clear a user's workspace to make this mode pass.

## Latest run — 2026-10-21

- Blank and Example dashboard builds: passed.
- Workspace relationship validation: passed.
- Public-release data boundary: passed; blank workspace, blank-derived root dashboards, reserved Example domains and public Markdown/CSV/HTML/JSON scanning confirmed. Non-Git release copies report the Git check as skipped rather than clean.
- Unit tests: 31 passed, including cross-creator/cross-offer references, timestamp mismatches, early/wrong-window measurements, incomplete scoring evidence, missing/zero cost inputs and attribution-scope comparison.
- Standard-browser review: updated Performance Dashboard rendered correctly with spend, CPD, CPI, comparable-results empty state and evidence-bounded next actions.

## Final-fix verification on 2026-10-21

- Full automated suite: 43/43 passed.
- Attribution exceptions: a mismatched `utm_campaign` or creator `utm_content` is blocked before performance data can be used.
- Spend exceptions: an unexplained cumulative decrease is blocked; a documented adjustment is accepted and the adjusted amount is used by cost metrics.
- Release exceptions: simulated sensitive text and unredacted labeled commercial terms are blocked, while fictional Example values remain allowed; a release copy without `.git` reports `Skipped — Not a Git Repository`.
- Blank workspace and fictional Example validation: passed.
- Root and Example dashboards: regenerated; exactly three dashboard types in each location.
- Data-table consolidation: passed; only `creators.csv`, `outreach-progress.csv` and `performance.csv` remain in each data root.
- Ordered directories: passed; numbered top-level workflow folders are present and legacy unnumbered paths are absent.
- Mode separation: a confirmed Persona with 10 populated creator rows passes daily validation and dashboard generation. Release checks run against an independent clean fixture; a populated release fixture is blocked without deleting or reverting its data.
- `git diff --check`, privacy scan and lowercase-brand scan: passed.
- puppyone Desktop preview, end-to-end live creator discovery, cross-Agent attachment persistence, delivery integrations and live analytics remain `Not verified`.

## Dashboard-visualization verification on 2026-10-21

- Full automated suite: 49/49 passed.
- Blank workspace and fictional Example validation: passed; all six generated dashboard files were rebuilt.
- Persona: six configured scoring weights render as a labelled donut without changing the scoring model.
- Outreach: each creator is counted once in the current-stage donut; A/B/C/D bars exclude and separately label unscored creators.
- Performance: KPIs use the latest snapshot per deliverable, D7/D14/D30 trend lines retain exact values, and creator bars appear only for like-for-like records.
- Empty State checks: passed; blank Workspace dashboards do not create synthetic chart marks.
- Responsive review: passed in a standard desktop viewport and a 600 px-wide browser viewport; no remote assets or CDN requests are used.
