"""Verification gate — the pure matching helpers and the orchestrator enforcement.

`steps/matching.py` is pure (no I/O), so the unit tests need no fixtures. The integration
tests drive `Steps.record` with a real `id_verificatie` persona (which carries `match`
rules on its single step) and an invitation that does/doesn't carry given/family names.
"""
import pytest

from domain.invitations import apply_invite_to_state, create_invitation
from services.persona_loader import get_persona_config
from steps import Steps
from steps.base import StepResult
from steps.matching import _norm, evaluate_matches, parse_rules, resolve_source


# ── pure helpers ───────────────────────────────────────────────────────────

def test_norm_folds_case_accents_and_whitespace():
    assert _norm('  KléYNJan ') == _norm('kleynjan')
    assert _norm('van  der\tBerg') == 'van der berg'
    assert _norm('José') == _norm('JOSE')


def test_resolve_source_variants():
    state = {'given_name': 'Peter', 'family_name': '', 'persona_params': {'faculty': 'FNWI'}}
    assert resolve_source(state, 'given_name') == 'Peter'
    assert resolve_source(state, 'family_name') is None      # empty → absent → rule skipped
    assert resolve_source(state, 'guest_email') is None      # missing key
    assert resolve_source(state, 'param:faculty') == 'FNWI'
    assert resolve_source(state, 'param:missing') is None
    assert resolve_source(state, 'const:https://x/mfa') == 'https://x/mfa'


def test_parse_rules_defaults_and_validation():
    rules = parse_rules([{'source': 'family_name', 'field': 'last_name'}])
    assert rules == [{'source': 'family_name', 'field': 'last_name',
                      'label': 'last_name', 'exact': False}]
    assert parse_rules(None) == [] and parse_rules([]) == []
    with pytest.raises(ValueError):
        parse_rules([{'source': 'bogus', 'field': 'x'}])
    with pytest.raises(ValueError):
        parse_rules([{'field': 'x'}])            # missing source


def test_evaluate_matches_pass_skip_and_fail():
    rules = parse_rules([
        {'source': 'family_name', 'field': 'last_name', 'label': 'Achternaam'},
        {'source': 'given_name', 'field': 'first_name'},
    ])
    state = {'family_name': 'Kleynjan', 'given_name': 'Peter'}
    # normalized-exact: exact letters differ → block, even though case/accents wouldn't
    fails = evaluate_matches(rules, state, {'last_name': 'Kleijnjan', 'first_name': 'PETER'})
    assert [f.field for f in fails] == ['last_name']
    assert fails[0].expected == 'Kleynjan' and fails[0].found == 'Kleijnjan'
    # a matching (case-insensitive) pair passes
    assert evaluate_matches(rules, state, {'last_name': ' kleynjan ', 'first_name': 'peter'}) == []


def test_evaluate_skips_when_source_absent_but_fails_when_output_missing():
    rules = parse_rules([{'source': 'family_name', 'field': 'last_name'}])
    assert evaluate_matches(rules, {'family_name': None}, {'last_name': 'X'}) == []      # source absent → skip
    fails = evaluate_matches(rules, {'family_name': 'Doe'}, {})                          # output missing → fail
    assert len(fails) == 1 and fails[0].found == ''


def test_exact_flag_bypasses_normalization():
    rules = parse_rules([{'source': 'const:https://refeds.org/profile/mfa',
                          'field': 'acr', 'exact': True}])
    assert evaluate_matches(rules, {}, {'acr': 'https://refeds.org/profile/mfa'}) == []
    # normalization would casefold these equal; exact must still reject a case difference
    assert evaluate_matches(rules, {}, {'acr': 'HTTPS://REFEDS.ORG/PROFILE/MFA'})


# ── orchestrator enforcement ───────────────────────────────────────────────

