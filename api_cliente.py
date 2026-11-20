"""Cliente HTTP genérico y seguro para consumir APIs externas con 'requests'.

Reglas que implementa (y que se defienden en la evaluación):

  * Toda petición lleva timeout explícito: (conexión, lectura). Sin timeout,
    una API colgada deja el programa congelado para siempre.
  * Los códigos HTTP se tratan distinto según su significado:
      - 2xx  -> éxito, se valida que el cuerpo sea JSON.
      - 4xx  -> error NUESTRO (URL, parámetro o llave mal). Repetir no lo arregla:
                NO se reintenta.
      - 429  -> "demasiadas peticiones": se respeta la cabecera Retry-After.
      - 5xx  -> error temporal DEL SERVIDOR: se reintenta.
      - Sin red / timeout -> problema temporal: se reintenta.
  * Reintentos acotados (por defecto 3 intentos) con backoff exponencial:
    1 s, 2 s, 4 s ... (+ un pequeño azar para no golpear al servidor todos a la vez).
  * "Cortocircuito": si un servicio agotó sus reintentos, durante los siguientes
    30 s las demás consultas a ese servicio fallan de inmediato (van directo al
    Plan B) en vez de esperar otra vez todos los reintentos.
  * Certificados SSL siempre verificados (nunca verify=False) y solo HTTPS
    (http únicamente para localhost, que usan las pruebas y la demo).
  * Los mensajes de error que ve el usuario no exponen URLs, llaves ni trazas;
    el detalle técnico queda en el log.
"""
from __future__ import annotations

import logging
import random
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

import requests

from dominio.excepciones import ServicioExternoError

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_RESPUESTA = 2 * 1024 * 1024   # 2 MB: una respuesta más grande no es la esperada
_HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------
# Excepciones del cliente (todas heredan de EcoTechError vía ServicioExternoError)
# ---------------------------------------------------------------------
class ServicioNoDisponibleError(ServicioExternoError):
    """Sin red, timeout, 5xx o 429 persistentes: se agotaron los reintentos. -> Plan B."""


class SolicitudRechazadaError(ServicioExternoError):
    """El servidor respondió 4xx (o la URL está mal configurada). No se reintenta."""


class RespuestaInvalidaError(ServicioExternoError):
    """La API respondió, pero el contenido no es JSON válido o no tiene el formato esperado."""


_MENSAJES_4XX = {
    400: "la solicitud enviada no es válida (400)",
    401: "el servicio rechazó las credenciales o la llave de API (401)",
    403: "el servicio denegó el acceso; revise la llave de API (403)",
    404: "el recurso solicitado no existe: URL o dato inexistente (404)",
    405: "método no permitido por el servicio (405)",
    422: "el servicio no pudo procesar los datos enviados (422)",
}


