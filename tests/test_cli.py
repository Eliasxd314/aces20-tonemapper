import numpy as np
import pytest
from PIL import Image

from aces20_tonemapper.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main


@pytest.fixture
def hdr_dir(tmp_path, ramp_rgb, write_exr):
    folder = tmp_path / "hdr"
    folder.mkdir()
    write_exr(folder / "one.exr", {"RGB": ramp_rgb})
    write_exr(folder / "two.exr", {"RGB": ramp_rgb * 0.5})
    return folder


def pngs(folder):
    return sorted(p.name for p in folder.glob("*.png"))


def test_converts_a_directory(hdr_dir):
    assert main([str(hdr_dir)]) == EXIT_OK
    assert pngs(hdr_dir) == ["one_aces20_ev0_sat1.png", "two_aces20_ev0_sat1.png"]


def test_converts_a_single_file_with_settings(hdr_dir):
    assert main([str(hdr_dir / "one.exr"), "-e", "1.5", "-s", "0.75"]) == EXIT_OK
    out = hdr_dir / "one_aces20_ev1.5_sat0.75.png"
    with Image.open(out) as png:
        assert png.text["HDR_Exposure_EV"] == "1.5"
        assert png.text["HDR_Saturation_Factor"] == "0.75"
        assert "ACES 2.0" in png.text["OCIO_View"]


def test_output_dir_is_created(hdr_dir, tmp_path):
    out_dir = tmp_path / "results" / "nested"
    assert main([str(hdr_dir), "-o", str(out_dir)]) == EXIT_OK
    assert len(pngs(out_dir)) == 2 and pngs(hdr_dir) == []


def test_existing_output_is_skipped_unless_overwrite(hdr_dir):
    target = hdr_dir / "one_aces20_ev0_sat1.png"
    target.write_bytes(b"precious")

    assert main([str(hdr_dir / "one.exr")]) == EXIT_OK
    assert target.read_bytes() == b"precious"

    assert main([str(hdr_dir / "one.exr"), "--overwrite"]) == EXIT_OK
    assert target.read_bytes() != b"precious"


def test_same_stem_different_format_does_not_collide(hdr_dir, ramp_rgb, write_tiff):
    write_tiff(hdr_dir / "one.tif", ramp_rgb)
    assert main([str(hdr_dir)]) == EXIT_OK
    assert pngs(hdr_dir) == [
        "one_exr_aces20_ev0_sat1.png",
        "one_tif_aces20_ev0_sat1.png",
        "two_aces20_ev0_sat1.png",
    ]


def test_one_bad_file_does_not_stop_the_batch(hdr_dir):
    (hdr_dir / "broken.exr").write_bytes(b"garbage")
    assert main([str(hdr_dir)]) == EXIT_FAILED
    assert pngs(hdr_dir) == ["one_aces20_ev0_sat1.png", "two_aces20_ev0_sat1.png"]


def test_missing_path_is_a_usage_error(tmp_path):
    assert main([str(tmp_path / "nope")]) == EXIT_USAGE


def test_unsupported_single_file_is_a_usage_error(tmp_path):
    jpg = tmp_path / "photo.jpg"
    jpg.write_bytes(b"x")
    assert main([str(jpg)]) == EXIT_USAGE


def test_directory_without_images_is_a_usage_error(tmp_path):
    (tmp_path / "empty").mkdir()
    assert main([str(tmp_path / "empty")]) == EXIT_USAGE


@pytest.mark.parametrize(
    "extra",
    [["--input-space", "Nope"], ["--display", "Nope"], ["--view", "Nope"], ["-c", "missing.ocio"]],
)
def test_bad_pipeline_options_are_usage_errors(hdr_dir, extra):
    assert main([str(hdr_dir), *extra]) == EXIT_USAGE
    assert pngs(hdr_dir) == []


def test_negative_saturation_is_rejected(hdr_dir):
    with pytest.raises(SystemExit) as exc:
        main([str(hdr_dir), "-s", "-1"])
    assert exc.value.code == 2


def test_integer_input_still_converts(tmp_path, write_tiff):
    write_tiff(tmp_path / "photo.tif", np.full((4, 4, 3), 128, dtype=np.uint8))
    assert main([str(tmp_path / "photo.tif"), "--input-space", "sRGB Encoded Rec.709 (sRGB)"]) == EXIT_OK
