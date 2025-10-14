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

def detect_file_type(file_data):
    """Detecta tipo de archivo"""
    # MP4 - buscar ftyp en los primeros bytes
    if b'ftyp' in file_data[:20]:
        return "mp4"
    elif file_data.startswith(b'\x89PNG'):
        return "png"
    elif file_data.startswith(b'\xFF\xD8\xFF'):
        return "jpg"
    elif file_data.startswith(b'RIFF') and b'AVI' in file_data[:20]:
        return "avi"
    elif file_data.startswith(b'\x1a\x45\xdf\xa3'):
        return "mkv"
    elif file_data.startswith(b'ID3') or file_data.startswith(b'\xff\xfb'):
        return "mp3"
    elif file_data.startswith(b'RIFF') and b'WAVE' in file_data[:20]:
        return "wav"
    else:
        return "bin"

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
        file_type = detect_file_type(file_data)
        
        # Crear directorio de salida si no existe
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Crear archivo con nombre único
        temp_filename = f"{output_name}_{uuid.uuid4().hex[:8]}.{file_type}"
        file_path = os.path.join(output_dir, temp_filename)
        
        # Guardar archivo
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        # Obtener la URL base del request
        base_url = request.url_root.rstrip('/')
        download_url = f"{base_url}/download/{temp_filename}"
        
        return jsonify({
            "success": True,
            "file_type": file_type,
            "file_size": len(file_data),
            "download_url": download_url,
            "filename": temp_filename,
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
        file_type = detect_file_type(file_data)
        
        # Crear directorio de salida si no existe
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Crear archivo con nombre único
        temp_filename = f"decoded_{uuid.uuid4().hex[:8]}.{file_type}"
        file_path = os.path.join(output_dir, temp_filename)
        
        # Guardar archivo
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
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
