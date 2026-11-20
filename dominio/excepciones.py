"""Excepciones propias del dominio EcoTech.

Todas heredan de EcoTechError, así el menú puede capturar cualquier error
del negocio con un solo except y mostrar un mensaje claro al usuario.
"""


class EcoTechError(Exception):
    """Excepción base para todos los errores del sistema EcoTech."""


class DatoInvalidoError(EcoTechError, ValueError):
    """Un dato ingresado no cumple las reglas del negocio (texto vacío, email mal escrito, etc.)."""


class RutInvalidoError(DatoInvalidoError):
    """El RUT no tiene formato válido o su dígito verificador no corresponde."""


class SueldoInvalidoError(DatoInvalidoError):
    """El sueldo no es un número mayor que cero."""


class RegistroDuplicadoError(EcoTechError):
    """Se intenta guardar un registro que ya existe (RUT o nombre repetido)."""


class RegistroNoEncontradoError(EcoTechError):
    """El registro buscado no existe en la base de datos."""


class ReferenciaInvalidaError(EcoTechError):
    """Se rompe la integridad referencial (ej. departamento inexistente o con empleados)."""


class PersistenciaError(EcoTechError):
    """Falla técnica de la base de datos (conexión, archivo bloqueado, SQL inválido)."""


# ---------------------------------------------------------------------
# Unidad 3: servicios externos y seguridad
# ---------------------------------------------------------------------
class ServicioExternoError(EcoTechError):
    """Falla al consumir una API externa (red, código HTTP o datos inválidos).

    El mensaje (str(error)) es apto para mostrarse al usuario: nunca incluye
    URLs con llaves, trazas ni datos internos. El detalle técnico va al log.
    """

    def __init__(self, mensaje: str, codigo_http: int | None = None):
        super().__init__(mensaje)
        self.codigo_http = codigo_http


class SinDatosLocalesError(EcoTechError):
    """La API no respondió y tampoco hay datos guardados para usar el Plan B."""


class AutenticacionError(EcoTechError):
    """Base de los errores de inicio de sesión y control de acceso."""


class CredencialesInvalidasError(AutenticacionError):
    """Usuario o contraseña incorrectos (mensaje genérico a propósito)."""


class CuentaBloqueadaError(AutenticacionError):
    """Demasiados intentos fallidos: la cuenta está bloqueada temporalmente."""


class AccesoDenegadoError(AutenticacionError):
    """El usuario no tiene permiso para la acción solicitada."""
