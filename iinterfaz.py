"""
StrangerTEC Morse Translator - Interfaz Gráfica PC 
CE-1104 Fundamentos de Sistemas Computacionales
Instituto Tecnológico de Costa Rica

Interfaz Tkinter para comunicación con la maqueta física (Raspberry Pi Pico W)
y gestión del juego de dos jugadores en código Morse.

Uso:
    python strangertec_gui_simple.py

Dependencias: tkinter (stdlib), serial (pyserial), threading, json, random, time
"""

import tkinter as tk
from tkinter import ttk, messagebox
import random
import time
import json
import socket
import threading
from datetime import datetime


# ─────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────

# Paleta de colores simple (fondo claro, acentos básicos)
COLORES = {
    "fondo":       "#2B0202",   
    "texto":       "#FFFFFF",   
    "led_on":      "#ffcc00",   # amarillo para LED encendido
    "led_off":     "#cccccc",   # gris para LED apagado
    "puntaje_a":   "#1155cc",   # azul jugador A
    "puntaje_b":   "#cc3311",   # rojo jugador B
    "verde":       "#228833",   # verde para confirmar
    "boton":       "#dddddd",   # gris botón normal
}

# Tabla Morse del proyecto (según convención del enunciado)
TABLA_MORSE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',
    'E': '.',     'F': '..-.',  'G': '--.',   'H': '....',
    'I': '..',    'J': '.---',  'K': '-.-',   'L': '.-..',
    'M': '--',    'N': '-.',    'O': '---',   'P': '.--.',
    'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',
    'Y': '-.--',  'Z': '--..',
    '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..',
    '9': '----.', '0': '-----',
    '+': '.-.-.',  '-': '-....-',
    ' ': '/'
}
MORSE_INVERSO = {v: k for k, v in TABLA_MORSE.items()}

# Frases predefinidas (máx 16 caracteres, según enunciado)
FRASES_PREDEFINIDAS = [
    "SOS",
    "SI",
    "NO",
    "HOLA",
    "TEC 2026",
    "MORSE 1+2",
    "ABRIR PORTAL",
    "WILL BYERS",
    "3+4-1",
    "STRANGER TEC",
]

# Temporización Morse (según enunciado)
UNIDAD_A = 0.2  # segundos
UNIDAD_B = 0.3  # segundos

# Distribución del panel de LEDs (3 filas, según enunciado)
FILA_LED_1 = list("ACEGIKMOQSUWY")
FILA_LED_2 = list("BDFHJLNPRTVXZ")
FILA_LED_3 = list("0123456789-+")


# ─────────────────────────────────────────────
#  UTILIDADES MORSE
# ─────────────────────────────────────────────

def texto_a_morse(texto: str) -> str:
    """Convierte texto plano a código Morse."""
    resultado = []
    for caracter in texto.upper():
        if caracter in TABLA_MORSE:
            resultado.append(TABLA_MORSE[caracter])
        elif caracter == ' ':
            resultado.append('/')
    return ' '.join(resultado)


def morse_a_texto(morse: str) -> str:
    """Convierte código Morse a texto plano."""
    palabras = morse.strip().split(' / ')
    resultado = []
    for palabra in palabras:
        for codigo in palabra.split():
            resultado.append(MORSE_INVERSO.get(codigo, '?'))
    return ''.join(resultado)


def calcular_puntaje(original: str, intento: str) -> tuple[int, int]:
    """
    Compara la frase original con el intento del jugador.
    Devuelve (caracteres_correctos, total_caracteres).
    """
    orig = original.upper().replace(' ', '')
    att  = intento.upper().replace(' ', '')
    correctos = sum(1 for a, b in zip(orig, att) if a == b)
    total = max(len(orig), len(att)) if max(len(orig), len(att)) > 0 else 1
    return correctos, total


# ─────────────────────────────────────────────
#  COMUNICACIÓN WiFi (reemplaza al Serial USB)
# ─────────────────────────────────────────────

class GestorSerial:
    """
    Gestiona la comunicación WiFi con la Raspberry Pi Pico W.
    Escucha en un puerto TCP; la Raspberry se conecta y envía letras.
    La interfaz nunca se congela: el servidor corre en un hilo daemon.
    """

    PUERTO_ESCUCHA = 8001   # debe coincidir con SERVER_PORT de la Raspberry

    def __init__(self, al_recibir_datos=None):
        self.conexion   = None   # socket del cliente (Raspberry)
        self.corriendo  = False
        self.hilo       = None
        self.al_recibir = al_recibir_datos  # callback(str)
        self._servidor  = None   # socket servidor TCP

    def listar_puertos(self):
        """Compatibilidad: retorna lista vacía (no se usan puertos COM)."""
        return []

    def conectar(self, puerto: str = "") -> bool:
        """
        Abre el servidor TCP y espera conexión de la Raspberry en un hilo.
        El parámetro 'puerto' se ignora (se usa PUERTO_ESCUCHA fijo).
        """
        try:
            self._servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._servidor.bind(("0.0.0.0", self.PUERTO_ESCUCHA))
            self._servidor.listen(1)
            self._servidor.settimeout(1.0)   # timeout para poder detener el hilo limpiamente
            self.corriendo = True
            self.hilo = threading.Thread(target=self._bucle_lectura, daemon=True)
            self.hilo.start()
            print(f"[WiFi] Servidor escuchando en puerto {self.PUERTO_ESCUCHA}...")
            return True
        except Exception as e:
            print(f"[WiFi] Error al iniciar servidor: {e}")
            return False

    def desconectar(self):
        """Cierra el servidor y la conexión con la Raspberry."""
        self.corriendo = False
        if self.conexion:
            try:
                self.conexion.close()
            except Exception:
                pass
        if self._servidor:
            try:
                self._servidor.close()
            except Exception:
                pass

    def enviar(self, datos: str):
        """Envía una cadena a la Raspberry (si hay conexión activa)."""
        if self.conexion:
            try:
                self.conexion.sendall((datos + '\n').encode())
            except Exception as e:
                print(f"[WiFi] Error al enviar: {e}")

    # Caracteres válidos que puede enviar la Raspberry como letra Morse
    _CHARS_VALIDOS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-")

    def _bucle_lectura(self):
        """
        Hilo daemon: acepta la conexión de la Raspberry y lee datos.
        Nunca bloquea la interfaz gráfica.
        Acumula datos en un buffer y procesa línea por línea para evitar
        que paquetes concatenados o ruidos de conexión se interpreten mal.
        """
        buffer = ""
        while self.corriendo:
            # Esperar que la Raspberry se conecte
            if self.conexion is None:
                buffer = ""
                try:
                    self.conexion, addr = self._servidor.accept()
                    self.conexion.settimeout(0.5)
                    print(f"[WiFi] Raspberry conectada desde {addr}")
                except socket.timeout:
                    continue
                except Exception:
                    break

            # Leer datos enviados por la Raspberry
            try:
                datos = self.conexion.recv(256)
                if not datos:
                    # Raspberry desconectada
                    self.conexion.close()
                    self.conexion = None
                    print("[WiFi] Raspberry desconectada. Esperando reconexión...")
                    continue
                buffer += datos.decode('utf-8', errors='ignore')
                # Procesar solo líneas completas (terminadas en \n)
                while '\n' in buffer:
                    linea, buffer = buffer.split('\n', 1)
                    linea = linea.strip()
                    if not linea:
                        continue
                    # Validar carácter suelto: ignorar si no es Morse válido
                    if len(linea) == 1 and linea.upper() not in self._CHARS_VALIDOS:
                        print(f"[WiFi] Carácter inválido ignorado: {repr(linea)}")
                        continue
                    if self.al_recibir:
                        self.al_recibir(linea)
            except socket.timeout:
                continue
            except Exception:
                self.conexion = None


