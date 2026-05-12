
# StrangerTEC - Morse Translator
# Raspberry Pi Pico W - MicroPython (Thonny)
#
# INTEGRACIÓN DE RED:
#   - WiFi y socket se conectan UNA SOLA VEZ al inicio.
#   - El bucle principal NO tiene sleeps extra ni recv bloqueantes.
#   - Si la red falla, la maqueta sigue en modo LOCAL sin trabarse.
#   - En Modo VERSUS envía la letra al servidor (C# / Python en VS).


from machine import Pin, PWM
import network
import socket
import time


# PINES

data = Pin(27, Pin.OUT)
clk  = Pin(26, Pin.OUT)

led14 = Pin(10, Pin.OUT)
led15 = Pin(11, Pin.OUT)
led16 = Pin(13, Pin.OUT)

led_builtin = Pin("LED", Pin.OUT)

btn_punto = Pin(16, Pin.IN, Pin.PULL_DOWN)
btn_raya  = Pin(19, Pin.IN, Pin.PULL_DOWN)

sw1 = Pin(17, Pin.IN, Pin.PULL_DOWN)   # GPIO17 = LOCAL
sw2 = Pin(18, Pin.IN, Pin.PULL_DOWN)   # GPIO18 = VERSUS

buzzer = PWM(Pin(5))
buzzer.freq(800)
buzzer.duty_u16(0)



# SECUENCIAS DE LEDS

led1  = [0, 0, 0, 0, 0, 0, 0, 1]
led2  = [0, 0, 0, 0, 0, 0, 1, 0]
led3  = [0, 0, 0, 0, 0, 1, 0, 0]
led4  = [0, 0, 0, 0, 1, 0, 0, 0]
led5  = [0, 0, 0, 1, 0, 0, 0, 0]
led6  = [0, 0, 1, 0, 0, 0, 0, 0]
led7  = [0, 1, 0, 0, 0, 0, 0, 0]
led8  = [1, 0, 0, 0, 0, 0, 0, 0]

led9  = [0, 0, 0, 0, 0, 0, 0, 1]
led10 = [0, 0, 0, 0, 0, 0, 1, 0]
led11 = [0, 0, 0, 0, 0, 1, 0, 0]
led12 = [0, 0, 0, 0, 1, 0, 0, 0]
led13 = [0, 0, 0, 1, 0, 0, 0, 0]



# DICCIONARIO MORSE

# La letra en texto es el string que se enviará por socket.
# 0 = punto (.)  /  1 = raya (-)

diccionario_morse = {
    (0, 1):              (led1,  1, 1, "A"),
    (1, 0, 0, 0):        (led1,  2, 1, "B"),
    (1, 0, 1, 0):        (led2,  1, 1, "C"),
    (1, 0, 0):           (led2,  2, 1, "D"),
    (0,):                (led3,  1, 1, "E"),
    (0, 0, 1, 0):        (led3,  2, 1, "F"),
    (1, 1, 0):           (led4,  1, 1, "G"),
    (0, 0, 0, 0):        (led4,  2, 1, "H"),
    (0, 0):              (led5,  1, 1, "I"),
    (0, 1, 1, 1):        (led5,  2, 1, "J"),
    (1, 0, 1):           (led6,  1, 1, "K"),
    (0, 1, 0, 0):        (led6,  2, 1, "L"),
    (1, 1):              (led7,  1, 1, "M"),
    (1, 0):              (led7,  2, 1, "N"),
    (1, 1, 1):           (led8,  1, 1, "O"),
    (0, 1, 1, 0):        (led8,  2, 1, "P"),
    (1, 1, 0, 1):        (led9,  1, 2, "Q"),
    (0, 1, 0):           (led9,  2, 2, "R"),
    (0, 0, 0):           (led10, 1, 2, "S"),
    (1,):                (led10, 2, 2, "T"),
    (0, 0, 1):           (led11, 1, 2, "U"),
    (0, 0, 0, 1):        (led11, 2, 2, "V"),
    (0, 1, 1):           (led12, 1, 2, "W"),
    (1, 0, 0, 1):        (led12, 2, 2, "X"),
    (1, 0, 1, 1):        (led13, 1, 2, "Y"),
    (1, 1, 0, 0):        (led13, 2, 2, "Z"),

    (1, 1, 1, 1, 1):     (led1,  3, 1, "0"),
    (0, 1, 1, 1, 1):     (led2,  3, 1, "1"),
    (0, 0, 1, 1, 1):     (led3,  3, 1, "2"),
    (0, 0, 0, 1, 1):     (led4,  3, 1, "3"),
    (0, 0, 0, 0, 1):     (led5,  3, 1, "4"),
    (0, 0, 0, 0, 0):     (led6,  3, 1, "5"),
    (1, 0, 0, 0, 0):     (led7,  3, 1, "6"),
    (1, 1, 0, 0, 0):     (led8,  3, 1, "7"),
    (1, 1, 1, 0, 0):     (led9,  3, 2, "8"),
    (1, 1, 1, 1, 0):     (led10, 3, 2, "9"),
    (0, 1, 0, 1, 0):     (led11, 3, 2, "+"),
    (1, 0, 0, 0, 0, 1):  (led12, 3, 2, "-"),
}



