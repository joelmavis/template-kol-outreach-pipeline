# KOL Outreach Pipeline Template

A lightweight, platform-agnostic workspace for people and AI assistants. Define an ideal key opinion leader (KOL), source creators, score evidence, review outreach priorities, and prepare communication drafts. Markdown, CSV, and a local HTML console require no account or online service.

> **Public template. All examples are fictional.** Every creator, handle, assessment, date, and communication was independently written for demonstration and marked 示例/SAMPLE. No real people, email addresses, tokens, credentials, or platform exports are included. Sample handles do not identify or link to real accounts.

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
