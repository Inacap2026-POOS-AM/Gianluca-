"""Persistencia del clima: guardado idempotente (upsert) y lectura para el Plan B."""
import sqlite3

from dominio.clima import RegistroClima
from dominio.validaciones import normalizar_clave
from repositorio.base import RepositorioBase


class ClimaRepositorio(RepositorioBase):
    MENSAJE_DUPLICADO = "Esa medición de clima ya estaba registrada."

    _SQL_EXISTE = """
        SELECT 1 FROM registro_clima
        WHERE clave_ciudad = ? AND codigo_pais = ? AND medido_en = ?
    """
    # UPSERT: si la medición ya existe solo se actualiza 'obtenido_en' (y los valores),
    # así correr el script dos veces NO duplica filas.
    _SQL_UPSERT = """
        INSERT INTO registro_clima (clave_ciudad, ciudad, codigo_pais, latitud, longitud, temperatura,
                                    humedad, codigo_clima, viento_kmh, medido_en, obtenido_en)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (clave_ciudad, codigo_pais, medido_en) DO UPDATE SET
            temperatura  = excluded.temperatura,
            humedad      = excluded.humedad,
            codigo_clima = excluded.codigo_clima,
            viento_kmh   = excluded.viento_kmh,
            obtenido_en  = excluded.obtenido_en
    """
    _SQL_ULTIMO_POR_CIUDAD = """
        SELECT ciudad, codigo_pais, latitud, longitud, temperatura, humedad, codigo_clima,
               viento_kmh, medido_en, obtenido_en
        FROM registro_clima
        WHERE clave_ciudad = ? AND (? IS NULL OR codigo_pais = ?)
        ORDER BY obtenido_en DESC, medido_en DESC
        LIMIT 1
    """

    def guardar(self, registro: RegistroClima) -> bool:
        """Devuelve True si la fila es nueva y False si solo se actualizó."""
        clave = (registro.clave_ciudad, registro.codigo_pais, registro.medido_en)
        with self._transaccion() as cursor:
            existia = cursor.execute(self._SQL_EXISTE, clave).fetchone() is not None
            cursor.execute(self._SQL_UPSERT, (
                registro.clave_ciudad, registro.ciudad, registro.codigo_pais, registro.latitud,
                registro.longitud, registro.temperatura, registro.humedad, registro.codigo_clima,
                registro.viento_kmh, registro.medido_en, registro.obtenido_en,
            ))
        return not existia

    def ultimo_por_ciudad(self, ciudad: str, codigo_pais: str | None = None) -> RegistroClima | None:
        fila = self._consultar_uno(self._SQL_ULTIMO_POR_CIUDAD,
                                   (normalizar_clave(ciudad), codigo_pais, codigo_pais))
        return None if fila is None else self._fila_a_registro(fila)

    def contar(self) -> int:
        return self._consultar_uno("SELECT COUNT(*) AS total FROM registro_clima")["total"]

    @staticmethod
    def _fila_a_registro(fila: sqlite3.Row) -> RegistroClima:
        return RegistroClima(
            ciudad=fila["ciudad"], codigo_pais=fila["codigo_pais"], latitud=fila["latitud"],
            longitud=fila["longitud"], temperatura=fila["temperatura"], humedad=fila["humedad"],
            codigo_clima=fila["codigo_clima"], viento_kmh=fila["viento_kmh"],
            medido_en=fila["medido_en"], obtenido_en=fila["obtenido_en"],
        )
