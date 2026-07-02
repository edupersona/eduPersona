"""Render a URL as a QR code data-URI for inline display (ui.html)."""
import segno


def qr_data_uri(url: str, scale: int = 6) -> str:
    """Return an SVG `data:` URI encoding `url` — drop straight into `ui.html`."""
    return segno.make(url).svg_data_uri(scale=scale)