# ─────────────────────────────────────────────
#  LÓGICA DEL JUEGO
# ─────────────────────────────────────────────

class EstadoJuego:
    """Guarda toda la información de la partida en curso."""

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        """Reinicia todos los valores al estado inicial."""
        self.estado            = "MENU"
        self.modo              = "ESCUCHA_Y_TRANSMISION"  # o TRANSMISION_SIMPLE
        self.tiempo_unidad     = UNIDAD_A
        self.total_rondas      = 3
        self.modo_presentacion = "LUCES"   # LUCES / SONIDO / AMBOS
        self.modo_switch       = "LOCAL"   # LOCAL / VERSUS
        self.frases            = list(FRASES_PREDEFINIDAS)
        self.frase_actual      = ""
        self.ronda             = 1
        self.puntaje_a         = 0
        self.puntaje_b         = 0
        self.entrada_a         = ""
        self.entrada_b         = ""
        self.historial         = []  # [(ronda, frase, pts_a, pts_b)]

    def seleccionar_frase(self) -> str:
        """Elige una frase aleatoria de la lista."""
        self.frase_actual = random.choice(self.frases).upper()
        return self.frase_actual

    def calcular_puntajes_ronda(self) -> tuple[int, int]:
        """Calcula puntajes de ambos jugadores para la ronda actual."""
        ca, ta = calcular_puntaje(self.frase_actual, self.entrada_a)
        cb, tb = calcular_puntaje(self.frase_actual, self.entrada_b)
        pts_a = int(100 * ca / ta) if ta else 0
        pts_b = int(100 * cb / tb) if tb else 0
        return pts_a, pts_b


# ─────────────────────────────────────────────
#  WIDGET: PANEL DE LEDS
# ─────────────────────────────────────────────

class PanelLED(tk.Canvas):
    """
    Panel de LEDs que replica la pared de luces de Joyce Byers.
    3 filas: letras impares / letras pares / dígitos y signos.
    """

    R   = 10    # radio del LED
    CW  = 36    # ancho de columna
    RH  = 36    # alto de fila
    PX  = 12    # padding horizontal
    PY  = 10    # padding vertical

    def __init__(self, parent, **kw):
        filas     = [FILA_LED_1, FILA_LED_2, FILA_LED_3]
        max_cols  = max(len(f) for f in filas)
        ancho     = self.PX * 2 + max_cols * self.CW
        alto      = self.PY * 2 + len(filas) * self.RH + 6
        super().__init__(parent, width=ancho, height=alto,
                         bg=COLORES["fondo"], highlightthickness=1,
                         highlightbackground="#aaaaaa", **kw)
        self._leds = {}      # char -> id oval
        self._etiq = {}      # char -> id texto
        self._dibujar()

    def _dibujar(self):
        """Dibuja todos los LEDs y sus etiquetas."""
        filas = [FILA_LED_1, FILA_LED_2, FILA_LED_3]
        for fi, fila in enumerate(filas):
            y = self.PY + fi * self.RH + self.R
            for ci, ch in enumerate(fila):
                x = self.PX + ci * self.CW + self.R
                oid = self.create_oval(
                    x - self.R, y - self.R, x + self.R, y + self.R,
                    fill=COLORES["led_off"], outline="#999999", width=1
                )
                tid = self.create_text(
                    x, y + self.R + 5, text=ch,
                    fill="#555555", font=("Courier New", 7, "bold")
                )
                self._leds[ch] = oid
                self._etiq[ch] = tid

    def encender(self, caracter: str, estado: bool):
        """Enciende (True) o apaga (False) el LED de un carácter."""
        ch = caracter.upper()
        if ch not in self._leds:
            return
        self.itemconfig(self._leds[ch], fill=COLORES["led_on"] if estado else COLORES["led_off"])
        self.itemconfig(self._etiq[ch], fill="#111111" if estado else "#555555")

    def apagar_todos(self):
        """Apaga todos los LEDs del panel."""
        for ch in self._leds:
            self.encender(ch, False)

    def animar_frase(self, frase: str, unidad_ms: int = 200, cb_fin=None):
        """
        Anima el panel mostrando cada carácter según temporización Morse:
        punto=1u, raya=3u, pausa entre símbolos=1u,
        pausa entre caracteres=3u, pausa entre palabras=7u.
        """
        self.apagar_todos()
        secuencia = []  # (char, ms_on, ms_off)
        for ch in frase.upper():
            if ch == ' ':
                secuencia.append((' ', 0, unidad_ms * 4))  # 4u extra (ya hay 3u previas)
                continue
            codigo = TABLA_MORSE.get(ch, '')
            for simbolo in codigo:
                dur = unidad_ms if simbolo == '.' else unidad_ms * 3
                secuencia.append((ch, dur, unidad_ms))
            secuencia.append((ch, 0, unidad_ms * 2))  # pausa entre caracteres

        def _reproducir(idx):
            if idx >= len(secuencia):
                self.apagar_todos()
                if cb_fin:
                    cb_fin()
                return
            ch, ms_on, ms_off = secuencia[idx]
            if ms_on > 0:
                self.encender(ch, True)
                self.after(ms_on, lambda: _apagar(idx, ms_off))
            else:
                _apagar(idx, ms_off)

        def _apagar(idx, ms_off):
            ch = secuencia[idx][0]
            if ch != ' ':
                self.encender(ch, False)
            self.after(ms_off, lambda: _reproducir(idx + 1))

        _reproducir(0)


# ─────────────────────────────────────────────
#  WIDGET: ENTRADA MORSE (JUGADOR A)
# ─────────────────────────────────────────────

