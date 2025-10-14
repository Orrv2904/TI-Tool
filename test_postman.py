#!/usr/bin/env python3
"""
Script para probar la API localmente como lo haría Postman
"""

import requests
import json
import time

def test_api():
    base_url = "http://localhost:5000"
    
    print("Probando API localmente...")
    print("=" * 50)
    
    # 1. Health Check
    print("\n1. Probando Health Check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
        return
    
    # 2. Test con imagen de ejemplo
    print("\n2. Probando decodificacion...")
    
    # Usar una imagen de prueba (puedes cambiar esta URL)
    test_url = "https://juriolrfbcebhpkfaqws.supabase.co/storage/v1/object/public/temp-files/ComfyUI_00001_jomqp_1760414302.png"
    
    payload = {
        "url": test_url
    }
    
    try:
        print(f"   Enviando URL: {test_url}")
        response = requests.post(
            f"{base_url}/decode", 
            json=payload, 
            timeout=120,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("   Exito!")
            print(f"   File Type: {result.get('file_type')}")
            print(f"   File Size: {result.get('file_size')} bytes")
            print(f"   Download URL: {result.get('download_url')}")
            print(f"   Filename: {result.get('filename')}")
            
            # 3. Probar descarga
            print("\n3. Probando descarga...")
            download_url = result.get('download_url')
            if download_url:
                try:
                    download_response = requests.get(download_url, timeout=30)
                    print(f"   Download Status: {download_response.status_code}")
                    if download_response.status_code == 200:
                        print(f"   Archivo descargado: {len(download_response.content)} bytes")
                    else:
                        print(f"   Error en descarga: {download_response.text}")
                except Exception as e:
                    print(f"   Error descargando: {e}")
        else:
            print(f"   Error: {response.text}")
            
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_api()