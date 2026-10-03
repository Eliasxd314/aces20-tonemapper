#!/usr/bin/env python3
import sys
import os
import argparse
import cv2
import numpy as np
import OpenEXR
import Imath
import PyOpenColorIO as OCIO
from PIL import Image
from PIL.PngImagePlugin import PngInfo

def read_pure_exr(file_path):
    """Reads raw float32 channels directly using the OpenEXR library."""
    exr_file = OpenEXR.InputFile(file_path)
    header = exr_file.header()
    
    dw = header['dataWindow']
    width = dw.max.x - dw.min.x + 1
    height = dw.max.y - dw.min.y + 1

    pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)
    
    # Extract channels in direct RGB order (preferred by OpenColorIO)
    c_r = np.frombuffer(exr_file.channel('R', pixel_type), dtype=np.float32).reshape(height, width)
    c_g = np.frombuffer(exr_file.channel('G', pixel_type), dtype=np.float32).reshape(height, width)
    c_b = np.frombuffer(exr_file.channel('B', pixel_type), dtype=np.float32).reshape(height, width)
    
    return cv2.merge([c_r, c_g, c_b])

def find_ocio_config():
    """Automatically searches for any .ocio configuration file in the current directory."""
    for file in os.listdir('.'):
        if file.lower().endswith('.ocio'):
            return file
    return None

def process_image(input_path, config_file, exposure, saturation):
    """Applies exposure multiplier, saturation adjustment, and the ACES 2.0 color pipeline."""
    base_name, ext = os.path.splitext(input_path)
    ext = ext.lower()
    output_path = f"{base_name}_aces20_exp{exposure}_sat{saturation}.png"

    config = OCIO.Config.CreateFromFile(config_file)
    
    print(f"\n[+] Processing: {input_path}")
    try:
        if ext == '.exr':
            rgb_img = read_pure_exr(input_path)
        elif ext in ['.tiff', '.tif', '.hdr']:
            img_raw = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
            if img_raw is None:
                raise ValueError("OpenCV could not decode the image matrix.")
            
            if img_raw.dtype == np.uint16:
                img_raw = img_raw.astype(np.float32) / 65535.0
            elif img_raw.dtype == np.uint8:
                img_raw = img_raw.astype(np.float32) / 255.0
                
            rgb_img = cv2.cvtColor(img_raw, cv2.COLOR_BGR2RGB)
        else:
            print(f"[-] Unsupported file extension: {ext}")
            return
    except Exception as e:
        print(f"[-] Critical decoding error on {input_path}: {e}")
        return

    # Apply linear exposure factor before tone mapping
    if exposure != 1.0:
        rgb_img = rgb_img * exposure

    # Ensure C-contiguous memory layout for OpenColorIO C++ compatibility
    img_buffer = np.ascontiguousarray(rgb_img, dtype=np.float32)
    
    try:
        transform_group = OCIO.GroupTransform()
        
        # Step A: Adjust saturation via native ASC-CDL math
        if saturation != 1.0:
            cdl = OCIO.CDLTransform()
            cdl.setSat(saturation)
            transform_group.appendTransform(cdl)
        
        # Step B: Compile official ACEScg to sRGB Display RRT+ODT transform
        aces_transform = OCIO.ColorSpaceTransform(src="ACEScg", dst="sRGB - Display")
        transform_group.appendTransform(aces_transform)
        
        processor = config.getProcessor(transform_group)
        cpu_processor = processor.getDefaultCPUProcessor()
        cpu_processor.applyRGB(img_buffer)
    except Exception as e:
        print(f"[-] OpenColorIO processing error: {e}")
        return

    # Format buffer to standard 8-bit LDR limits
    img_buffer = np.clip(img_buffer, 0.0, 1.0)
    img_8bit = (img_buffer * 255).astype(np.uint8)

    # Convert to Pillow image to inject metadata blocks safely
    pil_img = Image.fromarray(img_8bit)
    metadata = PngInfo()
    
    metadata.add_text("Software", "Custom ACES 2.0 Tonemapper CLI Tool")
    metadata.add_text("HDR_Exposure_Factor", str(exposure))
    metadata.add_text("HDR_Saturation_Factor", str(saturation))
    metadata.add_text("Color_Space_Pipeline", "ACEScg -> ASC-CDL -> sRGB Display")

    pil_img.save(output_path, pnginfo=metadata)
    print(f"    [!] Success! Output saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Cinematic HDR Tonemapper powered by ACES 2.0")
    parser.add_argument("input", nargs="?", help="Path to a single HDR file or a directory. Defaults to current path '.'")
    parser.add_argument("-e", "--exposure", type=float, default=1.0, help="Linear exposure multiplier factor. (Default: 1.0)")
    parser.add_argument("-s", "--saturation", type=float, default=1.0, help="ASC-CDL saturation adjustment factor. (Default: 1.0)")
    parser.add_argument("-c", "--config", type=str, default=None, help="Path to custom ACES .ocio config file. (Optional)")
    
    args = parser.parse_args()

    # Determine which .ocio config to use (argument overrides automatic lookup)
    if args.config:
        config_file = args.config
    else:
        config_file = find_ocio_config()

    if not config_file or not os.path.exists(config_file):
        print("[-] Error: No OpenColorIO (.ocio) configuration file found in the current directory.")
        print("    Please download an official ACES config and place it here, or pass it via '--config'.")
        sys.exit(1)

    target = args.input if args.input else "."
    valid_extensions = ('.exr', '.tiff', '.tif', '.hdr')

    if os.path.isfile(target):
        if target.lower().endswith(valid_extensions):
            process_image(target, config_file, args.exposure, args.saturation)
        else:
            print("[-] Error: Specified file must be an .exr, .tiff, .tif, or .hdr image.")
    elif os.path.isdir(target):
        files = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith(valid_extensions)]
        if not files:
            print(f"[-] No valid HDR source images found in directory: {target}")
            return
            
        print(f"[*] Batch processing {len(files)} files using OpenColorIO config: {config_file}")
        for file_path in files:
            process_image(file_path, config_file, args.exposure, args.saturation)
    else:
        print(f"[-] Error: '{target}' is not a valid file or directory path.")
        sys.exit(1)

if __name__ == "__main__":
    main()

