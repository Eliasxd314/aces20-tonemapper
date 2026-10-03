"""The color pipeline: input space -> ACEScg -> exposure -> saturation -> ACES 2.0 view."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import PyOpenColorIO as OCIO

from . import __version__
from .config import resolve_display_view, validate_color_space
from .errors import ConfigError

# Exposure and saturation are applied in this scene-linear working space.
WORKING_SPACE = "ACEScg"
_HALF_FLOAT_MAX = 65504.0


@dataclass(frozen=True)
class TonemapSettings:
    """User-facing parameters of the pipeline.

    exposure_ev: exposure offset in stops (EV); 0 = unchanged, +1 doubles light.
    saturation: ASC-CDL saturation; 1 = unchanged, 0 = monochrome.
    input_space: OCIO color space of the source pixels (default: ACEScg).
    display / view: OCIO display and view; ``None`` uses the config defaults.
    """

    exposure_ev: float = 0.0
    saturation: float = 1.0
    input_space: str = WORKING_SPACE
    display: str | None = None
    view: str | None = None


class Tonemapper:
    """Builds the OCIO processor once and applies it to any number of images."""

    def __init__(self, config: OCIO.Config, settings: TonemapSettings) -> None:
        self.settings = settings
        validate_color_space(config, settings.input_space)
        validate_color_space(config, WORKING_SPACE)
        self.display, self.view = resolve_display_view(config, settings.display, settings.view)

        try:
            self._cpu = config.getProcessor(self._build_transform()).getDefaultCPUProcessor()
        except OCIO.Exception as exc:
            raise ConfigError(f"Could not build the color pipeline: {exc}") from exc

    def _build_transform(self) -> OCIO.GroupTransform:
        s = self.settings
        group = OCIO.GroupTransform()

        if s.input_space != WORKING_SPACE:
            group.appendTransform(
                OCIO.ColorSpaceTransform(src=s.input_space, dst=WORKING_SPACE)
            )

        if s.exposure_ev != 0.0:
            exposure = OCIO.ExposureContrastTransform()
            exposure.setStyle(OCIO.EXPOSURE_CONTRAST_LINEAR)
            exposure.setExposure(s.exposure_ev)
            group.appendTransform(exposure)

        if s.saturation != 1.0:
            cdl = OCIO.CDLTransform()
            cdl.setStyle(OCIO.CDL_NO_CLAMP)
            cdl.setSat(s.saturation)
            group.appendTransform(cdl)

        group.appendTransform(
            OCIO.DisplayViewTransform(src=WORKING_SPACE, display=self.display, view=self.view)
        )
        return group

    def apply(self, rgb: np.ndarray) -> np.ndarray:
        """Return display-referred RGB float32 in [0, 1]. The input is not modified."""
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError(f"Expected an (H, W, 3) array, got shape {rgb.shape}")

        # NaN/inf pixels (common in renders) would otherwise poison the transform.
        out = np.nan_to_num(rgb, nan=0.0, posinf=_HALF_FLOAT_MAX, neginf=0.0)
        out = np.ascontiguousarray(out, dtype=np.float32)

        height, width = out.shape[:2]
        self._cpu.apply(OCIO.PackedImageDesc(out, width, height, 3))
        return np.clip(out, 0.0, 1.0, out=out)

    def metadata(self) -> dict[str, str]:
        """Provenance written into the PNG ``tEXt`` chunks (readable with exiftool)."""
        s = self.settings
        return {
            "Software": f"aces20-tonemapper {__version__}",
            "HDR_Exposure_EV": f"{s.exposure_ev:g}",
            "HDR_Saturation_Factor": f"{s.saturation:g}",
            "Input_Color_Space": s.input_space,
            "OCIO_Display": self.display,
            "OCIO_View": self.view,
            "Color_Space_Pipeline": (
                f"{s.input_space} -> {WORKING_SPACE} -> exposure -> ASC-CDL saturation "
                f"-> {self.display} / {self.view}"
            ),
        }
