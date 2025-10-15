#!/usr/bin/env python3
"""
API REST para procesar imágenes desde URLs
"""

from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
import numpy as np
import os
import tempfile
import uuid
from io import BytesIO
import base64

app = Flask(__name__)

def download_image_from_url(url):
    """Descarga imagen desde URL o data URL"""
    try:
        # Verificar si es una data URL
        if url.startswith('data:'):
            # Extraer el base64 de la data URL
            if ',' in url:
                header, data = url.split(',', 1)
                # Verificar que es una imagen
                if 'image/' not in header:
                    raise ValueError(f"Data URL no contiene una imagen: {header}")
                return base64.b64decode(data)
            else:
                raise ValueError("Data URL inválida")
        else:
            # URL HTTP normal
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            
            # Verificar que es una imagen
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError(f"URL no contiene una imagen: {content_type}")
            
            return response.content
    except Exception as e:
        raise Exception(f"Error descargando imagen: {e}")

def load_image_from_bytes(image_bytes):
    """Carga imagen desde bytes"""
    try:
        image = Image.open(BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        img_array = np.array(image)
        
        if img_array.max() <= 1.0:
            img_array = (img_array * 255).astype(np.uint8)
        else:
            img_array = img_array.astype(np.uint8)
        
        return img_array
    except Exception as e:
        raise Exception(f"Error procesando imagen: {e}")

def extract_binary_from_lsb(image_array):
    """Extrae datos binarios de los LSB"""
    try:
        height, width, channels = image_array.shape
        
        # Estrategias de extracción
        strategies = [
            (int(height * 0.20), int(height * 0.20)),  # 60% central
            (int(height * 0.10), int(height * 0.10)),  # 80% central
            (0, 0)  # Toda la imagen
        ]
        
        for top_skip, bottom_skip in strategies:
            start_row = top_skip
            end_row = height - bottom_skip
            binary_data = ""
            
            for i in range(start_row, end_row):
                for j in range(width):
                    for k in range(channels):
                        bit = image_array[i, j, k] & 1
                        binary_data += str(bit)
                        
                        if len(binary_data) >= 32:
                            try:
                                length_binary = binary_data[:32]
                                data_length = int(length_binary, 2)
                                total_bits_needed = 32 + data_length * 8
                                
                                while len(binary_data) < total_bits_needed:
                                    current_pos = len(binary_data)
                                    pixel_index = current_pos // 3
                                    channel_index = current_pos % 3
                                    
                                    available_pixels = (end_row - start_row) * width
                                    if pixel_index >= available_pixels:
                                        break
                                    
                                    row = start_row + (pixel_index // width)
                                    col = pixel_index % width
                                    
                                    if row < end_row and col < width:
                                        bit = image_array[row, col, channel_index] & 1
                                        binary_data += str(bit)
                                    else:
                                        break
                                
                                if len(binary_data) >= total_bits_needed:
                                    return binary_data[:total_bits_needed]
                                    
                            except ValueError:
                                continue
        
        return None
    except Exception as e:
        raise Exception(f"Error extrayendo datos: {e}")

def binary_to_bytes(binary_string):
    """Convierte binario a bytes"""
    try:
        if len(binary_string) % 8 != 0:
            binary_string = binary_string[:-(len(binary_string) % 8)]
        
        byte_data = bytearray()
        for i in range(0, len(binary_string), 8):
            byte_str = binary_string[i:i+8]
            byte_val = int(byte_str, 2)
            byte_data.append(byte_val)
        
        return bytes(byte_data)
    except Exception as e:
        raise Exception(f"Error convirtiendo binario: {e}")

def convert_to_png(image_data, original_format):
    """Convierte cualquier formato de imagen a PNG"""
    try:
        from PIL import Image
        import io
        
        # Abrir imagen desde bytes
        img = Image.open(io.BytesIO(image_data))
        
        # Convertir a RGB si es necesario (para formatos con paleta)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Mantener transparencia si existe
            if img.mode == 'P' and 'transparency' in img.info:
                img = img.convert('RGBA')
            elif img.mode == 'P':
                img = img.convert('RGB')
        elif img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        
        # Convertir a PNG en memoria
        png_buffer = io.BytesIO()
        img.save(png_buffer, format='PNG', optimize=True)
        png_data = png_buffer.getvalue()
        
        print(f"Convertido {original_format.upper()} a PNG: {len(image_data)} -> {len(png_data)} bytes")
        return png_data
        
    except Exception as e:
        print(f"Error convirtiendo {original_format} a PNG: {e}")
        # Si falla la conversión, devolver datos originales
        return image_data

def convert_svg_to_png(svg_data):
    """Convierte SVG a PNG (requiere librería adicional)"""
    try:
        # Para SVG, por ahora devolvemos los datos originales
        # En producción se podría usar cairosvg o similar
        print("SVG detectado - manteniendo formato original (conversión SVG→PNG no implementada)")
        return svg_data
    except Exception as e:
        print(f"Error procesando SVG: {e}")
        return svg_data

def detect_file_type(file_data):
    """Detecta tipo de archivo y extrae datos si es necesario"""
    
    # === DETECCIÓN DE IMÁGENES EMBEBIDAS ===
    
    # Buscar PNG embebido
    png_start = file_data.find(b'\x89PNG')
    if png_start != -1:
        png_data = file_data[png_start:]
        if len(png_data) > 8 and png_data.startswith(b'\x89PNG'):
            return "png", png_data  # Ya es PNG, no necesita conversión
    
    # Buscar JPEG embebido → PNG
    jpg_start = file_data.find(b'\xFF\xD8\xFF')
    if jpg_start != -1:
        jpg_data = file_data[jpg_start:]
        if len(jpg_data) > 4 and jpg_data.startswith(b'\xFF\xD8\xFF'):
            png_data = convert_to_png(jpg_data, "jpg")
            return "png", png_data
    
    # Buscar GIF embebido → PNG
    gif_start = file_data.find(b'GIF87a')
    if gif_start == -1:
        gif_start = file_data.find(b'GIF89a')
    if gif_start != -1:
        gif_data = file_data[gif_start:]
        if len(gif_data) > 6 and (gif_data.startswith(b'GIF87a') or gif_data.startswith(b'GIF89a')):
            png_data = convert_to_png(gif_data, "gif")
            return "png", png_data
    
    # Buscar WEBP embebido → PNG
    webp_start = file_data.find(b'RIFF')
    if webp_start != -1 and b'WEBP' in file_data[webp_start:webp_start+12]:
        webp_data = file_data[webp_start:]
        if len(webp_data) > 12 and webp_data.startswith(b'RIFF') and b'WEBP' in webp_data[:12]:
            png_data = convert_to_png(webp_data, "webp")
            return "png", png_data
    
    # Buscar BMP embebido → PNG
    bmp_start = file_data.find(b'BM')
    if bmp_start != -1:
        bmp_data = file_data[bmp_start:]
        if len(bmp_data) > 2 and bmp_data.startswith(b'BM'):
            png_data = convert_to_png(bmp_data, "bmp")
            return "png", png_data
    
    # Buscar TIFF embebido → PNG
    tiff_start = file_data.find(b'II*\x00')
    if tiff_start == -1:
        tiff_start = file_data.find(b'MM\x00*')
    if tiff_start != -1:
        tiff_data = file_data[tiff_start:]
        if len(tiff_data) > 4 and (tiff_data.startswith(b'II*\x00') or tiff_data.startswith(b'MM\x00*')):
            png_data = convert_to_png(tiff_data, "tiff")
            return "png", png_data
    
    # Buscar ICO embebido → PNG
    ico_start = file_data.find(b'\x00\x00\x01\x00')
    if ico_start != -1:
        ico_data = file_data[ico_start:]
        if len(ico_data) > 4 and ico_data.startswith(b'\x00\x00\x01\x00'):
            png_data = convert_to_png(ico_data, "ico")
            return "png", png_data
    
    # Buscar SVG embebido → PNG
    svg_start = file_data.find(b'<svg')
    if svg_start == -1:
        svg_start = file_data.find(b'<SVG')
    if svg_start != -1:
        # Buscar el final del SVG
        svg_end = file_data.find(b'</svg>', svg_start)
        if svg_end == -1:
            svg_end = file_data.find(b'</SVG>', svg_start)
        if svg_end != -1:
            svg_data = file_data[svg_start:svg_end + 6]  # Incluir </svg>
            png_data = convert_svg_to_png(svg_data)
            return "png", png_data
    
    # === DETECCIÓN DE VIDEOS EMBEBIDOS ===
    
    # Buscar MP4 embebido
    mp4_start = file_data.find(b'ftyp')
    if mp4_start != -1 and mp4_start < 20:
        mp4_data = file_data[mp4_start-4:]  # Incluir los 4 bytes anteriores
        return "mp4", mp4_data
    
    # === DETECCIÓN DE TIPOS DIRECTOS ===
    
    # Imágenes directas - TODAS se convierten a PNG
    if file_data.startswith(b'\x89PNG'):
        return "png", file_data  # Ya es PNG, no necesita conversión
    elif file_data.startswith(b'\xFF\xD8\xFF'):
        # JPEG → PNG
        png_data = convert_to_png(file_data, "jpg")
        return "png", png_data
    elif file_data.startswith(b'GIF87a') or file_data.startswith(b'GIF89a'):
        # GIF → PNG
        png_data = convert_to_png(file_data, "gif")
        return "png", png_data
    elif file_data.startswith(b'RIFF') and b'WEBP' in file_data[:12]:
        # WEBP → PNG
        png_data = convert_to_png(file_data, "webp")
        return "png", png_data
    elif file_data.startswith(b'BM'):
        # BMP → PNG
        png_data = convert_to_png(file_data, "bmp")
        return "png", png_data
    elif file_data.startswith(b'II*\x00') or file_data.startswith(b'MM\x00*'):
        # TIFF → PNG
        png_data = convert_to_png(file_data, "tiff")
        return "png", png_data
    elif file_data.startswith(b'\x00\x00\x01\x00'):
        # ICO → PNG
        png_data = convert_to_png(file_data, "ico")
        return "png", png_data
    elif file_data.startswith(b'<svg') or file_data.startswith(b'<SVG'):
        # SVG → PNG (requiere conversión especial)
        png_data = convert_svg_to_png(file_data)
        return "png", png_data
    
    # Videos directos
    elif file_data.startswith(b'RIFF') and b'AVI' in file_data[:20]:
        return "avi", file_data
    elif file_data.startswith(b'\x1a\x45\xdf\xa3'):
        return "mkv", file_data
    
    # Audio directo
    elif file_data.startswith(b'ID3') or file_data.startswith(b'\xff\xfb'):
        return "mp3", file_data
    elif file_data.startswith(b'RIFF') and b'WAVE' in file_data[:20]:
        return "wav", file_data
    
    # Fallback
    else:
        return "bin", file_data

def cleanup_old_files():
    """Limpia archivos antiguos (más de 1 día)"""
    try:
        output_dir = "output"
        if not os.path.exists(output_dir):
            return 0
        
        import time
        current_time = time.time()
        cleaned_count = 0
        total_files = 0
        
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            if os.path.isfile(file_path):
                total_files += 1
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > 86400:  # 1 día = 86400 segundos
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                        print(f"Archivo antiguo eliminado: {filename}")
                    except Exception as e:
                        print(f"Error eliminando {filename}: {e}")
        
        if cleaned_count > 0:
            print(f"Limpieza completada: {cleaned_count} archivos eliminados de {total_files} total")
        else:
            print(f"Limpieza completada: 0 archivos eliminados de {total_files} total")
            
        return cleaned_count
            
    except Exception as e:
        print(f"Error en limpieza: {e}")
        return 0

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "TT-Tools API",
        "version": "1.0.0"
    })

