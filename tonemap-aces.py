#!/usr/bin/env python3
import sys
import argparse
import cv2
import numpy as np
import OpenEXR
import Imath
import PyOpenColorIO as OCIO
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pathlib import Path  # <-- Cambiado: Usamos Pathlib para soporte multiplataforma

def read_pure_exr(file_path):
    """Reads raw float32 channels directly using the OpenEXR library."""
    # Convertimos Path a string absoluto para que la librería C++ de OpenEXR no falle en Windows
    str_path = str(Path(file_path).resolve())
    exr_file = OpenEXR.InputFile(str_path)
    header = exr_file.header()
    
    dw = header['dataWindow']
    width = dw.max.x - dw.min.x + 1
    height = dw.max.y - dw.min.y + 1

    pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)
    
    c_r = np.frombuffer(exr_file.channel('R', pixel_type), dtype=np.float32).reshape(height, width)
    c_g = np.frombuffer(exr_file.channel('G', pixel_type), dtype=np.float32).reshape(height, width)
    c_b = np.frombuffer(exr_file.channel('B', pixel_type), dtype=np.float32).reshape(height, width)
    
    return cv2.merge([c_r, c_g, c_b])

def find_ocio_config():
    """Automatically searches for any .ocio configuration file in the current directory."""
    # Búsqueda segura usando pathlib
    for item in Path('.').iterdir():
        if item.is_file() and item.suffix.lower() == '.ocio':
            return item
    return None

def process_image(input_path, config_file, exposure, saturation):
    """Applies exposure multiplier, saturation adjustment, and the ACES 2.0 color pipeline."""
    input_path = Path(input_path)
    ext = input_path.suffix.lower()
    
    # Construcción de ruta de salida compatible con Windows y Linux
    output_name = f"{input_path.stem}_aces20_exp{exposure}_sat{saturation}.png"
    output_path = input_path.parent / output_name

    # Convertimos a string plano para OpenColorIO
    str_config = str(Path(config_file).resolve())
    config = OCIO.Config.CreateFromFile(str_config)
    
    print(f"\n[+] Processing: {input_path}")
    try:
        if ext == '.exr':
            rgb_img = read_pure_exr(input_path)
        elif ext in ['.tiff', '.tif', '.hdr']:
            # OpenCV lee strings de ruta mejor en entornos multiplataforma
            img_raw = cv2.imread(str(input_path.resolve()), cv2.IMREAD_UNCHANGED)
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

    if exposure != 1.0:
        rgb_img = rgb_img * exposure

    img_buffer = np.ascontiguousarray(rgb_img, dtype=np.float32)
    
    try:
        transform_group = OCIO.GroupTransform()
        
        if saturation != 1.0:
            cdl = OCIO.CDLTransform()
            cdl.setSat(saturation)
            transform_group.appendTransform(cdl)
        
        aces_transform = OCIO.ColorSpaceTransform(src="ACEScg", dst="sRGB - Display")
        transform_group.appendTransform(aces_transform)
        
        processor = config.getProcessor(transform_group)
        cpu_processor = processor.getDefaultCPUProcessor()
        cpu_processor.applyRGB(img_buffer)
    except Exception as e:
        print(f"[-] OpenColorIO processing error: {e}")
        return

    img_buffer = np.clip(img_buffer, 0.0, 1.0)
    img_8bit = (img_buffer * 255).astype(np.uint8)

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

    if args.config:
        config_file = Path(args.config)
    else:
        config_file = find_ocio_config()

    if not config_file or not config_file.exists():
        print("[-] Error: No OpenColorIO (.ocio) configuration file found in the current directory.")
        print("    Please download an official ACES config and place it here, or pass it via '--config'.")
        sys.exit(1)

    target = Path(args.input) if args.input else Path(".")
    valid_extensions = ('.exr', '.tiff', '.tif', '.hdr')

    if target.is_file():
        if target.suffix.lower() in valid_extensions:
            process_image(target, config_file, args.exposure, args.saturation)
        else:
            print("[-] Error: Specified file must be an .exr, .tiff, .tif, or .hdr image.")
    elif target.is_dir():
        files = [f for f in target.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]
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

