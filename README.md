# ACES 2.0 HDR Tonemapper Script 🎬🍿

A command-line Python tool that applies the **ACES 2.0 (Academy Color Encoding System)** output transform to High Dynamic Range (HDR) images, with support for high-precision `.exr`, floating-point `.tiff` and Radiance `.hdr` files.

It includes exposure control in stops (EV), ASC-CDL saturation, batch processing, and writes the development settings into the output PNG as metadata.

## Installation

```bash
pip install -r requirements.txt
```

The Python wheels bundle OpenEXR and OpenColorIO, so no system libraries are normally needed. If `pip` ends up compiling OpenEXR, install the build tools first (Fedora):

```bash
sudo dnf install openexr openexr-devel zlib-devel gcc-c++ python3-devel
```

Optionally install `exiftool` to read the metadata embedded in the output files.

### OpenColorIO configuration

With **OpenColorIO >= 2.5** (what `requirements.txt` installs) the ACES 2.0 CG config is built in, so you don't need to download anything. A different config is looked up in this order:

1. `--config path/to/file.ocio`
2. the first `.ocio` file in the current directory
3. the `$OCIO` environment variable
4. the built-in ACES 2.0 CG config

If you use your own config, get the official ones from the [OpenColorIO-Config-ACES](https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES) repository (the *CG Config* is recommended).

## Features

- 🚀 **ACES 2.0 output transform:** a real display/view transform (with highlight roll-off) executed by OpenColorIO, not just a color space conversion.
- 📸 **Formats:** 16/32-bit OpenEXR (RGB, RGBA or single channel), floating-point and integer TIFF, and Radiance HDR.
- 🎛️ **Image controls:** exposure in stops (`-e`) and ASC-CDL saturation (`-s`), both applied in scene-linear ACEScg.
- 🎨 **Any input color space:** `--input-space` converts from Linear Rec.709, ACES2065-1, sRGB-encoded, etc.
- 📂 **Batch processing:** one config and one processor are built per run and reused for every file. A broken file is reported and skipped; the rest are still processed.
- 🏷️ **Metadata:** exposure, saturation, input space, display and view are embedded as PNG `tEXt` chunks (readable with `exiftool`).

## Usage

```bash
# One image: +1 stop of exposure and 25% less saturation
./tonemap-aces.py my_photo.exr -e 1.0 -s 0.75

# A whole directory
./tonemap-aces.py /path/to/my/hdr/images/

# An image that is not ACEScg (e.g. a linear sRGB render), saving results elsewhere
./tonemap-aces.py render.exr --input-space "Linear Rec.709 (sRGB)" -o results/

# Your own OCIO config, and a different display/view
./tonemap-aces.py landscape.exr --config /opt/ocio/studio-config.ocio --display "sRGB - Display"
```

Run `./tonemap-aces.py --help` for every option. The tool also works as `python -m aces20_tonemapper`.

### Options

| Option | Meaning |
| --- | --- |
| `-e, --exposure EV` | Exposure offset in **stops**. `0` leaves the image unchanged, `+1` doubles the light, `-1` halves it. |
| `-s, --saturation` | ASC-CDL saturation. `1` unchanged, `0` monochrome. |
| `--input-space NAME` | OCIO color space of the source pixels. Default: `ACEScg`. |
| `--display`, `--view` | OCIO display and view. Default: the config's defaults. |
| `-c, --config FILE` | OCIO config (see the lookup order above). |
| `-o, --output-dir DIR` | Where to write the PNGs. Default: next to each input. |
| `--overwrite` | Replace existing outputs. By default they are skipped. |
| `-v, --verbose` | Debug output. |

### Output files and exit codes

Results are named `<name>_aces20_ev<EV>_sat<S>.png`. If two inputs would collide (`shot.exr` and `shot.tif`), the source extension is added to the name (`shot_exr_...`, `shot_tif_...`).

| Exit code | Meaning |
| --- | --- |
| `0` | Everything converted (or was skipped because the output already exists). |
| `1` | At least one image failed. |
| `2` | Invalid usage or configuration; nothing was processed. |

### Notes

- **8/16-bit integer TIFFs** are normally display-encoded, not linear. Use `--input-space "sRGB Encoded Rec.709 (sRGB)"` for them; the tool warns when it suspects this.
- **Alpha channels** are dropped; the output is an opaque 8-bit PNG.
- **NaN/Inf pixels** (common in renders) are replaced before processing.
- Saturation uses ASC-CDL, whose luma weights are Rec.709 even though the working space is ACEScg.

## Upgrading from 0.1

- `-e` is now in **stops (EV)** instead of a linear multiplier. The old `-e 2.0` (×2) is now `-e 1`; the old `-e 1.0` (no change) is now `-e 0`, which is also the default.
- The old version converted with a plain color space transform, which **clipped everything above 1.0** instead of tone mapping. Results now use the real ACES 2.0 output transform, so images will look different (and better in the highlights).
- Existing output files are no longer overwritten unless you pass `--overwrite`.

## Project layout

```
tonemap-aces.py            thin entry point (keeps the old command working)
aces20_tonemapper/
    cli.py                 arguments, batch loop, exit codes
    config.py              OCIO config lookup and validation
    image_io.py            reading EXR/TIFF/HDR, writing PNG
    pipeline.py            the color pipeline (builds the OCIO processor once)
tests/                     pytest suite using small synthetic images
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute.
