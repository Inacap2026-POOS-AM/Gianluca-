"""Sincronización idempotente: descarga clima de las ubicaciones de proyectos y tipos de cambio.

Se puede ejecutar N veces seguidas: gracias a la restricción UNIQUE + UPSERT
la misma medición o la misma tasa nunca se guarda dos veces.
"""
from dataclasses import dataclass, field

from dominio.excepciones import EcoTechError
from repositorio.ubicacion_repo import UbicacionRepositorio
from servicios import ServiciosExternos
from servicios.resultado import fecha_local


@dataclass
class ResumenSincronizacion:
    nuevos: int = 0
    actualizados: int = 0
    desde_respaldo: int = 0
    fallidos: int = 0
    lineas: list[str] = field(default_factory=list)

    def registrar(self, etiqueta: str, resultado, fue_nuevo: bool | None) -> None:
        if resultado.es_respaldo:
            self.desde_respaldo += 1
            self.lineas.append(f"  [PLAN B] {etiqueta}: API no disponible, se mantiene el dato guardado el "
                               f"{fecha_local(resultado.dato.obtenido_en)}.")
        elif fue_nuevo:
            self.nuevos += 1
            self.lineas.append(f"  [NUEVO]  {etiqueta}")
        else:
            self.actualizados += 1
            self.lineas.append(f"  [YA EXISTÍA, actualizado] {etiqueta}")


def sincronizar(servicios: ServiciosExternos, ubicaciones: UbicacionRepositorio,
                monedas: tuple[str, ...]) -> ResumenSincronizacion:
    resumen = ResumenSincronizacion()
    # Cada elemento se procesa por separado: si una ciudad falla, las demás siguen
    for nombre_proyecto, ubicacion in ubicaciones.listar_con_proyecto():
        etiqueta = f"Clima {ubicacion.ciudad} ({ubicacion.codigo_pais}) - {nombre_proyecto}"
        try:
            resultado = servicios.clima.consultar(ubicacion.ciudad, ubicacion.codigo_pais)
            resumen.registrar(etiqueta, resultado, servicios.clima.ultimo_guardado_fue_nuevo)
        except EcoTechError as error:
            resumen.fallidos += 1
            resumen.lineas.append(f"  [ERROR]  {etiqueta}: {error}")
    for moneda in monedas:
        etiqueta = f"Tipo de cambio {moneda}/CLP"
        try:
            resultado = servicios.divisas.consultar(moneda)
            resumen.registrar(etiqueta, resultado, servicios.divisas.ultimo_guardado_fue_nuevo)
        except EcoTechError as error:
            resumen.fallidos += 1
            resumen.lineas.append(f"  [ERROR]  {etiqueta}: {error}")
    return resumen
