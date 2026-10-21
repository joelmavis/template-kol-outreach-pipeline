# Creator Outreach Pipeline

## Folder order

- `01-workspace/` — the blank private-work starting point.
- `02-examples/` — the complete fictional creator campaign.
- `03-config/` — the preserved six-dimension scoring configuration.
- `04-tools/` — dashboard, validation and release utilities.
- `05-tests/` — automated workflow and release checks.

Creator Outreach Pipeline is a ready-to-use workflow for defining the right creator profile, finding and scoring candidates, preparing personalized outreach, tracking real conversations, and reviewing published partnership results. Open this folder in puppyone Desktop and tell an Agent what you are promoting, who it is for, which platforms matter, and what kind of content you want. The Agent will build a persona for your approval before discovery begins, then keep the workspace and three HTML dashboards up to date. Drafts are never treated as sent messages, and scores never authorize contact. Real work stays in `01-workspace/`; the complete fictional campaign in `02-examples/sample-creator-campaign/` shows how every stage fits together.

## Start with one sentence

Say something like:

> Build a creator persona for a privacy-first meeting notes app for English-speaking product managers. Focus on YouTube and LinkedIn creators who publish practical workflow tutorials.

Then continue naturally:

- “The persona looks right. Find up to 20 creators and record only what you can verify.”
- “Prepare individual email and DM drafts for the top five eligible creators. Do not send anything.”
- “I sent the email to C-0003 today. Record that fact and suggest the next step.”
- “This creator offered two packages with different payment terms. Preserve both versions.”
- “The video went live on 12 November. Create D7, D14 and D30 tracking rows.”

## What you will see

- `persona-dashboard.html` — the current creator profile, confirmation state and six-dimension scoring-weight chart.
- `outreach-dashboard.html` — ranked candidates, contact states, tier distribution, negotiations, next actions and risks.
- `performance-dashboard.html` — latest-snapshot KPIs, cumulative D7/D14/D30 trends and like-for-like creator comparisons.

Each page prints the relevant source-file paths. Links are convenient but are not the only way to navigate in Desktop preview. Charts are generated from the same local configuration and CSV records as the tables, use no external assets or CDN, and show an Empty State instead of invented values when the required data is absent.

## Three data tables

The workspace intentionally exposes only three CSV tables:

- `creators.csv` — screened creators, evidence, six-dimension scores and ranking.
- `outreach-progress.csv` — relationship progress in one place. Typed rows hold current outreach state, activity history, offer versions and partnership/deliverable records.
- `performance.csv` — cumulative D7/D14/D30 results for published deliverables.

`persona.md` and the three HTML dashboards remain supporting documents and generated views; they are not additional data tables.

## The workflow

1. **Persona** — turn a short description, public URL or readable attachment into `01-workspace/persona.md`; confirm it before discovery.
2. **Discovery** — find as many candidates as the available evidence supports; never fill a requested quota with invented accounts.
3. **Scoring and drafts** — score only evidence-ready candidates with the six preserved dimensions; create a separate proposal, email draft and DM opener for each selected creator.
4. **Outreach** — add a current-state row only after the user reports a real send; append one event for each actual interaction.
5. **Follow-up** — record replies and facts, preserve opt-outs, and recommend rather than claim future actions.
6. **Offers and materials** — keep each package and payment structure as a separate offer; save authorized summaries and accessible files under the creator’s stable ID.
7. **Partnerships** — keep Negotiating, Confirmed, Published, Completed and Closed Lost distinct; publication date is D0.
8. **Review** — add cumulative D7/D14/D30 evidence only for published deliverables and state attribution limits.

See `PLAYBOOK.md` for field ownership and transition rules. `AGENTS.md` contains the shared rules every compatible file-based Agent should follow.

## Example campaign

`02-examples/sample-creator-campaign/` contains five fictional creators and demonstrates:

- discovery with missing evidence;
- verified scoring and unsent personalized drafts;
- synthetic correspondence and negotiation with multiple offers;
- a confirmed, published partnership with illustrative D7/D14/D30 data.

All names, accounts, messages, URLs and metrics in the example are illustrative. They do not represent real people or activity and are never copied into `01-workspace/`.

## Keep real work private

The tracked `01-workspace/*.csv`, `01-workspace/persona.md` and three root dashboards are intentionally blank starter files. Because they are already tracked by Git, adding them to `.gitignore` would **not** prevent later business data from being committed.

Before entering real creator or commercial information, make a working copy of this folder outside the public repository—for example, unzip the release into a separate private project folder and open that folder in puppyone. Keep the public repository as the distributable blank template. If a maintainer temporarily tests inside the repository, restore the blank workspace, rebuild the root dashboards and run this review before committing:

```sh
python3 04-tools/check_public_release.py
git status --short -- 01-workspace persona-dashboard.html outreach-dashboard.html performance-dashboard.html
git diff -- 01-workspace persona-dashboard.html outreach-dashboard.html performance-dashboard.html
```

Review every listed change. The release check blocks non-empty tracked workspace tables, collaboration/draft files, stale root dashboards, non-reserved Example contact domains and common sensitive-data patterns across public Markdown, CSV, HTML and JSON files. In an exported ZIP without Git metadata, it reports the Git check as skipped instead of claiming a clean repository. It complements—not replaces—human review of the complete staged diff.

## Two validation modes

- **User Workspace Mode** is the normal workflow. `python3 04-tools/validate_workspace.py` accepts a confirmed Persona and populated tables, and checks data integrity without deleting or resetting anything.
- **Template Release Mode** is only for maintainers preparing the blank public repository. `python3 04-tools/check_public_release.py` intentionally blocks confirmed Personas, business rows, drafts, collaboration material, and stale dashboards.

Agents must not run Template Release Mode after each user update. Automated release tests create their own clean temporary fixture, so the test suite can run without assuming that the user's `01-workspace/` is blank. If this working folder still points to GitHub or GitLab, treat all real creator contacts, prices, messages, and results as at risk of accidental publication until the work is moved to a private copy.

## Maintainer checks

End users do not need to run scripts. Maintainers and capable Agents rebuild and validate the static views with:

```sh
python3 04-tools/build_dashboards.py
python3 04-tools/build_dashboards.py --source 02-examples/sample-creator-campaign --output 02-examples/sample-creator-campaign --example
python3 04-tools/validate_workspace.py
python3 -m unittest discover -s 05-tests
```

Run `python3 04-tools/check_public_release.py` separately only when preparing a clean public template release.

The scripts use only the Python standard library. They do not scrape platforms, send messages, schedule reminders, connect analytics, sign contracts or make payments.

## License

Released under [CC0 1.0 Universal](LICENSE). Review all content before publishing a fork, and keep private creator data out of public repositories.
