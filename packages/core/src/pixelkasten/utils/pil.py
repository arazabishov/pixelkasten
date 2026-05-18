"""
PIL plugin registration.

`pillow-heif` adds HEIC/HEIF support to Pillow via a registered opener.
Call `ensure_pil_plugins()` once before opening images of unknown format;
it's idempotent and silent when pillow-heif isn't installed (HEIC reads
will then fail with PIL's normal "cannot identify image file" error).
"""

_REGISTERED = False


def ensure_pil_plugins() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    _REGISTERED = True
