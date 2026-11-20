"""Tipo de cambio y cálculo de pagos en moneda extranjera."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dominio.excepciones import DatoInvalidoError
from dominio.reportable import Reportable

# Monedas que no usan decimales en sus pagos
_SIN_DECIMALES = {"CLP", "PYG", "JPY", "COP"}


@dataclass(frozen=True)
class TipoCambio(Reportable):
    """Cuántos pesos chilenos (CLP) vale 1 unidad de 'moneda'."""
    moneda: str
    valor_clp: float
    actualizado_api: str     # fecha en que la API publicó la tasa (ISO 8601)
    obtenido_en: str         # cuándo la descargamos (ISO 8601 UTC) -> sirve para el Plan B

    def convertir_desde_clp(self, monto_clp: float) -> Decimal:
        """Convierte un monto en CLP a esta moneda usando Decimal (sin errores de redondeo de float)."""
        if monto_clp < 0:
            raise DatoInvalidoError("El monto a convertir no puede ser negativo.")
        resultado = Decimal(str(monto_clp)) / Decimal(str(self.valor_clp))
        paso = Decimal("1") if self.moneda in _SIN_DECIMALES else Decimal("0.01")
        return resultado.quantize(paso, rounding=ROUND_HALF_UP)

    def resumen(self) -> str:
        return (f"[Tipo cambio]  1 {self.moneda} = ${self.valor_clp:,.4f} CLP "
                f"(publicado {self.actualizado_api[:10]})")

    def __str__(self) -> str:
        return self.resumen()


@dataclass(frozen=True)
class PagoInternacional:
    rut: str
    nombre: str
    liquido_clp: float
    moneda: str
    monto: Decimal
    tasa: TipoCambio

    def __str__(self) -> str:
        return (f"{self.rut:<11} {self.nombre:<22} líquido ${self.liquido_clp:>12,.0f} CLP  ->  "
                f"{self.monto:>14,} {self.moneda}")
