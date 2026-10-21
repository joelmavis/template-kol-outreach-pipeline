# Creator Outreach Pipeline playbook

## 1. Import and maintain the Creator Database

Start from a local CSV or XLSX table whenever possible. Read the header, map recognisable fields into `creators.csv`, keep useful unmapped fields in `additional_data_json`, and preserve the source filename and row number.

Minimum viable row:

- Creator ID
- Channel name

Add channel URL, public source, checked date and supplementary fields when they are available. A missing subscriber count, email, average view count or country must not block the row.

Import in manageable batches. Deduplicate by channel URL when available, retain prior non-empty values and save after each batch. If an import is interrupted, reopen the current `creators.csv` and continue; never replace the database with only the unfinished batch.

## 2. Filter with natural language

The user describes the creators they need. Translate that request into transparent filters over recorded fields, such as:

- subscriber range;
- content category or keyword;
- language or region;
- public contact availability;
- recent activity or specific source fields.

Return the matching channel names and briefly explain why they matched. After the user selects creators, create or update one `outreach` row per creator with `Selected / To Contact`. Do not infer a send, reply or negotiation.

## 3. Prepare and track outreach

For each selected creator, prepare a separate email and DM draft using only recorded facts. Keep unavailable details explicit; do not fake personalisation.

Only after a real action occurs:

1. update the creator's current outreach row;
2. append one `activity` row with date, channel, summary and evidence source;
3. record the next action and next follow-up date;
4. rebuild the Outreach Dashboard.

## 4. Manage collaboration files

When a creator enters negotiation, create a stable folder under `01-workspace/collaborations/` and copy the three templates:

- `negotiation-summary.md` — latest state, key facts, open questions and next action;
- `pricing.md` — every proposal version, payment timing, deliverables and rights;
- `contract-draft.md` — working terms with an explicit Draft status.

Keep the current relationship status and collaboration folder path in `outreach-progress.csv`. Keep detailed working history in Markdown. Do not create a complex approval system; only explicit user confirmation changes the status to `Confirmed`.

## 5. Import and review performance

After publication, accept local CSV/XLSX results or a user-provided natural-language update. Match each row to exactly one published collaboration and deliverable.

Record:

- D7, D14 or D30 window;
- measurement date when known;
- downloads, installs and other supplied cumulative metrics;
- cumulative spend and currency;
- attribution source and metric definition;
- verification state and notes;
- optional UTM reference.

If the window or source is unclear, keep the record pending rather than calculating a confident result. Cumulative outcomes may not decline. A documented refund or correction may reduce spend only when the notes contain `[Spend adjustment: reason]`.

## Safe state transitions

```text
Selected / To Contact → Contacted → Replied → Negotiating
Negotiating → Confirmed → Published → Completed
Any active stage → Paused / Opted out / Closed Lost
```

No transition is automatic. Preserve an activity record or evidence source for every external-world change.

## Validation

Use `python3 04-tools/validate_workspace.py --source 01-workspace` during normal work. It validates IDs, cross-table relationships, collaboration folder requirements and cumulative performance without requiring a blank workspace.

Use `python3 04-tools/check_public_release.py` only in a clean release copy. A public-release failure must never be repaired by deleting the user's records.
