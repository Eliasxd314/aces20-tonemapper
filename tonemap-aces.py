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

def leer_exr_puro(ruta):
    archivo = OpenEXR.InputFile(ruta)
    header = archivo.header()
    
    dw = header['dataWindow']
    width = dw.max.x - dw.min.x + 1
    height = dw.max.y - dw.min.y + 1

    tipo_pixel = Imath.PixelType(Imath.PixelType.FLOAT)
    c_r = np.frombuffer(archivo.channel('R', tipo_pixel), dtype=np.float32).reshape(height, width)
    c_g = np.frombuffer(archivo.channel('G', tipo_pixel), dtype=np.float32).reshape(height, width)
    c_b = np.frombuffer(archivo.channel('B', tipo_pixel), dtype=np.float32).reshape(height, width)
    
    return cv2.merge([c_r, c_g, c_b])

def procesar_imagen(input_path, config_file, exposure, saturation):
    base_name, ext = os.path.splitext(input_path)
    ext = ext.lower()
    
    # 1. DINÁMICO: Incluir los parámetros de la prueba directo en el nombre del archivo
    output_path = f"{base_name}_aces20_exp{exposure}_sat{saturation}.png"

    config = OCIO.Config.CreateFromFile(config_file)
    
    print(f"\n[+] Procesando: {input_path}")
    try:
        if ext in ['.exr']:
            rgb_img = leer_exr_puro(input_path)
        elif ext in ['.tiff', '.tif', '.hdr']:
            img_raw = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
            if img_raw is None:
                raise ValueError("La imagen no pudo ser leída por OpenCV.")
            if img_raw.dtype == np.uint16:
                img_raw = img_raw.astype(np.float32) / 65535.0
            elif img_raw.dtype == np.uint8:
                img_raw = img_raw.astype(np.float32) / 255.0
            rgb_img = cv2.cvtColor(img_raw, cv2.COLOR_BGR2RGB)
        else:
            return
    except Exception as e:
        print(f"[-] Error crítico al decodificar la imagen: {e}")
        return

    if exposure != 1.0:
        rgb_img = rgb_img * exposure

    img_buffer = np.ascontiguousarray(rgb_img, dtype=np.float32)
    
    try:
        grupo = OCIO.GroupTransform()
        if saturation != 1.0:
            cdl = OCIO.CDLTransform()
            cdl.setSat(saturation)
            grupo.appendTransform(cdl)
        
        aces_transform = OCIO.ColorSpaceTransform(src="ACEScg", dst="sRGB - Display")
        grupo.appendTransform(aces_transform)
        
        procesador = config.getProcessor(grupo)
        cpu = procesador.getDefaultCPUProcessor()
        cpu.applyRGB(img_buffer)
    except Exception as e:
        print(f"[-] Error en el procesador de OpenColorIO: {e}")
        return

    # Pasar los datos a un formato compatible de 8 bits para pasarlo a Pillow
    img_buffer = np.clip(img_buffer, 0.0, 1.0)
    img_8bit = (img_buffer * 255).astype(np.uint8)

    # 2. METADATOS: Convertir la matriz de pixeles a objeto de imagen Pillow para inyectar texto plano
    pil_img = Image.fromarray(img_8bit)
    metadata = PngInfo()
    
    # Añadimos los metadatos personalizados en bloques de texto integrados
    metadata.add_text("Software", "Custom ACES 2.0 Tonemapper Script")
    metadata.add_text("HDR_Exposure_Factor", str(exposure))
    metadata.add_text("HDR_Saturation_Factor", str(saturation))
    metadata.add_text("Color_Space_Pipeline", "ACEScg -> ASC-CDL -> sRGB Display")

    # Guardar usando Pillow con el contenedor de metadatos adjunto
    pil_img.save(output_path, pnginfo=metadata)
    print(f"    [!] ¡Éxito! Archivo generado: {output_path}")
    print(f"    [i] Metadatos internos incrustados de forma segura.")

def main():
    parser = argparse.ArgumentParser(description="Procesador HDR cinematográfico con ACES 2.0 (Metadatos y nombres dinámicos)")
    parser.add_argument("input", nargs="?", help="Ruta del archivo o carpeta. Por defecto usa '.'")
    parser.add_argument("-e", "--exposure", type=float, default=1.0, help="Multiplicador de exposición lineal.")
    parser.add_argument("-s", "--saturation", type=float, default=1.0, help="Factor de saturación ASC-CDL.")
    
    args = parser.parse_args()

    config_file = "cg-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio"
    if not os.path.exists(config_file):
        print(f"[-] Error: Falta el archivo '{config_file}' en este directorio.")
        sys.exit(1)

    target = args.input if args.input else "."
    extensiones_validas = ('.exr', '.tiff', '.tif', '.hdr')

    if os.path.isfile(target):
        if target.lower().endswith(extensiones_validas):
            procesar_imagen(target, config_file, args.exposure, args.saturation)
    elif os.path.isdir(target):
        archivos = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith(extensiones_validas)]
        for file_path in archivos:
            procesar_imagen(file_path, config_file, args.exposure, args.saturation)

if __name__ == "__main__":
    main()

