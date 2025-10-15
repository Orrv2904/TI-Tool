#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
import numpy as np
import os
import tempfile
import uuid
from io import BytesIO
import base64
import time

app = Flask(__name__)

# Directorio para archivos temporales
UPLOAD_FOLDER = 'output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    """Extrae datos binarios de los LSB con múltiples estrategias"""
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
        
        print(f"Convirtiendo {original_format.upper()} a PNG...")
        print(f"  Datos originales: {len(image_data)} bytes")
        print(f"  Magic bytes: {image_data[:8].hex()}")
        
        # Abrir imagen desde bytes
        img = Image.open(io.BytesIO(image_data))
        print(f"  Imagen abierta: {img.size}, modo: {img.mode}")
        
        # Convertir a PNG
        png_buffer = io.BytesIO()
        img.save(png_buffer, format='PNG')
        png_data = png_buffer.getvalue()
        
        print(f"  PNG generado: {len(png_data)} bytes")
        print(f"  PNG magic: {png_data[:8].hex()}")
        print(f"CONVERSIÓN EXITOSA: {original_format.upper()} -> PNG")
        return png_data
        
    except Exception as e:
        print(f"ERROR convirtiendo {original_format} a PNG: {e}")
        print(f"  Devolviendo datos originales ({len(image_data)} bytes)")
        return image_data

def detect_file_type(file_data):
    """Detecta tipo de archivo y lo convierte a PNG si es necesario"""
    
    # === DETECCIÓN DE IMÁGENES DIRECTAS ===
    
    # PNG directo
    if file_data.startswith(b'\x89PNG'):
        return "png", file_data
    
    # JPEG → PNG
    elif file_data.startswith(b'\xFF\xD8\xFF'):
        png_data = convert_to_png(file_data, "jpg")
        return "png", png_data
    
    # GIF → PNG
    elif file_data.startswith(b'GIF87a') or file_data.startswith(b'GIF89a'):
        png_data = convert_to_png(file_data, "gif")
        return "png", png_data
    
    # WEBP → PNG
    elif file_data.startswith(b'RIFF') and b'WEBP' in file_data[:12]:
        png_data = convert_to_png(file_data, "webp")
        return "png", png_data
    
    # BMP → PNG (con validación mejorada)
    elif file_data.startswith(b'BM'):
        print(f"BMP detectado, validando header...")
        if len(file_data) >= 6:
            bmp_size = int.from_bytes(file_data[2:6], byteorder='little')
            print(f"Tamaño del BMP según header: {bmp_size} bytes")
            
            # Solo procesar si el tamaño es razonable
            if 1000 <= bmp_size <= len(file_data) and bmp_size <= 50 * 1024 * 1024:  # Max 50MB
                bmp_data = file_data[:bmp_size]
                print(f"BMP válido, convirtiendo a PNG...")
                png_data = convert_to_png(bmp_data, "bmp")
                return "png", png_data
            else:
                print(f"BMP con tamaño inválido: {bmp_size} bytes, saltando...")
                return "bin", file_data
        else:
            print("BMP con header incompleto")
            return "bin", file_data
    
    # TIFF → PNG
    elif file_data.startswith(b'II*\x00') or file_data.startswith(b'MM\x00*'):
        png_data = convert_to_png(file_data, "tiff")
        return "png", png_data
    
    # ICO → PNG
    elif file_data.startswith(b'\x00\x00\x01\x00'):
        png_data = convert_to_png(file_data, "ico")
        return "png", png_data
    
    # === DETECCIÓN DE VIDEOS EMBEBIDOS ===
    
    # Buscar MP4 embebido
    mp4_start = file_data.find(b'ftyp')
    if mp4_start != -1 and mp4_start < 20:
        print(f"MP4 embebido encontrado en posicion: {mp4_start}")
        mp4_data = file_data[mp4_start-4:]  # Incluir los 4 bytes anteriores
        print(f"MP4 válido, tamaño: {len(mp4_data)} bytes")
        return "mp4", mp4_data
    
    # === DETECCIÓN DE IMÁGENES EMBEBIDAS ===
    
    # Buscar PNG embebido
    png_start = file_data.find(b'\x89PNG')
    if png_start != -1:
        png_data = file_data[png_start:]
        return "png", png_data
    
    # Buscar JPEG embebido → PNG
    jpg_start = file_data.find(b'\xFF\xD8\xFF')
    if jpg_start != -1:
        jpg_data = file_data[jpg_start:]
        png_data = convert_to_png(jpg_data, "jpg")
        return "png", png_data
    
    # Buscar BMP embebido → PNG (con validación)
    bmp_start = file_data.find(b'BM')
    if bmp_start != -1:
        print(f"BMP embebido encontrado en posicion: {bmp_start}")
        bmp_data = file_data[bmp_start:]
        
        if len(bmp_data) >= 6:
            bmp_size = int.from_bytes(bmp_data[2:6], byteorder='little')
            print(f"Tamaño del BMP según header: {bmp_size} bytes")
            
            # Solo procesar si el tamaño es razonable
            if 1000 <= bmp_size <= len(bmp_data) and bmp_size <= 50 * 1024 * 1024:  # Max 50MB
                bmp_data = bmp_data[:bmp_size]
                print(f"BMP válido, convirtiendo a PNG...")
                png_data = convert_to_png(bmp_data, "bmp")
                return "png", png_data
            else:
                print(f"BMP embebido con tamaño inválido: {bmp_size} bytes, saltando...")
    
    # Buscar GIF embebido → PNG
    gif_start = file_data.find(b'GIF87a')
    if gif_start == -1:
        gif_start = file_data.find(b'GIF89a')
    if gif_start != -1:
        gif_data = file_data[gif_start:]
        png_data = convert_to_png(gif_data, "gif")
        return "png", png_data
    
    # Buscar WEBP embebido → PNG
    webp_start = file_data.find(b'RIFF')
    if webp_start != -1 and b'WEBP' in file_data[webp_start:webp_start+12]:
        webp_data = file_data[webp_start:]
        png_data = convert_to_png(webp_data, "webp")
        return "png", png_data
    
    # Fallback
    return "bin", file_data

