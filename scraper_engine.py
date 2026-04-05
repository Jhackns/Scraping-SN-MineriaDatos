"""
scraper_engine.py
-----------------
Motor de scraping SENAMHI — Estrategia: Navegación Orgánica + Iteración de Años.
"""

import os
import re
import time
import random
import shutil
import logging
import pandas as pd
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

# Selectores
SEL_IFRAME_MAP  = "iframe[src*='mapa-estaciones']"
SEL_MARKER      = "img.leaflet-marker-icon"
SEL_POPUP       = "div.leaflet-popup-content"
SEL_POPUP_CLOSE = "a.leaflet-popup-close-button"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_driver(ruta_descarga: str) -> uc.Chrome:
    os.makedirs(ruta_descarga, exist_ok=True)
    driver_path = ChromeDriverManager().install()
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    
    prefs = {
        "download.default_directory": os.path.abspath(ruta_descarga),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    return uc.Chrome(driver_executable_path=driver_path, options=options, use_subprocess=True)

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
# Motor Principal (Estructura de 3 Niveles)
# ---------------------------------------------------------------------------

def ejecutar_extraccion(depto_input: str) -> None:
    """
    Motor de extracción genérico para cualquier departamento del SENAMHI.
    """
    depto_nombre = depto_input.strip()
    depto_slug = depto_nombre.lower().replace(" ", "%20")
    ruta_trabajo = os.path.join(DATOS_EXTRAIDOS, depto_nombre.title().replace("/", "_"))
    url_final = f"https://www.senamhi.gob.pe/?p=estaciones&dp={depto_slug}"
    
    driver = None
    try:
        driver = _crear_driver(ruta_trabajo)
        log.info(f"Navegando a {url_final}")
        driver.get(url_final)
        
        time.sleep(5) # Carga inicial
        
        # NIVEL 1 (Mapa)
        iframe_mapa = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_IFRAME_MAP)))
        driver.switch_to.frame(iframe_mapa)
        
        marcadores = WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, SEL_MARKER)))
        total = len(marcadores)
        log.info(f"Detectadas {total} estaciones en {depto_nombre}.")

        for i in range(total):
            try:
                marcadores = driver.find_elements(By.CSS_SELECTOR, SEL_MARKER)
                if i >= len(marcadores): break
                marker = marcadores[i]
                
                log.info(f"[{i+1}/{total}] Abriendo marcador (MouseEvent JS)...")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", marker)
                time.sleep(0.5)
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('click', {view: window, bubbles: true, cancelable: true}));",
                    marker
                )
                
                # NIVEL 2 (Popup)
                popup = WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.CSS_SELECTOR, SEL_POPUP)))
                iframe_p = WebDriverWait(popup, 10).until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
                driver.switch_to.frame(iframe_p)
                
                btn_tabla = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Tabla')]")))
                driver.execute_script("arguments[0].click();", btn_tabla)
                time.sleep(2)
                
                # EXTRACCIÓN DE FECHAS
                select_filtro = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "CBOFiltro")))
                opciones = driver.find_elements(By.CSS_SELECTOR, "#CBOFiltro option")
                fechas = [op.get_attribute("value").strip() for op in opciones if op.get_attribute("value").strip().isdigit()]
                
                if not fechas:
                    log.warning("    ✗ Estación sin historial numérico.")
                    driver.switch_to.default_content()
                    driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, SEL_IFRAME_MAP))
                    driver.execute_script("document.querySelector('a.leaflet-popup-close-button')?.click();")
                    continue

                cod_estacion = driver.execute_script("return document.getElementById('estaciones')?.value || '';")
                if not cod_estacion: cod_estacion = f"cod_{i+1}"
                
                log.info(f"    Historial: {len(fechas)} meses.")

                # ITERACIÓN ETL
                for fecha in fechas:
                    log.info(f"      -> {fecha}")
                    try:
                        select_f = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "CBOFiltro")))
                        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));", select_f, fecha)
                        time.sleep(5)
                        
                        # RE-ENGANCHE
                        driver.switch_to.default_content()
                        driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_IFRAME_MAP))))
                        driver.switch_to.frame(WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "iframe"))))
                        
                        btn_t = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Tabla')]")))
                        driver.execute_script("arguments[0].click();", btn_t)
                        time.sleep(2)
                        
                        # NIVEL 3 (Datos)
                        iframe_cont = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "contenedor")))
                        driver.switch_to.frame(iframe_cont)
                        
                        if "Fatal error:" in driver.page_source or "TypeError" in driver.page_source:
                            log.warning("        [FAIL] Error de servidor PHP.")
                            driver.switch_to.parent_frame()
                            continue
                        
                        snapshot = _snapshot_csvs(ruta_trabajo)
                        driver.execute_script("document.getElementById('export2').click();")
                        
                        archivo = _esperar_csv_nuevo(ruta_trabajo, snapshot)
                        if archivo:
                            ruta_final = os.path.join(ruta_trabajo, f"Estacion_{cod_estacion}", "data")
                            os.makedirs(ruta_final, exist_ok=True)
                            destino = os.path.join(ruta_final, f"{fecha}_Estacion_{cod_estacion}.csv")
                            shutil.move(archivo, destino)
                            log.info(f"        ✔ Capturado.")
                        
                        driver.switch_to.parent_frame()
                    except Exception as e:
                        log.error(f"        ✗ Error en fecha {fecha}: {e}")
                        driver.switch_to.default_content()
                        driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, SEL_IFRAME_MAP))
                        driver.switch_to.frame(driver.find_element(By.TAG_NAME, "iframe"))

                # CERRAR
                driver.switch_to.default_content()
                driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, SEL_IFRAME_MAP))
                driver.execute_script("document.querySelector('a.leaflet-popup-close-button')?.click();")
                time.sleep(1)

            except Exception as e:
                log.error(f"Error Estación {i+1}: {e}")
                try: 
                    driver.switch_to.default_content()
                    driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, SEL_IFRAME_MAP))
                    driver.execute_script("document.querySelector('a.leaflet-popup-close-button')?.click();")
                except: pass

    except Exception as e:
        log.critical(f"Error Fatal: {e}")
    finally:
        if driver: driver.quit()
        log.info("Proceso terminado.")
