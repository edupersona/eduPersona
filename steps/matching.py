"""Declarative verification gate — match a step's output against expected values.

A step's `config['match']` is a list of rules, each comparing an *expected* value
(an invitation field, a persona_param, or a fixed literal) against an *actual* value
(a key in the step's output). The orchestrator evaluates them when a step reports
`completed`; any failure blocks the step (see `Steps.record`).

This module is pure and side-effect-free so it is trivially unit-testable; the sources
it reads all live in the orchestrator's session `state` (no DB access).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

# Invitation-derived sources exposed on the session state by apply_invite_to_state.
_STATE_SOURCES = ('given_name', 'family_name', 'guest_email')


@dataclass(frozen=True)
class MatchFailure:
    label: str
    source: str
    field: str
    expected: str
    found: str


def _norm(s: Any) -> str:
    """Normalise for comparison: strip diacritics (NFKD), casefold, collapse whitespace."""
    text = unicodedata.normalize('NFKD', str(s))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(text.casefold().split())


def resolve_source(state: dict, source: str) -> str | None:
    """Resolve a rule's `source` to its expected value, or None when absent.

    `const:<value>` → the literal; `param:<key>` → persona_params[key];
    otherwise a top-level invitation field (given_name / family_name / guest_email).
    """
    if source.startswith('const:'):
        return source[len('const:'):]
    if source.startswith('param:'):
        value = (state.get('persona_params') or {}).get(source[len('param:'):])
    else:
        value = state.get(source)
    if value is None:
        return None
    value = str(value)
    return value or None


def parse_rules(cfg_match: Any) -> list[dict]:
    """Validate + normalise a step's `match` config into a list of rule dicts.

    Raises ValueError on a malformed rule so bad config fails at startup (the persona
    loader builds every Steps instance). An absent/empty `match` yields no rules.
    """
    if not cfg_match:
        return []
    if not isinstance(cfg_match, list):
        raise ValueError("'match' must be a list of rules")
    rules: list[dict] = []
    for rule in cfg_match:
        if not isinstance(rule, dict) or not rule.get('source') or not rule.get('field'):
            raise ValueError(f"match rule needs 'source' and 'field': {rule!r}")
        source = str(rule['source'])
        if not (source.startswith(('const:', 'param:')) or source in _STATE_SOURCES):
            raise ValueError(f"unknown match source {source!r}")
        rules.append({
            'source': source,
            'field': str(rule['field']),
            'label': str(rule.get('label') or rule['field']),
            'exact': bool(rule.get('exact', False)),
        })
    return rules


def evaluate_matches(rules: list[dict], state: dict, output: dict) -> list[MatchFailure]:
    """Return the rules that fail. A rule fails when its expected value is present but the
    output value is missing/empty or does not match. A missing expected value skips the rule."""
    failures: list[MatchFailure] = []
    for rule in rules:
        expected = resolve_source(state, rule['source'])
        if expected is None:  # nothing to enforce against
            continue
        found_raw = output.get(rule['field'])
        found = '' if found_raw is None else str(found_raw)
        if rule['exact']:
            ok = found == expected
        else:
            ok = bool(found) and _norm(found) == _norm(expected)
        if not ok:
            failures.append(MatchFailure(
                label=rule['label'], source=rule['source'], field=rule['field'],
                expected=expected, found=found))
    return failures