def cleanup_old_files():
    """Limpia archivos antiguos (más de 1 día)"""
    try:
        current_time = time.time()
        cleaned_count = 0
        total_files = 0
        
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
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
        print(f"Descargando imagen: {image_url}")
        
        # Descargar imagen
        image_bytes = download_image_from_url(image_url)
        print(f"Imagen descargada: {len(image_bytes)} bytes")
        
        # Procesar imagen
        print("Procesando imagen...")
        img_array = load_image_from_bytes(image_bytes)
        print(f"Imagen procesada: {img_array.shape}")
        
        # Extraer datos
        print("Extrayendo datos ocultos...")
        binary_data = extract_binary_from_lsb(img_array)
        
        if not binary_data:
            return jsonify({
                "error": "No se encontraron datos ocultos en la imagen",
                "success": False
            }), 404
        
        print(f"Bits extraidos: {len(binary_data)}")
        
        # Convertir a bytes
        file_data = binary_to_bytes(binary_data)
        print(f"Bytes extraidos: {len(file_data)}")
        
        # Detectar tipo y convertir
        file_type, extracted_data = detect_file_type(file_data)
        print(f"Tipo detectado: {file_type}, tamaño: {len(extracted_data)} bytes")
        
        # Limpiar archivos antiguos
        cleaned_files = cleanup_old_files()
        
        # Crear archivo con nombre único
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        temp_filename = f"decoded_{timestamp}_{unique_id}.{file_type}"
        file_path = os.path.join(UPLOAD_FOLDER, temp_filename)
        
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
        print(f"Error en decode: {e}")
        return jsonify({
            "error": str(e),
            "success": False
        }), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Descarga archivo decodificado"""
    try:
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Archivo no encontrado"}), 404
        
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Iniciando TT-Tools API Server (VERSION FINAL)...")
    print("Endpoints disponibles:")
    print("   GET  /health - Health check")
    print("   POST /decode - Decodificar imagen (devuelve JSON)")
    print("   GET  /download/<filename> - Descargar archivo")
    print("\n Ejemplo de uso:")
    print('curl -X POST http://localhost:5000/decode -H "Content-Type: application/json" -d \'{"url": "https://example.com/image.png"}\'')
    
    app.run(host='0.0.0.0', port=5000, debug=True)