class PanelEntradaMorse(tk.LabelFrame):
    """
    Panel de entrada Morse para el Jugador A.
    ESPACIO del teclado: presión corta = punto, presión larga = raya.
    Muestra el código acumulado y el texto decodificado.
    """

    def __init__(self, parent, al_ingresar_char=None, **kw):
        super().__init__(parent, text="Entrada Morse — Jugador A",
                         bg=COLORES["fondo"], font=("Arial", 10, "bold"), **kw)
        self.al_ingresar_char = al_ingresar_char
        self._buffer_morse    = ""
        self._buffer_texto    = ""
        self._tiempo_presion  = None
        self._tarea_char      = None
        self._tarea_espacio   = None
        self._unidad_ms       = 200
        self._construir()
        self.vincular_teclas()

    def establecer_unidad(self, unidad_ms: int):
        """Actualiza la duración de la unidad temporal."""
        self._unidad_ms = unidad_ms

    def _construir(self):
        # Código Morse acumulado (símbolos . y -)
        tk.Label(self, text="Código Morse:", bg=COLORES["fondo"]).pack(anchor="w", padx=8)
        self.var_morse = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_morse,
                 font=("Courier New", 16, "bold"), bg=COLORES["fondo"],
                 fg="#FFFFFF", width=28, anchor="w").pack(padx=8)

        # Texto decodificado
        tk.Label(self, text="Texto decodificado:", bg=COLORES["fondo"]).pack(anchor="w", padx=8)
        self.var_texto = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_texto,
                 font=("Courier New", 14, "bold"), bg=COLORES["fondo"],
                 fg=COLORES["puntaje_a"], width=28, anchor="w").pack(padx=8)

        # Botón PULSAR
        self.boton = tk.Button(
            self, text="● PULSAR  [ESPACIO]",
            font=("Arial", 11, "bold"), relief="raised",
            bg=COLORES["boton"], cursor="hand2",
            command=None  # se controla con bind
        )
        self.boton.pack(fill="x", padx=8, pady=6)
        self.boton.bind("<ButtonPress-1>",   self._al_presionar)
        self.boton.bind("<ButtonRelease-1>", self._al_soltar)

        # Botones de control
        marco_ctrl = tk.Frame(self, bg=COLORES["fondo"])
        marco_ctrl.pack(fill="x", padx=8, pady=2)
        tk.Button(marco_ctrl, text="Borrar carácter [DEL]",
                  command=self._borrar_caracter,
                  bg=COLORES["boton"]).pack(side="left", padx=2)
        tk.Button(marco_ctrl, text="Espacio [/]",
                  command=self._agregar_espacio,
                  bg=COLORES["boton"]).pack(side="left", padx=2)
        tk.Button(marco_ctrl, text="Limpiar todo",
                  command=self._limpiar_todo,
                  bg=COLORES["boton"]).pack(side="right", padx=2)

        # Instrucciones breves
        tk.Label(self,
                 text="Corto (<1.5 unidades)=PUNTO  |  Largo=RAYA\n"
                      "Silencio 3.5u=fin carácter  |  Silencio 7u=espacio",
                 bg=COLORES["fondo"], fg="#FFFFFF",
                 font=("Arial", 8)).pack(pady=4)

    def vincular_teclas(self):
        """Vincula ESPACIO del teclado como botón Morse."""
        self.master.bind("<KeyPress-space>",   self._al_presionar)
        self.master.bind("<KeyRelease-space>", self._al_soltar)
        self.master.bind("<Delete>",           lambda e: self._borrar_caracter())
        self.master.bind("<slash>",            lambda e: self._agregar_espacio())

    def _al_presionar(self, evento=None):
        """Registra el inicio de la presión."""
        if self._tiempo_presion is not None:
            return
        self._tiempo_presion = time.time()
        self.boton.config(relief="sunken", bg="#aaaaaa")
        for tarea in (self._tarea_char, self._tarea_espacio):
            if tarea:
                self.after_cancel(tarea)
        self._tarea_char = self._tarea_espacio = None

    def _al_soltar(self, evento=None):
        """Mide la duración y agrega punto o raya al buffer."""
        if self._tiempo_presion is None:
            return
        duracion_ms = (time.time() - self._tiempo_presion) * 1000
        self._tiempo_presion = None
        self.boton.config(relief="raised", bg=COLORES["boton"])

        simbolo = '.' if duracion_ms < (self._unidad_ms * 1.5) else '-'
        self._buffer_morse += simbolo
        self.var_morse.set(self._buffer_morse)

        # Programar decodificación del carácter tras 3.5 unidades de silencio
        if self._tarea_char:
            self.after_cancel(self._tarea_char)
        self._tarea_char = self.after(int(self._unidad_ms * 3.5), self._confirmar_caracter)

    def _confirmar_caracter(self):
        """Decodifica el buffer Morse y lo agrega al texto."""
        self._tarea_char = None
        codigo = self._buffer_morse.strip()
        if not codigo:
            return
        decodificado = MORSE_INVERSO.get(codigo, '?')
        self._buffer_texto += decodificado
        self.var_texto.set(self._buffer_texto)
        self._buffer_morse = ""
        self.var_morse.set("")
        if self.al_ingresar_char:
            self.al_ingresar_char(decodificado)
        # Programar espacio de palabra tras 7 unidades de silencio
        if self._tarea_espacio:
            self.after_cancel(self._tarea_espacio)
        self._tarea_espacio = self.after(int(self._unidad_ms * 7), self._confirmar_espacio)

    def _confirmar_espacio(self):
        """Agrega espacio de palabra si el jugador dejó de escribir."""
        self._tarea_espacio = None
        if self._buffer_texto and not self._buffer_texto.endswith(' '):
            self._buffer_texto += ' '
            self.var_texto.set(self._buffer_texto)

    def _borrar_caracter(self):
        """Borra el último símbolo Morse o el último carácter decodificado."""
        if self._buffer_morse:
            self._buffer_morse = ""
            self.var_morse.set("")
        elif self._buffer_texto:
            self._buffer_texto = self._buffer_texto[:-1]
            self.var_texto.set(self._buffer_texto)

    def _agregar_espacio(self):
        """Agrega espacio manualmente entre palabras."""
        self._buffer_texto += ' '
        self.var_texto.set(self._buffer_texto)

    def _limpiar_todo(self):
        """Borra todo el buffer."""
        self._buffer_morse = self._buffer_texto = ""
        self.var_morse.set("")
        self.var_texto.set("")

    def obtener_texto(self) -> str:
        """Retorna el texto decodificado sin espacios extremos."""
        return self._buffer_texto.strip()

    def reiniciar(self):
        """Cancela tareas pendientes y limpia el buffer."""
        for tarea in (self._tarea_char, self._tarea_espacio):
            if tarea:
                self.after_cancel(tarea)
        self._tarea_char = self._tarea_espacio = None
        self._limpiar_todo()


# ─────────────────────────────────────────────
#  PANTALLA BASE
# ─────────────────────────────────────────────

class PantallaBase(tk.Frame):
    """Frame base para todas las pantallas."""
    def __init__(self, parent, app, **kw):
        super().__init__(parent, bg=COLORES["fondo"], **kw)
        self.app = app

    def al_mostrar(self):
        """Se llama cada vez que la pantalla se vuelve visible."""
        pass


# ─────────────────────────────────────────────
#  PANTALLA: MENÚ PRINCIPAL
# ─────────────────────────────────────────────

