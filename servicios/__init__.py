"""Servicios de integración con APIs externas (clima y divisas)."""
import sqlite3
from dataclasses import dataclass

from api_cliente import ClienteAPI
from config import Configuracion
from repositorio import ClimaRepositorio, TipoCambioRepositorio
from servicios.clima_servicio import ClimaServicio
from servicios.divisas_servicio import DivisasServicio


@dataclass
class ServiciosExternos:
    clima: ClimaServicio
    divisas: DivisasServicio
    repo_clima: ClimaRepositorio
    repo_tipo_cambio: TipoCambioRepositorio
    clientes: tuple[ClienteAPI, ...]

    def cerrar(self) -> None:
        for cliente in self.clientes:
            cliente.cerrar()


def crear_servicios(conexion: sqlite3.Connection, config: Configuracion) -> ServiciosExternos:
    comunes = {"timeout": config.timeout, "max_intentos": config.max_intentos}
    geo = ClienteAPI("Geocodificación (Open-Meteo)", config.url_geocodificacion, **comunes)
    clima = ClienteAPI("Clima (Open-Meteo)", config.url_clima, **comunes)

    url_divisas = config.url_divisas
    cabeceras = None
    if config.divisas_api_key:
        # Plan con llave: la llave viaja en una cabecera, NO en la URL (así no queda en logs ni historial)
        url_divisas = "https://v6.exchangerate-api.com/v6"
        cabeceras = {"Authorization": f"Bearer {config.divisas_api_key}"}
    divisas = ClienteAPI("Tipo de cambio (ExchangeRate-API)", url_divisas, cabeceras=cabeceras, **comunes)

    repo_clima, repo_tc = ClimaRepositorio(conexion), TipoCambioRepositorio(conexion)
    return ServiciosExternos(
        clima=ClimaServicio(geo, clima, repo_clima),
        divisas=DivisasServicio(divisas, repo_tc),
        repo_clima=repo_clima,
        repo_tipo_cambio=repo_tc,
        clientes=(geo, clima, divisas),
    )
