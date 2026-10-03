"""Command-line interface: argument parsing, batch processing and exit codes.

Exit codes:
    0  every image was converted (or deliberately skipped)
    1  at least one image failed
    2  invalid usage or configuration; nothing was processed
"""

from __future__ import annotations

import argparse
import enum
import logging
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .config import load_config
from .errors import TonemapError
from .image_io import SUPPORTED_EXTENSIONS, is_supported, read_image, write_png
from .pipeline import WORKING_SPACE, Tonemapper, TonemapSettings

log = logging.getLogger("aces20_tonemapper")

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


class Status(enum.Enum):
    CONVERTED = "converted"
    SKIPPED = "skipped"
    FAILED = "failed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tonemap-aces",
        description="HDR tonemapper powered by the ACES 2.0 output transform (OpenColorIO).",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=".",
        help="HDR file (.exr, .tif/.tiff, .hdr) or a directory of them. Default: current directory.",
    )
    parser.add_argument(
        "-e", "--exposure", type=float, default=0.0, metavar="EV",
        help="Exposure offset in stops (EV). +1 doubles the light, -1 halves it. (Default: 0)",
    )
    parser.add_argument(
        "-s", "--saturation", type=float, default=1.0,
        help="ASC-CDL saturation factor; 1 = unchanged, 0 = monochrome. (Default: 1.0)",
    )
    parser.add_argument(
        "--input-space", default=WORKING_SPACE, metavar="NAME",
        help=f"OCIO color space of the source pixels. (Default: {WORKING_SPACE}). Examples: "
             "'Linear Rec.709 (sRGB)', 'ACES2065-1', 'sRGB Encoded Rec.709 (sRGB)'.",
    )
    parser.add_argument("--display", default=None, help="OCIO display. (Default: the config's default)")
    parser.add_argument("--view", default=None, help="OCIO view. (Default: the config's default)")
    parser.add_argument(
        "-c", "--config", default=None,
        help="Path to an OCIO .ocio config. Default: a .ocio in the current directory, "
             "then $OCIO, then the ACES 2.0 config built into OpenColorIO >= 2.5.",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Directory for the PNG results. (Default: next to each input file)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace existing output files instead of skipping them.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug messages.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def collect_inputs(target: Path) -> list[Path]:
    """Return the supported images at ``target`` (a file or a directory), sorted by name."""
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.is_file() and is_supported(p))


def output_path_for(
    input_path: Path,
    settings: TonemapSettings,
    output_dir: Path | None,
    include_extension: bool = False,
) -> Path:
    stem = f"{input_path.stem}_{input_path.suffix.lstrip('.').lower()}" if include_extension else input_path.stem
    name = f"{stem}_aces20_ev{settings.exposure_ev:g}_sat{settings.saturation:g}.png"
    return (output_dir or input_path.parent) / name


def plan_outputs(
    files: list[Path], settings: TonemapSettings, output_dir: Path | None
) -> list[Path]:
    """Output path for each input. Files that would collide (``a.exr`` + ``a.tif``) get
    their source extension added to the name, so no result silently replaces another."""
    default_paths = [output_path_for(f, settings, output_dir) for f in files]
    counts = Counter(default_paths)
    return [
        output_path_for(f, settings, output_dir, include_extension=counts[path] > 1)
        for f, path in zip(files, default_paths)
    ]


def process_file(
    input_path: Path, output_path: Path, tonemapper: Tonemapper, overwrite: bool
) -> Status:
    """Convert one image. Never raises: failures are logged and reported as ``Status.FAILED``."""
    if output_path.exists() and not overwrite:
        log.warning("Skipping %s: %s already exists (use --overwrite).", input_path.name, output_path.name)
        return Status.SKIPPED

    log.info("Processing %s", input_path)
    try:
        image = read_image(input_path)
        if image.integer_source and tonemapper.settings.input_space in (WORKING_SPACE, "Linear Rec.709 (sRGB)"):
            log.warning(
                "%s stores 8/16-bit integers, which are usually display-encoded, but the input "
                "space is '%s' (linear). If colors look wrong, try "
                "--input-space 'sRGB Encoded Rec.709 (sRGB)'.",
                input_path.name, tonemapper.settings.input_space,
            )
        result = tonemapper.apply(image.rgb)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_png(result, output_path, tonemapper.metadata())
    except TonemapError as exc:
        log.error("%s: %s", input_path.name, exc)
        return Status.FAILED
    except Exception:  # keep a batch going; the traceback is still logged
        log.exception("Unexpected error while processing %s", input_path.name)
        return Status.FAILED

    log.info("Saved %s", output_path)
    return Status.CONVERTED


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.saturation < 0:
        parser.error("--saturation must be >= 0")

    target = Path(args.input)
    if not target.exists():
        log.error("'%s' is not a valid file or directory.", target)
        return EXIT_USAGE
    if target.is_file() and not is_supported(target):
        log.error("Unsupported file '%s'. Supported extensions: %s", target.name,
                  ", ".join(sorted(SUPPORTED_EXTENSIONS)))
        return EXIT_USAGE
    files = collect_inputs(target)
    if not files:
        log.error("No supported HDR images found in directory: %s", target)
        return EXIT_USAGE

    settings = TonemapSettings(
        exposure_ev=args.exposure,
        saturation=args.saturation,
        input_space=args.input_space,
        display=args.display,
        view=args.view,
    )
    try:
        tonemapper = Tonemapper(load_config(args.config), settings)
    except TonemapError as exc:
        log.error("%s", exc)
        return EXIT_USAGE
    log.info("Pipeline: %s -> %s / %s", settings.input_space, tonemapper.display, tonemapper.view)

    outputs = plan_outputs(files, settings, args.output_dir)
    results = [
        process_file(src, dst, tonemapper, args.overwrite) for src, dst in zip(files, outputs)
    ]
    counts = {status: results.count(status) for status in Status}
    if len(files) > 1:
        log.info(
            "Done: %d converted, %d skipped, %d failed.",
            counts[Status.CONVERTED], counts[Status.SKIPPED], counts[Status.FAILED],
        )
    return EXIT_FAILED if counts[Status.FAILED] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
