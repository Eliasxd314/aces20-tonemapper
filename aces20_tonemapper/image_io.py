"""Reading HDR images into RGB float32 matrices and writing PNG output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import OpenEXR
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .errors import ImageReadError

EXR_EXTENSIONS = frozenset({".exr"})
OPENCV_EXTENSIONS = frozenset({".tiff", ".tif", ".hdr"})
SUPPORTED_EXTENSIONS = EXR_EXTENSIONS | OPENCV_EXTENSIONS


@dataclass(frozen=True)
class LoadedImage:
    """An image decoded to RGB float32, shape (height, width, 3), C-contiguous."""

    rgb: np.ndarray
    # True when the source stored integer code values (8/16-bit), which are
    # normally display-encoded rather than scene-linear.
    integer_source: bool = False


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def read_image(path: str | Path) -> LoadedImage:
    """Decode ``path`` (.exr, .tif/.tiff, .hdr) into RGB float32."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in EXR_EXTENSIONS:
        return _read_exr(path)
    if ext in OPENCV_EXTENSIONS:
        return _read_with_opencv(path)
    raise ImageReadError(f"Unsupported file extension: {ext or '(none)'}")


def _to_rgb(array: np.ndarray, source: str) -> np.ndarray:
    """Normalize an (H, W) or (H, W, C) array to (H, W, 3) in RGB order, dropping alpha."""
    if array.ndim == 2:
        array = np.repeat(array[..., np.newaxis], 3, axis=2)
    elif array.ndim == 3 and array.shape[2] in (3, 4):
        array = array[..., :3]
    elif array.ndim == 3 and array.shape[2] == 2:  # gray + alpha
        array = np.repeat(array[..., :1], 3, axis=2)
    else:
        raise ImageReadError(f"{source}: unsupported array shape {array.shape}")
    return np.ascontiguousarray(array, dtype=np.float32)


def _read_exr(path: Path) -> LoadedImage:
    try:
        channels = OpenEXR.File(str(path.resolve())).channels()
    except Exception as exc:  # OpenEXR raises generic exceptions for bad files
        raise ImageReadError(f"Could not read EXR '{path.name}': {exc}") from exc

    # The high-level API groups R/G/B(/A) into one "RGB"/"RGBA" entry, also for
    # layered files (e.g. "ViewLayer.Combined.RGBA").
    for key in channels:
        if key.split(".")[-1] in ("RGB", "RGBA"):
            return LoadedImage(_to_rgb(channels[key].pixels, path.name))
    if "Y" in channels:
        return LoadedImage(_to_rgb(channels["Y"].pixels, path.name))

    available = ", ".join(channels) or "none"
    raise ImageReadError(
        f"EXR '{path.name}' has no RGB or Y channels (available: {available})."
    )


def _read_with_opencv(path: Path) -> LoadedImage:
    try:
        # imdecode + fromfile (instead of imread) also handles non-ASCII paths.
        raw = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except OSError as exc:
        raise ImageReadError(f"Could not open '{path.name}': {exc}") from exc
    if raw is None:
        raise ImageReadError(f"OpenCV could not decode '{path.name}'.")

    if raw.dtype == np.uint8:
        raw, integer = raw.astype(np.float32) / 255.0, True
    elif raw.dtype == np.uint16:
        raw, integer = raw.astype(np.float32) / 65535.0, True
    elif raw.dtype in (np.float32, np.float64):
        raw, integer = raw.astype(np.float32), False
    else:
        raise ImageReadError(f"'{path.name}': unsupported pixel type {raw.dtype}.")

    if raw.ndim == 3 and raw.shape[2] >= 3:
        raw = raw[..., 2::-1]  # OpenCV is BGR(A); take channels 2,1,0 -> RGB
    return LoadedImage(_to_rgb(raw, path.name), integer_source=integer)


def write_png(rgb: np.ndarray, path: str | Path, metadata: dict[str, str] | None = None) -> None:
    """Write display-referred RGB in [0, 1] as an 8-bit PNG with ``tEXt`` metadata."""
    code_values = np.rint(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    info = PngInfo()
    for key, value in (metadata or {}).items():
        info.add_text(key, str(value))
    Image.fromarray(code_values).save(path, pnginfo=info)
