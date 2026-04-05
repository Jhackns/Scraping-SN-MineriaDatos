# SENAMHI Data Extractor 🚀

Automatización profesional para la extracción masiva de datos históricos meteorológicos de las estaciones del SENAMHI (Perú). Esta aplicación utiliza una arquitectura de **scraping de bajo nivel** con `undetected-chromedriver` para navegar el mapa regional, manejar iframes anidados e iterar automáticamente por todos los periodos disponibles desde 1960 hasta la actualidad.

**TAREA-LORETO:** Releases (v1.0.0-Loreto-Dataset) comprimido en .zip → https://github.com/Jhackns/Scraping-SN-MineriaDatos/releases/tag/Loreto-dataset

## 🛠️ Requisitos Previos

Antes de comenzar, asegúrate de tener instalado:
*   **Python 3.10 o superior**
*   **Google Chrome** (recomentamos la última versión estable)

## 📦 Instalación

1.  Clona o descarga este repositorio en tu máquina local.
2.  Abre una terminal en la carpeta del proyecto.
3.  Instala todas las dependencias necesarias ejecutando el siguiente comando:

```bash
pip install -r requirements.txt
```

## 🚀 Instrucciones de Uso

Sigue estos pasos para iniciar la descarga de datos:

1.  **Ejecutar la App:** Inicia la interfaz gráfica ejecutando el archivo principal:
    ```bash
    python main.py
    ```
2.  **Seleccionar Región:** En la parte superior de la ventana, utiliza el desplegable **"Departamento"** para elegir la región que deseas procesar (ej. Amazonas, Loreto, Lima).
    *   *Nota: "Lima" incluye las estaciones de Lima y Callao automáticamente.*
3.  **Iniciar Extracción:** Haz clic en el botón azul **"Iniciar"**.
    *   Se abrirá una ventana automatizada de Chrome. **No la cierres ni interactúes con ella** mientras el bot trabaja.
    *   El bot navegará por el mapa y abrirá cada estación una por una.
4.  **Ver el Progreso:** Puedes monitorear cada descarga en tiempo real a través de la **Consola de Log** integrada en la aplicación.
5.  **Resultados:** Los archivos CSV se descargarán, validarán y organizarán automáticamente en carpetas dentro del directorio:
    `DatosExtraidos / [Departamento] / Estacion_[Código] / data / [Fecha]_Estacion_[Código].csv`

## 🧠 Características Técnicas

*   **ETL Ready:** Los archivos se renombran automáticamente con un formato estandarizado listo para análisis de datos.
*   **Manejo de Errores PHP:** Detecta automáticamente caídas del servidor del SENAMHI ("Fatal error") y salta a la siguiente fecha para no interrumpir el flujo.
*   **Re-enganche de Sesión:** Gestión robusta de `iframes` para evitar que la sesión expire o el DOM se vuelva obsoleto durante la recarga de tablas.
*   **Validación de Datos:** Filtra archivos corruptos o vacíos que el servidor envía ocasionalmente como HTML.

---


### 🛠️ ¿Por qué esta solución?

**El Problema:** El sitio web del SENAMHI presenta una estructura técnica compleja basada en **iframes anidados de hasta 3 niveles**, controles de formulario que pierden el foco al recargar tablas y bloqueos automáticos ante comportamientos no humanos (captcha/detección de bots). La automatización convencional de clicks falla ante estos elementos.

**La Solución:** Implementamos una **arquitectura de navegación de 3 niveles** (Mapa → Estación → Datos) utilizando `undetected-chromedriver` para evadir huellas de bot. Utilizamos inyección de JavaScript directa (`MouseEvent` y eventos `change` nativos) para interactuar con los elementos invisibles o bloqueados por otros componentes del mapa.