# CONFIGURACIÓN DE RED

WIFI_SSID     = "cele"
WIFI_PASSWORD = "c3l3xt3."
SERVER_IP     = "10.55.219.37"
SERVER_PORT   = 8001
WIFI_TIMEOUT  = 10   # segundos; si no conecta, sigue en modo local



# FUNCIONES DE RED


def conectar_wifi():
    """
    Intenta conectar al WiFi con timeout de WIFI_TIMEOUT segundos.
    Si no lo logra, retorna False y el programa sigue en modo local.
    NO tiene bucle infinito — nunca congela la Raspberry.
    """
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        if wlan.isconnected():
            print("[WiFi] Ya conectado:", wlan.ifconfig()[0])
            return True

        print("[WiFi] Conectando a '" + WIFI_SSID + "'...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        inicio = time.time()
        while not wlan.isconnected():
            if time.time() - inicio >= WIFI_TIMEOUT:
                print("[WiFi] Timeout. Continuando en modo local.")
                return False
            time.sleep(0.2)   # espera corta solo durante la conexión inicial

        print("[WiFi] Conectado. IP: " + wlan.ifconfig()[0])
        return True

    except Exception as e:
        print("[WiFi] Error: " + str(e))
        return False


def crear_socket():
    """
    Crea el socket TCP y lo conecta al servidor UNA SOLA VEZ.
    Se configura como NO BLOQUEANTE para no congelar el bucle principal.
    Retorna el socket listo, o None si falla.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_IP, SERVER_PORT))
        s.setblocking(False)   # ← NO BLOQUEANTE: clave para no congelar la Raspberry
        print("[Socket] Conectado a " + SERVER_IP + ":" + str(SERVER_PORT))
        return s
    except Exception as e:
        print("[Socket] No se pudo conectar: " + str(e))
        return None


def enviar_letra_socket(sock, letra):
    """
    Envía la letra como string al servidor, terminada en '\n' para que
    la interfaz pueda separar mensajes en el buffer línea por línea.
    Protegido con try/except: si la red cae o el servidor se apaga,
    la Raspberry NO se traba y sigue funcionando en modo local.
    """
    if sock is None:
        return
    try:
        sock.sendall((letra + '\n').encode())
        print("[Socket] Enviado: '" + letra + "'")
    except Exception as e:
        print("[Socket] Fallo al enviar '" + letra + "': " + str(e))



# FUNCIONES DE HARDWARE


def pulso_clock():
    clk.value(1)
    time.sleep(0.001)
    clk.value(0)
    time.sleep(0.001)


def buzzer_on(freq=800):
    buzzer.freq(freq)
    buzzer.duty_u16(30000)


def buzzer_off():
    buzzer.duty_u16(0)


def apagar_filas():
    led14.value(0)
    led15.value(0)
    led16.value(0)


def apagar_registro():
    """Limpia los DOS registros enviando 16 ceros."""
    for _ in range(16):
        data.value(0)
        pulso_clock()


def apagar_todo():
    apagar_filas()
    apagar_registro()
    buzzer_off()
    led_builtin.value(0)


def encender_fila(fila):
    apagar_filas()
    if fila == 1:
        led14.value(1)
    elif fila == 2:
        led15.value(1)
    elif fila == 3:
        led16.value(1)


def proyectar_resultado(bits, fila, registro):
    apagar_todo()
    time.sleep(0.05)

    if registro == 1:
        for _ in range(8):
            data.value(0)
            pulso_clock()
        for bit in bits:
            data.value(bit)
            pulso_clock()

    elif registro == 2:
        for bit in bits:
            data.value(bit)
            pulso_clock()
        for _ in range(8):
            data.value(0)
            pulso_clock()

    encender_fila(fila)


def get_mode():
    local  = sw1.value()   # GPIO17 = LOCAL
    versus = sw2.value()   # GPIO18 = VERSUS

    if local and not versus:
        return "LOCAL"
    elif versus and not local:
        return "VERSUS"
    elif local and versus:
        return "ERROR_DOS_MODOS"
    else:
        return "SIN_MODO"



# INICIO — hardware

apagar_todo()
print("StrangerTEC listo")

modo = get_mode()
if modo == "LOCAL":
    print("Modo: LOCAL - 1 maqueta, 2 jugadores")
elif modo == "VERSUS":
    print("Modo: VERSUS - 2 maquetas por WiFi")
elif modo == "ERROR_DOS_MODOS":
    print("ERROR: apague uno de los switches")
else:
    print("Sin modo seleccionado - active un switch")

for _ in range(3):
    led_builtin.value(1)
    time.sleep(0.1)
    led_builtin.value(0)
    time.sleep(0.1)



# INICIO — red  (UNA SOLA VEZ, FUERA del while True)

# Solo intenta conectar si el switch de VERSUS está activo desde el inicio.
# Si el usuario cambia el switch en caliente, el socket seguirá siendo None
# hasta reiniciar (comportamiento seguro y predecible).

client_socket = None

if modo == "VERSUS":
    wifi_ok = conectar_wifi()
    if wifi_ok:
        client_socket = crear_socket()
    else:
        print("[Red] Modo VERSUS sin red: operando en local.")
else:
    print("[Red] Modo LOCAL: sin conexión de red.")



# VARIABLES DEL BUCLE PRINCIPAL

secuencia          = []
ultimo_toque       = time.time()
led_encendida      = False
tiempo_apagado_led = 0



# BUCLE PRINCIPAL
# Sin time.sleep() al final — máxima velocidad para no perder
# pulsos de los botones. El único sleep es el de 0.001 s dentro
# de pulso_clock(), que es parte del protocolo del 74LS164D.

while True:

    # ── Botón PUNTO ─────────────────────────────────────────
    if btn_punto.value() == 1:
        if led_encendida:
            apagar_todo()
            led_encendida = False

        buzzer_on(800)
        led_builtin.value(1)
        while btn_punto.value() == 1:
            time.sleep(0.001)
        buzzer_off()
        led_builtin.value(0)

        secuencia.append(0)
        ultimo_toque = time.time()
        print("Secuencia:", secuencia, "-> punto")

    # ── Botón RAYA ──────────────────────────────────────────
    elif btn_raya.value() == 1:
        if led_encendida:
            apagar_todo()
            led_encendida = False

        buzzer_on(400)
        led_builtin.value(1)
        while btn_raya.value() == 1:
            time.sleep(0.001)
        buzzer_off()
        led_builtin.value(0)

        secuencia.append(1)
        ultimo_toque = time.time()
        print("Secuencia:", secuencia, "-> raya")

    # ── Timeout de 2 s → identificar letra ───
    if len(secuencia) > 0 and time.time() - ultimo_toque >= 5:
        resultado = diccionario_morse.get(tuple(secuencia))
        secuencia = []   # limpiar ANTES de enviar para evitar doble proceso

        if resultado:
            bits, fila, registro, letra = resultado   # ← desempaqueta la letra
            print("Letra:", letra, "-> bits:", bits, "fila:", fila, "registro:", registro)

            proyectar_resultado(bits, fila, registro)
            led_encendida      = True
            tiempo_apagado_led = time.time() + 3

            # ── Envío por socket solo en Modo VERSUS ────────
            if get_mode() == "VERSUS":
                # Reconectar si el socket murió, ANTES de intentar enviar
                if client_socket is None:
                    wifi_ok = conectar_wifi()
                    if wifi_ok:
                        client_socket = crear_socket()
                # Enviar UNA SOLA VEZ la letra final ya decodificada
                if client_socket is not None:
                    enviar_letra_socket(client_socket, letra)

        else:
            print("Secuencia no encontrada:", secuencia)
            apagar_todo()
            led_encendida = False

    # ── Apagado automático del LED tras 3 s ─────────────────
    if led_encendida and time.time() >= tiempo_apagado_led:
        apagar_todo()
        led_encendida = False

    # ── NO hay time.sleep() aquí ─────────────────────────────
    # El bucle corre a máxima velocidad para capturar cada pulsación.