async def _id_steps(test_tenant, *, given=None, family=None) -> Steps:
    created = await create_invitation(test_tenant, 'id_verificatie', 'id@example.org', 'EMP-9',
                                      given_name=given, family_name=family)
    state: dict = {}
    await apply_invite_to_state(test_tenant, state, created['code'])
    cfg = get_persona_config(test_tenant, 'id_verificatie')
    return Steps(test_tenant, state, {'steps': cfg.steps})


_MATCH_OUTPUT = {'first_name': 'Peter', 'last_name': 'Kleynjan', 'document_number': 'X1'}


async def test_record_completes_when_output_matches_invitation(test_tenant):
    steps = await _id_steps(test_tenant, given='Peter', family='Kleynjan')
    await steps.record('id_document', StepResult('completed', output=_MATCH_OUTPUT))
    assert steps.outcomes['id_document'] == 'completed'
    assert steps.outputs['id_document']['document_number'] == 'X1'
    assert steps.all_steps_done


async def test_record_blocks_and_drops_output_on_mismatch(test_tenant):
    steps = await _id_steps(test_tenant, given='Peter', family='Kleynjan')
    await steps.record('id_document', StepResult('completed', output={**_MATCH_OUTPUT, 'last_name': 'Kleijnjan'}))
    assert steps.outcomes['id_document'] == 'failed'
    assert 'id_document' not in steps.outputs               # rejected output never surfaces
    assert not steps.all_steps_done
    slot = steps.state['step_state']['id_document']
    assert [f['field'] for f in slot['match_failures']] == ['last_name']


async def test_record_skips_gate_when_invitation_has_no_names(test_tenant):
    steps = await _id_steps(test_tenant)                     # no given/family → rules skip
    await steps.record('id_document', StepResult('completed', output={'last_name': 'Whoever'}))
    assert steps.outcomes['id_document'] == 'completed'


async def test_card_state_stays_attached_so_record_writes_are_visible(test_tenant):
    """Regression for the accept.py ordering bug: apply_invite_to_state resets step_state, and
    Steps captures each card's state slot at construction — so the invite must be applied BEFORE
    Steps is built. `_id_steps` uses that order; assert the card's own `self.state` is the very
    slot the orchestrator writes to, so match_failures set in record() surface to the card."""
    steps = await _id_steps(test_tenant, given='Peter', family='Kleynjan')
    card = steps.step_instances[0]
    assert card.state is steps.state['step_state']['id_document']  # attached, not orphaned
    await card.complete({**_MATCH_OUTPUT, 'last_name': 'Kleijnjan'})  # via the card, like the live poll
    assert card.state.get('match_failures')                          # visible on the card → block renders


async def test_building_steps_before_applying_invite_orphans_state(test_tenant):
    """Encodes WHY accept.py applies the invite first: the reverse order detaches the card slot."""
    created = await create_invitation(test_tenant, 'id_verificatie', 'id@example.org', 'EMP-9',
                                      given_name='Peter', family_name='Kleynjan')
    state: dict = {}
    cfg = get_persona_config(test_tenant, 'id_verificatie')
    steps = Steps(test_tenant, state, {'steps': cfg.steps})          # built first (the bug)
    await apply_invite_to_state(test_tenant, state, created['code'])  # resets step_state → orphans
    # the card holds a slot that is no longer reachable from the session state at all
    assert 'id_document' not in state['step_state']
    assert isinstance(steps.step_instances[0].state, dict)


async def test_restart_clears_progress(test_tenant):
    steps = await _id_steps(test_tenant, given='Peter', family='Kleynjan')
    await steps.record('id_document', StepResult('completed', output={**_MATCH_OUTPUT, 'last_name': 'X'}))
    assert steps.state['step_state']['id_document'].get('match_failures')
    await steps.restart()
    assert steps.outcomes == {}
    # step_state is rebuilt with fresh card defaults (phase='start'), no lingering failure
    assert 'match_failures' not in steps.state['step_state'].get('id_document', {})
    assert steps.state['step_state']['id_document'].get('phase') == 'start'
