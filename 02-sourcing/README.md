# Sourcing playbook

Start with the persona's audience problem, topics, language, and format. Search manually on the relevant platforms, inspect recent content and substantive comments, and record the evidence window. Platform examples are discovery ideas, not integrations or endorsements.

| Channel | Discovery approach | Query template |
| --- | --- | --- |
| YouTube | Topic videos, adjacent channels, creator collaborations | `{{TOPIC}} {{AUDIENCE_PROBLEM}} {{LANGUAGE}}` |
| X | Topic discussions, creator replies, relevant lists | `"{{TOPIC}}" "{{USE_CASE}}"` |
| Xiaohongshu / 小红书 | Topic keywords, educational notes, relevant tags | `{{中文主题}} {{目标人群}} {{使用场景}}` |
| Instagram / TikTok | Topic tags and related format creators | `{{TOPIC_TAG}} {{FORMAT}}` |
| Blogs / newsletters / podcasts | Niche roundups, interviews, author archives | `{{NICHE}} {{FORMAT}} {{MARKET}}` |

Adapt query syntax to the channel. Explore adjacent terms and smaller specialists; avoid follower count as the only filter. Respect platform access rules and creators' contact preferences. This template does not scrape or retrieve anything.

Use `candidate_id` as a stable key. Check existing rows and follow-up logs before adding someone. Deduplicate platform + case-insensitive handle; cross-platform identity merges require evidence. Record the persona ID, source query, evidence summary/reference, date, reviewer, and ratings. Keep contact details in a separate private workspace.

`candidates.csv` contains only invented 示例/SAMPLE data; its evidence is demonstration text, not verified research. Never visit sample handles as if they were sourced accounts.
