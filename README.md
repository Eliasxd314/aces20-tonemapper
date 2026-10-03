# ACES 2.0 HDR Tonemapper Script 🎬🍿

A command-line Python script designed to natively apply the **ACES 2.0 (Academy Color Encoding System)** tone mapping pipeline to High Dynamic Range (HDR) images, featuring robust support for high-precision `.exr` and `.tiff` files.

The script includes linear exposure multipliers, color-hardware saturation controls via ASC-CDL math, automatic batch processing, and injects persistent development metadata into the output files.

## Prerequisites (Fedora Linux)

Ensure you install the required system development libraries before setting up the Python dependencies:

```bash
sudo dnf install openexr openexr-devel zlib-devel gcc-c++ python3-devel exiftool
pip install -r requirements.txt
```

> **Important Note:** This script requires an official ACES 2.0 OpenColorIO configuration file. Download the `.ocio` profile (the *CG Config* version is highly recommended) from the official [OpenColorIO-Config-ACES](https://github.com) repository and place it in the same directory as the script. The script will automatically detect and use it.

## Features

- 🚀 **Pure ACES 2.0 Pipeline:** Exact mathematical color transformations powered natively by OpenColorIO.
- 📸 **Format Support:** High-precision native decoding for 16/32-bit OpenEXR and floating-point TIFF matrices.
- 🎛️ **Image Controls:** Fine-tune image states with linear exposure (`-e`) and ASC-CDL saturation (`-s`) modifiers.
- 📂 **Smart Configuration Lookup:** Automatically searches for any `.ocio` file in the execution directory, reducing hardcoding friction.
- 🏷️ **Persistent Metadata:** Injects development factors internally into the output PNG containers (`tEXt` chunks), readable globally via `exiftool`.

## Usage Examples

**Process a single HDR image reducing chromatic saturation by 25%:**
```bash
./tonemap-aces.py my_photo.exr -e 1.0 -s 0.75
```

**Batch process an entire directory of HDR exposures at once:**
```bash
./tonemap-aces.py /path/to/my/hdr/images/
```

**Explicitly pass an external OpenColorIO config file location:**
```bash
./tonemap-aces.py landscape.exr --config /opt/ocio/studio-config.ocio
```

