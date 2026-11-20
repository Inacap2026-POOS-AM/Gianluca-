"""Usuario del sistema (quien inicia sesión), distinto de Empleado."""
from dataclasses import dataclass

ROLES = ("admin", "operador")


@dataclass(frozen=True)
class Usuario:
    """Sesión autenticada. A propósito NO guarda la contraseña ni su hash:
    el hash solo existe dentro del repositorio y del servicio de autenticación."""
    id: int
    nombre_usuario: str
    rol: str

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"
