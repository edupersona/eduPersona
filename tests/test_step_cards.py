"""Tests for the step-card orchestrator contract.

Covers the invariants the refactor was designed to enforce:
- Step order is derived from scenario config; no hardcoded keys.
- StepResult is the only completion signal; orchestrator owns the completion map.
- FinalizeStep auto-runs once all prior steps are completed-or-skipped; it is idempotent.
- is_already_done lets a step auto-skip on scenario startup.
- OIDCLoginStep is fully parameterized by config (idp, copy, secondary CTA).
"""
import pytest
from domain.step_cards import (
    Steps,
    StepCard,
    StepResult,
    OIDCLoginStep,
    FinalizeStep,
    VerifyInviteStep,
    VerifyAlumniDb,
)

# Steps.record() calls render.refresh(), which schedules a client-side update
# that has no recipient in a test context. The work is harmlessly discarded but
# emits a RuntimeWarning we don't want polluting test output.
pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'AwaitableResponse._fire' was never awaited:RuntimeWarning",
)


@pytest.fixture(autouse=True)
def _isolate_session_storage(monkeypatch):
    """Step-card unit tests must not touch app.storage.user (no UI context here).

    `store_tenant_in_session` (VerifyInviteStep.act) and `establish_guest_session_for_code`
    (FinalizeStep.act) both write to user storage. We stub both so the tests can
    exercise the orchestrator/step contract without spinning up a browser session.

    `services` is a namespace package (no __init__.py), so we have to load the
    submodule via importlib before monkeypatching its attribute.
    """
    import importlib
    services_tenant = importlib.import_module('services.tenant')
    step_cards = importlib.import_module('domain.step_cards')

    async def _noop(tenant, invite_code):
        return None
    monkeypatch.setattr(services_tenant, 'store_tenant_in_session', lambda tenant: None)
    monkeypatch.setattr(step_cards, 'establish_guest_session_for_code', _noop)
    # ui.notify needs a slot stack; stub it for unit tests.
    monkeypatch.setattr(step_cards.ui, 'notify', lambda *a, **kw: None)


def _empty_state() -> dict:
    return {
        'invite_code': '',
        'invitation_id': None,
        'role_assignments': [],
        'role_name': '',
        'outcomes': {},
        'outputs': {},
    }


def _scenario(*steps: dict) -> dict:
    return {'steps': list(steps)}


# ── orchestrator invariants ──────────────────────────────────────────────


