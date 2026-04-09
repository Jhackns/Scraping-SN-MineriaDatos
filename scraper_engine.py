"""
scraper_engine.py
-----------------
Motor de scraping SENAMHI — Estrategia: Extractor de Alta Velocidad.
Evade Cloudflare y DOM timeouts usando Volcado de Memoria Leaflet y requests directos a Level 2.
"""

import os
import time
import random
import shutil
import logging
import json
import re
import urllib.parse
from datetime import datetime

import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------------------------------------------------------
# Configuración Global
# ---------------------------------------------------------------------------

PROJECT_ROOT    = os.path.dirname(os.path.abspath(__file__))
DATOS_EXTRAIDOS = os.path.join(PROJECT_ROOT, "DatosExtraidos")
JSON_ESTACIONES = os.path.join(PROJECT_ROOT, "estaciones_peru.json")

# Selectores
SEL_IFRAME_MAP  = "iframe[src*='mapa-estaciones']"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Diccionario para nombres descriptivos
DICCIONARIO_CATE = {
    "CO": "Convencional",
    "PLU": "Pluviometrica",
    "HLM": "Hidrometrica",
    "HLG": "Hidrologica",
    "EAMA": "Automatica",
    "PE": "Proposito_Especifico",
    "MAP": "Meteorologica_Agricola"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_driver(ruta_descarga: str) -> uc.Chrome:
    os.makedirs(ruta_descarga, exist_ok=True)
    driver_path = ChromeDriverManager().install()
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    
    # REGLA 1: Contexto Persistente para mantener cookies de CF (Cloudflare)
    perfil_dir = os.path.join(PROJECT_ROOT, "PerfilChrome")
    options.add_argument(f"--user-data-dir={perfil_dir}")
    
    prefs = {
        "download.default_directory": os.path.abspath(ruta_descarga),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    return uc.Chrome(driver_executable_path=driver_path, options=options, use_subprocess=True)

def _cargar_catalogo_json() -> dict:
    if not os.path.exists(JSON_ESTACIONES):
        log.error("Archivo estaciones_peru.json no encontrado.")
        return {}
    with open(JSON_ESTACIONES, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["cod"]: item for item in data if "cod" in item}

def _obtener_nombre_descriptivo(cate: str, ico: str) -> str:
    es_automatica = cate.upper() in ["EAMA", "EHA"]
    if ico.upper() == "H":
        return "Estación Hidrológica Automatica" if es_automatica else "Estación Hidrológica Convencional"
    else:
        return "Estación Meteorológica Automatica" if es_automatica else "Estación Meteorológica Convencional"

def _snapshot_csvs(carpeta: str) -> set:
    if not os.path.exists(carpeta): return set()
    return {f for f in os.listdir(carpeta) if f.lower().endswith(".csv") and not f.endswith(".crdownload")}

def _esperar_csv_nuevo(carpeta: str, snapshot_antes: set, timeout: int = 45) -> str | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        actuales = _snapshot_csvs(carpeta)
        nuevos = actuales - snapshot_antes
        if nuevos:
            lista = sorted(nuevos, key=lambda f: os.path.getmtime(os.path.join(carpeta, f)), reverse=True)
            return os.path.join(carpeta, lista[0])
        time.sleep(1)
    return None

def _es_csv_valido(ruta: str) -> bool:
    try:
        if not os.path.exists(ruta): return False
        with open(ruta, 'r', encoding='latin-1', errors='ignore') as f:
            head = f.read(200).lower()
            if "<html" in head or "<doctype" in head:
                return False
        return os.path.getsize(ruta) > 200
    except:
        return False

# ---------------------------------------------------------------------------
# Motor Principal (Alta Velocidad + Extracción de Memoria)
# ---------------------------------------------------------------------------

def ejecutar_extraccion(depto_input: str) -> None:
    # Preparar el directorio de trabajo
    depto_nombre = depto_input.strip()
    depto_slug = depto_nombre.lower().replace(" ", "-")
    ruta_trabajo = os.path.join(DATOS_EXTRAIDOS, depto_nombre.title().replace("/", "_"))
    
    url_mapa = f"https://www.senamhi.gob.pe/?p=estaciones&dp={depto_slug}"
    catalogo = _cargar_catalogo_json()
    
    driver = None
    try:
        driver = _crear_driver(ruta_trabajo)
        
        # 1. VISITAR MAPA GENERAL PARA DESCARGAR LISTA DESDE LEAFLET
        log.info(f"Fase 1: Reconocimiento (Volcado Leaflet) -> {url_mapa}")
        driver.get(url_mapa)
        
        # Retraso Humano de WAF
        time.sleep(random.uniform(3.0, 5.5))
        
        # Entramos a Nivel 1
        iframe_mapa = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_IFRAME_MAP)))
        driver.switch_to.frame(iframe_mapa)
        
        # Esperamos que cargue algún marker para asegurar que Leaflet esté vivo
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "img.leaflet-marker-icon")))

        # Inyectamos script mágico para volcar memoria de local vars de Leaflet
        script_dump = r"""
            let mapVar = window.map || window.mapa || Object.values(window).find(v => v && v._layers);
            if(!mapVar) return [];
            let layers = Object.values(mapVar._layers);
            let markers = layers.filter(l => l.options && l.options.icon && l._popup);
            return markers.map(m => {
                let html = m._popup._content;
                let match = html.match(/map_red_graf\.php\?([^"']+)/);
                if(match) {
                    return match[1]; // Return query string
                }
                return null;
            }).filter(u => u !== null);
        """
        queries_estaciones = driver.execute_script(script_dump)
        driver.switch_to.default_content()

        if not queries_estaciones:
            log.warning("No se pudo extraer data de memoria Leaflet. Abortando extraccción.")
            return
            
        total_st = len(queries_estaciones)
        log.info(f"¡Volcado Exitoso! Se detectaron {total_st} estaciones. Pasando a Fase 2 (Navegación Directa).")

        # 2. FASE DIRECTA OMITIENDO MAPA GLOBAL
        for i, query_string in enumerate(queries_estaciones):
            # Parseamos la info desde la query obtenida
            params = urllib.parse.parse_qs(query_string)
            cod_estacion = params.get('cod', [''])[0]
            cate_estacion = params.get('cate', [''])[0]
            tipo_ico = params.get('tipo_esta', [''])[0]
            cod_old = params.get('cod_old', [''])[0]
            estado_estacion = params.get('estado', [''])[0]

            if not cod_estacion:
                continue

            # REGLA 4: Respaldo de Estructura de Datos
            info_json = catalogo.get(cod_estacion)
            if info_json:
                nombre_carpeta_tipo = _obtener_nombre_descriptivo(info_json["cate"], info_json["ico"])
                nombre_real = info_json.get("nom", f"Estacion_{cod_estacion}").replace("/", "-")
            else:
                if cate_estacion and tipo_ico:
                    nombre_carpeta_tipo = _obtener_nombre_descriptivo(cate_estacion, tipo_ico)
                else:
                    nombre_carpeta_tipo = "Tipo_Desconocido"
                nombre_real = f"Estacion_{cod_estacion}"

            # ---------------------------------------------------------
            # MEGA MEJORA: Sistema de Caché (Saltear Descargadas)
            # ---------------------------------------------------------
            ruta_estacion_data = os.path.join(ruta_trabajo, nombre_carpeta_tipo, nombre_real, "data")
            if os.path.exists(ruta_estacion_data):
                csvs_previos = [f for f in os.listdir(ruta_estacion_data) if f.endswith(".csv")]
                if len(csvs_previos) > 0:
                    log.info(f"[{i+1}/{total_st}] [SALTO] La estación {nombre_real} ya tiene {len(csvs_previos)} CSVs. Omitiendo...")
                    continue
            # ---------------------------------------------------------


            # REGLA 1 (Parcheada): La trampa del diferido
            # SENAMHI proporciona el estado EN SU PROPIO SCRIPT de Leaflet. Forzar REAL crashéaba Convencionales
            # y forzar DIFERIDO crashéaba Automáticas. Utilizaremos el nativo de Leaflet.
            cate_usar = info_json["cate"] if info_json else cate_estacion
            estado_seguro = estado_estacion if estado_estacion else ("AUTOMATICA" if cate_usar.upper() in ["EAMA", "EHA"] else "REAL")

            # REGLA 3: Codificación de URL Limpia
            parametros_limpios = {
                'cod': cod_estacion,
                'estado': estado_seguro,
                'tipo_esta': info_json["ico"] if info_json else tipo_ico,
                'cate': cate_usar,
                'cod_old': info_json["cod_old"] if info_json and "cod_old" in info_json else cod_old
            }
            url_directa = "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/map_red_graf.php?" + urllib.parse.urlencode(parametros_limpios)

            log.info(f"[{i+1}/{total_st}] Extrayendo -> {nombre_real} (Tipo: {nombre_carpeta_tipo})")

            # Retraso Humano de WAF (REGLA 2)
            time.sleep(random.uniform(3.0, 5.5))
            
            # Saltamos directo a Nivel 2!
            driver.get(url_directa)
            
            try:
                # Omitimos Nivel 1. Ahora el origen de página es el Nivel 2.
                # Aumentamos el Timeout a 60 segundos para dar tiempo a CF Captcha o Red Lenta
                btn_tabla = WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Tabla')]")))
                driver.execute_script("arguments[0].click();", btn_tabla)
                time.sleep(1.5)
                
                # Extraemos meses historicos
                select_filtro = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "CBOFiltro")))
                opciones = driver.find_elements(By.CSS_SELECTOR, "#CBOFiltro option")
                fechas = [op.get_attribute("value").strip() for op in opciones if op.get_attribute("value").strip().isdigit()]
                
                if not fechas:
                    log.warning(f"    ✗ Estación {cod_estacion} sin historial. Saltando.")
                    continue
                    
                log.info(f"    Meses a procesar: {len(fechas)}")
                
                for fecha in fechas:
                    try:
                        select_f = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "CBOFiltro")))
                        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));", select_f, fecha)
                        
                        # Retraso post-filtro
                        time.sleep(2)
                        
                        # "Re-enganche Light" (No interviene Nivel 1)
                        driver.switch_to.default_content()
                        
                        # Oprimimos la tabla de nuevo para seguridad si el script DOM reseteó tabs
                        try:
                            t_btn = driver.find_element(By.XPATH, "//a[contains(text(),'Tabla')]")
                            driver.execute_script("arguments[0].click();", t_btn)
                            time.sleep(1)
                        except: pass
                        
                        # Bajamos a Nivel 3 (Datos)
                        iframe_cont = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "contenedor")))
                        driver.switch_to.frame(iframe_cont)
                        
                        if "Fatal error:" in driver.page_source or "TypeError" in driver.page_source:
                            log.warning(f"        [FAIL] Servidor PHP rehusó procesar {fecha}.")
                            driver.switch_to.default_content()
                            continue
                            
                        # REGLA 2: Límite de Velocidad Exportación
                        time.sleep(random.uniform(3.0, 5.5))
                        
                        snapshot = _snapshot_csvs(ruta_trabajo)
                        driver.execute_script("document.getElementById('export2')?.click();")
                        
                        archivo = _esperar_csv_nuevo(ruta_trabajo, snapshot)
                        if archivo:
                            ruta_final = os.path.join(ruta_trabajo, nombre_carpeta_tipo, nombre_real, "data")
                            os.makedirs(ruta_final, exist_ok=True)
                            destino = os.path.join(ruta_final, f"{fecha}_Estacion_{cod_estacion}.csv")
                            shutil.move(archivo, destino)
                            log.info(f"        ✔ {fecha} capturado.")
                        else:
                            log.warning(f"        ✗ {fecha} timeout descarga.")
                            
                        driver.switch_to.default_content()
                    except Exception as loop_e:
                        log.error(f"        ✗ Excepción en iteración fecha {fecha}: {loop_e}")
                        driver.switch_to.default_content()

            except Exception as e:
                log.error(f"✗ Fallo rotundo en acceso a {cod_estacion}: {e}")
                continue

    except Exception as general_e:
        log.critical(f"Error Fatal General: {general_e}")
    finally:
        if driver:
            driver.quit()
        log.info("Operaciones finalizadas.")
