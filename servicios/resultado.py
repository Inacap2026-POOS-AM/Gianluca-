"""Resultado de una consulta externa: indica si el dato viene de la API o del respaldo local (Plan B)."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

T = TypeVar("T")

ORIGEN_API = "API"
ORIGEN_LOCAL = "BD local (Plan B)"


def describir_antiguedad(obtenido_en_iso: str, ahora: datetime | None = None) -> str:
    """'2026-11-20T13:05:00+00:00' -> 'hace 2 h 10 min'."""
    try:
        obtenido = datetime.fromisoformat(obtenido_en_iso)
    except ValueError:
        return "antigüedad desconocida"
    if obtenido.tzinfo is None:
        obtenido = obtenido.replace(tzinfo=timezone.utc)
    segundos = int(((ahora or datetime.now(timezone.utc)) - obtenido).total_seconds())
    if segundos < 60:
        return "hace menos de 1 min"
    minutos, horas, dias = segundos // 60, segundos // 3600, segundos // 86400
    if dias >= 1:
        return f"hace {dias} día(s) y {horas % 24} h"
    if horas >= 1:
        return f"hace {horas} h {minutos % 60} min"
    return f"hace {minutos} min"


def fecha_local(iso: str) -> str:
    """Muestra una fecha ISO UTC en la hora local del equipo: '2026-11-20 10:05'."""
    try:
        fecha = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone().strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class ResultadoConsulta(Generic[T]):
    dato: T
    origen: str = ORIGEN_API
    motivo: str | None = None  # por qué se usó el Plan B (mensaje seguro para el usuario)

    @property
    def es_respaldo(self) -> bool:
        return self.origen == ORIGEN_LOCAL

    def encabezado(self) -> str:
        obtenido = getattr(self.dato, "obtenido_en", "")
        if not self.es_respaldo:
            return f"Fuente: {self.origen} (datos en línea, {fecha_local(obtenido)})"
        return (f"AVISO - Fuente: {self.origen}. {self.motivo}\n"
                f"  Datos guardados el {fecha_local(obtenido)} ({describir_antiguedad(obtenido)}). "
                f"Pueden no estar actualizados.")
