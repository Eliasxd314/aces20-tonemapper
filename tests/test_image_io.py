import numpy as np
import pytest
from PIL import Image

from aces20_tonemapper.errors import ImageReadError
from aces20_tonemapper.image_io import is_supported, read_image, write_png


def test_exr_rgb_float32_roundtrip(tmp_path, ramp_rgb, write_exr):
    path = write_exr(tmp_path / "a.exr", {"RGB": ramp_rgb})
    image = read_image(path)
    np.testing.assert_array_equal(image.rgb, ramp_rgb)
    assert image.rgb.dtype == np.float32 and not image.integer_source


def test_exr_half_is_converted_to_float32(tmp_path, ramp_rgb, write_exr):
    path = write_exr(tmp_path / "half.exr", {"RGB": ramp_rgb.astype(np.float16)})
    image = read_image(path)
    assert image.rgb.dtype == np.float32
    np.testing.assert_allclose(image.rgb, ramp_rgb, rtol=1e-3)


def test_exr_alpha_is_dropped(tmp_path, ramp_rgb, write_exr):
    rgba = np.concatenate([ramp_rgb, np.ones(ramp_rgb.shape[:2] + (1,), np.float32)], axis=2)
    image = read_image(write_exr(tmp_path / "rgba.exr", {"RGBA": rgba}))
    assert image.rgb.shape == ramp_rgb.shape
    np.testing.assert_array_equal(image.rgb, ramp_rgb)


def test_exr_single_channel_is_expanded_to_rgb(tmp_path, ramp_rgb, write_exr):
    luma = ramp_rgb[..., 0].copy()
    image = read_image(write_exr(tmp_path / "y.exr", {"Y": luma}))
    assert image.rgb.shape == luma.shape + (3,)
    for channel in range(3):
        np.testing.assert_array_equal(image.rgb[..., channel], luma)


def test_exr_without_color_channels_raises(tmp_path, ramp_rgb, write_exr):
    path = write_exr(tmp_path / "depth.exr", {"Z": ramp_rgb[..., 0].copy()})
    with pytest.raises(ImageReadError, match="no RGB or Y channels"):
        read_image(path)


def test_float_tiff_keeps_channel_order(tmp_path, ramp_rgb, write_tiff):
    image = read_image(write_tiff(tmp_path / "a.tiff", ramp_rgb))
    np.testing.assert_array_equal(image.rgb, ramp_rgb)  # R, G, B not swapped
    assert not image.integer_source


def test_float_tiff_with_alpha(tmp_path, ramp_rgb, write_tiff):
    rgba = np.concatenate([ramp_rgb, np.ones(ramp_rgb.shape[:2] + (1,), np.float32)], axis=2)
    image = read_image(write_tiff(tmp_path / "a.tif", rgba))
    np.testing.assert_array_equal(image.rgb, ramp_rgb)


def test_grayscale_tiff_is_expanded_to_rgb(tmp_path, ramp_rgb, write_tiff):
    luma = ramp_rgb[..., 0].copy()
    image = read_image(write_tiff(tmp_path / "g.tif", luma))
    assert image.rgb.shape == luma.shape + (3,)


def test_integer_tiffs_are_normalized_and_flagged(tmp_path, write_tiff):
    u8 = np.full((4, 4, 3), 255, dtype=np.uint8)
    u16 = np.full((4, 4, 3), 65535, dtype=np.uint16)
    for name, array in (("u8.tif", u8), ("u16.tif", u16)):
        image = read_image(write_tiff(tmp_path / name, array))
        assert image.integer_source
        np.testing.assert_allclose(image.rgb, 1.0)


def test_corrupt_files_raise_image_read_error(tmp_path):
    for name in ("bad.exr", "bad.tif"):
        path = tmp_path / name
        path.write_bytes(b"definitely not an image")
        with pytest.raises(ImageReadError):
            read_image(path)


def test_unsupported_extension_raises(tmp_path):
    with pytest.raises(ImageReadError, match="Unsupported"):
        read_image(tmp_path / "photo.jpg")


def test_is_supported_is_case_insensitive(tmp_path):
    assert is_supported(tmp_path / "A.EXR") and is_supported(tmp_path / "b.TIF")
    assert not is_supported(tmp_path / "c.png")


def test_write_png_quantizes_and_embeds_metadata(tmp_path):
    rgb = np.zeros((2, 3, 3), dtype=np.float32)
    rgb[0, 0] = (1.5, 0.5, -0.2)  # out of range values are clipped
    path = tmp_path / "out.png"
    write_png(rgb, path, {"HDR_Exposure_EV": "1", "Software": "test"})

    with Image.open(path) as png:
        assert png.mode == "RGB" and png.size == (3, 2)
        assert png.text["HDR_Exposure_EV"] == "1" and png.text["Software"] == "test"
        assert png.getpixel((0, 0)) == (255, 128, 0)
