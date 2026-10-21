# QA — Creator Outreach Pipeline v3.0

## Automated result

- Test suite: **41/41 passed**
- Blank Workspace validation: passed
- Isolated fictional fixture validation: passed
- Three root Dashboards: regenerated from the blank Workspace
- Three fixture Dashboards: regenerated from the fictional regression data
- Public release boundary: passed
- Formatting check: passed

## Real local-table acceptance

The supplied local creator CSV was tested in dry-run mode against the v3.0 importer:

- Source rows recognised: **50**
- Rows accepted into the temporary database model: **50**
- Duplicate or malformed row failure: none
- Real source file copied into the repository: **no**
- Creator names, contact details and URLs printed to test output: **no**

This acceptance test confirmed the importer can map the supplied Chinese/English header mix, retain unsupported source fields as additional data and avoid making legacy priority fields part of the active workflow.

## Covered scenarios

- CSV with UTF-8 BOM
- XLSX first-sheet reading without external packages
- Minimum viable creator rows with missing supplementary information
- Deterministic ID generation when an input has no Creator ID
- Channel-URL deduplication
- Incremental import that fills blanks without overwriting prior non-empty values
- Original source copy preservation in a private Workspace
- Selected creator starts at “Selected / To Contact”
- Selection and draft creation do not create contact events
- One current outreach state per creator
- Negotiation requires the three Markdown working files
- Proposal/draft, confirmation and publication remain distinct
- Performance accepts local data without UTM
- Performance requires a published deliverable
- Cumulative outcomes cannot decrease
- Cumulative spend reductions require a documented adjustment
- Names-first HTML rendering with secondary internal IDs
- Actionable Empty States in all three root Dashboards
- Public release scanning blocks populated Workspace data and simulated sensitive text

## Manual checks still required in puppyone Desktop

- Attach a CSV through the Desktop UI and confirm the Agent can read the attachment path.
- Attach an XLSX through the Desktop UI and confirm the same first-sheet import behaviour.
- Ask one Agent to import and filter creators, then ask a different Agent to continue from the saved files.
- Confirm the three generated HTML files open correctly in puppyone Desktop preview at wide and narrow panel widths.
- Confirm source copies under 01-workspace/imports remain available to later Agents in a private user project.
- Confirm any connected mail, messaging or analytics tool still asks for explicit action-specific authorisation.

These items depend on the Desktop attachment, preview and multi-Agent runtime and cannot be proven by the repository-only automated suite.
