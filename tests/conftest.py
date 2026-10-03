"""Shared fixtures: a built-in ACES 2.0 config and tiny synthetic HDR images."""

from __future__ import annotations

import cv2
import numpy as np
import OpenEXR
import PyOpenColorIO as OCIO
import pytest

from aces20_tonemapper import DEFAULT_BUILTIN_CONFIG

EXR_HEADER = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}


def pytest_collection_modifyitems(config, items):
    """Skip the whole suite on OpenColorIO builds without the ACES 2.0 built-in config."""
    if DEFAULT_BUILTIN_CONFIG in list(OCIO.BuiltinConfigRegistry()):
        return
    skip = pytest.mark.skip(reason=f"OpenColorIO build lacks {DEFAULT_BUILTIN_CONFIG}")
    for item in items:
        item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Run every test in an empty cwd with no $OCIO, so config lookup is deterministic."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OCIO", raising=False)


@pytest.fixture(scope="session")
def config():
    return OCIO.Config.CreateFromBuiltinConfig(DEFAULT_BUILTIN_CONFIG)


@pytest.fixture
def ramp_rgb():
    """A 8x16 scene-linear ramp from deep shadow to ~+5 stops over white (ACEScg values)."""
    ramp = np.tile(np.logspace(-3, 1.5, 16, dtype=np.float32), (8, 1))
    return np.stack([ramp, ramp * 0.6, ramp * 0.3], axis=2).astype(np.float32)


@pytest.fixture
def write_exr():
    def _write(path, channels):
        OpenEXR.File(EXR_HEADER, channels).write(str(path))
        return path
    return _write


@pytest.fixture
def write_tiff():
    """Write an RGB-ordered array as TIFF (OpenCV expects BGR(A) on disk order)."""
    def _write(path, array):
        if array.ndim == 3:
            array = np.concatenate([array[..., 2::-1], array[..., 3:]], axis=2) if array.shape[2] == 4 \
                else array[..., ::-1]
        assert cv2.imwrite(str(path), np.ascontiguousarray(array))
        return path
    return _write
