"""Registro de clima obtenido desde la API (o desde la BD en modo Plan B)."""
from dataclasses import dataclass

from dominio.reportable import Reportable
from dominio.validaciones import normalizar_clave

# Códigos WMO que usa Open-Meteo para el "estado del tiempo"
DESCRIPCION_WMO = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Niebla", 48: "Niebla con escarcha",
    51: "Llovizna ligera", 53: "Llovizna moderada", 55: "Llovizna intensa",
    56: "Llovizna helada ligera", 57: "Llovizna helada intensa",
    61: "Lluvia ligera", 63: "Lluvia moderada", 65: "Lluvia intensa",
    66: "Lluvia helada ligera", 67: "Lluvia helada intensa",
    71: "Nevada ligera", 73: "Nevada moderada", 75: "Nevada intensa", 77: "Granos de nieve",
    80: "Chubascos ligeros", 81: "Chubascos moderados", 82: "Chubascos violentos",
    85: "Chubascos de nieve ligeros", 86: "Chubascos de nieve intensos",
    95: "Tormenta eléctrica", 96: "Tormenta con granizo ligero", 99: "Tormenta con granizo intenso",
}
_TORMENTA = {95, 96, 99}
_PRECIPITACION = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86}


@dataclass(frozen=True)
class RegistroClima(Reportable):
    """Datos climáticos relevantes para planificar la ejecución de un proyecto.

    Es inmutable (frozen): una medición no se modifica, se reemplaza por otra.
    Los valores ya llegan validados por DeserializadorClima.
    """
    ciudad: str
    codigo_pais: str
    latitud: float
    longitud: float
    temperatura: float          # °C
    humedad: int                # %
    codigo_clima: int           # código WMO
    viento_kmh: float
    medido_en: str              # hora de la medición informada por la API (hora local de la ciudad)
    obtenido_en: str            # cuándo la descargamos (ISO 8601 UTC) -> sirve para el Plan B

    @property
    def clave_ciudad(self) -> str:
        return normalizar_clave(self.ciudad)

    @property
    def descripcion(self) -> str:
        return DESCRIPCION_WMO.get(self.codigo_clima, f"Código WMO {self.codigo_clima}")

    def evaluar_operacion(self) -> str:
        """Recomendación para la planificación de trabajos en terreno."""
        if self.codigo_clima in _TORMENTA:
            return "REPROGRAMAR: tormenta eléctrica, suspender trabajos en exterior."
        if self.viento_kmh >= 50:
            return "REPROGRAMAR: viento fuerte, suspender trabajos en altura (paneles, aerogeneradores)."
        if self.codigo_clima in _PRECIPITACION:
            return "PRECAUCIÓN: precipitaciones, priorizar tareas bajo techo."
        if self.temperatura >= 32:
            return "PRECAUCIÓN: calor extremo, jornadas cortas e hidratación."
        if self.temperatura <= 0:
            return "PRECAUCIÓN: riesgo de heladas en superficies y equipos."
        return "APTO: condiciones normales para trabajos en terreno."

    def resumen(self) -> str:
        return (f"[Clima]        {self.ciudad} ({self.codigo_pais}) {self.temperatura:.1f} °C, "
                f"humedad {self.humedad}%, {self.descripcion}, viento {self.viento_kmh:.0f} km/h "
                f"(medido {self.medido_en})")

    def __str__(self) -> str:
        return self.resumen()
