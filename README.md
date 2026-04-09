# SENAMHI Data Extractor (High-Speed Memory Edition) 🚀

Automatización de grado ingeniería para la extracción masiva de datos históricos meteorológicos del SENAMHI (Perú). Esta versión utiliza una arquitectura avanzada de **Volcado de Memoria Leaflet** y **Navegación Directa por Endpoint**, reduciendo los tiempos de extracción de horas a minutos.

##Releases
### Dataset comprimidos (dataset 4 regiones Senamhi) en .zip: 
1. Amazonas: https://github.com/Jhackns/Scraping-SN-MineriaDatos/releases/tag/Dataset

2. Ucayali: https://github.com/Jhackns/Scraping-SN-MineriaDatos/releases/tag/ucayaly-dataset

3. Madre de Dios: https://github.com/Jhackns/Scraping-SN-MineriaDatos/releases/tag/madre-de-dios-dataset

4. Loreto: https://github.com/Jhackns/Scraping-SN-MineriaDatos/releases/tag/Loreto-dataset

## 🛠️ Requisitos Previos

*   **Python 3.10+**
*   **Google Chrome** (última versión estable)
*   **estaciones_peru.json**: Catálogo local para el mapeo descriptivo de estaciones.

## 📦 Instalación

```bash
pip install -r requirements.txt
```

## 🚀 Instrucciones de Uso

1.  **Ejecutar la App:** `python main.py`
2.  **Seleccionar Región:** Elige el departamento deseado. El sistema ajusta automáticamente los Slugs (ej: `Madre de Dios` -> `madre-de-dios`).
3.  **Sistema de Caché Inteligente:** Si ya has descargado estaciones previamente, el bot las identificará y lanzará un mensaje de **[SALTO]**, omitiendo la descarga en milisegundos para enfocarse solo en los datos faltantes o nuevos.
4.  **Monitoreo:** No cierres la ventana de Chrome; permite que el driver gestione el Captcha de Cloudflare si es necesario (el sistema tiene un timeout de espera de 60s).

## 📂 Estructura de Datos (ETL Ready)

Los datos se organizan estrictamente en 4 categorías maestras siguiendo la lógica oficial del SENAMHI:
`DatosExtraidos / [Departamento] / [Categoría_Tipo] / [Nombre_Estacion] / data / [CSV]`

Las categorías son:
*   Estación Meteorológica Convencional
*   Estación Meteorológica Automatica
*   Estación Hidrológica Convencional
*   Estación Hidrológica Automatica

## 🧠 Arquitectura Técnica Superior

### El Problema (Legado)
El método visual tradicional (clics en el mapa) fallaba debido a la carga de **iframes anidados de 3 niveles**, renderizado lento de Leaflet y la detección agresiva de bots de Cloudflare que bloqueaba interacciones físicas.

### La Solución (Actual)
*   **Leaflet Memory Dump:** En lugar de buscar y hacer clic en marcadores, el script inyecta JS para leer la variable `window.map._layers` y extraer los metadatos de todas las estaciones instantáneamente.
*   **Direct-to-Popup Strategy:** Navegamos directamente al endpoint `map_red_graf.php` usando los parámetros capturados en memoria. Esto elimina el 100% de la carga visual del mapa global.
*   **Contexto Persistente:** Utilizamos un `user-data-dir` (PerfilChrome) para guardar sesiones y evadir defensas de Cloudflare.
*   **Parche de Estado Nativo:** Detectamos dinámicamente si la estación es `REAL`, `DIFERIDO` o `AUTOMATICA` directamente del código del servidor, evitando los cierres inesperados de conexión por parámetros inválidos.

---
*Desarrollado para la automatización masiva y eficiente de minería de datos.*
