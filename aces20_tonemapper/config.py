"""OpenColorIO configuration lookup and validation."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import PyOpenColorIO as OCIO

from . import DEFAULT_BUILTIN_CONFIG
from .errors import ConfigError

log = logging.getLogger(__name__)


def find_local_config(directory: Path | None = None) -> Path | None:
    """Return the first ``.ocio`` file (sorted by name) in ``directory``, if any."""
    directory = directory or Path(".")
    candidates = sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".ocio"
    )
    return candidates[0] if candidates else None


def load_config(explicit_path: str | Path | None = None) -> OCIO.Config:
    """Load an OCIO config. Lookup order:

    1. ``explicit_path`` (``--config``)
    2. first ``.ocio`` file in the current directory
    3. the ``$OCIO`` environment variable
    4. the ACES 2.0 CG config built into OpenColorIO (>= 2.5)
    """
    try:
        if explicit_path:
            path = Path(explicit_path)
            if not path.is_file():
                raise ConfigError(f"OCIO config file not found: {path}")
            log.info("Using OCIO config: %s", path)
            return OCIO.Config.CreateFromFile(str(path.resolve()))

        local = find_local_config()
        if local:
            log.info("Using OCIO config found in current directory: %s", local)
            return OCIO.Config.CreateFromFile(str(local.resolve()))

        if os.environ.get("OCIO"):
            log.info("Using OCIO config from $OCIO: %s", os.environ["OCIO"])
            return OCIO.Config.CreateFromEnv()

        log.info("Using built-in OCIO config: %s", DEFAULT_BUILTIN_CONFIG)
        return OCIO.Config.CreateFromBuiltinConfig(DEFAULT_BUILTIN_CONFIG)
    except ConfigError:
        raise
    except OCIO.Exception as exc:
        raise ConfigError(
            f"Could not load the OpenColorIO config: {exc}\n"
            f"The built-in ACES 2.0 config needs OpenColorIO >= 2.5 "
            f"(installed: {OCIO.__version__}). Upgrade it or pass --config."
        ) from exc


def resolve_display_view(
    config: OCIO.Config, display: str | None, view: str | None
) -> tuple[str, str]:
    """Validate (or default) the display and view, returning the final pair."""
    displays = list(config.getDisplays())
    display = display or config.getDefaultDisplay()
    if display not in displays:
        raise ConfigError(f"Display '{display}' not found. Available: {', '.join(displays)}")

    views = list(config.getViews(display))
    view = view or config.getDefaultView(display)
    if view not in views:
        raise ConfigError(
            f"View '{view}' not found for display '{display}'. Available: {', '.join(views)}"
        )

    if "ACES 2.0" not in view:
        log.warning(
            "View '%s' does not look like an ACES 2.0 output transform; "
            "the result may not be ACES 2.0.",
            view,
        )
    return display, view


def validate_color_space(config: OCIO.Config, name: str) -> None:
    """Raise ConfigError if ``name`` is not a color space, role or alias in the config."""
    if config.getColorSpace(name) is None:
        names = [cs.getName() for cs in config.getColorSpaces()]
        raise ConfigError(
            f"Color space '{name}' not found in the config. Available: {', '.join(names)}"
        )
