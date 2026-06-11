"""Built-in step cards. Importing this package imports each card module, which
auto-registers the StepCard subclass by class name (see steps.base). To add a
card: drop a module here defining a StepCard subclass and add it below."""
from steps.cards.collect_intake import CollectIntakeStep
from steps.cards.oidc_login import OIDCLoginStep
from steps.cards.verify_alumni_db import VerifyAlumniDb
from steps.cards.verify_mobile import VerifyMobileStep
from steps.cards.verify_mfa import VerifyMfaStep

__all__ = ['CollectIntakeStep', 'OIDCLoginStep', 'VerifyAlumniDb', 'VerifyMobileStep', 'VerifyMfaStep']
