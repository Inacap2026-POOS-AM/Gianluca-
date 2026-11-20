"""Autenticación de usuarios con bcrypt (hash + salt) y bloqueo por intentos fallidos.

Por qué bcrypt y no hashlib.sha256 / md5:
  * bcrypt genera un SALT aleatorio por contraseña y lo guarda dentro del hash,
    así dos usuarios con la misma clave tienen hashes distintos (no sirven
    tablas arcoíris).
  * Es LENTO a propósito (factor de costo = rondas): probar millones de claves
    por fuerza bruta se vuelve impracticable. sha256 es rapidísimo -> malo para claves.
"""
import logging
from datetime import datetime, timedelta, timezone

import bcrypt

from dominio.excepciones import (AccesoDenegadoError, CredencialesInvalidasError, CuentaBloqueadaError,
                                 DatoInvalidoError)
from dominio.usuario import ROLES, Usuario
from dominio.validaciones import (LARGO_MAXIMO_CONTRASENA_BYTES, validar_contrasena_nueva,
                                  validar_nombre_usuario)
from repositorio.usuario_repo import UsuarioRepositorio

logger = logging.getLogger(__name__)

MENSAJE_GENERICO = "Usuario o contraseña incorrectos."


class ServicioAutenticacion:
    MAX_INTENTOS = 5          # intentos fallidos seguidos antes de bloquear
    MINUTOS_BLOQUEO = 5

    def __init__(self, repositorio: UsuarioRepositorio, rondas_bcrypt: int = 12):
        self._repo = repositorio
        self._rondas = rondas_bcrypt
        # Hash "señuelo": si el usuario no existe igual se ejecuta checkpw, así el tiempo
        # de respuesta no revela qué nombres de usuario existen (enumeración de usuarios).
        self._hash_senuelo = bcrypt.hashpw(b"senuelo-no-es-una-clave", bcrypt.gensalt(rounds=rondas_bcrypt))

    # ----------------------------- hashing -----------------------------
    def generar_hash(self, contrasena: str) -> str:
        return bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt(rounds=self._rondas)).decode("ascii")

    @staticmethod
    def _verificar(contrasena: str, hash_guardado: bytes) -> bool:
        try:
            return bcrypt.checkpw(contrasena.encode("utf-8"), hash_guardado)
        except ValueError:
            # Hash corrupto en la BD: se trata como credencial inválida y se registra
            logger.error("Hash de contraseña con formato inválido en la BD")
            return False

    # ----------------------------- usuarios ----------------------------
    def hay_usuarios(self) -> bool:
        return self._repo.contar() > 0

    def registrar(self, nombre_usuario: str, contrasena: str, rol: str = "operador",
                  solicitante: Usuario | None = None) -> Usuario:
        """Crea un usuario. Si ya existen usuarios, solo un admin puede crear otros."""
        if self.hay_usuarios() and (solicitante is None or not solicitante.es_admin):
            raise AccesoDenegadoError("Solo un administrador puede crear usuarios.")
        if rol not in ROLES:
            raise DatoInvalidoError(f"Rol inválido. Use: {', '.join(ROLES)}.")
        nombre_usuario = validar_nombre_usuario(nombre_usuario)
        validar_contrasena_nueva(contrasena, nombre_usuario)
        creado_en = datetime.now(timezone.utc).isoformat(timespec="seconds")
        usuario = self._repo.crear(nombre_usuario, self.generar_hash(contrasena), rol, creado_en)
        logger.info("Usuario '%s' creado con rol %s", nombre_usuario, rol)
        return usuario

    # ------------------------------ login ------------------------------
    def iniciar_sesion(self, nombre_usuario: str, contrasena: str) -> Usuario:
        # Validación de entrada: vacíos o absurdamente largos se rechazan sin tocar la BD
        if not isinstance(nombre_usuario, str) or not nombre_usuario.strip():
            raise CredencialesInvalidasError("Debe ingresar el usuario.")
        if not isinstance(contrasena, str) or not contrasena:
            raise CredencialesInvalidasError("Debe ingresar la contraseña.")
        if len(nombre_usuario) > 30 or len(contrasena.encode("utf-8")) > LARGO_MAXIMO_CONTRASENA_BYTES:
            raise CredencialesInvalidasError(MENSAJE_GENERICO)

        nombre_usuario = nombre_usuario.strip().lower()
        registro = self._repo.obtener_credenciales(nombre_usuario)
        if registro is None:
            self._verificar(contrasena, self._hash_senuelo)  # mismo costo de tiempo
            logger.warning("Login fallido: usuario inexistente")
            raise CredencialesInvalidasError(MENSAJE_GENERICO)

        usuario, hash_guardado, intentos, bloqueado_hasta = registro
        ahora = datetime.now(timezone.utc)
        if bloqueado_hasta and datetime.fromisoformat(bloqueado_hasta) > ahora:
            logger.warning("Login rechazado: cuenta '%s' bloqueada", nombre_usuario)
            raise CuentaBloqueadaError(
                f"Cuenta bloqueada temporalmente por intentos fallidos. Intente en {self.MINUTOS_BLOQUEO} minutos.")

        if not self._verificar(contrasena, hash_guardado.encode("ascii")):
            nuevo_bloqueo = None
            if intentos + 1 >= self.MAX_INTENTOS:
                nuevo_bloqueo = (ahora + timedelta(minutes=self.MINUTOS_BLOQUEO)).isoformat(timespec="seconds")
            self._repo.registrar_fallo(usuario.id, nuevo_bloqueo)
            logger.warning("Login fallido para '%s' (intento %s)", nombre_usuario, intentos + 1)
            raise CredencialesInvalidasError(MENSAJE_GENERICO)

        self._repo.reiniciar_intentos(usuario.id)
        logger.info("Inicio de sesión correcto: '%s'", nombre_usuario)
        return usuario
