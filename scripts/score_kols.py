#!/usr/bin/env python3
"""Offline KOL scoring and draft generation; Python standard library only."""
import argparse
import csv
from datetime import date
import html
import json
import math
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE_FIELDS = ['candidate_id', 'sample_marker', 'name', 'handle', 'platform',
               'persona_id', 'source_query', 'evidence', 'assessed_on', 'reviewer']
DERIVED = ['rank', 'score', 'tier', 'priority', 'recommendation', 'assessment_type']


def number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label}: expected a finite number')
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label}: expected a finite number') from None
    if not math.isfinite(result):
        raise ValueError(f'{label}: expected a finite number')
    return result


def validate_config(config):
    scale = number(config['scale_max'], 'scale_max')
    if scale <= 0:
        raise ValueError('scale_max must be positive')
    dimensions = config['dimensions']
    if not isinstance(dimensions, dict) or not dimensions:
        raise ValueError('dimensions must be a nonempty object')
    weights = []
    for key, value in dimensions.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in BASE_FIELDS + DERIVED:
            raise ValueError('Invalid dimension name')
        weight = number(value, key)
        if weight < 0:
            raise ValueError('Weights cannot be negative')
        weights.append(weight)
    if not math.isfinite(sum(weights)) or sum(weights) <= 0:
        raise ValueError('Weights need a finite positive total')
    tiers = config['tiers']
    if [t['tier'] for t in tiers] != list('ABCD'):
        raise ValueError('Tiers must be A, B, C, D in that order')
    previous = 101
    for tier in tiers:
        threshold = number(tier['min_score'], 'min_score')
        if not 0 <= threshold <= 100 or threshold >= previous:
            raise ValueError('Thresholds must strictly descend within 0..100')
        previous = threshold
        for field in ['priority', 'recommendation']:
            if not isinstance(tier[field], str) or not tier[field].strip():
                raise ValueError(f'{field} must be nonempty text')
    if number(tiers[-1]['min_score'], 'min_score') != 0:
        raise ValueError('D must start at zero')
    return config


def rank_rows(config, rows):
    validate_config(config)
    seen_ids, seen_handles = set(), set()
    ranked = []
    for row in rows:
        if any(not isinstance(row.get(key), str) or not row[key].strip()
               for key in BASE_FIELDS + list(config['dimensions'])):
            raise ValueError('Missing required candidate values')
        cid = row['candidate_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', cid) or cid.casefold() in seen_ids:
            raise ValueError('Invalid or duplicate candidate ID')
        identity = (row['platform'].strip().casefold(), row['handle'].strip().casefold())
        if identity in seen_handles:
            raise ValueError('Duplicate platform/handle pair')
        date.fromisoformat(row['assessed_on'])
        seen_ids.add(cid.casefold())
        seen_handles.add(identity)
        weighted = 0
        total = sum(float(w) for w in config['dimensions'].values())
        for dimension, weight in config['dimensions'].items():
            rating = number(row[dimension], dimension)
            if not 0 <= rating <= float(config['scale_max']):
                raise ValueError(f'{dimension}: rating outside configured scale')
            weighted += (float(weight) / total) * (rating / float(config['scale_max']))
        score = min(100.0, weighted * 100)
        tier = next(t for t in config['tiers'] if score >= float(t['min_score']))
        ranked.append(dict(row, score=f'{score:.2f}', tier=tier['tier'],
                           priority=tier['priority'], recommendation=tier['recommendation'],
                           assessment_type='AI suggestion', _score=score))
    ranked.sort(key=lambda row: (-row['_score'], row['candidate_id']))
    for index, row in enumerate(ranked, 1):
        row.pop('_score')
        row['rank'] = index
    return ranked


def render_email(template, row):
    return re.sub(r'\{\{([A-Za-z0-9_]+)\}\}',
                  lambda match: str(row.get(match[1], match[0])), template)


def render_dashboard(rows):
    fields = ['rank', 'name', 'handle', 'platform', 'score', 'tier', 'priority', 'recommendation']
    head = ''.join(f'<th scope="col">{html.escape(key)}</th>' for key in fields)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(row[key]))}</td>'
                                   for key in fields) + '</tr>' for row in rows)
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>KOL Outreach Pipeline</title>
<style>body{{font:16px system-ui,sans-serif;margin:2rem;color:#183044;background:#f4f7fa}}table{{border-collapse:collapse;background:white;width:100%}}th,td{{padding:.8rem;border:1px solid #ccd6df;text-align:left}}.table{{overflow:auto}}a{{color:#075d96}}</style>
<h1>KOL Outreach Pipeline</h1><p>Public template. All examples are fictional. 示例/SAMPLE.</p>
<p>AI suggestions — human evidence and brand safety review required. Scores do not authorize contact.</p>
<p><a href="../03-scoring-and-ranking/ranked-kols.csv">Ranked CSV</a> · <a href="../04-outreach-priority/outreach-priority.csv">Priorities</a> · <a href="../06-follow-up-log/README.md">Follow-up guide</a></p>
<p>{len(rows)} candidates. Regenerate after input changes.</p><div class="table"><table><caption>Scored candidates</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></html>\n'''


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / '01-kol-profile-and-scoring/scoring-config.json')
    parser.add_argument('--input', type=Path, default=ROOT / '02-sourcing/candidates.csv')
    parser.add_argument('--output-root', type=Path, default=ROOT)
    parser.add_argument('--email-template', type=Path, default=ROOT / '05-first-email-templates/first-email-template.md')
    parser.add_argument('--generate-emails', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = validate_config(json.loads(args.config.read_text(encoding='utf-8')))
        with args.input.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            required = BASE_FIELDS + list(config['dimensions'])
            if len(fields) != len(set(fields)) or not set(required) <= set(fields) or set(fields) & set(DERIVED):
                raise ValueError('Invalid CSV headers: missing, duplicate, or reserved columns')
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError('Malformed CSV row width')
        ranked = rank_rows(config, rows)
        template = args.email_template.read_text(encoding='utf-8') if args.generate_emails else None
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        parser.error(str(error))
    out = args.output_root
    write_csv(out / '03-scoring-and-ranking/ranked-kols.csv', DERIVED + fields, ranked)
    write_csv(out / '04-outreach-priority/outreach-priority.csv',
              ['candidate_id', 'sample_marker', 'tier', 'priority', 'recommendation', 'assessment_type'], ranked)
    console = out / '00-console/dashboard.html'
    console.parent.mkdir(parents=True, exist_ok=True)
    console.write_text(render_dashboard(ranked), encoding='utf-8')
    if template is not None:
        drafts = out / '05-first-email-templates/drafts'
        if drafts.exists():
            shutil.rmtree(drafts)
        drafts.mkdir(parents=True)
        for row in ranked:
            (drafts / f"{row['candidate_id']}.md").write_text(render_email(template, row), encoding='utf-8')
    print(f'Generated ranked CSV, priorities, dashboard for {len(ranked)} candidates'
          + (' and email drafts.' if template is not None else '.'))


if __name__ == '__main__':
    main()
