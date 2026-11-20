"""Persistencia de usuarios. Solo maneja hashes: nunca recibe ni guarda contraseñas en texto plano."""
import sqlite3

from dominio.excepciones import RegistroNoEncontradoError
from dominio.usuario import Usuario
from repositorio.base import RepositorioBase


class UsuarioRepositorio(RepositorioBase):
    MENSAJE_DUPLICADO = "Ya existe un usuario con ese nombre."

    def crear(self, nombre_usuario: str, hash_contrasena: str, rol: str, creado_en: str) -> Usuario:
        with self._transaccion() as cursor:
            cursor.execute(
                "INSERT INTO usuario (nombre_usuario, hash_contrasena, rol, creado_en) VALUES (?, ?, ?, ?)",
                (nombre_usuario, hash_contrasena, rol, creado_en),
            )
            nuevo_id = cursor.lastrowid
        return Usuario(nuevo_id, nombre_usuario, rol)

    def obtener_credenciales(self, nombre_usuario: str) -> tuple[Usuario, str, int, str | None] | None:
        """Devuelve (usuario, hash, intentos_fallidos, bloqueado_hasta) o None si no existe."""
        fila = self._consultar_uno(
            "SELECT id, nombre_usuario, rol, hash_contrasena, intentos_fallidos, bloqueado_hasta "
            "FROM usuario WHERE nombre_usuario = ?",
            (nombre_usuario,),
        )
        if fila is None:
            return None
        return self._fila_a_usuario(fila), fila["hash_contrasena"], fila["intentos_fallidos"], fila["bloqueado_hasta"]

    def registrar_fallo(self, id_usuario: int, bloqueado_hasta: str | None) -> None:
        with self._transaccion() as cursor:
            cursor.execute(
                "UPDATE usuario SET intentos_fallidos = intentos_fallidos + 1, bloqueado_hasta = ? WHERE id = ?",
                (bloqueado_hasta, id_usuario),
            )

    def reiniciar_intentos(self, id_usuario: int) -> None:
        with self._transaccion() as cursor:
            cursor.execute(
                "UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?", (id_usuario,)
            )

    def actualizar_hash(self, id_usuario: int, hash_contrasena: str) -> None:
        with self._transaccion() as cursor:
            cursor.execute("UPDATE usuario SET hash_contrasena = ? WHERE id = ?", (hash_contrasena, id_usuario))
            if cursor.rowcount == 0:
                raise RegistroNoEncontradoError("El usuario no existe.")

    def listar(self) -> list[Usuario]:
        filas = self._consultar_todos("SELECT id, nombre_usuario, rol FROM usuario ORDER BY nombre_usuario")
        return [self._fila_a_usuario(f) for f in filas]

    def contar(self) -> int:
        return self._consultar_uno("SELECT COUNT(*) AS total FROM usuario")["total"]

    @staticmethod
    def _fila_a_usuario(fila: sqlite3.Row) -> Usuario:
        return Usuario(fila["id"], fila["nombre_usuario"], fila["rol"])