@app.route('/decode', methods=['POST'])
def decode_image():
    """Decodifica imagen desde URL"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({
                "error": "URL requerida",
                "example": {"url": "https://example.com/image.png"}
            }), 400
        
        image_url = data['url']
        # Generar nombre automático basado en timestamp
        import time
        output_name = f"decoded_{int(time.time())}"
        
        # Descargar imagen
        print(f"Descargando imagen: {image_url}")
        image_bytes = download_image_from_url(image_url)
        
        # Procesar imagen
        print("Procesando imagen...")
        img_array = load_image_from_bytes(image_bytes)
        
        # Extraer datos
        print("Extrayendo datos ocultos...")
        binary_data = extract_binary_from_lsb(img_array)
        
        if not binary_data:
            return jsonify({
                "error": "No se encontraron datos ocultos en la imagen",
                "success": False
            }), 404
        
        # Convertir a bytes
        file_data = binary_to_bytes(binary_data)
        file_type, extracted_data = detect_file_type(file_data)
        
        # Crear directorio de salida si no existe
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Limpiar archivos antiguos
        cleaned_files = cleanup_old_files()
        
        # Crear archivo con nombre único
        temp_filename = f"{output_name}_{uuid.uuid4().hex[:8]}.{file_type}"
        file_path = os.path.join(output_dir, temp_filename)
        
        # Guardar archivo
        with open(file_path, 'wb') as f:
            f.write(extracted_data)
        
        # Obtener la URL base del request
        base_url = request.url_root.rstrip('/')
        download_url = f"{base_url}/download/{temp_filename}"
        
        # Calcular fecha de eliminación (1 día desde ahora)
        import datetime
        deletion_date = datetime.datetime.now() + datetime.timedelta(days=1)
        deletion_timestamp = int(deletion_date.timestamp())
        
        return jsonify({
            "success": True,
            "file_type": file_type,
            "file_size": len(extracted_data),
            "download_url": download_url,
            "filename": temp_filename,
            "deletion_date": deletion_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "deletion_timestamp": deletion_timestamp,
            "expires_in_hours": 24,
            "cleanup_info": {
                "files_cleaned": cleaned_files,
                "cleanup_message": f"Se eliminaron {cleaned_files} archivos antiguos"
            },
            "message": f"Archivo {file_type} extraído exitosamente"
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Descarga archivo decodificado"""
    try:
        output_dir = "output"
        file_path = os.path.join(output_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Archivo no encontrado"}), 404
        
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/decode/direct', methods=['POST'])
def decode_image_direct():
    """Decodifica imagen y devuelve archivo directamente"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({"error": "URL requerida"}), 400
        
        image_url = data['url']
        
        # Procesar imagen (mismo código que arriba)
        image_bytes = download_image_from_url(image_url)
        img_array = load_image_from_bytes(image_bytes)
        binary_data = extract_binary_from_lsb(img_array)
        
        if not binary_data:
            return jsonify({"error": "No se encontraron datos ocultos"}), 404
        
        file_data = binary_to_bytes(binary_data)
        file_type, extracted_data = detect_file_type(file_data)
        
        # Crear directorio de salida si no existe
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Limpiar archivos antiguos
        cleanup_old_files()
        
        # Crear archivo con nombre único
        temp_filename = f"decoded_{uuid.uuid4().hex[:8]}.{file_type}"
        file_path = os.path.join(output_dir, temp_filename)
        
        # Guardar archivo
        with open(file_path, 'wb') as f:
            f.write(extracted_data)
        
        return send_file(file_path, as_attachment=True, download_name=f"decoded.{file_type}")
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Iniciando TT-Tools API Server...")
    print("Endpoints disponibles:")
    print("   GET  /health - Health check")
    print("   POST /decode - Decodificar imagen (devuelve JSON)")
    print("   POST /decode/direct - Decodificar imagen (devuelve archivo)")
    print("   GET  /download/<filename> - Descargar archivo")
    print("\n Ejemplo de uso:")
    print('curl -X POST http://localhost:5000/decode -H "Content-Type: application/json" -d \'{"url": "https://example.com/image.png"}\'')
    
    app.run(host='0.0.0.0', port=5000, debug=True)
