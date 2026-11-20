"""Tipo de cambio y cálculo de pagos internacionales, con degradación controlada (Plan B)."""
import logging

from api_cliente import ClienteAPI
from dominio.empleado import Empleado
from dominio.excepciones import ServicioExternoError, SinDatosLocalesError
from dominio.tipo_cambio import PagoInternacional, TipoCambio
from dominio.validaciones import validar_moneda
from repositorio.tipo_cambio_repo import TipoCambioRepositorio
from servicios.deserializadores import DeserializadorTipoCambio, ahora_utc_iso
from servicios.resultado import ORIGEN_LOCAL, ResultadoConsulta

logger = logging.getLogger(__name__)


class DivisasServicio:
    def __init__(self, cliente: ClienteAPI, repositorio: TipoCambioRepositorio,
                 deserializador: DeserializadorTipoCambio | None = None):
        self._cliente = cliente
        self._repo = repositorio
        self._deserializador = deserializador or DeserializadorTipoCambio()
        self.ultimo_guardado_fue_nuevo: bool | None = None

    def consultar(self, moneda: str) -> ResultadoConsulta[TipoCambio]:
        moneda = validar_moneda(moneda)          # lista blanca: solo códigos ISO conocidos
        self.ultimo_guardado_fue_nuevo = None
        if moneda == "CLP":
            return ResultadoConsulta(TipoCambio("CLP", 1.0, ahora_utc_iso(), ahora_utc_iso()))
        try:
            datos = self._cliente.obtener_json(f"latest/{moneda}")
            tasa = self._deserializador.desde_json(datos, moneda)
        except ServicioExternoError as error:
            logger.warning("Tipo de cambio %s no disponible en línea (%s). Se usa Plan B.",
                           moneda, type(error).__name__)
            local = self._repo.ultimo(moneda)
            if local is None:
                raise SinDatosLocalesError(
                    f"{error}\n  Tampoco hay un tipo de cambio {moneda} guardado para usar como respaldo.")
            return ResultadoConsulta(local, origen=ORIGEN_LOCAL, motivo=str(error))
        self.ultimo_guardado_fue_nuevo = self._repo.guardar(tasa)
        return ResultadoConsulta(tasa)

    def calcular_pagos(self, empleados: list[Empleado], moneda: str) \
            -> tuple[ResultadoConsulta[TipoCambio], list[PagoInternacional]]:
        """Convierte el sueldo líquido (CLP) de cada empleado a la moneda del país del proyecto."""
        resultado = self.consultar(moneda)
        tasa = resultado.dato
        pagos = [
            PagoInternacional(
                rut=e.rut, nombre=e.nombre, liquido_clp=e.calcular_sueldo_liquido(),
                moneda=tasa.moneda, monto=tasa.convertir_desde_clp(e.calcular_sueldo_liquido()), tasa=tasa,
            )
            for e in empleados
        ]
        return resultado, pagos
