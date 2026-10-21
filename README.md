# Creator Outreach Pipeline

## Folder order

- `01-workspace/` — the blank private-work starting point.
- `02-examples/` — the complete fictional creator campaign.
- `03-config/` — the preserved six-dimension scoring configuration.
- `04-tools/` — dashboard, validation and release utilities.
- `05-tests/` — automated workflow and release checks.

Creator Outreach Pipeline is a ready-to-use YouTube creator database and collaboration workflow. Open this folder in puppyone Desktop and provide either a product or collaboration brief, or one or more YouTube channel links. The Agent can save the first verified batch immediately, continue filling missing public information later, prepare personalised outreach, track real conversations and review published partnership results. Drafts are never treated as sent messages, scores never authorize contact, and missing data is never converted into invented facts. Real work stays in `01-workspace/`; the fictional YouTube campaign in `02-examples/sample-creator-campaign/` shows how every stage fits together.

## Start with one sentence

Say something like:

> Find 20 YouTube creators for a privacy-first meeting notes app used by English-speaking product managers. Save them in batches and keep unavailable fields blank.

Then continue naturally:

- “Start with these five YouTube channel links and build the database from what you can verify.”
- “Continue from the existing CSV and complete the next batch without overwriting earlier results.”
- “Prepare individual email and DM drafts for the top five eligible creators. Do not send anything.”
- “I sent the email to C-0003 today. Record that fact and suggest the next step.”
- “This creator offered two packages with different payment terms. Preserve both versions.”
- “The video went live on 12 November. Create D7, D14 and D30 tracking rows.”

## What you will see

- `creator-database-dashboard.html` — creator totals, verification, contactability, scoring tiers, subscriber bands, ranking and missing data.
- `outreach-dashboard.html` — ranked candidates, contact states, tier distribution, negotiations, next actions and risks.
- `performance-dashboard.html` — latest-snapshot KPIs, cumulative D7/D14/D30 trends and like-for-like creator comparisons.

Each page prints the relevant source-file paths. Links are convenient but are not the only way to navigate in Desktop preview. Charts are generated from the same local configuration and CSV records as the tables, use no external assets or CDN, and show an Empty State instead of invented values when the required data is absent.

## Three data tables

The workspace intentionally exposes only three CSV tables:

- `creators.csv` — channel identity and source, verification state, optional subscriber/view/frequency/engagement/contact fields, six-dimension scores and ranking. Partial rows are valid.
- `outreach-progress.csv` — relationship progress in one place. Typed rows hold current outreach state, activity history, offer versions and partnership/deliverable records.
- `performance.csv` — cumulative D7/D14/D30 results for published deliverables.

The three HTML dashboards are generated views, not additional data tables.

## The workflow

1. **Creator Database** — start from a product brief, collaboration material, channel links, a creator list or CSV. Discover and verify in batches, save partial rows and continue from the existing database.
2. **Personalised Outreach** — score only evidence-supported records with the preserved six dimensions; create a separate proposal, email draft and DM opener for each user-selected creator.
3. **Outreach Tracking** — record a current state only after the user reports a real send; append one event for each actual interaction and preserve opt-outs.
4. **Collaboration Management** — keep packages, payment structures, negotiation records, briefs and deliverables distinct under stable creator and collaboration IDs.
5. **Performance Tracking** — add cumulative D7/D14/D30 evidence only for published deliverables and state attribution limits.

See `PLAYBOOK.md` for field ownership and transition rules. `AGENTS.md` contains the shared rules every compatible file-based Agent should follow.

## Example campaign

`02-examples/sample-creator-campaign/` contains five fictional YouTube creators and demonstrates:

- discovery with missing evidence;
- verified scoring and unsent personalized drafts;
- synthetic correspondence and negotiation with multiple offers;
- a confirmed, published partnership with illustrative D7/D14/D30 data.

All names, accounts, messages, URLs and metrics in the example are illustrative. They do not represent real people or activity and are never copied into `01-workspace/`.

## Keep real work private

The tracked `01-workspace/*.csv` and three root dashboards are intentionally blank starter files. Because they are already tracked by Git, adding them to `.gitignore` would **not** prevent later business data from being committed.

Before entering real creator or commercial information, make a working copy of this folder outside the public repository—for example, unzip the release into a separate private project folder and open that folder in puppyone. Keep the public repository as the distributable blank template. If a maintainer temporarily tests inside the repository, restore the blank workspace, rebuild the root dashboards and run this review before committing:

```sh
python3 04-tools/check_public_release.py
git status --short -- 01-workspace creator-database-dashboard.html outreach-dashboard.html performance-dashboard.html
git diff -- 01-workspace creator-database-dashboard.html outreach-dashboard.html performance-dashboard.html
```

Review every listed change. The release check blocks non-empty tracked workspace tables, collaboration/draft files, stale root dashboards, non-reserved Example contact domains and common sensitive-data patterns across public Markdown, CSV, HTML and JSON files. In an exported ZIP without Git metadata, it reports the Git check as skipped instead of claiming a clean repository. It complements—not replaces—human review of the complete staged diff.

## Two validation modes

- **User Workspace Mode** is the normal workflow. `python3 04-tools/validate_workspace.py` accepts partial Creator Database rows and populated business tables, and checks data integrity without deleting or resetting anything.
- **Template Release Mode** is only for maintainers preparing the blank public repository. `python3 04-tools/check_public_release.py` intentionally blocks business rows, drafts, collaboration material and stale dashboards.

Agents must not run Template Release Mode after each user update. Automated release tests create their own clean temporary fixture, so the test suite can run without assuming that the user's `01-workspace/` is blank. If this working folder still points to GitHub or GitLab, treat all real creator contacts, prices, messages, and results as at risk of accidental publication until the work is moved to a private copy.

## Maintainer checks

End users do not need to run scripts. Maintainers and capable Agents rebuild and validate the static views with:

```sh
python3 04-tools/build_dashboards.py
python3 04-tools/build_dashboards.py --source 02-examples/sample-creator-campaign --output 02-examples/sample-creator-campaign --example
python3 04-tools/import_creator_batch.py path/to/creator-batch.csv
python3 04-tools/validate_workspace.py
python3 -m unittest discover -s 05-tests
```

Run `python3 04-tools/check_public_release.py` separately only when preparing a clean public template release.

The scripts use only the Python standard library. They do not scrape platforms, send messages, schedule reminders, connect analytics, sign contracts or make payments.

## License

Released under [CC0 1.0 Universal](LICENSE). Review all content before publishing a fork, and keep private creator data out of public repositories.