class PantallaMenu(PantallaBase):
    """Menú de inicio con los botones principales."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        # Título
        tk.Label(self, text="StrangerTEC — Morse Translator",
                 font=("Arial", 22, "bold"), bg=COLORES["fondo"], fg="#FFFFFF").pack(pady=(30, 5))
        tk.Label(self, text="CE-1104 · ITCR · I Sem. 2026",
                 font=("Arial", 10), bg=COLORES["fondo"], fg="#FFFFFF").pack()

        # Indicador de conexión con la maqueta
        self.var_conexion = tk.StringVar(value="● Maqueta: desconectada")
        self.lbl_conexion = tk.Label(self, textvariable=self.var_conexion,
                 font=("Arial", 10), bg=COLORES["fondo"], fg="red")
        self.lbl_conexion.pack(pady=6)

        # Separador
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=40, pady=10)

        # Botones del menú
        marco = tk.Frame(self, bg=COLORES["fondo"])
        marco.pack(pady=10)

        botones = [
            ("Nueva partida",       self.app.mostrar_config,         14),
            ("Editar frases",       self.app.mostrar_editor_frases,   11),
            ("Conectar maqueta",    self.app.mostrar_dialogo_serial,  11),
            ("Ver historial",       self.app.mostrar_historial,       11),
        ]
        for texto, cmd, tam in botones:
            tk.Button(marco, text=texto, command=cmd,
                      font=("Arial", tam), width=22,
                      bg=COLORES["boton"], relief="raised", cursor="hand2",
                      pady=6).pack(pady=5)

    def actualizar_conexion(self, conectado: bool):
        """Actualiza el indicador visual de conexión."""
        if conectado:
            self.var_conexion.set("● Maqueta: conectada")
            self.lbl_conexion.config(fg="green")
        else:
            self.var_conexion.set("● Maqueta: desconectada")
            self.lbl_conexion.config(fg="red")


# ─────────────────────────────────────────────
#  PANTALLA: CONFIGURACIÓN
# ─────────────────────────────────────────────

class PantallaConfig(PantallaBase):
    """Configuración de la partida antes de iniciar."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        tk.Label(self, text="Configuración de partida",
                 font=("Arial", 16, "bold"), bg=COLORES["fondo"]).pack(pady=(20, 10))

        # Marco central con todas las opciones
        marco = tk.Frame(self, bg=COLORES["fondo"])
        marco.pack(expand=True)

        # ── Modo de juego ──
        tk.Label(marco, text="Modo de juego:", font=("Arial", 11, "bold"),
                 bg=COLORES["fondo"]).grid(row=0, column=0, sticky="w", pady=6, padx=10)
        self.var_modo = tk.StringVar(value="ESCUCHA_Y_TRANSMISION")
        tk.Radiobutton(marco, text="Escucha y Transmisión", variable=self.var_modo,
                       value="ESCUCHA_Y_TRANSMISION", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=0, column=1, sticky="w")
        tk.Radiobutton(marco, text="Transmisión Simple", variable=self.var_modo,
                       value="TRANSMISION_SIMPLE", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=0, column=2, sticky="w")

        # ── Unidad de tiempo ──
        tk.Label(marco, text="Unidad de tiempo:", font=("Arial", 11, "bold"),
                 bg=COLORES["fondo"]).grid(row=1, column=0, sticky="w", pady=6, padx=10)
        self.var_unidad = tk.StringVar(value="A")
        tk.Radiobutton(marco, text="A = 0.2 s (rápido)", variable=self.var_unidad,
                       value="A", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=1, column=1, sticky="w")
        tk.Radiobutton(marco, text="B = 0.3 s (lento)", variable=self.var_unidad,
                       value="B", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=1, column=2, sticky="w")

        # ── Presentación en maqueta ──
        tk.Label(marco, text="Presentación (maqueta):", font=("Arial", 11, "bold"),
                 bg=COLORES["fondo"]).grid(row=2, column=0, sticky="w", pady=6, padx=10)
        self.var_presentacion = tk.StringVar(value="LUCES")
        for col, (val, lbl) in enumerate([("LUCES", "Luces"), ("SONIDO", "Sonido"), ("AMBOS", "Ambos")]):
            tk.Radiobutton(marco, text=lbl, variable=self.var_presentacion,
                           value=val, bg=COLORES["fondo"],
                           font=("Arial", 10)).grid(row=2, column=col+1, sticky="w")

        # ── Switch de modo ──
        tk.Label(marco, text="Switch:", font=("Arial", 11, "bold"),
                 bg=COLORES["fondo"]).grid(row=3, column=0, sticky="w", pady=6, padx=10)
        self.var_switch = tk.StringVar(value="LOCAL")
        tk.Radiobutton(marco, text="Local (1 maqueta)", variable=self.var_switch,
                       value="LOCAL", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=3, column=1, sticky="w")
        tk.Radiobutton(marco, text="Versus (WiFi)", variable=self.var_switch,
                       value="VERSUS", bg=COLORES["fondo"],
                       font=("Arial", 10)).grid(row=3, column=2, sticky="w")

        # ── Número de rondas ──
        tk.Label(marco, text="Rondas:", font=("Arial", 11, "bold"),
                 bg=COLORES["fondo"]).grid(row=4, column=0, sticky="w", pady=6, padx=10)
        self.var_rondas = tk.IntVar(value=3)
        tk.Spinbox(marco, from_=1, to=10, textvariable=self.var_rondas,
                   width=5, font=("Arial", 11)).grid(row=4, column=1, sticky="w")

        # Botones
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=40, pady=10)
        marco_btns = tk.Frame(self, bg=COLORES["fondo"])
        marco_btns.pack()
        tk.Button(marco_btns, text="◀ Volver", command=self.app.mostrar_menu,
                  font=("Arial", 11), width=12, bg=COLORES["boton"]).pack(side="left", padx=10)
        tk.Button(marco_btns, text="▶ Iniciar partida", command=self._iniciar,
                  font=("Arial", 11, "bold"), width=16,
                  bg="#ccffcc").pack(side="left", padx=10)

    def _iniciar(self):
        """Guarda la configuración e inicia la partida."""
        juego = self.app.juego
        juego.modo              = self.var_modo.get()
        juego.tiempo_unidad     = UNIDAD_A if self.var_unidad.get() == "A" else UNIDAD_B
        juego.total_rondas      = self.var_rondas.get()
        juego.modo_presentacion = self.var_presentacion.get()
        juego.modo_switch       = self.var_switch.get()
        juego.ronda             = 1
        juego.puntaje_a         = 0
        juego.puntaje_b         = 0
        juego.historial         = []
        # Enviar configuración a la maqueta
        self.app.enviar_serial(json.dumps({
            "cmd":    "CONFIG",
            "unidad": juego.tiempo_unidad,
            "modo":   juego.modo_presentacion,
            "switch": juego.modo_switch,
        }))
        self.app.mostrar_juego()


# ─────────────────────────────────────────────
#  PANTALLA: JUEGO
# ─────────────────────────────────────────────

