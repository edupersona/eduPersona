"""Onboarding step cards + orchestrator — the public API and extension surface.

Importing this package registers all built-in cards (via steps.cards). Adopters
customize onboarding in two ways: order/compose steps in settings.json, and add
new cards under steps/cards/ — subclass StepCard, paint render_enabled(), finish
with self.complete()/self.fail(). See docs/step_cards.md for the full contract.
"""
from steps.base import (
    STEP_CARD_CLASSES,
    Outcome,
    StepCard,
    StepResult,
    expandable_info,
)
from steps.orchestrator import Steps, render_welcome
from steps.cards import (
    OIDCLoginStep,
    VerifyAlumniDb,
    VerifyMfaStep,
    VerifyMobileStep,
)

__all__ = [
    'STEP_CARD_CLASSES',
    'Outcome',
    'StepCard',
    'StepResult',
    'expandable_info',
    'Steps',
    'render_welcome',
    'OIDCLoginStep',
    'VerifyAlumniDb',
    'VerifyMfaStep',
    'VerifyMobileStep',
]
