"""Clase base de los repositorios: transacciones y traducción de errores.

Todos los repositorios heredan de aquí, así el manejo de commit/rollback y la
conversión de errores de sqlite3 a errores del negocio se escribe una sola vez.
"""
import logging
import sqlite3
from contextlib import contextmanager

from dominio.excepciones import (DatoInvalidoError, EcoTechError, PersistenciaError,
                                 ReferenciaInvalidaError, RegistroDuplicadoError)

logger = logging.getLogger(__name__)
# U3: el usuario ve un mensaje genérico; el detalle técnico de sqlite3 solo va al log
MENSAJE_ERROR_BD = "Error interno de base de datos. El detalle quedó registrado en logs/ecotech.log."


class RepositorioBase:
    # Cada repositorio hijo redefine estos mensajes con su propio vocabulario
    MENSAJE_DUPLICADO = "El registro ya existe."
    MENSAJE_REFERENCIA = "La operación rompe una relación con otra tabla."

    def __init__(self, conexion: sqlite3.Connection):
        self._conexion = conexion

    @contextmanager
    def _transaccion(self):
        """Ejecuta un bloque de escrituras como una sola transacción (todo o nada).

        Si todo sale bien -> commit(). Si algo falla -> rollback() y se relanza
        el error traducido al vocabulario del negocio.
        """
        cursor = self._conexion.cursor()
        try:
            yield cursor
        except sqlite3.IntegrityError as error:
            self._conexion.rollback()
            raise self._traducir_error_integridad(error) from error
        except sqlite3.Error as error:
            self._conexion.rollback()
            logger.error("Error sqlite3 en transacción: %s", error)
            raise PersistenciaError(MENSAJE_ERROR_BD) from error
        except EcoTechError:
            # Error de negocio detectado a mitad de la transacción: se deshace y se relanza
            self._conexion.rollback()
            raise
        else:
            self._conexion.commit()
        finally:
            cursor.close()

    def _consultar_uno(self, sql: str, parametros: tuple = ()) -> sqlite3.Row | None:
        try:
            return self._conexion.execute(sql, parametros).fetchone()
        except sqlite3.Error as error:
            logger.error("Error sqlite3 en consulta: %s", error)
            raise PersistenciaError(MENSAJE_ERROR_BD) from error

    def _consultar_todos(self, sql: str, parametros: tuple = ()) -> list[sqlite3.Row]:
        try:
            return self._conexion.execute(sql, parametros).fetchall()
        except sqlite3.Error as error:
            logger.error("Error sqlite3 en consulta: %s", error)
            raise PersistenciaError(MENSAJE_ERROR_BD) from error

    def _traducir_error_integridad(self, error: sqlite3.IntegrityError) -> EcoTechError:
        logger.warning("Restricción de integridad: %s", error)
        mensaje = str(error).upper()
        if "UNIQUE" in mensaje or "PRIMARY KEY" in mensaje:
            return RegistroDuplicadoError(self.MENSAJE_DUPLICADO)
        if "FOREIGN KEY" in mensaje:
            return ReferenciaInvalidaError(self.MENSAJE_REFERENCIA)
        if "CHECK" in mensaje or "NOT NULL" in mensaje:
            return DatoInvalidoError("La base de datos rechazó un dato inválido.")
        return PersistenciaError(MENSAJE_ERROR_BD)
