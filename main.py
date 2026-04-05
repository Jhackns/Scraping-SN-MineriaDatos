"""
main.py
-------
Interfaz gráfica de usuario para el proyecto SENAMHI Data Extractor.

Construida con Flet (https://flet.dev). Ejecuta las funciones de
scraper_engine.py en hilos secundarios para que la UI nunca se congele.

Uso:
    python main.py
"""

import flet as ft
import threading
import logging
import sys
import os

# Asegurar que el directorio raíz del proyecto esté en sys.path para
# importar scraper_engine independientemente de la CWD
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scraper_engine import ejecutar_extraccion

# ---------------------------------------------------------------------------
# Constantes de diseño (paleta profesional dark-mode)
# ---------------------------------------------------------------------------

DEPARTAMENTOS = [
    "Amazonas", "Ancash", "Apurimac", "Arequipa", "Ayacucho", "Cajamarca",
    "Cusco", "Huancavelica", "Huanuco", "Ica", "Junin", "La Libertad",
    "Lambayeque", "Lima", "Loreto", "Madre de Dios", "Moquegua", "Pasco",
    "Piura", "Puno", "San Martin", "Tacna", "Tumbes", "Ucayali"
]


# Colores principales
COLOR_BG_PAGE        = "#0D1117"   # Fondo de página: negro azulado
COLOR_BG_CARD        = "#161B22"   # Fondo de tarjetas / paneles
COLOR_BG_CONSOLE     = "#0D1117"   # Fondo de la consola de log
COLOR_ACCENT         = "#1F6FEB"   # Azul GitHub Actions — botón primario
COLOR_ACCENT_HOVER   = "#388BFD"   # Azul claro en hover
COLOR_ACCENT_2       = "#238636"   # Verde éxito — botón de descarga
COLOR_ACCENT_2_HOVER = "#2EA043"
COLOR_BORDER         = "#30363D"   # Borde sutil
COLOR_TEXT_PRIMARY   = "#E6EDF3"   # Texto principal
COLOR_TEXT_SECONDARY = "#8B949E"   # Texto secundario / timestamps
COLOR_TEXT_SUCCESS   = "#3FB950"   # Verde log
COLOR_TEXT_WARNING   = "#D29922"   # Amarillo log
COLOR_TEXT_ERROR     = "#F85149"   # Rojo log
COLOR_PROGRESS_BAR   = "#1F6FEB"

FONT_MONO = "Consolas, 'Courier New', monospace"


# ---------------------------------------------------------------------------
# Handler de logging que redirige mensajes al widget de consola de Flet
# ---------------------------------------------------------------------------

class FletLogHandler(logging.Handler):
    """Envía cada registro de logging al ListView de la consola en la UI."""

    def __init__(self, agregar_linea_fn):
        super().__init__()
        self._agregar = agregar_linea_fn

    def emit(self, record: logging.LogRecord):
        msg    = self.format(record)
        nivel  = record.levelname  # DEBUG, INFO, WARNING, ERROR, CRITICAL
        self._agregar(msg, nivel)


# ---------------------------------------------------------------------------
# Aplicación principal
# ---------------------------------------------------------------------------