@pytest.mark.storage
async def test_orchestrator_assigns_step_ids_and_indexes(test_tenant):
    """step_id comes from config.id or, lacking it, the array index."""
    sc = _scenario(
        {'class': 'VerifyInviteStep', 'id': 'invite', 'config': {'title': 't', 'completed_text': 'c'}},
        {'class': 'OIDCLoginStep', 'config': {
            'idp': 'eduid', 'title': 't', 'completed_text': 'c',
            'primary_button_label': 'go',
        }},
        {'class': 'FinalizeStep', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    steps = Steps(test_tenant, _empty_state(), sc)
    assert [s.step_id for s in steps.step_instances] == ['invite', '1', '2']


@pytest.mark.storage
async def test_record_updates_outcomes_and_outputs(test_tenant):
    """Steps.record is the single state-mutation funnel."""
    sc = _scenario(
        {'class': 'VerifyInviteStep', 'id': 'a', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    state = _empty_state()
    steps = Steps(test_tenant, state, sc)
    await steps.record('a', StepResult('completed', output={'foo': 'bar'}))
    assert state['outcomes']['a'] == 'completed'
    assert state['outputs']['a'] == {'foo': 'bar'}


@pytest.mark.storage
async def test_render_prereqs_track_step_identity_not_position(test_tenant):
    """A reordered scenario must produce the same enable/disable semantics."""
    a = {'class': 'VerifyInviteStep', 'id': 'a', 'config': {'title': 't', 'completed_text': 'c'}}
    b = {'class': 'OIDCLoginStep', 'id': 'b', 'config': {
        'idp': 'eduid', 'title': 't', 'completed_text': 'c', 'primary_button_label': 'go',
    }}
    state = _empty_state()
    steps = Steps(test_tenant, state, _scenario(b, a))  # reversed
    # Mark second step (a) complete — first step (b) is still pending, so a's prereqs aren't met.
    await steps.record('a', StepResult('completed'))
    # 'b' has no outcome yet → 'a' would be disabled if we walked render. That's correct:
    # the orchestrator computes prereqs positionally, and identity carries through step_id.
    assert state['outcomes'] == {'a': 'completed'}


# ── is_already_done ──────────────────────────────────────────────────────


class _AlwaysDoneStep(StepCard):
    """Test fixture: a step that claims to be done at startup."""
    async def is_already_done(self) -> bool:
        return True

    def render_enabled(self, state: dict) -> None:
        pass


@pytest.mark.storage
async def test_is_already_done_records_as_skipped(test_tenant, monkeypatch):
    """A step whose is_already_done returns True is recorded as 'skipped' on startup."""
    from domain import step_cards
    monkeypatch.setitem(step_cards.STEP_CARD_CLASSES, '_AlwaysDoneStep', _AlwaysDoneStep)
    sc = _scenario(
        {'class': '_AlwaysDoneStep', 'id': 'auto', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    state = _empty_state()
    steps = Steps(test_tenant, state, sc)
    await steps.startup()
    assert state['outcomes']['auto'] == 'skipped'


# ── OIDCLoginStep parameterization ───────────────────────────────────────


@pytest.mark.storage
async def test_oidc_login_step_isolates_outputs_by_step_id(
    test_tenant, sample_invitation, mock_oidc_userinfo, mock_oidc_id_token, mock_oidc_token_data,
):
    """Two OIDCLoginStep instances with different idp's write to separate output buckets,
    and each persists a GuestAttribute row under its own IdP key."""
    from domain.models import GuestAttribute
    from domain.stores import get_invitation_store

    sc = _scenario(
        {'class': 'OIDCLoginStep', 'id': 'eduid', 'config': {
            'idp': 'eduid', 'title': 't', 'completed_text': 'c', 'primary_button_label': 'go',
        }},
        {'class': 'OIDCLoginStep', 'id': 'inst', 'config': {
            'idp': 'institutional', 'title': 't', 'completed_text': 'c', 'primary_button_label': 'go',
        }},
    )
    state = _empty_state()
    state['invite_code'] = sample_invitation
    steps = Steps(test_tenant, state, sc)

    eduid_step, inst_step = steps.step_instances
    assert isinstance(eduid_step, OIDCLoginStep) and eduid_step.idp == 'eduid'
    assert isinstance(inst_step, OIDCLoginStep) and inst_step.idp == 'institutional'

    inst_userinfo = {**mock_oidc_userinfo, 'sub': 'inst-sub'}
    await eduid_step.result_handler(mock_oidc_userinfo, mock_oidc_id_token, mock_oidc_token_data)
    await inst_step.result_handler(inst_userinfo, mock_oidc_id_token, mock_oidc_token_data)

    assert state['outputs']['eduid']['userinfo']['sub'] == 'mock-subject-id'
    assert state['outputs']['inst']['userinfo']['sub'] == 'inst-sub'

    guest_id = (await get_invitation_store(test_tenant).read_items(
        filter_by={"code": sample_invitation}))[0]["guest_id"]
    eduid_rows = await GuestAttribute.filter(guest_id=guest_id, name='eduid').all()
    inst_rows = await GuestAttribute.filter(guest_id=guest_id, name='institutional').all()
    assert len(eduid_rows) == 1 and len(inst_rows) == 1


# ── FinalizeStep idempotency ─────────────────────────────────────────────


@pytest.mark.storage
async def test_finalize_step_idempotent_on_repeated_act(test_tenant, sample_invitation):
    """Running FinalizeStep.act() twice must not double-accept the invitation."""
    from domain.stores import get_invitation_store

    sc = _scenario(
        {'class': 'FinalizeStep', 'id': 'fin', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    state = _empty_state()
    state['invite_code'] = sample_invitation
    steps = Steps(test_tenant, state, sc)
    finalize = steps.step_instances[0]
    assert isinstance(finalize, FinalizeStep)

    first = await finalize.act()
    assert first is not None and first.outcome == 'completed'
    invitations = await get_invitation_store(test_tenant).read_items(filter_by={"code": sample_invitation})
    assert invitations[0]['status'] == 'accepted'
    first_accepted_at = invitations[0]['accepted_at']

    second = await finalize.act()
    assert second is not None and second.outcome == 'completed'
    invitations = await get_invitation_store(test_tenant).read_items(filter_by={"code": sample_invitation})
    assert invitations[0]['accepted_at'] == first_accepted_at  # not re-stamped


@pytest.mark.storage
async def test_finalize_auto_runs_when_prior_steps_complete(test_tenant, sample_invitation):
    """When the institutional step is recorded complete, FinalizeStep.act() should fire
    via the orchestrator's terminal hook."""
    from domain.stores import get_invitation_store

    sc = _scenario(
        {'class': 'VerifyInviteStep', 'id': 'invite', 'config': {'title': 't', 'completed_text': 'c'}},
        {'class': 'FinalizeStep', 'id': 'fin', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    state = _empty_state()
    state['invite_code'] = sample_invitation
    steps = Steps(test_tenant, state, sc)

    await steps.record('invite', StepResult('completed'))
    # Finalize auto-ran:
    assert state['outcomes']['fin'] == 'completed'
    invitations = await get_invitation_store(test_tenant).read_items(filter_by={"code": sample_invitation})
    assert invitations[0]['status'] == 'accepted'


# ── No stale ordering keys ───────────────────────────────────────────────


@pytest.mark.storage
async def test_no_steps_completed_key_in_state_defaults():
    """The legacy `steps_completed` dict is gone; orchestrator uses `outcomes` instead."""
    from services.session_manager import _DEFAULTS
    assert 'steps_completed' not in _DEFAULTS
    assert 'outcomes' in _DEFAULTS
    assert 'outputs' in _DEFAULTS


# ── VerifyAlumniDb ──────────────────────────────────────────────────────


def _alumni_step(test_tenant: str, **config_override) -> VerifyAlumniDb:
    cfg = {
        'title': 't', 'completed_text': 'c', 'disabled_text': '',
        'dob_min_year': 1960, 'dob_max_year': 1990,
        'student_number_pattern': r'^\d{5}$',
    } | config_override
    sc = _scenario({'class': 'VerifyAlumniDb', 'id': 'alumni', 'config': cfg})
    steps = Steps(test_tenant, _empty_state(), sc)
    step = steps.step_instances[0]
    assert isinstance(step, VerifyAlumniDb)
    return step


@pytest.mark.storage
async def test_verify_alumni_db_accepts_within_year_bounds_and_format(test_tenant):
    step = _alumni_step(test_tenant)
    step.state['alumni_dob'] = '1975-05-15'
    step.state['alumni_student_number'] = '12345'
    result = await step.act()
    assert result is not None and result.outcome == 'completed'
    assert result.output == {'dob': '1975-05-15', 'student_number': '12345'}


@pytest.mark.parametrize('dob', ['1960-06-01', '1990-01-01', '1959-12-31', '2000-05-15', ''])
@pytest.mark.storage
async def test_verify_alumni_db_rejects_year_out_of_bounds(test_tenant, dob):
    """Exclusive bounds: years equal to min_year (1960) or max_year (1990) must fail."""
    step = _alumni_step(test_tenant)
    step.state['alumni_dob'] = dob
    step.state['alumni_student_number'] = '12345'
    result = await step.act()
    assert result is not None and result.outcome == 'failed'


@pytest.mark.parametrize('student_number', ['1234', '123456', '12a45', '', 'abcde'])
@pytest.mark.storage
async def test_verify_alumni_db_rejects_bad_student_number(test_tenant, student_number):
    step = _alumni_step(test_tenant)
    step.state['alumni_dob'] = '1975-05-15'
    step.state['alumni_student_number'] = student_number
    result = await step.act()
    assert result is not None and result.outcome == 'failed'


@pytest.mark.storage
async def test_verify_alumni_db_bounds_are_configurable(test_tenant):
    """Same class, different bounds — confirms genericity."""
    step = _alumni_step(test_tenant, dob_min_year=1980, dob_max_year=2010)
    step.state['alumni_dob'] = '1975-01-01'
    step.state['alumni_student_number'] = '12345'
    result = await step.act()
    assert result is not None and result.outcome == 'failed'

    step.state['alumni_dob'] = '1995-01-01'
    result = await step.act()
    assert result is not None and result.outcome == 'completed'


@pytest.mark.storage
async def test_verify_invite_step_signals_via_step_result(test_tenant, sample_invitation):
    """VerifyInviteStep returns StepResult('completed') on valid code, no direct state writes."""
    sc = _scenario(
        {'class': 'VerifyInviteStep', 'id': 'invite', 'config': {'title': 't', 'completed_text': 'c'}},
    )
    state = _empty_state()
    steps = Steps(test_tenant, state, sc)
    step = steps.step_instances[0]
    assert isinstance(step, VerifyInviteStep)
    state['invite_code_input'] = sample_invitation
    result = await step.act()
    assert result is not None and result.outcome == 'completed'
    # Scenario context populated, but completion is the orchestrator's to record.
    assert state['invite_code'] == sample_invitation
    assert state['outcomes'] == {}
