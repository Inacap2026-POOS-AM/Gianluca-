"""Configuración leída desde variables de entorno (.env) y registro de logs.

Nada sensible se escribe en el código: URLs, llaves de API y parámetros
viven en .env (que está en .gitignore). Se sube solo .env.example.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dominio.excepciones import DatoInvalidoError
from dominio.validaciones import validar_moneda

RAIZ_PROYECTO = Path(__file__).resolve().parent
CARPETA_LOGS = RAIZ_PROYECTO / "logs"


def _leer_float(nombre: str, por_defecto: float, minimo: float, maximo: float) -> float:
    texto = os.getenv(nombre, "").strip()
    if not texto:
        return por_defecto
    try:
        valor = float(texto)
    except ValueError as error:
        raise DatoInvalidoError(f"La variable {nombre} del .env debe ser numérica.") from error
    if not minimo <= valor <= maximo:
        raise DatoInvalidoError(f"La variable {nombre} del .env debe estar entre {minimo} y {maximo}.")
    return valor


@dataclass(frozen=True)
class Configuracion:
    url_geocodificacion: str
    url_clima: str
    url_divisas: str
    divisas_api_key: str = ""          # opcional: plan con llave de ExchangeRate-API
    timeout_conexion: float = 3.05
    timeout_lectura: float = 10.0
    max_intentos: int = 3
    bcrypt_rondas: int = 12
    monedas_sincronizar: tuple[str, ...] = ("USD", "EUR", "PEN", "COP")

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        monedas = os.getenv("ECOTECH_MONEDAS_SINCRONIZAR", "USD,EUR,PEN,COP")
        return cls(
            url_geocodificacion=os.getenv("ECOTECH_URL_GEOCODIFICACION",
                                          "https://geocoding-api.open-meteo.com/v1").strip(),
            url_clima=os.getenv("ECOTECH_URL_CLIMA", "https://api.open-meteo.com/v1").strip(),
            url_divisas=os.getenv("ECOTECH_URL_DIVISAS", "https://open.er-api.com/v6").strip(),
            divisas_api_key=os.getenv("ECOTECH_DIVISAS_API_KEY", "").strip(),
            timeout_conexion=_leer_float("ECOTECH_HTTP_TIMEOUT_CONEXION", 3.05, 0.5, 30),
            timeout_lectura=_leer_float("ECOTECH_HTTP_TIMEOUT_LECTURA", 10.0, 1, 60),
            max_intentos=int(_leer_float("ECOTECH_HTTP_MAX_INTENTOS", 3, 1, 4)),
            bcrypt_rondas=int(_leer_float("ECOTECH_BCRYPT_ROUNDS", 12, 4, 15)),
            monedas_sincronizar=tuple(validar_moneda(m) for m in monedas.split(",") if m.strip()),
        )

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.timeout_conexion, self.timeout_lectura)

    def __repr__(self) -> str:
        # Nunca mostrar la llave de API si alguien imprime la configuración
        llave = "***" if self.divisas_api_key else "(sin llave)"
        return f"Configuracion(clima={self.url_clima!r}, divisas={self.url_divisas!r}, api_key={llave})"


def configurar_logging(nivel_consola: int = logging.CRITICAL + 1) -> None:
    """Detalle técnico -> logs/ecotech.log. La consola solo muestra mensajes amigables.

    Para la demo de errores se puede pasar nivel_consola=logging.INFO y ver los reintentos.
    """
    CARPETA_LOGS.mkdir(exist_ok=True)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for manejador in list(raiz.handlers):
        raiz.removeHandler(manejador)
    archivo = logging.FileHandler(CARPETA_LOGS / "ecotech.log", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    raiz.addHandler(archivo)
    consola = logging.StreamHandler()
    consola.setLevel(nivel_consola)
    consola.setFormatter(logging.Formatter("    [log] %(message)s"))
    raiz.addHandler(consola)
    # urllib3 registra la URL completa de cada petición: se silencia para no filtrar llaves al log
    logging.getLogger("urllib3").setLevel(logging.WARNING)
