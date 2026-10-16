# KOL Outreach Pipeline Template

A lightweight, platform-agnostic workspace for people and AI assistants. Define an ideal key opinion leader (KOL), source creators, score evidence, review outreach priorities, and prepare communication drafts. Markdown, CSV, and a local HTML console require no account or online service.

> **Public template. All examples are fictional.** Every creator, handle, assessment, date, and communication was independently written for demonstration and marked SAMPLE. No real people, email addresses, tokens, credentials, or platform exports are included. Sample handles do not identify or link to real accounts.

## Quick Start

1. Copy this template into a **private workspace** before using real records. Remove fictional candidate rows, follow-up examples, and generated outputs; keep CSV headers.
2. Fill in the [ideal persona](01-kol-profile-and-scoring/ideal-kol-persona-template.md), replacing `{{YOUR_PRODUCT}}` and other placeholders. Adjust the [scoring configuration](01-kol-profile-and-scoring/scoring-config.json) using the [scoring guide](01-kol-profile-and-scoring/README.md).
3. Use the [sourcing playbook](02-sourcing/README.md) and add evidence-backed ratings to [candidates.csv](02-sourcing/candidates.csv). Missing ratings must be researched; they are not silently treated as zero.
4. Run with Python 3.9 or later (standard library only), from this directory:

   ```sh
   python3 -m unittest discover tests
   python3 scripts/score_kols.py --generate-emails
   ```

5. Open [dashboard.html](00-console/dashboard.html) locally. Review [ranked candidates](03-scoring-and-ranking/ranked-kols.csv), [priority recommendations](04-outreach-priority/outreach-priority.csv), and [drafts](05-first-email-templates/drafts). Replace placeholders and obtain human review before any use.
6. Record authorized communications and next actions in [follow-up records](06-follow-up-log/README.md). Nothing sends messages automatically.

## How to use

Paste one of these prompts into an AI agent in PuppyOne, replacing the bracketed inputs; use a private copy for real work and keep this public template limited to blank forms and fictional SAMPLE examples.

### Build a KOL persona from scratch

Turn a campaign brief into concrete audience, content, evidence, and collaboration criteria.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, and 01-kol-profile-and-scoring/ideal-kol-persona-template.md. Using this brief: [product, campaign goal, audience, markets, budget], help me complete the persona template in my private copy. Ask for missing essentials, preserve placeholders for unknowns, and define topics, platforms, audience size fit, evidence window, engagement signals, exclusions, and success measures. Do not invent evidence or human review. In the public template, retain placeholders or use only independently authored fictional SAMPLE content.
```

### Source candidates on a given platform

Use the persona to guide manual discovery and evidence collection on a chosen platform.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/ideal-kol-persona-template.md, 01-kol-profile-and-scoring/README.md, 02-sourcing/README.md, 02-sourcing/candidates.csv, and 06-follow-up-log/. For [platform] and [candidate count], propose persona-based search queries and a manual review checklist. Use only evidence I supply from manual research to add complete, evidence-backed rows to 02-sourcing/candidates.csv in my private copy. Preserve stable candidate IDs, deduplicate platform/handle pairs, and check follow-up history and opt-outs. Report missing evidence as Needs verification in your response; do not invent numeric ratings or add incomplete rows. Do not operate the platform or contact anyone. Keep real records out of the public template.
```

### Score and rank an existing list