class PantallaJuego(PantallaBase):
    """Pantalla principal del juego donde transcurre la partida."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        # ── Cabecera con ronda, fase y puntajes ──
        cab = tk.Frame(self, bg="#dddddd", relief="groove", bd=1)
        cab.pack(fill="x", pady=(0, 4))

        self.var_ronda = tk.StringVar(value="Ronda 1")
        tk.Label(cab, textvariable=self.var_ronda,
                 font=("Arial", 13, "bold"), bg="#dddddd").pack(side="left", padx=12, pady=6)

        self.var_fase = tk.StringVar(value="")
        tk.Label(cab, textvariable=self.var_fase,
                 font=("Arial", 11), bg="#dddddd").pack(side="left", padx=6)

        # Puntajes en cabecera
        marco_pts = tk.Frame(cab, bg="#dddddd")
        marco_pts.pack(side="right", padx=12)
        tk.Label(marco_pts, text="Jugador A:", bg="#dddddd",
                 font=("Arial", 10)).grid(row=0, column=0, padx=4)
        self.var_puntaje_a = tk.StringVar(value="0")
        tk.Label(marco_pts, textvariable=self.var_puntaje_a,
                 font=("Arial", 16, "bold"), fg=COLORES["puntaje_a"],
                 bg="#dddddd").grid(row=0, column=1, padx=4)
        tk.Label(marco_pts, text="Jugador B:", bg="#dddddd",
                 font=("Arial", 10)).grid(row=0, column=2, padx=8)
        self.var_puntaje_b = tk.StringVar(value="0")
        tk.Label(marco_pts, textvariable=self.var_puntaje_b,
                 font=("Arial", 16, "bold"), fg=COLORES["puntaje_b"],
                 bg="#dddddd").grid(row=0, column=3, padx=4)

        # ── Frase actual ──
        marco_frase = tk.LabelFrame(self, text="Frase de la ronda",
                                     font=("Arial", 10, "bold"), bg=COLORES["fondo"])
        marco_frase.pack(fill="x", padx=10, pady=4)
        self.var_frase = tk.StringVar(value="???")
        tk.Label(marco_frase, textvariable=self.var_frase,
                 font=("Courier New", 20, "bold"), bg=COLORES["fondo"],
                 fg="#FFFFFF").pack(pady=4)
        self.var_morse_frase = tk.StringVar(value="")
        tk.Label(marco_frase, textvariable=self.var_morse_frase,
                 font=("Courier New", 9), bg=COLORES["fondo"],
                 fg="#FFFFFF", wraplength=700).pack(pady=(0, 4))

        # ── Cuerpo: panel LED + entrada Morse ──
        cuerpo = tk.Frame(self, bg=COLORES["fondo"])
        cuerpo.pack(fill="both", expand=True, padx=10, pady=4)

        # Panel LED (izquierda)
        marco_led = tk.LabelFrame(cuerpo, text="Panel de luces — Maqueta",
                                   font=("Arial", 10, "bold"), bg=COLORES["fondo"])
        marco_led.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.panel_led = PanelLED(marco_led)
        self.panel_led.pack(padx=6, pady=6)

        # Botones de acción del panel LED
        marco_acc = tk.Frame(marco_led, bg=COLORES["fondo"])
        marco_acc.pack(fill="x", padx=6, pady=4)
        self.btn_animar = tk.Button(marco_acc, text="▶ Animar frase (LEDs)",
                                     command=self._animar_frase, bg=COLORES["boton"])
        self.btn_animar.pack(side="left", padx=4)
        tk.Button(marco_acc, text="📡 Enviar a maqueta",
                  command=self._enviar_a_pico, bg=COLORES["boton"]).pack(side="left", padx=4)

        # Panel derecho: entrada Morse + estado jugador B
        derecha = tk.Frame(cuerpo, bg=COLORES["fondo"], width=320)
        derecha.pack(side="right", fill="y")
        derecha.pack_propagate(False)

        # Entrada Morse Jugador A
        self.entrada_morse = PanelEntradaMorse(derecha,
                                               al_ingresar_char=self._al_ingresar_char)
        self.entrada_morse.pack(fill="x", pady=(0, 6))

        # Estado jugador B (recibido de maqueta)
        marco_b = tk.LabelFrame(derecha, text="Jugador B — Maqueta",
                                  font=("Arial", 10, "bold"), bg=COLORES["fondo"])
        marco_b.pack(fill="x")
        self.var_morse_b = tk.StringVar(value="")
        tk.Label(marco_b, textvariable=self.var_morse_b,
                 font=("Courier New", 13, "bold"), bg=COLORES["fondo"],
                 fg="#FFFFFF", width=28, anchor="w").pack(padx=6)
        self.var_texto_b = tk.StringVar(value="")
        tk.Label(marco_b, textvariable=self.var_texto_b,
                 font=("Courier New", 13, "bold"), bg=COLORES["fondo"],
                 fg=COLORES["puntaje_b"], width=28, anchor="w").pack(padx=6, pady=(0, 4))

        # Log del sistema
        marco_log = tk.LabelFrame(derecha, text="Log del sistema",
                                   font=("Arial", 9), bg=COLORES["fondo"])
        marco_log.pack(fill="both", expand=True, pady=(6, 0))
        self.texto_log = tk.Text(marco_log, height=5, font=("Courier New", 8),
                                  relief="flat", bd=1, state="disabled",
                                  bg="#f8f8f8")
        self.texto_log.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Pie: confirmar / omitir / menú ──
        pie = tk.Frame(self, bg=COLORES["fondo"])
        pie.pack(fill="x", padx=10, pady=6)

        self.btn_confirmar = tk.Button(pie, text="✔ Confirmar respuesta",
                                        command=self._confirmar_respuesta,
                                        font=("Arial", 11, "bold"),
                                        bg="#ccffcc", state="disabled")
        self.btn_confirmar.pack(side="left", padx=6)

        tk.Button(pie, text="⏭ Omitir turno",
                  command=self._omitir_turno,
                  font=("Arial", 10), bg=COLORES["boton"]).pack(side="left", padx=4)

        tk.Button(pie, text="◀ Menú",
                  command=self.app.mostrar_menu,
                  font=("Arial", 10), bg=COLORES["boton"]).pack(side="right", padx=6)

    def al_mostrar(self):
        """Inicia la ronda al mostrar la pantalla."""
        self._iniciar_ronda()

    def _iniciar_ronda(self):
        """Prepara la interfaz para el inicio de una ronda."""
        juego = self.app.juego
        self.var_ronda.set(f"Ronda {juego.ronda} de {juego.total_rondas}")
        frase = juego.seleccionar_frase()
        self.var_frase.set(frase)
        self.var_morse_frase.set(texto_a_morse(frase))
        self.panel_led.apagar_todos()
        self.entrada_morse.reiniciar()
        self.var_morse_b.set("")
        self.var_texto_b.set("")
        self.var_puntaje_a.set(str(juego.puntaje_a))
        self.var_puntaje_b.set(str(juego.puntaje_b))
        self.entrada_morse.establecer_unidad(int(juego.tiempo_unidad * 1000))
        self._establecer_fase("A")
        self._registrar(f"Ronda {juego.ronda} iniciada. Frase: {frase}")
        # Enviar frase a la maqueta
        self.app.enviar_serial(json.dumps({"cmd": "FRASE", "texto": frase}))

    def _establecer_fase(self, fase: str):
        """Cambia la fase activa: 'A' (PC) o 'B' (maqueta)."""
        self.app.juego.estado = f"JUGANDO_{fase}"
        if fase == "A":
            self.var_fase.set("→ Turno: Jugador A (teclado)")
            self.btn_confirmar.config(state="normal", bg="#ccffcc")
        else:
            self.var_fase.set("→ Turno: Jugador B (maqueta)")
            self.btn_confirmar.config(state="normal", bg="#ffcccc")
        self._registrar(f"Turno jugador {fase}")

    def _al_ingresar_char(self, ch: str):
        """Callback cuando el Jugador A decodifica un carácter."""
        pass  # Se puede usar para retroalimentación adicional

    def _animar_frase(self):
        """Anima el panel LED con la frase en código Morse."""
        juego = self.app.juego
        unidad_ms = int(juego.tiempo_unidad * 1000)
        self.btn_animar.config(state="disabled")
        self.panel_led.animar_frase(
            juego.frase_actual, unidad_ms,
            cb_fin=lambda: self.btn_animar.config(state="normal"))

    def _enviar_a_pico(self):
        """Envía la frase actual a la maqueta para reproducirla."""
        juego = self.app.juego
        self.app.enviar_serial(json.dumps({
            "cmd":    "REPRODUCIR",
            "texto":  juego.frase_actual,
            "unidad": juego.tiempo_unidad,
            "modo":   juego.modo_presentacion,
        }))
        self._registrar("Frase enviada a la maqueta.")

    def _confirmar_respuesta(self):
        """El jugador activo confirma su respuesta."""
        juego = self.app.juego
        if juego.estado == "JUGANDO_A":
            juego.entrada_a = self.entrada_morse.obtener_texto()
            self._registrar(f"Jugador A: '{juego.entrada_a}'")
            self.entrada_morse.reiniciar()
            if juego.modo == "ESCUCHA_Y_TRANSMISION":
                self._establecer_fase("B")
                self._registrar("Esperando respuesta de Jugador B...")
                self.app.enviar_serial(json.dumps({"cmd": "TURNO_B"}))
            else:
                self._finalizar_ronda()
        elif juego.estado == "JUGANDO_B":
            # En modo local, B también puede usar teclado (para demo)
            juego.entrada_b = self.entrada_morse.obtener_texto() or self.var_texto_b.get()
            self._registrar(f"Jugador B: '{juego.entrada_b}'")
            self._finalizar_ronda()

    def _omitir_turno(self):
        """El jugador activo omite su turno (puntaje 0)."""
        juego = self.app.juego
        if juego.estado == "JUGANDO_A":
            juego.entrada_a = ""
            if juego.modo == "ESCUCHA_Y_TRANSMISION":
                self._establecer_fase("B")
            else:
                self._finalizar_ronda()
        elif juego.estado == "JUGANDO_B":
            juego.entrada_b = ""
            self._finalizar_ronda()

    def _finalizar_ronda(self):
        """Calcula puntajes y muestra resultados de la ronda."""
        juego = self.app.juego
        pts_a, pts_b = juego.calcular_puntajes_ronda()
        juego.puntaje_a += pts_a
        juego.puntaje_b += pts_b
        juego.historial.append((juego.ronda, juego.frase_actual, pts_a, pts_b))
        self.var_puntaje_a.set(str(juego.puntaje_a))
        self.var_puntaje_b.set(str(juego.puntaje_b))
        self._registrar(f"Ronda {juego.ronda}: A={pts_a}pts  B={pts_b}pts")
        ganador = "A" if pts_a > pts_b else ("B" if pts_b > pts_a else "EMPATE")
        self.app.mostrar_resultado_ronda(pts_a, pts_b, ganador,
                                          juego.frase_actual, juego.entrada_a, juego.entrada_b)

    def recibir_de_pico(self, datos: dict):
        """
        Procesa datos JSON de la Raspberry Pi Pico W.
        Comandos: MORSE_SIM, MORSE_CHAR, MORSE_ESPACIO, B_LISTO, LED_ON, LED_OFF.
        """
        cmd = datos.get("cmd", "")
        if cmd == "MORSE_SIM":
            self.var_morse_b.set(self.var_morse_b.get() + datos.get("sim", ""))
        elif cmd == "MORSE_CHAR":
            ch = datos.get("char", "?")
            self.var_texto_b.set(self.var_texto_b.get() + ch)
            self.var_morse_b.set("")
        elif cmd == "MORSE_ESPACIO":
            actual = self.var_texto_b.get()
            if not actual.endswith(' '):
                self.var_texto_b.set(actual + ' ')
        elif cmd == "B_LISTO":
            self.app.juego.entrada_b = self.var_texto_b.get().strip()
            self._finalizar_ronda()
        elif cmd == "LED_ON":
            ch = datos.get("char", "")
            if ch:
                self.panel_led.encender(ch, True)
        elif cmd == "LED_OFF":
            ch = datos.get("char", "")
            if ch:
                self.panel_led.encender(ch, False)

    def siguiente_ronda(self):
        """Avanza a la siguiente ronda o muestra resultados finales."""
        juego = self.app.juego
        juego.ronda += 1
        if juego.ronda > juego.total_rondas:
            self.app.mostrar_resultados_finales()
        else:
            self._iniciar_ronda()

    def _registrar(self, mensaje: str):
        """Agrega una línea al log del sistema con timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.texto_log.config(state="normal")
        self.texto_log.insert("end", f"[{ts}] {mensaje}\n")
        self.texto_log.see("end")
        self.texto_log.config(state="disabled")


