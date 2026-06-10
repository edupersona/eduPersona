"""Domain layer: models and invitation lifecycle.

Intentionally light on re-exports: importing submodules directly (e.g.
`from domain.invitations import create_invitation`) avoids an import cycle —
domain.invitations -> services.persona_loader -> domain.persona would re-enter
this package __init__ before persona_loader finished initializing.
"""