Validate candidate inputs and regenerate the ranking, priorities, and dashboard.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, 01-kol-profile-and-scoring/scoring-config.json, 02-sourcing/candidates.csv, and scripts/score_kols.py. Check the existing list for required fields, duplicate IDs or platform/handle pairs, dates, and evidence-backed ratings within the configured scale. Report unresolved issues without inventing values. Once inputs are valid, run python3 -m unittest discover tests and python3 scripts/score_kols.py --generate-emails from the repository root. Summarize 03-scoring-and-ranking/ranked-kols.csv, 04-outreach-priority/outreach-priority.csv, and 00-console/dashboard.html, noting evidence gaps and human review needs. Regenerate derived files instead of editing them; draft generation replaces 05-first-email-templates/drafts/. Scores do not authorize contact.
```

### Write first emails for tier A

Prepare tier-A email text for human review using verified evidence and the reusable template.

```text
Read AGENTS.md, 99-system-rules/, 05-first-email-templates/README.md, 05-first-email-templates/first-email-template.md, and 06-follow-up-log/. Run python3 scripts/score_kols.py --generate-emails to refresh the rankings and drafts; this replaces 05-first-email-templates/drafts/ and generates drafts for every tier, not just A. Select tier A from 03-scoring-and-ranking/ranked-kols.csv, check follow-up history and opt-outs, and present personalized first-email proposals in your response for eligible candidates using [campaign brief] and only supplied, verified content references. Preserve unknown placeholders and flag missing evidence, contact eligibility, brand safety review, or approval. Keep the reusable template's placeholders and do not hand-edit generated drafts. Do not send anything; humans decide whether to contact each candidate.
```

### Update the follow-up log

Record supplied communication events and next actions without inferring authorization or outcomes.

```text
Read AGENTS.md, 99-system-rules/, 06-follow-up-log/README.md, 06-follow-up-log/follow-up-template.csv, 06-follow-up-log/follow-up-example.csv, and 02-sourcing/candidates.csv. In my private copy, append one row per supplied event to 06-follow-up-log/follow-up-template.csv using these facts: [candidate ID, event date, channel, actual event, owner, authorization, next action and date]. Preserve the header, stable candidate IDs, and existing history. Use only Draft, Awaiting reply, Replied, Paused, Closed, or Opted out as statuses. Ask about missing facts; do not invent replies, approvals, dates, or contact attempts. Respect opt-outs and the agreed cadence and attempt limit when suggesting next actions. Do not send messages or schedule anything. Keep real events out of the public template.
```

### Adjust scoring weights and re-rank

Compare the effect of a weight change while preserving the existing scoring dimensions and evidence.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, 01-kol-profile-and-scoring/scoring-config.json, 02-sourcing/candidates.csv, and scripts/score_kols.py. Note current scores, tiers, and ranks from 03-scoring-and-ranking/ranked-kols.csv. Apply these requested dimension weights: [weights and rationale] to 01-kol-profile-and-scoring/scoring-config.json, retaining dimension keys, scale, and tier thresholds. Weights must be finite, nonnegative, and have a positive total; they need not sum to 100. Run python3 -m unittest discover tests and python3 scripts/score_kols.py --generate-emails. Report before/after score, rank, and tier changes and explain the tradeoffs. Do not change evidence or ratings to obtain a desired result, and do not hand-edit derived outputs. Draft generation replaces 05-first-email-templates/drafts/; all recommendations remain subject to human review.
```

## Workspace guide

| Directory | Contents |
| --- | --- |
| [00-console](00-console/README.md) | Static dashboard, daily todos, and sync log |
| [01-kol-profile-and-scoring](01-kol-profile-and-scoring/README.md) | Persona, configurable weighted model, and scoring anchors |
| [02-sourcing](02-sourcing/README.md) | Cross-platform discovery, query templates, and fictional input CSV |
| [03-scoring-and-ranking](03-scoring-and-ranking/README.md) | Generated scores and deterministic ranking |
| [04-outreach-priority](04-outreach-priority/README.md) | Generated tier priorities and recommended actions |
| [05-first-email-templates](05-first-email-templates/README.md) | First-email template and optional generated drafts |
| [06-follow-up-log](06-follow-up-log/README.md) | Blank follow-up records and fictional examples |
| [99-system-rules](99-system-rules/fields-and-statuses.md) | Schema, naming, human review, and public maintenance rules |
| scripts / tests | Offline generator and standard-library unit tests |

## Daily workflow

1. Confirm the persona, campaign goals, capacity, and current scoring weights.
2. Search relevant channels, deduplicate by platform and handle, and record evidence and assessment dates.
3. Review evidence quality, assign dimension ratings, and resolve missing information before scoring.
4. Regenerate outputs after changes. Scores, tiers, and priorities are **AI suggestions**, not approval to contact anyone. Brand-safety concerns require human review regardless of score.
5. Review priority recommendations and personalize drafts with a specific, verified content reference and clear collaboration proposal.
6. Record actual authorized contacts, replies, next actions, and opt-outs. Check the follow-up log before contacting anyone; stop after an opt-out or the agreed follow-up limit.

## Generator options

`python3 scripts/score_kols.py --help` lists `--config`, `--input`, `--output-root`, `--email-template`, and `--generate-emails`. Defaults resolve relative to the repository, so invoking the script from another directory works. Custom paths resolve relative to your working directory. Use a separate output root when experimenting. Email generation replaces the generated drafts directory; keep manual edits elsewhere. Without the flag, existing drafts are left untouched and may be stale.

Weights must be finite, nonnegative, and have a positive total. Ratings must be finite numbers from zero to `scale_max`. Tier thresholds descend strictly from A through D; D starts at zero. Malformed inputs fail before output writing. CSV and HTML are derived views; edit the input and rerun. No scraping, login, scheduled tasks, integrations, or delivery is configured.

## Maintaining the public template

Read [AGENTS.md](AGENTS.md) and [public-template maintenance](99-system-rules/public-template-maintenance.md). Keep real records in a separate private workspace. Ignore rules are only a supporting measure; review content before publication. The template is dedicated to the public domain under [CC0 1.0 Universal](LICENSE).