# ─────────────────────────────────────────────
#  PANTALLA: RESULTADO DE RONDA
# ─────────────────────────────────────────────

class PantallaResultadoRonda(PantallaBase):
    """Muestra los resultados al finalizar cada ronda."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        self.var_titulo = tk.StringVar(value="Resultado de la ronda")
        tk.Label(self, textvariable=self.var_titulo,
                 font=("Arial", 18, "bold"), bg=COLORES["fondo"]).pack(pady=(30, 10))

        self.var_ganador = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_ganador,
                 font=("Arial", 16, "bold"), bg=COLORES["fondo"]).pack(pady=6)

        # Tabla de comparación
        marco_tabla = tk.Frame(self, bg=COLORES["fondo"], relief="groove", bd=1)
        marco_tabla.pack(padx=60, pady=10, fill="x")

        encabezados = ["", "Jugador A", "Jugador B"]
        for ci, h in enumerate(encabezados):
            tk.Label(marco_tabla, text=h, font=("Arial", 11, "bold"),
                     bg="#dddddd", width=20, relief="groove").grid(
                row=0, column=ci, padx=2, pady=2, sticky="ew")

        filas = ["Frase original:", "Su respuesta:", "Puntaje ronda:"]
        self.vars_tabla = [[tk.StringVar() for _ in range(2)] for _ in range(3)]
        for ri, etq in enumerate(filas):
            tk.Label(marco_tabla, text=etq, font=("Arial", 10),
                     bg=COLORES["fondo"], width=20, anchor="w").grid(
                row=ri+1, column=0, padx=2, pady=3, sticky="w")
            for ci in range(2):
                color = COLORES["puntaje_a"] if ci == 0 else COLORES["puntaje_b"]
                tk.Label(marco_tabla, textvariable=self.vars_tabla[ri][ci],
                         font=("Arial", 11, "bold"), fg=color,
                         bg=COLORES["fondo"], width=20).grid(
                    row=ri+1, column=ci+1, padx=2, pady=3)

        # Marcador acumulado
        marco_acum = tk.Frame(self, bg="#eeeeee", relief="groove", bd=1)
        marco_acum.pack(padx=60, pady=8, fill="x")
        tk.Label(marco_acum, text="Marcador acumulado",
                 font=("Arial", 10, "bold"), bg="#eeeeee").pack(pady=(6, 2))
        self.var_acumulado = tk.StringVar(value="")
        tk.Label(marco_acum, textvariable=self.var_acumulado,
                 font=("Arial", 13, "bold"), bg="#eeeeee").pack(pady=(0, 8))

        # Botones
        marco_btns = tk.Frame(self, bg=COLORES["fondo"])
        marco_btns.pack(pady=20)
        self.btn_siguiente = tk.Button(marco_btns, text="▶ Siguiente ronda",
                                        command=self._siguiente,
                                        font=("Arial", 12, "bold"),
                                        width=18, bg="#ccffcc")
        self.btn_siguiente.pack(side="left", padx=10)
        tk.Button(marco_btns, text="◀ Menú", command=self.app.mostrar_menu,
                  font=("Arial", 11), width=10, bg=COLORES["boton"]).pack(side="left", padx=10)

    def cargar(self, pts_a, pts_b, ganador, frase, entrada_a, entrada_b):
        """Carga los datos de la ronda terminada."""
        juego = self.app.juego
        self.var_titulo.set(f"Resultado — Ronda {juego.ronda}")

        if ganador == "EMPATE":
            self.var_ganador.set("¡Empate!")
        else:
            color = COLORES["puntaje_a"] if ganador == "A" else COLORES["puntaje_b"]
            self.var_ganador.set(f"★ Gana Jugador {ganador}")

        self.vars_tabla[0][0].set(frase)
        self.vars_tabla[0][1].set(frase)
        self.vars_tabla[1][0].set(entrada_a or "(sin respuesta)")
        self.vars_tabla[1][1].set(entrada_b or "(sin respuesta)")
        self.vars_tabla[2][0].set(f"{pts_a} pts")
        self.vars_tabla[2][1].set(f"{pts_b} pts")
        self.var_acumulado.set(f"Jugador A: {juego.puntaje_a} pts   |   Jugador B: {juego.puntaje_b} pts")

        if juego.ronda >= juego.total_rondas:
            self.btn_siguiente.config(text="🏆 Ver resultados finales")

    def _siguiente(self):
        """Avanza a la siguiente ronda o muestra resultados finales."""
        juego = self.app.juego
        if juego.ronda >= juego.total_rondas:
            self.app.mostrar_resultados_finales()
        else:
            self.app.mostrar_juego()
            self.app.pantallas["juego"].siguiente_ronda()


# ─────────────────────────────────────────────
#  PANTALLA: RESULTADOS FINALES
# ─────────────────────────────────────────────

class PantallaResultadosFinales(PantallaBase):
    """Resultados totales al terminar todas las rondas."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        tk.Label(self, text="🏆 Resultados Finales",
                 font=("Arial", 20, "bold"), bg=COLORES["fondo"]).pack(pady=(30, 10))

        self.var_campeon = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_campeon,
                 font=("Arial", 18, "bold"), bg=COLORES["fondo"]).pack(pady=6)

        # Tabla de historial completo
        marco_tabla = tk.Frame(self, bg=COLORES["fondo"], relief="groove", bd=1)
        marco_tabla.pack(padx=40, pady=10, fill="x")
        self.marco_filas = marco_tabla
        self.widgets_tabla = []

        encabezados = ["Ronda", "Frase", "Jugador A", "Jugador B", "Ganador"]
        for ci, h in enumerate(encabezados):
            tk.Label(marco_tabla, text=h, font=("Arial", 10, "bold"),
                     bg="#dddddd", width=16, relief="groove").grid(
                row=0, column=ci, padx=2, pady=2)

        # Puntaje total
        marco_total = tk.Frame(self, bg="#eeeeee", relief="groove", bd=1)
        marco_total.pack(padx=40, pady=8, fill="x")
        tk.Label(marco_total, text="Puntaje total",
                 font=("Arial", 11, "bold"), bg="#eeeeee").pack(pady=(8, 2))
        self.var_total = tk.StringVar(value="")
        tk.Label(marco_total, textvariable=self.var_total,
                 font=("Arial", 15, "bold"), bg="#eeeeee").pack(pady=(0, 8))

        # Botones
        marco_btns = tk.Frame(self, bg=COLORES["fondo"])
        marco_btns.pack(pady=20)
        tk.Button(marco_btns, text="🔄 Nueva partida", command=self.app.mostrar_config,
                  font=("Arial", 12, "bold"), width=16, bg="#ccffcc").pack(side="left", padx=10)
        tk.Button(marco_btns, text="◀ Menú principal", command=self.app.mostrar_menu,
                  font=("Arial", 11), width=14, bg=COLORES["boton"]).pack(side="left", padx=10)

    def cargar(self):
        """Carga y muestra los resultados finales."""
        juego = self.app.juego
        for w in self.widgets_tabla:
            w.destroy()
        self.widgets_tabla.clear()

        for ri, (ronda, frase, pa, pb) in enumerate(juego.historial):
            ganador = "A" if pa > pb else ("B" if pb > pa else "E")
            colores_fila = [
                COLORES["texto"], COLORES["texto"],
                COLORES["puntaje_a"], COLORES["puntaje_b"],
                COLORES["puntaje_a"] if ganador == "A" else
                (COLORES["puntaje_b"] if ganador == "B" else COLORES["texto"])
            ]
            for ci, (val, col) in enumerate(zip(
                [str(ronda), frase, f"{pa}pts", f"{pb}pts", ganador], colores_fila
            )):
                lbl = tk.Label(self.marco_filas, text=val,
                               font=("Arial", 10), fg=col, bg=COLORES["fondo"],
                               width=16, relief="groove")
                lbl.grid(row=ri+1, column=ci, padx=2, pady=2)
                self.widgets_tabla.append(lbl)

        self.var_total.set(
            f"Jugador A: {juego.puntaje_a} pts   |   Jugador B: {juego.puntaje_b} pts")

        if juego.puntaje_a > juego.puntaje_b:
            self.var_campeon.set("🌟 ¡Ganador: Jugador A!")
        elif juego.puntaje_b > juego.puntaje_a:
            self.var_campeon.set("🌟 ¡Ganador: Jugador B!")
        else:
            self.var_campeon.set("⚡ ¡Empate total!")


