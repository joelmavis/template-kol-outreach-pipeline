# Profile and scoring model

Complete the persona first. The default configurable model weights audience fit 30, content relevance 25, engagement quality 20, audience size band 5, brand safety 15, and collaboration readiness 5. Weights need not sum to 100; the generator normalizes them.

`score = 100 × sum(weight × rating / scale_max) / sum(weights)`

The default scale is 0–5. Score thresholds are inclusive: A ≥85, B ≥70, C ≥50, D ≥0. Classification uses the unrounded score; displayed scores have two decimals. Edit weights, scale, thresholds, priority labels, and recommendations in `scoring-config.json`. Dimension keys correspond to CSV columns; adding a dimension requires a matching numeric column. Tier names remain A/B/C/D.

| Dimension | 0 anchor | Midpoint anchor (2.5) | 5 anchor |
| --- | --- | --- | --- |
| audience_fit | No demonstrated target overlap | Partial evidenced overlap | Strong evidenced overlap |
| content_relevance | Unrelated topics | Some relevant recent work | Consistent relevant recent work |
| engagement_quality | Predominantly low-quality interactions | Mixed substantive responses | Consistent substantive discussion |
| audience_size_band | Outside useful campaign range | Adjacent to desired range | Within persona sweet spot |
| brand_safety | Documented unresolved conflicts | Review flags need resolution | Reviewed sample fits stated requirements |
| collaboration_readiness | Incompatible availability or scope | Unclear terms or availability | Explicitly compatible stated terms |

Interpolate using documented evidence; these anchors are a starting point, not universal truth. Size fit is not raw follower count: a smaller specialist may score higher. Compare engagement within channel/format context, not raw likes across platforms. Missing evidence is `Needs verification` in notes and must be resolved before entering a numeric rating; zero means an evidenced low rating.

Record evidence, assessment date, reviewer, and uncertainty. Example ratings are fabricated illustrations. Brand safety is not guaranteed by a high aggregate: humans must separately resolve any concerns before outreach.
