import numpy as np
import PyOpenColorIO as OCIO
import pytest

from aces20_tonemapper.errors import ConfigError
from aces20_tonemapper.pipeline import Tonemapper, TonemapSettings


def gray(value):
    return np.full((2, 2, 3), value, dtype=np.float32)


def test_matches_reference_aces2_view_transform(config, ramp_rgb):
    """With neutral settings the result is exactly OCIO's ACES 2.0 display/view transform."""
    expected = ramp_rgb.copy()
    dvt = OCIO.DisplayViewTransform(
        src="ACEScg", display="sRGB - Display", view="ACES 2.0 - SDR 100 nits (Rec.709)"
    )
    cpu = config.getProcessor(dvt).getDefaultCPUProcessor()
    cpu.apply(OCIO.PackedImageDesc(expected, 16, 8, 3))

    result = Tonemapper(config, TonemapSettings()).apply(ramp_rgb)
    np.testing.assert_allclose(result, np.clip(expected, 0, 1), atol=1e-6)


def test_highlights_roll_off_instead_of_hard_clipping(config):
    """Regression: the original script clipped everything above 1.0 (no tone mapping)."""
    tm = Tonemapper(config, TonemapSettings())
    four, sixteen = tm.apply(gray(4.0))[0, 0, 0], tm.apply(gray(16.0))[0, 0, 0]
    assert four < sixteen < 1.0


def test_positive_ev_doubles_scene_light(config, ramp_rgb):
    plus_one = Tonemapper(config, TonemapSettings(exposure_ev=1.0)).apply(ramp_rgb)
    doubled = Tonemapper(config, TonemapSettings()).apply(ramp_rgb * 2)
    np.testing.assert_allclose(plus_one, doubled, atol=1e-5)


def test_negative_ev_is_darker(config):
    base = Tonemapper(config, TonemapSettings()).apply(gray(0.18))
    darker = Tonemapper(config, TonemapSettings(exposure_ev=-1.0)).apply(gray(0.18))
    assert darker.mean() < base.mean()


def test_zero_saturation_is_neutral_gray(config):
    colorful = np.full((2, 2, 3), (0.5, 0.1, 0.05), dtype=np.float32)
    out = Tonemapper(config, TonemapSettings(saturation=0.0)).apply(colorful)
    np.testing.assert_allclose(out[..., 0], out[..., 1], atol=2e-3)
    np.testing.assert_allclose(out[..., 1], out[..., 2], atol=2e-3)


def test_input_space_changes_the_result(config):
    red = np.full((2, 2, 3), (0.8, 0.05, 0.05), dtype=np.float32)
    as_acescg = Tonemapper(config, TonemapSettings()).apply(red)
    as_rec709 = Tonemapper(config, TonemapSettings(input_space="Linear Rec.709 (sRGB)")).apply(red)
    assert not np.allclose(as_acescg, as_rec709, atol=1e-3)


def test_nan_and_inf_pixels_give_finite_output(config):
    img = gray(0.5)
    img[0, 0] = (np.nan, np.inf, -np.inf)
    out = Tonemapper(config, TonemapSettings()).apply(img)
    assert np.isfinite(out).all() and out.min() >= 0.0 and out.max() <= 1.0


def test_apply_does_not_modify_its_input(config, ramp_rgb):
    before = ramp_rgb.copy()
    Tonemapper(config, TonemapSettings(exposure_ev=2.0, saturation=0.5)).apply(ramp_rgb)
    np.testing.assert_array_equal(ramp_rgb, before)


def test_output_is_float32_in_unit_range(config, ramp_rgb):
    out = Tonemapper(config, TonemapSettings()).apply(ramp_rgb)
    assert out.dtype == np.float32 and out.shape == ramp_rgb.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_rejects_wrong_shape(config):
    with pytest.raises(ValueError):
        Tonemapper(config, TonemapSettings()).apply(np.zeros((4, 4), dtype=np.float32))


@pytest.mark.parametrize(
    "settings",
    [
        TonemapSettings(input_space="Nope"),
        TonemapSettings(display="Nope"),
        TonemapSettings(view="Nope"),
    ],
)
def test_invalid_names_raise_config_error(config, settings):
    with pytest.raises(ConfigError):
        Tonemapper(config, settings)


def test_metadata_describes_the_settings(config):
    tm = Tonemapper(config, TonemapSettings(exposure_ev=-1.5, saturation=0.8))
    meta = tm.metadata()
    assert meta["HDR_Exposure_EV"] == "-1.5"
    assert meta["HDR_Saturation_Factor"] == "0.8"
    assert meta["OCIO_View"] == "ACES 2.0 - SDR 100 nits (Rec.709)"