# ─────────────────────────────────────────────
#  PANTALLA: EDITOR DE FRASES
# ─────────────────────────────────────────────

class PantallaEditorFrases(PantallaBase):
    """Editor para gestionar la lista de frases del juego."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        tk.Label(self, text="Editor de frases",
                 font=("Arial", 16, "bold"), bg=COLORES["fondo"]).pack(pady=(20, 4))
        tk.Label(self, text="Máx. 16 caracteres por frase. Caracteres válidos: A-Z, 0-9, +, -",
                 font=("Arial", 9), bg=COLORES["fondo"], fg="#CCCCCC").pack()

        principal = tk.Frame(self, bg=COLORES["fondo"])
        principal.pack(fill="both", expand=True, padx=30, pady=10)

        # Lista de frases
        marco_lista = tk.LabelFrame(principal, text="Frases actuales",
                                     font=("Arial", 10, "bold"), bg=COLORES["fondo"])
        marco_lista.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.lista = tk.Listbox(marco_lista, font=("Courier New", 11),
                                 relief="flat", bd=1, height=12,
                                 selectbackground="#aaddff")
        self.lista.pack(fill="both", expand=True, padx=6, pady=6)
        self.lista.bind("<<ListboxSelect>>", self._al_seleccionar)

        # Panel de edición
        marco_ed = tk.LabelFrame(principal, text="Editar",
                                  font=("Arial", 10, "bold"), bg=COLORES["fondo"], width=250)
        marco_ed.pack(side="right", fill="y")
        marco_ed.pack_propagate(False)

        tk.Label(marco_ed, text="Frase:", bg=COLORES["fondo"],
                 font=("Arial", 10)).pack(pady=(12, 2))
        self.var_entrada = tk.StringVar()
        tk.Entry(marco_ed, textvariable=self.var_entrada,
                 font=("Courier New", 12), width=18).pack(padx=12)

        self.var_conteo = tk.StringVar(value="0/16")
        tk.Label(marco_ed, textvariable=self.var_conteo,
                 font=("Arial", 9), bg=COLORES["fondo"], fg="#CCCCCC").pack()
        self.var_entrada.trace_add("write", self._actualizar_conteo)

        tk.Label(marco_ed, text="Morse:", bg=COLORES["fondo"],
                 font=("Arial", 9), fg="#CCCCCC").pack(pady=(8, 0))
        self.var_morse_prev = tk.StringVar(value="")
        tk.Label(marco_ed, textvariable=self.var_morse_prev,
                 font=("Courier New", 8), bg=COLORES["fondo"],
                 fg="#FFFFFF", wraplength=220).pack(padx=8)

        for texto, cmd, color in [
            ("✚ Agregar",              self._agregar,              "#ccffcc"),
            ("✎ Actualizar selección", self._actualizar,            COLORES["boton"]),
            ("✖ Eliminar selección",   self._eliminar,              "#ffcccc"),
            ("↺ Restaurar predefinidas",self._restaurar_predefinidas, COLORES["boton"]),
        ]:
            tk.Button(marco_ed, text=texto, command=cmd,
                      font=("Arial", 9), bg=color, relief="raised",
                      width=22).pack(pady=3, padx=10, fill="x")

        tk.Button(self, text="◀ Volver", command=self.app.mostrar_menu,
                  font=("Arial", 10), bg=COLORES["boton"]).pack(pady=10)

    def al_mostrar(self):
        self._recargar_lista()

    def _recargar_lista(self):
        self.lista.delete(0, "end")
        for frase in self.app.juego.frases:
            self.lista.insert("end", frase)

    def _al_seleccionar(self, evento=None):
        sel = self.lista.curselection()
        if sel:
            self.var_entrada.set(self.lista.get(sel[0]))

    def _actualizar_conteo(self, *_):
        val = self.var_entrada.get().upper()[:16]
        self.var_conteo.set(f"{len(val)}/16")
        self.var_morse_prev.set(texto_a_morse(val))

    def _validar(self):
        val = self.var_entrada.get().strip().upper()[:16]
        if not val:
            messagebox.showwarning("Aviso", "La frase no puede estar vacía.")
            return None
        return val

    def _agregar(self):
        val = self._validar()
        if val and val not in self.app.juego.frases:
            if len(self.app.juego.frases) >= 20:
                messagebox.showwarning("Límite", "Máximo 20 frases.")
                return
            self.app.juego.frases.append(val)
            self._recargar_lista()

    def _actualizar(self):
        sel = self.lista.curselection()
        val = self._validar()
        if sel and val:
            self.app.juego.frases[sel[0]] = val
            self._recargar_lista()

    def _eliminar(self):
        sel = self.lista.curselection()
        if sel and len(self.app.juego.frases) > 3:
            del self.app.juego.frases[sel[0]]
            self._recargar_lista()
        else:
            messagebox.showwarning("Aviso", "Se requieren al menos 3 frases.")

    def _restaurar_predefinidas(self):
        self.app.juego.frases = list(FRASES_PREDEFINIDAS)
        self._recargar_lista()


# ─────────────────────────────────────────────
#  PANTALLA: HISTORIAL
# ─────────────────────────────────────────────

class PantallaHistorial(PantallaBase):
    """Historial de partidas jugadas."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._construir()

    def _construir(self):
        tk.Label(self, text="Historial de partidas",
                 font=("Arial", 16, "bold"), bg=COLORES["fondo"]).pack(pady=(20, 10))

        marco = tk.Frame(self, bg=COLORES["fondo"])
        marco.pack(fill="both", expand=True, padx=30, pady=4)

        columnas = ("ronda", "frase", "puntos_a", "puntos_b", "ganador")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=14)

        for col, ancho, etq in [
            ("ronda",    80,  "Ronda"),
            ("frase",    200, "Frase"),
            ("puntos_a", 120, "Jugador A"),
            ("puntos_b", 120, "Jugador B"),
            ("ganador",  100, "Ganador"),
        ]:
            self.tabla.heading(col, text=etq)
            self.tabla.column(col, width=ancho, anchor="center")

        self.tabla.pack(fill="both", expand=True)

        tk.Button(self, text="◀ Volver", command=self.app.mostrar_menu,
                  font=("Arial", 10), bg=COLORES["boton"]).pack(pady=10)

    def al_mostrar(self):
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        for ronda, frase, pa, pb in self.app.juego.historial:
            ganador = "A" if pa > pb else ("B" if pb > pa else "E")
            self.tabla.insert("", "end",
                               values=(ronda, frase, f"{pa}pts", f"{pb}pts", ganador))