class ClienteAPI:
    """Envuelve una requests.Session apuntando a una URL base."""

    def __init__(self, nombre: str, url_base: str, *,
                 timeout: tuple[float, float] = (3.05, 10.0),
                 max_intentos: int = 3,
                 espera_base: float = 1.0,
                 espera_maxima: float = 30.0,
                 cabeceras: dict[str, str] | None = None,
                 pausa_tras_falla: float = 30.0,
                 sesion: requests.Session | None = None,
                 dormir: Callable[[float], None] = time.sleep):
        if not 1 <= max_intentos <= 4:
            raise ValueError("max_intentos debe estar entre 1 y 4 (reintentos acotados).")
        self.nombre = nombre
        self._url_base = url_base.rstrip("/")
        self._timeout = timeout
        self._max_intentos = max_intentos
        self._espera_base = espera_base
        self._espera_maxima = espera_maxima
        self._sesion = sesion or requests.Session()
        self._sesion.headers.update({"Accept": "application/json",
                                     "User-Agent": "EcoTech-Solutions/3.0 (TI3021)"})
        if cabeceras:
            self._sesion.headers.update(cabeceras)
        self._dormir = dormir  # se inyecta para que las pruebas no esperen de verdad
        self._pausa_tras_falla = pausa_tras_falla
        self._no_disponible_hasta = 0.0

    # ------------------------------------------------------------------
    def obtener_json(self, ruta: str = "", params: dict | None = None) -> dict:
        """GET a url_base/ruta y devuelve el JSON como dict. Lanza ServicioExternoError."""
        url = f"{self._url_base}/{ruta.lstrip('/')}" if ruta else self._url_base
        self._verificar_esquema(url)
        if time.monotonic() < self._no_disponible_hasta:
            raise ServicioNoDisponibleError(
                f"{self.nombre}: el servicio falló hace instantes; se usa el respaldo sin reintentar.")
        ultimo_motivo = "error desconocido"

        for intento in range(1, self._max_intentos + 1):
            espera: float | None = None
            try:
                respuesta = self._sesion.get(url, params=params, timeout=self._timeout)
            except requests.exceptions.SSLError as error:
                # Certificado inválido o interceptado: NO se desactiva la verificación ni se reintenta
                logger.error("[%s] error de certificado SSL: %s", self.nombre, type(error).__name__)
                raise SolicitudRechazadaError(
                    f"{self.nombre}: no se pudo verificar el certificado de seguridad; "
                    "por seguridad no se continúa.") from error
            except requests.exceptions.Timeout:
                ultimo_motivo = "el servicio no respondió a tiempo (timeout)"
            except requests.exceptions.ConnectionError:
                ultimo_motivo = "no hay conexión con el servicio (red caída o DNS)"
            except (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema,
                    requests.exceptions.InvalidSchema) as error:
                logger.error("[%s] URL mal configurada: %s", self.nombre, type(error).__name__)
                raise SolicitudRechazadaError(f"{self.nombre}: la URL del servicio está mal configurada.") from error
            except requests.exceptions.RequestException as error:
                # Cualquier otra falla de requests se trata como temporal, pero se registra el tipo
                ultimo_motivo = f"falla de comunicación ({type(error).__name__})"
            else:
                codigo = respuesta.status_code
                if 200 <= codigo < 300:
                    logger.info("[%s] HTTP %s en intento %s", self.nombre, codigo, intento)
                    self._no_disponible_hasta = 0.0
                    return self._leer_json(respuesta)
                if codigo == 429:
                    ultimo_motivo = "el servicio limitó las consultas (429)"
                    espera = self._leer_retry_after(respuesta)
                    if espera is not None and espera > self._espera_maxima:
                        logger.warning("[%s] 429 con Retry-After=%ss (> máximo): no se espera", self.nombre, espera)
                        self._no_disponible_hasta = time.monotonic() + min(espera, 300)
                        raise ServicioNoDisponibleError(
                            f"{self.nombre}: {ultimo_motivo}; pide esperar {espera:.0f} s.", 429)
                elif 500 <= codigo < 600:
                    ultimo_motivo = f"el servidor tuvo un error interno ({codigo})"
                elif 400 <= codigo < 500:
                    motivo = _MENSAJES_4XX.get(codigo, f"el servicio rechazó la solicitud ({codigo})")
                    logger.warning("[%s] HTTP %s: no se reintenta (error del cliente)", self.nombre, codigo)
                    raise SolicitudRechazadaError(f"{self.nombre}: {motivo}.", codigo)
                else:
                    raise RespuestaInvalidaError(f"{self.nombre}: código HTTP inesperado ({codigo}).", codigo)

            logger.warning("[%s] intento %s/%s fallido: %s", self.nombre, intento, self._max_intentos, ultimo_motivo)
            if intento < self._max_intentos:
                if espera is None:
                    espera = self._calcular_backoff(intento)
                logger.info("[%s] esperando %.1f s antes de reintentar", self.nombre, espera)
                self._dormir(espera)

        self._no_disponible_hasta = time.monotonic() + self._pausa_tras_falla
        raise ServicioNoDisponibleError(
            f"{self.nombre}: {ultimo_motivo}. Se agotaron {self._max_intentos} intentos.")

    def cerrar(self) -> None:
        self._sesion.close()

    # ------------------------------------------------------------------
    def _calcular_backoff(self, intento: int) -> float:
        """Backoff exponencial: base * 2^(intento-1) + azar de hasta 10 %, con tope."""
        espera = self._espera_base * (2 ** (intento - 1))
        espera += random.uniform(0, espera * 0.1)
        return min(espera, self._espera_maxima)

    @staticmethod
    def _leer_retry_after(respuesta) -> float | None:
        """Retry-After puede venir en segundos ('5') o como fecha HTTP. Si es inválido -> None."""
        valor = respuesta.headers.get("Retry-After")
        if not valor:
            return None
        valor = valor.strip()
        if valor.isdigit():
            return float(valor)
        try:
            fecha = parsedate_to_datetime(valor)
        except (TypeError, ValueError):
            return None
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return max(0.0, (fecha - datetime.now(timezone.utc)).total_seconds())

    def _leer_json(self, respuesta) -> dict:
        if len(respuesta.content) > TAMANO_MAXIMO_RESPUESTA:
            raise RespuestaInvalidaError(f"{self.nombre}: la respuesta es demasiado grande.")
        try:
            datos = respuesta.json()
        except ValueError as error:  # requests.JSONDecodeError hereda de ValueError
            logger.error("[%s] cuerpo no es JSON válido", self.nombre)
            raise RespuestaInvalidaError(f"{self.nombre}: la respuesta no es JSON válido.") from error
        if not isinstance(datos, dict):
            raise RespuestaInvalidaError(f"{self.nombre}: se esperaba un objeto JSON.")
        return datos

    def _verificar_esquema(self, url: str) -> None:
        partes = urlparse(url)
        if partes.scheme == "https" and partes.netloc:
            return
        if partes.scheme == "http" and partes.hostname in _HOSTS_LOCALES:
            return
        logger.error("[%s] URL rechazada: esquema '%s' no permitido", self.nombre, partes.scheme)
        raise SolicitudRechazadaError(f"{self.nombre}: la URL del servicio está mal configurada (se exige HTTPS).")
