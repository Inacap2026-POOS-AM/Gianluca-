"""Deserializadores propios: validan el JSON de las APIs y lo convierten en objetos del dominio.

Nunca se confía en la forma del JSON: si falta un campo, cambia de tipo o
trae un valor fuera de rango, se lanza RespuestaInvalidaError (no KeyError
ni TypeError sueltos que botarían el programa).
"""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from api_cliente import RespuestaInvalidaError
from dominio.clima import RegistroClima
from dominio.excepciones import DatoInvalidoError
from dominio.tipo_cambio import TipoCambio


def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DeserializadorBase:
    FUENTE = "API"

    def _campo(self, datos: dict, clave: str, tipos: tuple, contexto: str):
        if not isinstance(datos, dict) or clave not in datos:
            raise RespuestaInvalidaError(f"{self.FUENTE}: falta el campo '{clave}' en {contexto}.")
        valor = datos[clave]
        # bool es subclase de int: se rechaza para que True no pase como número
        if isinstance(valor, bool) or not isinstance(valor, tipos):
            raise RespuestaInvalidaError(f"{self.FUENTE}: el campo '{clave}' tiene un tipo inesperado.")
        return valor

    def _numero(self, datos: dict, clave: str, contexto: str, minimo: float, maximo: float) -> float:
        valor = float(self._campo(datos, clave, (int, float), contexto))
        if not math.isfinite(valor) or not minimo <= valor <= maximo:
            raise RespuestaInvalidaError(f"{self.FUENTE}: '{clave}' fuera de rango ({valor}).")
        return valor


class DeserializadorClima(DeserializadorBase):
    """Convierte las respuestas de Open-Meteo (geocodificación + pronóstico) en RegistroClima."""
    FUENTE = "Open-Meteo"

    def ubicacion_desde_json(self, datos: dict, ciudad_consultada: str) -> dict:
        """Toma el primer resultado de la geocodificación. Sin resultados -> la ciudad no existe."""
        resultados = datos.get("results") if isinstance(datos, dict) else None
        if not resultados:
            # Respuesta 200 válida pero vacía: es un dato del usuario, no una caída de la API
            raise DatoInvalidoError(f"No se encontró la ciudad '{ciudad_consultada}'. Revise el nombre o el país.")
        if not isinstance(resultados, list) or not isinstance(resultados[0], dict):
            raise RespuestaInvalidaError(f"{self.FUENTE}: 'results' no tiene el formato esperado.")
        primero = resultados[0]
        codigo_pais = self._campo(primero, "country_code", (str,), "results[0]").upper()
        return {
            "ciudad": self._campo(primero, "name", (str,), "results[0]").strip()[:60],
            "codigo_pais": codigo_pais[:2],
            "latitud": self._numero(primero, "latitude", "results[0]", -90, 90),
            "longitud": self._numero(primero, "longitude", "results[0]", -180, 180),
        }

    def clima_desde_json(self, datos: dict, ubicacion: dict) -> RegistroClima:
        actual = self._campo(datos, "current", (dict,), "la respuesta")
        medido_en = self._campo(actual, "time", (str,), "current")
        try:
            datetime.fromisoformat(medido_en)
        except ValueError as error:
            raise RespuestaInvalidaError(f"{self.FUENTE}: fecha de medición inválida.") from error
        return RegistroClima(
            ciudad=ubicacion["ciudad"],
            codigo_pais=ubicacion["codigo_pais"],
            latitud=ubicacion["latitud"],
            longitud=ubicacion["longitud"],
            temperatura=round(self._numero(actual, "temperature_2m", "current", -90, 60), 1),
            humedad=int(self._numero(actual, "relative_humidity_2m", "current", 0, 100)),
            codigo_clima=int(self._numero(actual, "weather_code", "current", 0, 99)),
            viento_kmh=round(self._numero(actual, "wind_speed_10m", "current", 0, 500), 1),
            medido_en=medido_en,
            obtenido_en=ahora_utc_iso(),
        )


class DeserializadorTipoCambio(DeserializadorBase):
    """Convierte la respuesta de ExchangeRate-API (latest/{MONEDA}) en un TipoCambio a CLP."""
    FUENTE = "ExchangeRate-API"

    def desde_json(self, datos: dict, moneda: str) -> TipoCambio:
        resultado = self._campo(datos, "result", (str,), "la respuesta")
        if resultado != "success":
            tipo_error = datos.get("error-type", "desconocido")
            raise RespuestaInvalidaError(f"{self.FUENTE}: la API informó un error ({str(tipo_error)[:40]}).")
        base = self._campo(datos, "base_code", (str,), "la respuesta")
        if base.upper() != moneda:
            raise RespuestaInvalidaError(f"{self.FUENTE}: se pidió {moneda} y llegó {base[:3]}.")
        # El endpoint abierto usa 'rates'; el plan con llave usa 'conversion_rates'
        tasas = datos.get("rates") or datos.get("conversion_rates")
        if not isinstance(tasas, dict):
            raise RespuestaInvalidaError(f"{self.FUENTE}: no vienen tasas de cambio.")
        valor_clp = self._numero(tasas, "CLP", "rates", 1e-9, 1e9)
        if valor_clp <= 0:
            raise RespuestaInvalidaError(f"{self.FUENTE}: tasa CLP no positiva.")
        return TipoCambio(
            moneda=moneda,
            valor_clp=valor_clp,
            actualizado_api=self._fecha_publicacion(datos),
            obtenido_en=ahora_utc_iso(),
        )

    def _fecha_publicacion(self, datos: dict) -> str:
        texto = self._campo(datos, "time_last_update_utc", (str,), "la respuesta")
        try:
            fecha = parsedate_to_datetime(texto)  # 'Fri, 20 Nov 2026 00:02:31 +0000'
        except (TypeError, ValueError) as error:
            raise RespuestaInvalidaError(f"{self.FUENTE}: fecha de publicación inválida.") from error
        return fecha.astimezone(timezone.utc).isoformat(timespec="seconds")
