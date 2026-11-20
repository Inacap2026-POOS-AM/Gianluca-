"""Script de sincronización de datos externos (prueba en vivo de idempotencia).

Ejecutar:  python sincronizar.py
Correrlo dos veces seguidas NO duplica registros: la segunda vez todo aparece
como "YA EXISTÍA" y el conteo de filas no cambia. Sin red, usa el Plan B.
"""
import logging
import sys

from config import Configuracion, configurar_logging
from dominio.excepciones import EcoTechError
from menu_servicios import imprimir_sincronizacion, iniciar_sesion
from repositorio import UbicacionRepositorio, UsuarioRepositorio
from repositorio.conexion import cargar_variables_entorno, inicializar_bd, obtener_conexion
from seguridad.autenticacion import ServicioAutenticacion
from servicios import crear_servicios

logger = logging.getLogger(__name__)


def main() -> int:
    configurar_logging()
    cargar_variables_entorno()
    conexion = None
    servicios = None
    try:
        config = Configuracion.desde_entorno()
        conexion = obtener_conexion()
        inicializar_bd(conexion)
        # Solo usuarios autenticados pueden ejecutar la sincronización
        if iniciar_sesion(ServicioAutenticacion(UsuarioRepositorio(conexion), config.bcrypt_rondas)) is None:
            return 1
        servicios = crear_servicios(conexion, config)
        ubicaciones = UbicacionRepositorio(conexion)
        if not ubicaciones.listar_con_proyecto():
            print("  Aviso: ningún proyecto tiene ubicación; solo se sincronizarán tipos de cambio.")
            print("  (Ejecute main.py y cargue los datos de ejemplo o use Servicios externos > opción 6.)")
        imprimir_sincronizacion(servicios, ubicaciones, config)
    except (KeyboardInterrupt, EOFError):
        print("\nSincronización cancelada.")
        return 1
    except EcoTechError as error:
        print(f"No se pudo sincronizar: {error}")
        return 1
    except Exception:  # noqa: BLE001 - nunca mostrar una traza al usuario
        logger.exception("Error inesperado en sincronizar.py")
        print("Ocurrió un error inesperado. El detalle quedó en logs/ecotech.log.")
        return 1
    finally:
        if servicios is not None:
            servicios.cerrar()
        if conexion is not None:
            conexion.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