# ─────────────────────────────────────────────
#  APLICACIÓN PRINCIPAL
# ─────────────────────────────────────────────

class Aplicacion(tk.Tk):
    """Ventana principal de StrangerTEC."""

    def __init__(self):
        super().__init__()
        self.title("StrangerTEC — Morse Translator")
        self.geometry("920x660")
        self.minsize(840, 580)
        self.configure(bg=COLORES["fondo"])

        self.juego   = EstadoJuego()
        self.serial  = GestorSerial(al_recibir_datos=self._al_recibir_serial)
        self._conectado = False

        self.pantallas: dict[str, PantallaBase] = {}
        self._pantalla_actual: PantallaBase | None = None
        self._construir_pantallas()
        self.mostrar_menu()

    def _construir_pantallas(self):
        """Instancia todas las pantallas y las apila en la misma posición."""
        for nombre, clase in [
            ("menu",           PantallaMenu),
            ("config",         PantallaConfig),
            ("juego",          PantallaJuego),
            ("resultado_ronda",PantallaResultadoRonda),
            ("final",          PantallaResultadosFinales),
            ("editor_frases",  PantallaEditorFrases),
            ("historial",      PantallaHistorial),
        ]:
            pantalla = clase(self, self)
            pantalla.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.pantallas[nombre] = pantalla

    def _mostrar_pantalla(self, nombre: str):
        """Muestra la pantalla indicada."""
        pantalla = self.pantallas[nombre]
        pantalla.lift()
        pantalla.al_mostrar()
        self._pantalla_actual = pantalla

    def mostrar_menu(self):           self._mostrar_pantalla("menu")
    def mostrar_config(self):         self._mostrar_pantalla("config")
    def mostrar_juego(self):          self._mostrar_pantalla("juego")
    def mostrar_editor_frases(self):  self._mostrar_pantalla("editor_frases")
    def mostrar_historial(self):      self._mostrar_pantalla("historial")

    def mostrar_resultado_ronda(self, pts_a, pts_b, ganador, frase, entrada_a, entrada_b):
        self.pantallas["resultado_ronda"].cargar(pts_a, pts_b, ganador, frase, entrada_a, entrada_b)
        self._mostrar_pantalla("resultado_ronda")

    def mostrar_resultados_finales(self):
        self.pantallas["final"].cargar()
        self._mostrar_pantalla("final")

    def mostrar_dialogo_serial(self):
        """Diálogo para iniciar el servidor WiFi y esperar la Raspberry."""
        dlg = tk.Toplevel(self)
        dlg.title("Conectar Maqueta (WiFi)")
        dlg.geometry("360x200")
        dlg.grab_set()

        tk.Label(dlg, text="Conectar maqueta por WiFi",
                 font=("Arial", 11, "bold")).pack(pady=(16, 4))
        tk.Label(dlg, text=f"La interfaz escucha en el puerto {GestorSerial.PUERTO_ESCUCHA}.\n"
                            "Enciende la Raspberry con el switch en VERSUS.",
                 font=("Arial", 9), fg="#CCCCCC", justify="center").pack(pady=(0, 8))

        var_estado = tk.StringVar(value="")
        lbl_estado = tk.Label(dlg, textvariable=var_estado, font=("Arial", 10))
        lbl_estado.pack()

        def _conectar():
            if self.serial.conectar():
                self._conectado = True
                self.pantallas["menu"].actualizar_conexion(True)
                var_estado.set("✔ Servidor activo — esperando Raspberry...")
                lbl_estado.config(fg="green")
                dlg.after(1200, dlg.destroy)
            else:
                var_estado.set("✘ Error al iniciar servidor")
                lbl_estado.config(fg="red")

        def _desconectar():
            self.serial.desconectar()
            self._conectado = False
            self.pantallas["menu"].actualizar_conexion(False)
            var_estado.set("Servidor detenido")
            lbl_estado.config(fg="gray")

        marco_btns = tk.Frame(dlg)
        marco_btns.pack(pady=10)
        tk.Button(marco_btns, text="Iniciar servidor",  command=_conectar,    bg="#ccffcc", width=14).pack(side="left", padx=6)
        tk.Button(marco_btns, text="Detener servidor",  command=_desconectar, bg="#ffcccc", width=14).pack(side="left", padx=6)
        tk.Button(marco_btns, text="Cerrar",            command=dlg.destroy,               width=8 ).pack(side="left", padx=6)

    def enviar_serial(self, datos: str):
        """Envía datos por serial si hay conexión, y muestra en el log."""
        if self._conectado:
            self.serial.enviar(datos)
        if self._pantalla_actual is self.pantallas.get("juego"):
            self.pantallas["juego"]._registrar(f"→ {datos[:60]}")

    def _al_recibir_serial(self, crudo: str):
        """Callback del hilo serial al recibir datos."""
        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError:
            self.after(0, lambda: self._despachar_crudo(crudo))
            return
        self.after(0, lambda: self._despachar_json(datos))

    def _despachar_json(self, datos: dict):
        """Envía datos JSON a la pantalla de juego."""
        p = self.pantallas.get("juego")
        if p and self._pantalla_actual is p:
            p.recibir_de_pico(datos)

    def _despachar_crudo(self, crudo: str):
        """Muestra datos crudos de debug en el log del juego."""
        p = self.pantallas.get("juego")
        if p and self._pantalla_actual is p:
            p._registrar(f"[Pico] {crudo}")


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()