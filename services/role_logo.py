"""Save uploaded role logos to static/{tenant}/logos/ and persist the filename."""
import re
from pathlib import Path, PurePosixPath

from nicegui.elements.upload_files import FileUpload

from domain.stores import get_role_store


STATIC_ROOT = Path('static')
ALLOWED_LOGO_EXTS = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}
MAX_LOGO_BYTES = 1_000_000


async def save_role_logo(tenant: str, role: dict, file: FileUpload) -> str:
    """Save an uploaded logo and persist Role.logo_file_name.

    Returns the saved filename. Raises ValueError on type/size rejection.
    """
    basename = PurePosixPath(file.name or '').name.lower()
    ext = Path(basename).suffix
    if ext not in ALLOWED_LOGO_EXTS:
        raise ValueError(f"Unsupported file type: {ext or '(none)'}")
    if file.size() > MAX_LOGO_BYTES:
        raise ValueError("File exceeds 1 MB limit")
    safe = re.sub(r'[^a-z0-9._-]+', '-', basename).strip('-') or f'logo{ext}'
    new_name = f"role{role['id']}_{safe}"
    logos_dir = STATIC_ROOT / tenant / 'logos'
    target = logos_dir / new_name

    old = role.get('logo_file_name')
    if old and old.startswith(f"role{role['id']}_"):
        old_path = logos_dir / old
        if old_path != target and old_path.exists():
            old_path.unlink()

    await file.save(target)
    await get_role_store(tenant).update_item(role['id'], {"logo_file_name": new_name})
    return new_name
