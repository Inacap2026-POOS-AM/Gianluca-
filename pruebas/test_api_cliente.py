"""Pruebas del ClienteAPI: timeout, reintentos, backoff, 4xx/429/5xx y errores de red.

Se usa una sesión falsa (no hay red) y un 'dormir' falso que anota las esperas,
así las pruebas son instantáneas y deterministas.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from api_cliente import (ClienteAPI, RespuestaInvalidaError, ServicioNoDisponibleError,
                         SolicitudRechazadaError)


class RespuestaFalsa:
    def __init__(self, codigo: int, cuerpo=None, cabeceras: dict | None = None):
        self.status_code = codigo
        self.headers = cabeceras or {}
        self._texto = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo if cuerpo is not None else {})
        self.content = self._texto.encode("utf-8")

    def json(self):
        try:
            return json.loads(self._texto)
        except json.JSONDecodeError as error:
            raise requests.exceptions.JSONDecodeError(error.msg, error.doc, error.pos) from error


class SesionFalsa:
    """Devuelve (o lanza) los elementos de 'guion' en orden y registra cada llamada."""

    def __init__(self, *guion):
        self.guion = list(guion)
        self.headers = {}
        self.llamadas = []

    def get(self, url, params=None, timeout=None):
        self.llamadas.append({"url": url, "params": params, "timeout": timeout})
        siguiente = self.guion.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    def close(self):
        return None


def crear_cliente(*guion, max_intentos=3):
    esperas = []
    sesion = SesionFalsa(*guion)
    cliente = ClienteAPI("Prueba", "https://api.ejemplo.cl/v1", max_intentos=max_intentos,
                         sesion=sesion, dormir=esperas.append)
    return cliente, sesion, esperas


class PruebasCodigosHttp(unittest.TestCase):
    def test_200_devuelve_json_y_usa_timeout(self):
        cliente, sesion, esperas = crear_cliente(RespuestaFalsa(200, {"ok": True}))
        self.assertEqual(cliente.obtener_json("recurso", params={"a": 1}), {"ok": True})
        self.assertEqual(sesion.llamadas[0]["url"], "https://api.ejemplo.cl/v1/recurso")
        self.assertIsNotNone(sesion.llamadas[0]["timeout"], "Toda petición debe llevar timeout")
        self.assertEqual(esperas, [])

    def test_404_no_se_reintenta(self):
        cliente, sesion, esperas = crear_cliente(RespuestaFalsa(404), RespuestaFalsa(200))
        with self.assertRaises(SolicitudRechazadaError) as contexto:
            cliente.obtener_json("no-existe")
        self.assertEqual(contexto.exception.codigo_http, 404)
        self.assertEqual(len(sesion.llamadas), 1)   # un solo intento
        self.assertEqual(esperas, [])

    def test_401_no_se_reintenta(self):
        cliente, sesion, _ = crear_cliente(RespuestaFalsa(401))
        with self.assertRaises(SolicitudRechazadaError):
            cliente.obtener_json()
        self.assertEqual(len(sesion.llamadas), 1)

    def test_500_se_reintenta_hasta_el_maximo(self):
        cliente, sesion, esperas = crear_cliente(*[RespuestaFalsa(500)] * 3)
        with self.assertRaises(ServicioNoDisponibleError):
            cliente.obtener_json()
        self.assertEqual(len(sesion.llamadas), 3)
        self.assertEqual(len(esperas), 2)   # espera entre intentos, no después del último

    def test_backoff_exponencial(self):
        cliente, _, esperas = crear_cliente(*[RespuestaFalsa(503)] * 4, max_intentos=4)
        with self.assertRaises(ServicioNoDisponibleError):
            cliente.obtener_json()
        # base 1 s -> ~1, ~2, ~4 (+ hasta 10 % de azar)
        for espera, esperado in zip(esperas, [1, 2, 4]):
            self.assertGreaterEqual(espera, esperado)
            self.assertLessEqual(espera, esperado * 1.1)

    def test_503_y_luego_exito(self):
        cliente, sesion, _ = crear_cliente(RespuestaFalsa(503), RespuestaFalsa(200, {"v": 1}))
        self.assertEqual(cliente.obtener_json(), {"v": 1})
        self.assertEqual(len(sesion.llamadas), 2)

    def test_429_respeta_retry_after(self):
        cliente, _, esperas = crear_cliente(RespuestaFalsa(429, cabeceras={"Retry-After": "7"}),
                                            RespuestaFalsa(200, {"v": 1}))
        self.assertEqual(cliente.obtener_json(), {"v": 1})
        self.assertEqual(esperas, [7.0])

    def test_429_con_espera_excesiva_no_bloquea(self):
        cliente, sesion, esperas = crear_cliente(RespuestaFalsa(429, cabeceras={"Retry-After": "3600"}))
        with self.assertRaises(ServicioNoDisponibleError):
            cliente.obtener_json()
        self.assertEqual(esperas, [])
        self.assertEqual(len(sesion.llamadas), 1)

    def test_cortocircuito_tras_agotar_reintentos(self):
        cliente, sesion, _ = crear_cliente(*[RespuestaFalsa(500)] * 3, RespuestaFalsa(200, {"v": 1}))
        with self.assertRaises(ServicioNoDisponibleError):
            cliente.obtener_json()
        with self.assertRaises(ServicioNoDisponibleError):
            cliente.obtener_json()          # falla inmediato: no vuelve a llamar a la API
        self.assertEqual(len(sesion.llamadas), 3)

    def test_maximo_de_intentos_acotado(self):
        with self.assertRaises(ValueError):
            ClienteAPI("x", "https://a.cl", max_intentos=10)


class PruebasRedYContenido(unittest.TestCase):
    def test_sin_red_se_reintenta_y_falla_controlado(self):
        cliente, sesion, _ = crear_cliente(*[requests.exceptions.ConnectionError("dns")] * 3)
        with self.assertRaises(ServicioNoDisponibleError) as contexto:
            cliente.obtener_json()
        self.assertEqual(len(sesion.llamadas), 3)
        self.assertNotIn("dns", str(contexto.exception))  # no se filtra el detalle técnico

    def test_timeout_se_reintenta(self):
        cliente, sesion, _ = crear_cliente(requests.exceptions.ReadTimeout(), RespuestaFalsa(200, {"v": 2}))
        self.assertEqual(cliente.obtener_json(), {"v": 2})
        self.assertEqual(len(sesion.llamadas), 2)

    def test_error_ssl_no_se_reintenta(self):
        cliente, sesion, _ = crear_cliente(requests.exceptions.SSLError("cert"), RespuestaFalsa(200))
        with self.assertRaises(SolicitudRechazadaError):
            cliente.obtener_json()
        self.assertEqual(len(sesion.llamadas), 1)

    def test_json_corrupto(self):
        cliente, _, _ = crear_cliente(RespuestaFalsa(200, "<html>no</html>"))
        with self.assertRaises(RespuestaInvalidaError):
            cliente.obtener_json()

    def test_json_que_no_es_objeto(self):
        cliente, _, _ = crear_cliente(RespuestaFalsa(200, [1, 2, 3]))
        with self.assertRaises(RespuestaInvalidaError):
            cliente.obtener_json()

    def test_http_externo_rechazado(self):
        cliente = ClienteAPI("x", "http://api.ejemplo.cl", sesion=SesionFalsa())
        with self.assertRaises(SolicitudRechazadaError):
            cliente.obtener_json()


class _Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):  # noqa: N802
        codigo = int(self.path.strip("/").split("?")[0] or 200)
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"codigo": %d}' % codigo)


class PruebasConServidorReal(unittest.TestCase):
    """Integración con 'requests' de verdad contra un servidor local."""

    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Manejador)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        self.esperas = []
        self.cliente = ClienteAPI("Local", self.url, timeout=(1, 1), dormir=self.esperas.append)

    def tearDown(self):
        self.cliente.cerrar()

    def test_200(self):
        self.assertEqual(self.cliente.obtener_json("200"), {"codigo": 200})

    def test_404_real(self):
        with self.assertRaises(SolicitudRechazadaError):
            self.cliente.obtener_json("404")
        self.assertEqual(self.esperas, [])

    def test_500_real(self):
        with self.assertRaises(ServicioNoDisponibleError):
            self.cliente.obtener_json("500")
        self.assertEqual(len(self.esperas), 2)


if __name__ == "__main__":
    unittest.main()
