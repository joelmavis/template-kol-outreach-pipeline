# Creator Outreach Pipeline

Creator Outreach Pipeline is a local-first, Agent-driven workflow for building a YouTube creator database from your own files, selecting the right channels in natural language, managing outreach and collaboration, and reviewing post-publication results.

Open this folder in puppyone Desktop and say:

> Import this creator spreadsheet, then show me the channels most relevant to our current collaboration goal.

You do not need to edit CSV files or create folders manually. The Agent reads the supplied table, maps useful fields, preserves partial records and source provenance, and updates the three HTML Dashboards.

## Folder order

- `01-workspace/` — your three working tables, imported source copies, drafts and collaboration folders.
- `03-templates/` — lightweight collaboration note templates.
- `04-tools/` — local import, validation and Dashboard utilities.
- `05-tests/` — isolated fictional fixtures and automated checks; not part of the starting workspace.

## Start from a local table

The preferred input is a CSV or XLSX creator table. Existing exports, internal lists and manually maintained spreadsheets are all valid starting points.

Examples:

- “Import this table. Keep all useful source columns and leave unavailable fields blank.”
- “From the imported creators, select English-language productivity channels with 10K–100K subscribers and a public contact route.”
- “Move these six channels into outreach as Selected / To Contact. Do not record them as contacted.”
- “Prepare one personalised email and DM draft for each selected creator. Do not send anything.”
- “This creator replied and shared a proposal. Update the relationship and create the collaboration folder.”
- “Import this D14 performance spreadsheet and update the Performance Dashboard.”

If a supplied table does not contain every standard field, the import still succeeds. Missing information remains blank or `Unknown`; it is never invented. Extra source columns are retained in `additional_data_json`, and an original source copy is preserved under `01-workspace/imports/` in private working copies.

## The five-step workflow

1. **Creator Database** — import local CSV/XLSX tables, map fields, deduplicate by channel URL and continue in batches.
2. **Natural-language filtering** — describe the audience size, content direction, region, language, contactability or recent activity you need. The Agent explains the applied criteria and synchronises only the selected channels to outreach.
3. **Outreach** — create personalised drafts, then record real contact, replies and follow-ups only after they occur.
4. **Collaboration** — keep relationship status in `outreach-progress.csv` and detailed working history in one creator folder containing negotiation, pricing and contract-draft notes.
5. **Performance** — import or describe D7/D14/D30 results after publication. UTM is optional; cost and conversion metrics appear only when the measurement source and definition are clear.

## Three data tables

- `01-workspace/creators.csv` — creator identity, public information, source trace, field completeness and missing information. External verification is optional.
- `01-workspace/outreach-progress.csv` — selected creators, current outreach state, real communication events and collaboration/deliverable status. Creator Name and business fields come first; stable IDs remain at the end.
- `01-workspace/performance.csv` — cumulative D7/D14/D30 results for published deliverables.

HTML files are generated views, not additional tables.

## Three Dashboards

- `creator-database-dashboard.html` — creator totals, field completeness, subscriber bands, content categories, filter results, missing information and creator-specific next actions.
- `outreach-dashboard.html` — selected creators, contact/reply/negotiation status, recent communication and next actions.
- `performance-dashboard.html` — D7/D14/D30 trends, downloads, installs, cost efficiency and like-for-like comparisons.

All pages are generated from local files, use no external CDN and show clear Empty States when the workspace has no data. Partial rows still appear: supplied values are shown, missing values remain empty or `N/A`, and internal IDs stay secondary to channel, collaboration and content names.

## Collaboration folders

When a creator enters negotiation, create:

```text
01-workspace/collaborations/<creator-name-or-stable-slug>/
├── negotiation-summary.md
├── pricing.md
└── contract-draft.md
```

Use the files under `03-templates/collaboration/`. A contract draft is not a signed agreement, and only explicit user confirmation may advance the relationship to `Confirmed`.

## Validation modes

**User Workspace Mode** is normal use. It accepts populated tables and partial creator records:

```sh
python3 04-tools/validate_workspace.py --source 01-workspace
python3 04-tools/build_dashboards.py
```

**Template Release Mode** is only for maintainers preparing the blank public repository:

```sh
python3 04-tools/check_public_release.py
```

Never delete user records or imported files to satisfy a release check. Keep real creator contacts, proposals and results in a private working copy outside the public template repository.

## Maintainer checks

```sh
python3 04-tools/import_creator_batch.py path/to/creators.csv --dry-run
python3 04-tools/import_performance_data.py path/to/results.xlsx --dry-run
python3 04-tools/build_dashboards.py
python3 04-tools/build_dashboards.py --source 05-tests/fixtures/sample-creator-campaign --output 05-tests/fixtures/sample-creator-campaign --fixture
python3 04-tools/validate_workspace.py
python3 -m unittest discover -s 05-tests
python3 04-tools/check_public_release.py
```

The utilities use only the Python standard library. They do not scrape platforms, send messages, sign contracts, schedule meetings, connect analytics or make payments.

## License

Released under [CC0 1.0 Universal](LICENSE). Review all content before publishing a fork, and keep private creator data out of public repositories.
