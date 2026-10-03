# ACES 2.0 HDR Tonemapper Script 🎬🍿

Un script en Python de línea de comandos diseñado para aplicar de forma nativa el pipeline de mapeo de tonos **ACES 2.0 (Academy Color Encoding System)** a imágenes de alto rango dinámico (HDR), con soporte para archivos `.exr` y `.tiff` de alta precisión.

El script incluye ajustes de exposición lineal, control de saturación por hardware de color (ASC-CDL), procesamiento por lotes (batch) e incrusta metadatos personalizados dentro del archivo de salida.

## Prerrequisitos (Fedora Linux)

Asegúrate de instalar las librerías de desarrollo del sistema antes de instalar las dependencias de Python:

```bash
sudo dnf install openexr openexr-devel zlib-devel gcc-c++ python3-devel exiftool
pip install -r requirements.txt
```

> **Nota Importante:** Este script requiere el archivo de configuración oficial de ACES 2.0. Debes descargar el archivo `.ocio` (se recomienda la versión *CG Config*) desde el repositorio oficial de [OpenColorIO-Config-ACES](https://github.com) y colocarlo en el mismo directorio con el nombre `cg-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio`.

## Características

- 🚀 **Pipeline ACES 2.0 Puro:** Transformación matemática exacta usando OpenColorIO.
- 📸 **Soporte de Formatos:** Decodificación nativa de archivos OpenEXR de 16/32-bit y TIFF flotantes.
- 🎛️ **Controles de Imagen:** Modificadores de exposición lineal (`-e`) y saturación cromática (`-s`).
- 📂 **Procesamiento por Lotes:** Procesa directorios enteros si no se especifica un archivo.
- 🏷️ **Metadatos Persistentes:** Inyecta factores de revelado internamente en el PNG (`tEXt`), legibles con `exiftool`.

## Ejemplos de Uso

**Revelar una sola imagen ajustando saturación:**
```bash
./tonemap-aces.py mi_foto.exr -e 1.0 -s 0.75
```

**Procesar una carpeta completa en lote:**
```bash
./tonemap-aces.py /ruta/a/mis/imagenes/hdr/
```
