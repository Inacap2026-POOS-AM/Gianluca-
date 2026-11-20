"""Persistencia del tipo de cambio: upsert idempotente y lectura para el Plan B."""
import sqlite3

from dominio.tipo_cambio import TipoCambio
from repositorio.base import RepositorioBase


class TipoCambioRepositorio(RepositorioBase):
    _SQL_EXISTE = "SELECT 1 FROM tipo_cambio WHERE moneda = ? AND actualizado_api = ?"
    _SQL_UPSERT = """
        INSERT INTO tipo_cambio (moneda, valor_clp, actualizado_api, obtenido_en)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (moneda, actualizado_api) DO UPDATE SET
            valor_clp   = excluded.valor_clp,
            obtenido_en = excluded.obtenido_en
    """
    _SQL_ULTIMO = """
        SELECT moneda, valor_clp, actualizado_api, obtenido_en
        FROM tipo_cambio
        WHERE moneda = ?
        ORDER BY actualizado_api DESC, obtenido_en DESC
        LIMIT 1
    """

    def guardar(self, tasa: TipoCambio) -> bool:
        """Devuelve True si la fila es nueva y False si solo se actualizó."""
        with self._transaccion() as cursor:
            existia = cursor.execute(self._SQL_EXISTE, (tasa.moneda, tasa.actualizado_api)).fetchone() is not None
            cursor.execute(self._SQL_UPSERT, (tasa.moneda, tasa.valor_clp, tasa.actualizado_api, tasa.obtenido_en))
        return not existia

    def ultimo(self, moneda: str) -> TipoCambio | None:
        fila = self._consultar_uno(self._SQL_ULTIMO, (moneda,))
        return None if fila is None else self._fila_a_tasa(fila)

    def contar(self) -> int:
        return self._consultar_uno("SELECT COUNT(*) AS total FROM tipo_cambio")["total"]

    @staticmethod
    def _fila_a_tasa(fila: sqlite3.Row) -> TipoCambio:
        return TipoCambio(moneda=fila["moneda"], valor_clp=fila["valor_clp"],
                          actualizado_api=fila["actualizado_api"], obtenido_en=fila["obtenido_en"])
