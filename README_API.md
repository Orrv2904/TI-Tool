# TT-Tools API Server

API REST para decodificar imágenes con archivos ocultos usando esteganografía LSB.

## Inicio Rápido

### 1. Instalar dependencias
```bash
pip install -r requirements_api.txt
```

### 2. Ejecutar servidor
```bash
python api_server.py
```

### 3. Probar API
```bash
curl -X POST http://localhost:5000/decode \
  -H "Content-Type: application/json" \
  -d '{"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="}'
```

## Endpoints

### GET /health
Verificar estado del servidor
```json
{
  "status": "ok",
  "service": "TT-Tools API",
  "version": "1.0.0"
}
```

### POST /decode
Decodificar imagen y devolver metadatos + archivo en base64
```json
{
  "url": "https://example.com/image.png",
  "output_name": "archivo_extraido"
}
```

**Respuesta:**
```json
{
  "success": true,
  "file_type": "mp4",
  "file_size": 1234567,
  "file_data": "base64_encoded_data",
  "message": "Archivo decodificado exitosamente"
}
```

### POST /decode/direct
Decodificar imagen y devolver archivo directamente
```json
{
  "url": "https://example.com/image.png"
}
```

**Respuesta:** Archivo binario directo

## Integración con n8n

1. **Crear nodo HTTP Request**
2. **Método:** POST
3. **URL:** `http://localhost:5000/decode`
4. **Headers:** `Content-Type: application/json`
5. **Body:** JSON con la URL de la imagen

## Tipos de archivo soportados

- **Imágenes:** PNG, JPG, BMP
- **Videos:** MP4, AVI, MOV
- **Audio:** WAV, MP3
- **Documentos:** PDF, TXT
- **Archivos binarios:** Cualquier tipo

## Despliegue

### Local
```bash
python api_server.py
```

### Docker
```bash
docker build -t tt-tools-api .
docker run -p 5000:5000 tt-tools-api
```

### Render
```bash
# Subir a GitHub y conectar con Render
# El archivo render.yaml ya está configurado
```
