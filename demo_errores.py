"""Demostración en vivo del manejo de errores HTTP, reintentos y Plan B (sin depender de internet).

Ejecutar:  python demo_errores.py

Levanta un servidor HTTP falso en 127.0.0.1 que responde a propósito con
200, 404, 429 (+Retry-After), 500, 503, respuestas lentas y JSON corrupto,
y muestra qué hace ClienteAPI en cada caso. Al final simula una caída total
de la API de clima y muestra el Plan B leyendo la base de datos.
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from api_cliente import ClienteAPI
from config import configurar_logging
from dominio.clima import RegistroClima
from dominio.excepciones import EcoTechError
from repositorio import ClimaRepositorio
from repositorio.conexion import inicializar_bd, obtener_conexion
from servicios.clima_servicio import ClimaServicio
from menu_servicios import mostrar_clima

CONTADORES: dict[str, int] = {}


class ManejadorFalso(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia el log por defecto del servidor
        return

    def _responder(self, codigo: int, cuerpo: str, cabeceras: dict | None = None):
        datos = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        for clave, valor in (cabeceras or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        try:
            self.wfile.write(datos)
        except (BrokenPipeError, ConnectionResetError):
            # El cliente ya cortó por timeout (caso /lento): es lo esperado en la demo
            self.close_connection = True

    def do_GET(self):  # noqa: N802 (nombre exigido por http.server)
        ruta = self.path.split("?")[0].strip("/")
        CONTADORES[ruta] = CONTADORES.get(ruta, 0) + 1
        vez = CONTADORES[ruta]
        ok = json.dumps({"estado": "ok", "llamada": vez})
        if ruta == "ok":
            self._responder(200, ok)
        elif ruta == "no-existe":
            self._responder(404, '{"error": "not found"}')
        elif ruta == "limite":           # 429 la primera vez, luego OK
            self._responder(429, '{"error": "too many"}', {"Retry-After": "1"}) if vez == 1 else self._responder(200, ok)
        elif ruta == "inestable":        # 503 dos veces, luego OK
            self._responder(503, '{"error": "unavailable"}') if vez <= 2 else self._responder(200, ok)
        elif ruta == "caido":            # 500 siempre
            self._responder(500, '{"error": "internal"}')
        elif ruta == "lento":            # tarda más que el timeout de lectura
            time.sleep(1.5)
            self._responder(200, ok)
        elif ruta == "json-corrupto":
            self._responder(200, "<html>esto no es JSON</html>")
        else:
            self._responder(404, "{}")


def probar(cliente: ClienteAPI, ruta: str, explicacion: str) -> None:
    print(f"\n>>> GET /{ruta}   ({explicacion})")
    inicio = time.monotonic()
    try:
        datos = cliente.obtener_json(ruta)
        print(f"    RESULTADO: éxito -> {datos}")
    except EcoTechError as error:
        codigo = getattr(error, "codigo_http", None)
        print(f"    RESULTADO: {type(error).__name__} (HTTP {codigo or '-'}) -> {error}")
    print(f"    Tiempo total: {time.monotonic() - inicio:.1f} s")


def demo_plan_b(puerto_cerrado: int) -> None:
    print("\n" + "=" * 70)
    print(" PLAN B: la API de clima está caída / sin red")
    print("=" * 70)
    conexion = obtener_conexion(":memory:")
    inicializar_bd(conexion)
    repo = ClimaRepositorio(conexion)
    hace_3_horas = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
    repo.guardar(RegistroClima("Antofagasta", "CL", -23.65, -70.4, 19.4, 68, 2, 14.0,
                               "2026-11-20T09:00", hace_3_horas))
    url_muerta = f"http://127.0.0.1:{puerto_cerrado}"
    servicio = ClimaServicio(ClienteAPI("Geocodificación", url_muerta, espera_base=0.3),
                             ClienteAPI("Clima", url_muerta, espera_base=0.3), repo)
    mostrar_clima(servicio.consultar("Antofagasta", "CL"))
    print("\n>>> Ciudad sin datos guardados y sin red:")
    try:
        servicio.consultar("Valdivia", "CL")
    except EcoTechError as error:
        print(f"  ! {error}")
    conexion.close()


def main() -> None:
    configurar_logging(nivel_consola=logging.INFO)  # muestra los reintentos en pantalla
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), ManejadorFalso)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}"
    cliente = ClienteAPI("API de prueba", url, timeout=(1, 1), max_intentos=3, espera_base=0.3)

    print("=" * 70)
    print(" DEMO: manejo diferenciado de códigos HTTP (servidor local falso)")
    print("=" * 70)
    probar(cliente, "ok", "200: éxito al primer intento")
    probar(cliente, "no-existe", "404: error del cliente -> NO se reintenta")
    probar(cliente, "limite", "429: respeta Retry-After = 1 s y reintenta")
    probar(cliente, "inestable", "503, 503, 200: backoff exponencial y éxito al 3er intento")
    probar(cliente, "caido", "500 siempre: 3 intentos acotados y luego se rinde")
    probar(cliente, "lento", "responde en 1.5 s con timeout de 1 s -> timeout y reintento")
    probar(cliente, "json-corrupto", "200 pero el cuerpo no es JSON -> error controlado")

    puerto = servidor.server_address[1]
    servidor.shutdown()
    servidor.server_close()
    cliente.cerrar()
    print("\n>>> Servidor apagado (simula 'sin red'):")
    probar(ClienteAPI("API de prueba", url, timeout=(1, 1), espera_base=0.3), "ok", "conexión rechazada")
    demo_plan_b(puerto)


if __name__ == "__main__":
    main()
