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

## How to use / 使用方法

Paste one of these prompts into an AI agent in PuppyOne, replacing the bracketed inputs; use a private copy for real work and keep this public template limited to blank forms and fictional 示例/SAMPLE examples.

### Build a KOL persona from scratch / 从零建立 KOL 画像

Turn a campaign brief into concrete audience, content, evidence, and collaboration criteria.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, and 01-kol-profile-and-scoring/ideal-kol-persona-template.md. Using this brief: [product, campaign goal, audience, markets, budget], help me complete the persona template in my private copy. Ask for missing essentials, preserve placeholders for unknowns, and define topics, platforms, audience size fit, evidence window, engagement signals, exclusions, and success measures. Do not invent evidence or human review. In the public template, retain placeholders or use only independently authored fictional 示例/SAMPLE content.

中文：阅读上述规则和画像模板，根据[产品、目标、受众、市场、预算]完善私有副本中的画像；缺失信息先询问或保留占位符，不编造证据或审核。公开模板仅保留占位符或虚构示例。
```

### Source candidates on a given platform / 按画像寻找平台候选人

Use the persona to guide manual discovery and evidence collection on a chosen platform.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/ideal-kol-persona-template.md, 01-kol-profile-and-scoring/README.md, 02-sourcing/README.md, 02-sourcing/candidates.csv, and 06-follow-up-log/. For [platform] and [candidate count], propose persona-based search queries and a manual review checklist. Use only evidence I supply from manual research to add complete, evidence-backed rows to 02-sourcing/candidates.csv in my private copy. Preserve stable candidate IDs, deduplicate platform/handle pairs, and check follow-up history and opt-outs. Report missing evidence as Needs verification in your response; do not invent numeric ratings or add incomplete rows. Do not operate the platform or contact anyone. Keep real records out of the public template.

中文：按画像为[平台]设计搜索词和人工筛选清单；仅用我提供的研究证据在私有副本中补充完整候选记录，保留 ID、去重并检查跟进及退订。缺失证据标记待核实，不编造评分，不操作平台或联系候选人。
```

### Score and rank an existing list / 为现有名单评分排序

Validate candidate inputs and regenerate the ranking, priorities, and dashboard.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, 01-kol-profile-and-scoring/scoring-config.json, 02-sourcing/candidates.csv, and scripts/score_kols.py. Check the existing list for required fields, duplicate IDs or platform/handle pairs, dates, and evidence-backed ratings within the configured scale. Report unresolved issues without inventing values. Once inputs are valid, run python3 -m unittest discover tests and python3 scripts/score_kols.py --generate-emails from the repository root. Summarize 03-scoring-and-ranking/ranked-kols.csv, 04-outreach-priority/outreach-priority.csv, and 00-console/dashboard.html, noting evidence gaps and human review needs. Regenerate derived files instead of editing them; draft generation replaces 05-first-email-templates/drafts/. Scores do not authorize contact.

中文：检查现有名单、证据和评分配置，缺失信息不得编造；输入有效后运行上述测试与生成命令，汇总排名、优先级和看板，提醒草稿目录会被替换，评分不代表联系授权。
```

### Write first emails for tier A / 为 A 档撰写首封邮件

Prepare tier-A email text for human review using verified evidence and the reusable template.

```text
Read AGENTS.md, 99-system-rules/, 05-first-email-templates/README.md, 05-first-email-templates/first-email-template.md, and 06-follow-up-log/. Run python3 scripts/score_kols.py --generate-emails to refresh the rankings and drafts; this replaces 05-first-email-templates/drafts/ and generates drafts for every tier, not just A. Select tier A from 03-scoring-and-ranking/ranked-kols.csv, check follow-up history and opt-outs, and present personalized first-email proposals in your response for eligible candidates using [campaign brief] and only supplied, verified content references. Preserve unknown placeholders and flag missing evidence, contact eligibility, brand safety review, or approval. Keep the reusable template's placeholders and do not hand-edit generated drafts. Do not send anything; humans decide whether to contact each candidate.

中文：运行上述生成命令后只筛选 A 档供审核；生成器会替换所有档位的草稿。检查跟进及退订，用[活动简报]和已核实证据在回复中起草邮件，未知项保留占位符，不手改生成文件，不发送。
```

### Update the follow-up log / 更新跟进记录

Record supplied communication events and next actions without inferring authorization or outcomes.

```text
Read AGENTS.md, 99-system-rules/, 06-follow-up-log/README.md, 06-follow-up-log/follow-up-template.csv, 06-follow-up-log/follow-up-example.csv, and 02-sourcing/candidates.csv. In my private copy, append one row per supplied event to 06-follow-up-log/follow-up-template.csv using these facts: [candidate ID, event date, channel, actual event, owner, authorization, next action and date]. Preserve the header, stable candidate IDs, and existing history. Use only Draft, Awaiting reply, Replied, Paused, Closed, or Opted out as statuses. Ask about missing facts; do not invent replies, approvals, dates, or contact attempts. Respect opt-outs and the agreed cadence and attempt limit when suggesting next actions. Do not send messages or schedule anything. Keep real events out of the public template.

中文：依据[候选 ID、日期、渠道、实际事件、负责人、授权、下一步及日期]在私有副本的空白跟进表追加事件；保留表头和历史，使用规定状态，缺失事实先询问，遵守退订和跟进上限，不发送或安排任务。
```

### Adjust scoring weights and re-rank / 调整权重并重新排序

Compare the effect of a weight change while preserving the existing scoring dimensions and evidence.

```text
Read AGENTS.md, 99-system-rules/, 01-kol-profile-and-scoring/README.md, 01-kol-profile-and-scoring/scoring-config.json, 02-sourcing/candidates.csv, and scripts/score_kols.py. Note current scores, tiers, and ranks from 03-scoring-and-ranking/ranked-kols.csv. Apply these requested dimension weights: [weights and rationale] to 01-kol-profile-and-scoring/scoring-config.json, retaining dimension keys, scale, and tier thresholds. Weights must be finite, nonnegative, and have a positive total; they need not sum to 100. Run python3 -m unittest discover tests and python3 scripts/score_kols.py --generate-emails. Report before/after score, rank, and tier changes and explain the tradeoffs. Do not change evidence or ratings to obtain a desired result, and do not hand-edit derived outputs. Draft generation replaces 05-first-email-templates/drafts/; all recommendations remain subject to human review.

中文：按[权重及理由]调整配置中的现有维度权重，保持量表、阈值和候选证据不变；权重须有限、非负且总和大于零。运行上述测试和生成命令，对比得分、排名及档位变化，提醒草稿会被替换，建议需人工审核。
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
