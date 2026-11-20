"""Consulta de clima para planificar proyectos, con degradación controlada (Plan B)."""
import logging

from api_cliente import ClienteAPI
from dominio.clima import RegistroClima
from dominio.excepciones import ServicioExternoError, SinDatosLocalesError
from dominio.validaciones import validar_ciudad, validar_codigo_pais
from repositorio.clima_repo import ClimaRepositorio
from servicios.deserializadores import DeserializadorClima
from servicios.resultado import ORIGEN_LOCAL, ResultadoConsulta

logger = logging.getLogger(__name__)

VARIABLES_ACTUALES = "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"


class ClimaServicio:
    def __init__(self, cliente_geo: ClienteAPI, cliente_clima: ClienteAPI, repositorio: ClimaRepositorio,
                 deserializador: DeserializadorClima | None = None):
        self._geo = cliente_geo
        self._clima = cliente_clima
        self._repo = repositorio
        self._deserializador = deserializador or DeserializadorClima()
        self.ultimo_guardado_fue_nuevo: bool | None = None

    def consultar(self, ciudad: str, codigo_pais: str | None = None) -> ResultadoConsulta[RegistroClima]:
        """1) valida la entrada  2) llama a la API  3) guarda (idempotente)  4) si falla -> Plan B."""
        ciudad = validar_ciudad(ciudad)
        codigo_pais = validar_codigo_pais(codigo_pais) if codigo_pais else None
        self.ultimo_guardado_fue_nuevo = None
        try:
            registro = self._consultar_api(ciudad, codigo_pais)
        except ServicioExternoError as error:
            logger.warning("Clima de '%s' no disponible en línea (%s). Se usa Plan B.", ciudad, type(error).__name__)
            return self._plan_b(ciudad, codigo_pais, str(error))
        self.ultimo_guardado_fue_nuevo = self._repo.guardar(registro)
        return ResultadoConsulta(registro)

    def probar_endpoint_invalido(self, ciudad: str = "Santiago", codigo_pais: str = "CL") -> ResultadoConsulta:
        """Diagnóstico para la prueba en vivo 'URL inválida': pide una ruta que no existe (404)."""
        try:
            self._clima.obtener_json("endpoint-que-no-existe", params={"latitude": 0, "longitude": 0})
        except ServicioExternoError as error:
            return self._plan_b(validar_ciudad(ciudad), validar_codigo_pais(codigo_pais), str(error))
        raise SinDatosLocalesError("El endpoint de prueba respondió OK (no se pudo simular el fallo).")

    # ------------------------------------------------------------------
    def _consultar_api(self, ciudad: str, codigo_pais: str | None) -> RegistroClima:
        parametros_geo = {"name": ciudad, "count": 1, "language": "es", "format": "json"}
        if codigo_pais:
            parametros_geo["countryCode"] = codigo_pais
        geo = self._geo.obtener_json("search", params=parametros_geo)
        ubicacion = self._deserializador.ubicacion_desde_json(geo, ciudad)
        datos = self._clima.obtener_json("forecast", params={
            "latitude": ubicacion["latitud"],
            "longitude": ubicacion["longitud"],
            "current": VARIABLES_ACTUALES,
            "timezone": "auto",
        })
        return self._deserializador.clima_desde_json(datos, ubicacion)

    def _plan_b(self, ciudad: str, codigo_pais: str | None, motivo: str) -> ResultadoConsulta[RegistroClima]:
        local = self._repo.ultimo_por_ciudad(ciudad, codigo_pais)
        if local is None:
            raise SinDatosLocalesError(
                f"{motivo}\n  Tampoco hay datos guardados de '{ciudad}'. Intente cuando vuelva la conexión.")
        return ResultadoConsulta(local, origen=ORIGEN_LOCAL, motivo=motivo)
