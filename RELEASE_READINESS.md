# Release readiness

## Scope

Creator Outreach Pipeline v2.0 upgrades the original KOL scoring template without changing its six scoring dimensions or A/B/C/D thresholds. The user experience is conversation-first; CSV and HTML maintenance is performed by a capable Agent rather than required from the end user.

## Included

- Exactly three main dashboards: persona, outreach and performance.
- Blank real-workspace schemas with stable IDs and separate current-state/history tables.
- Evidence-aware scoring that leaves incomplete candidates unscored.
- Cross-table creator, offer, collaboration, deliverable and UTM campaign ownership checks.
- UTC-normalized confirmation, publication and D7/D14/D30 measurement-window validation.
- Draft-only authorization gate, append-only activity model, multi-offer support and distinct confirmation/publication states.
- Per-deliverable cumulative D7/D14/D30 tracking with non-decreasing spend checks and documented refund/correction handling.
- Spend, cost per download/install, like-for-like comparison and evidence-bounded next actions in the existing Performance Dashboard.
- One complete campaign containing five fictional creators, individual draft material, negotiation summaries, a published illustrative partnership and three dashboards.
- Standard-library build/validation scripts and automated tests.

## Data boundary

The public example contains only fictional identities, reserved `example.com` URLs, synthetic correspondence and illustrative metrics. No internal creator negotiations, real prices, private contact information or collaboration attachments are included. `workspace/` is blank. Real use must happen in a separate private working copy outside the public repository because `.gitignore` cannot protect these already-tracked starter files. `scripts/check_public_release.py` verifies the blank workspace, blank-derived root dashboards, reserved Example domains and public text files before release; exported copies without Git metadata are explicitly reported as skipped for the Git-status step.

## Known environment limits

- puppyone Desktop link behavior and cross-Agent attachment persistence require live client verification; the template does not claim they were verified.
- Web discovery, authenticated platform access, delivery, calendar reminders and analytics depend on the active Agent’s connected capabilities and separate user authorization.
- The dashboards are static generated views, not live platform synchronization.

## Final gate

Release only after both dashboard builds, validation, `scripts/check_public_release.py`, the full unit-test suite, a stale/private-data search and `git diff --check` pass. Review `git status` and the staged diff for `workspace/` plus the three root dashboards. Record the actual results rather than claiming success from file presence alone.

## Previous verification on 2026-10-21

- Blank workspace build: passed; three dashboards generated.
- Fictional campaign build: passed; three dashboards generated.
- Data validation: passed for 0-user-data workspace and five-creator example.
- Automated tests: 16 passed.
- Browser review: persona, outreach and performance example dashboards rendered successfully in a standard browser.
- Privacy/branding scan: no internal case names, real channel URLs, Gmail addresses, legacy title or capitalized brand spelling found.
- `git diff --check`: passed.
- puppyone Desktop-specific preview behavior and cross-Agent attachment persistence remain explicitly unverified environment capabilities.

## Fix-brief release gate

**Recommendation: Ready for release**, subject to the explicitly unverified client/integration checks below.

- P0 cross-table and time validation: passed.
- P1 scoring evidence gates: passed; incomplete `Verified` rows become `Needs verification / Unscored`.
- P1 Performance analysis: passed; spend, CPD, CPI, like-for-like comparison rules and evidence-bounded next actions are present without adding a dashboard.
- P1 public-data isolation: passed; blank tracked workspace, blank-derived root dashboards, reserved Example domains and a maintainer pre-commit check are enforced.
- Automated tests: 31 passed.
- Standard-browser review: passed for the updated Example Performance Dashboard.
- Privacy, branding and whitespace checks: passed.

Not verified: puppyone Desktop-specific HTML preview, a live eight-step campaign with real platform tools, cross-Agent attachment persistence, email/DM delivery and live analytics. These are environment-dependent and are not represented as completed product capabilities.

## Final-fix verification on 2026-10-21

**Recommendation: Ready for public v2.0 release**, with the client-dependent checks below still requiring manual verification.

- UTM attribution: passed; Performance campaign and optional creator attribution must match the corresponding published partnership. Legitimate cross-campaign work uses a separate collaboration and deliverable.
- Cumulative spend: passed; unexplained decreases are blocked, documented refunds/corrections are accepted, and CPD/CPI use the adjusted cumulative amount.
- Public release boundary: passed; public Markdown, CSV, HTML and JSON files are scanned for common sensitive-data patterns. A non-Git release copy reports `Skipped — Not a Git Repository`.
- Automated tests: 39/39 passed, including the new negative and exception-path cases.
- Data/build checks: blank workspace and five-creator fictional Example passed; all three root dashboards and all three Example dashboards were regenerated.
- Structure: the eight-step workflow, three dashboard types, six scoring dimensions and existing Example structure remain unchanged.

Still requires manual testing in puppyone Desktop: open all three dashboards through the client preview; confirm relative/local navigation behavior; run one eight-step handoff across different Agents with attachments; confirm permission prompts before real email/DM delivery; and verify a real analytics import against the platform source. No live outreach, delivery or real commercial data was used in this verification.
