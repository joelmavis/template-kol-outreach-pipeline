# Fields and statuses

Input CSV requires `candidate_id`, `sample_marker`, `name`, `handle`, `platform`, `persona_id`, `source_query`, `evidence`, `assessed_on`, `reviewer`, and each configured dimension. Required values cannot be blank. `assessed_on` is an ISO date. IDs and platform/handle pairs must be unique. Ratings use the configured scale. Extra columns are retained unless they collide with generated fields: `rank`, `score`, `tier`, `priority`, `recommendation`, `assessment_type`.

Generated assessment type is `AI suggestion`; tiers are A/B/C/D, with configurable minimum scores, priorities, and recommendations. A score is not a contact status. Follow-up statuses are defined in the follow-up guide and maintained by humans.