def main(page: ft.Page):
    # -----------------------------------------------------------------------
    # Configuración de la página
    # -----------------------------------------------------------------------
    page.title       = "SENAMHI Data Extractor"
    page.theme_mode  = ft.ThemeMode.DARK
    page.bgcolor     = COLOR_BG_PAGE
    page.padding     = 0
    page.spacing     = 0
    page.window.width        = 960
    page.window.height       = 720
    page.window.min_width    = 800
    page.window.min_height   = 600
    page.window.resizable    = True

    # Fuente personalizada (requiere flet >= 0.21; si falla, Flet usa la default)
    page.fonts = {
        "Outfit": "https://fonts.gstatic.com/s/outfit/v11/QGYyz_MVcBeNP4NjuGObqx1XmO1I4TC1C4G-EiAou6Y.woff2",
    }

    # -----------------------------------------------------------------------
    # Estado compartido (accedido desde el hilo UI y el hilo del scraper)
    # -----------------------------------------------------------------------
    _hilo_activo: dict = {"corriendo": False}   # dict mutable para pasar por referencia

    # -----------------------------------------------------------------------
    # Referencia a los controles (se definen abajo y se usan en callbacks)
    # -----------------------------------------------------------------------
    progreso_bar    = ft.ProgressBar(
        width=None,
        value=0,
        color=COLOR_PROGRESS_BAR,
        bgcolor=COLOR_BORDER,
        visible=False,
    )
    progreso_label  = ft.Text(
        value="",
        size=12,
        color=COLOR_TEXT_SECONDARY,
        visible=False,
    )

    log_listview = ft.ListView(
        expand=True,
        spacing=0,
        auto_scroll=True,
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
    )

    dd_departamento = ft.Dropdown(
        options=[ft.dropdown.Option(d) for d in DEPARTAMENTOS],
        value="Amazonas",
        width=200,
        border_color=COLOR_BORDER,
        color=COLOR_TEXT_PRIMARY,
        bgcolor=COLOR_BG_CONSOLE,
        text_size=14,
        content_padding=10,
    )

    btn_extraccion = ft.Ref[ft.ElevatedButton]()

    # -----------------------------------------------------------------------
    # Helpers de UI (thread-safe via page.update())
    # -----------------------------------------------------------------------

    def _color_para_nivel(nivel: str) -> str:
        mapa = {
            "DEBUG":    COLOR_TEXT_SECONDARY,
            "INFO":     COLOR_TEXT_PRIMARY,
            "WARNING":  COLOR_TEXT_WARNING,
            "ERROR":    COLOR_TEXT_ERROR,
            "CRITICAL": COLOR_TEXT_ERROR,
        }
        return mapa.get(nivel, COLOR_TEXT_PRIMARY)

    def agregar_linea_consola(mensaje: str, nivel: str = "INFO"):
        """Agrega una línea al log_listview y refresca la página."""
        color = _color_para_nivel(nivel)
        fila = ft.Text(
            value=mensaje,
            size=12,
            color=color,
            font_family="Consolas, Courier New",
            selectable=True,
            no_wrap=False,
        )
        log_listview.controls.append(fila)
        page.update()

    def _set_ui_ocupada(activa: bool, msg_progreso: str = ""):
        """Activa/desactiva controles durante una operación en curso."""
        _hilo_activo["corriendo"] = activa
        btn_extraccion.current.disabled = activa
        dd_departamento.disabled        = activa
        progreso_bar.visible            = activa
        progreso_label.visible          = activa and bool(msg_progreso)
        progreso_bar.value              = None if activa else 0
        progreso_label.value            = msg_progreso
        page.update()

    # -----------------------------------------------------------------------
    # Configurar logging para que todos los mensajes vayan a la consola Flet
    # -----------------------------------------------------------------------
    flet_handler = FletLogHandler(agregar_linea_consola)
    flet_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    # Adjuntar al root logger para capturar todo (incluyendo scraper_engine)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(flet_handler)

    # Redirigir también los print() al log
    class PrintRedirect:
        def __init__(self, fn): self._fn = fn
        def write(self, txt):
            if txt.strip():
                self._fn(txt.strip(), "INFO")
        def flush(self): pass

    sys.stdout = PrintRedirect(agregar_linea_consola)

    # -----------------------------------------------------------------------
    # Callbacks de los botones (se ejecutan en hilos separados)
    # -----------------------------------------------------------------------

    def _run_extraccion():
        depto = dd_departamento.value
        _set_ui_ocupada(True, f"Extrayendo y descargando datos históricos de {depto}...")
        try:
            agregar_linea_consola("═" * 60, "INFO")
            agregar_linea_consola(f"▶  Iniciando Extracción en {depto} (flujo unificado)", "INFO")
            agregar_linea_consola("═" * 60, "INFO")
            ejecutar_extraccion(depto)
            agregar_linea_consola(f"✔  Extracción completada. Revisa DatosExtraidos/{depto}/", "INFO")
        except Exception as e:
            agregar_linea_consola(f"✘  Error: {e}", "ERROR")
        finally:
            _set_ui_ocupada(False)

    def on_click_extraccion(e):
        if _hilo_activo["corriendo"]:
            return
        hilo = threading.Thread(target=_run_extraccion, daemon=True)
        hilo.start()

    def on_limpiar_consola(e):
        log_listview.controls.clear()
        page.update()

    # -----------------------------------------------------------------------
    # Construcción de la UI
    # -----------------------------------------------------------------------

    # -- Header ---------------------------------------------------------
    header = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.CLOUD_DOWNLOAD_ROUNDED,
                            size=36,
                            color=COLOR_ACCENT,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "SENAMHI Data Extractor",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_PRIMARY,
                                    font_family="Outfit",
                                ),
                                ft.Text(
                                    "Región Geográfica — Datos Históricos Meteorológicos",
                                    size=13,
                                    color=COLOR_TEXT_SECONDARY,
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),
                ft.Row(
                    controls=[
                        ft.Text("Departamento:", color=COLOR_TEXT_SECONDARY, size=14),
                        dd_departamento,
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                ft.Divider(height=1, color=COLOR_BORDER),
            ],
            spacing=16,
        ),
        padding=ft.padding.only(left=24, top=24, right=24, bottom=12),
        bgcolor=COLOR_BG_CARD,
    )

    # -- Panel de acciones ----------------------------------------------
    def _build_action_card(
        numero: str,
        titulo: str,
        descripcion: str,
        icono: str,
        color_btn: str,
        color_btn_hover: str,
        ref: ft.Ref,
        on_click,
    ) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(numero, size=28, weight=ft.FontWeight.BOLD, color=color_btn),
                        width=48,
                        alignment=ft.alignment.center,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(titulo, size=15, weight=ft.FontWeight.W_600, color=COLOR_TEXT_PRIMARY),
                            ft.Text(descripcion, size=12, color=COLOR_TEXT_SECONDARY),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        ref=ref,
                        text="Ejecutar",
                        icon=icono,
                        on_click=on_click,
                        style=ft.ButtonStyle(
                            bgcolor={
                                ft.ControlState.DEFAULT: color_btn,
                                ft.ControlState.HOVERED: color_btn_hover,
                                ft.ControlState.DISABLED: COLOR_BORDER,
                            },
                            color={
                                ft.ControlState.DEFAULT: "#FFFFFF",
                                ft.ControlState.DISABLED: COLOR_TEXT_SECONDARY,
                            },
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.padding.symmetric(horizontal=20, vertical=12),
                            elevation={"pressed": 0, "": 2},
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
            bgcolor=COLOR_BG_CARD,
            border=ft.border.all(1, COLOR_BORDER),
            border_radius=10,
            padding=ft.padding.symmetric(horizontal=20, vertical=16),
        )

    card_extraccion = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.ROCKET_LAUNCH_ROUNDED,
                        size=30,
                        color=COLOR_ACCENT,
                    ),
                    width=52,
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            "Iniciar Extracción Regional",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "Navega el mapa de la región seleccionada, abre cada estación, exporta CSV histórico (1960–hoy) "
                            "y organiza los archivos automáticamente en carpetas.",
                            size=12,
                            color=COLOR_TEXT_SECONDARY,
                        ),
                    ],
                    spacing=3,
                    expand=True,
                ),
                ft.ElevatedButton(
                    ref=btn_extraccion,
                    text="Iniciar",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    on_click=on_click_extraccion,
                    style=ft.ButtonStyle(
                        bgcolor={
                            ft.ControlState.DEFAULT:  COLOR_ACCENT,
                            ft.ControlState.HOVERED:  COLOR_ACCENT_HOVER,
                            ft.ControlState.DISABLED: COLOR_BORDER,
                        },
                        color={
                            ft.ControlState.DEFAULT:  "#FFFFFF",
                            ft.ControlState.DISABLED: COLOR_TEXT_SECONDARY,
                        },
                        shape=ft.RoundedRectangleBorder(radius=8),
                        padding=ft.padding.symmetric(horizontal=24, vertical=14),
                        elevation={"pressed": 0, "": 3},
                    ),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
        bgcolor=COLOR_BG_CARD,
        border=ft.border.all(1, COLOR_ACCENT),   # Borde azul para destacarlo
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=20, vertical=18),
    )

    panel_acciones = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "ACCIÓN",
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=COLOR_TEXT_SECONDARY,
                    style=ft.TextStyle(letter_spacing=2.0),
                ),
                card_extraccion,
                ft.Column(
                    controls=[progreso_bar, progreso_label],
                    spacing=4,
                ),
            ],
            spacing=12,
        ),
        padding=ft.padding.symmetric(horizontal=24, vertical=16),
    )

    # -- Consola de Log -------------------------------------------------
    consola_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.TERMINAL_ROUNDED, size=16, color=COLOR_TEXT_SECONDARY),
                ft.Text(
                    "Consola de Log",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=COLOR_TEXT_SECONDARY,
                    style=ft.TextStyle(letter_spacing=1.2),
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    icon_color=COLOR_TEXT_SECONDARY,
                    tooltip="Limpiar consola",
                    on_click=on_limpiar_consola,
                    icon_size=18,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        padding=ft.padding.only(left=16, top=10, right=8, bottom=10),
        bgcolor=COLOR_BG_CARD,
        border=ft.border.only(
            top=ft.BorderSide(1, COLOR_BORDER),
            bottom=ft.BorderSide(1, COLOR_BORDER),
        ),
    )

    panel_consola = ft.Container(
        content=ft.Column(
            controls=[
                consola_header,
                ft.Container(
                    content=log_listview,
                    bgcolor=COLOR_BG_CONSOLE,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
        expand=True,
        border=ft.border.all(1, COLOR_BORDER),
        border_radius=10,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )

    consola_wrapper = ft.Container(
        content=panel_consola,
        padding=ft.padding.only(left=24, top=0, right=24, bottom=24),
        expand=True,
    )

    # -- Footer ---------------------------------------------------------
    footer = ft.Container(
        content=ft.Text(
            "SENAMHI Data Extractor · Automatización con undetected-chromedriver · Flet UI",
            size=11,
            color=COLOR_TEXT_SECONDARY,
            text_align=ft.TextAlign.CENTER,
        ),
        padding=ft.padding.symmetric(vertical=8),
        alignment=ft.alignment.center,
    )

    # -- Layout principal -----------------------------------------------
    page.add(
        ft.Column(
            controls=[
                header,
                panel_acciones,
                consola_wrapper,
                footer,
            ],
            spacing=0,
            expand=True,
        )
    )

    # Mensaje de bienvenida en la consola
    agregar_linea_consola("┌─────────────────────────────────────────────────────────┐", "INFO")
    agregar_linea_consola("│   SENAMHI Data Extractor — Listo para operar            │", "INFO")
    agregar_linea_consola("│   Presiona 'Iniciar' para comenzar la extracción        │", "INFO")
    agregar_linea_consola("│   El navegador se abrirá automáticamente                │", "INFO")
    agregar_linea_consola("└─────────────────────────────────────────────────────────┘", "INFO")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ft.app(target=main)
