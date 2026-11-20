"""Pruebas de deserializadores, persistencia idempotente, Plan B y pagos internacionales."""
import unittest
from decimal import Decimal

from api_cliente import RespuestaInvalidaError, ServicioNoDisponibleError, SolicitudRechazadaError
from dominio import Empleado
from dominio.excepciones import DatoInvalidoError, SinDatosLocalesError
from repositorio import ClimaRepositorio, TipoCambioRepositorio
from repositorio.conexion import inicializar_bd, obtener_conexion
from servicios.clima_servicio import ClimaServicio
from servicios.deserializadores import DeserializadorClima, DeserializadorTipoCambio
from servicios.divisas_servicio import DivisasServicio
from servicios.resultado import ORIGEN_LOCAL

GEO_OK = {"results": [{"name": "Arequipa", "country_code": "PE", "latitude": -16.39, "longitude": -71.53}]}
CLIMA_OK = {"current": {"time": "2026-11-20T10:00", "interval": 900, "temperature_2m": 21.3,
                        "relative_humidity_2m": 35, "weather_code": 1, "wind_speed_10m": 12.5}}
DIVISA_OK = {"result": "success", "base_code": "USD", "time_last_update_utc": "Fri, 20 Nov 2026 00:02:31 +0000",
             "rates": {"USD": 1, "CLP": 950.0, "PEN": 3.7}}


class ClienteFalso:
    """Imita a ClienteAPI: devuelve un dict o lanza la excepción configurada."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = 0

    def obtener_json(self, ruta="", params=None):
        self.llamadas += 1
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


class BaseBD(unittest.TestCase):
    def setUp(self):
        self.conexion = obtener_conexion(":memory:")
        inicializar_bd(self.conexion)
        self.repo_clima = ClimaRepositorio(self.conexion)
        self.repo_tc = TipoCambioRepositorio(self.conexion)

    def tearDown(self):
        self.conexion.close()


class PruebasDeserializadores(unittest.TestCase):
    def test_clima_valido(self):
        d = DeserializadorClima()
        registro = d.clima_desde_json(CLIMA_OK, d.ubicacion_desde_json(GEO_OK, "Arequipa"))
        self.assertEqual((registro.ciudad, registro.codigo_pais, registro.humedad), ("Arequipa", "PE", 35))
        self.assertEqual(registro.descripcion, "Mayormente despejado")

    def test_ciudad_inexistente(self):
        with self.assertRaises(DatoInvalidoError):
            DeserializadorClima().ubicacion_desde_json({"generationtime_ms": 0.1}, "Ciudadfalsa")

    def test_campo_faltante(self):
        d = DeserializadorClima()
        ubicacion = d.ubicacion_desde_json(GEO_OK, "Arequipa")
        with self.assertRaises(RespuestaInvalidaError):
            d.clima_desde_json({"current": {"time": "2026-11-20T10:00"}}, ubicacion)

    def test_tipo_incorrecto_o_fuera_de_rango(self):
        d = DeserializadorClima()
        ubicacion = d.ubicacion_desde_json(GEO_OK, "Arequipa")
        for campo, valor in (("temperature_2m", "21"), ("relative_humidity_2m", 150), ("temperature_2m", True)):
            malo = {"current": {**CLIMA_OK["current"], campo: valor}}
            with self.subTest(campo=campo, valor=valor), self.assertRaises(RespuestaInvalidaError):
                d.clima_desde_json(malo, ubicacion)

    def test_divisa_valida(self):
        tasa = DeserializadorTipoCambio().desde_json(DIVISA_OK, "USD")
        self.assertEqual(tasa.valor_clp, 950.0)
        self.assertTrue(tasa.actualizado_api.startswith("2026-11-20T00:02:31"))

    def test_divisa_error_api_y_base_distinta(self):
        with self.assertRaises(RespuestaInvalidaError):
            DeserializadorTipoCambio().desde_json({"result": "error", "error-type": "unsupported-code"}, "USD")
        with self.assertRaises(RespuestaInvalidaError):
            DeserializadorTipoCambio().desde_json(DIVISA_OK, "EUR")
        with self.assertRaises(RespuestaInvalidaError):
            DeserializadorTipoCambio().desde_json({**DIVISA_OK, "rates": {"CLP": -5}}, "USD")


class PruebasClimaServicio(BaseBD):
    def servicio(self, geo, clima):
        return ClimaServicio(ClienteFalso(geo), ClienteFalso(clima), self.repo_clima)

    def test_idempotencia_dos_ejecuciones_no_duplican(self):
        servicio = self.servicio(GEO_OK, CLIMA_OK)
        servicio.consultar("Arequipa", "PE")
        self.assertTrue(servicio.ultimo_guardado_fue_nuevo)
        servicio.consultar("arequipa", "PE")      # segunda ejecución (incluso con otra capitalización)
        self.assertFalse(servicio.ultimo_guardado_fue_nuevo)
        self.assertEqual(self.repo_clima.contar(), 1)

    def test_plan_b_sin_red_usa_datos_locales(self):
        self.servicio(GEO_OK, CLIMA_OK).consultar("Arequipa", "PE")
        caido = self.servicio(ServicioNoDisponibleError("sin red"), None)
        resultado = caido.consultar("Arequipa", "PE")
        self.assertEqual(resultado.origen, ORIGEN_LOCAL)
        self.assertTrue(resultado.es_respaldo)
        self.assertIn("Datos guardados el", resultado.encabezado())  # se informa la antigüedad
        self.assertEqual(resultado.dato.temperatura, 21.3)

    def test_plan_b_tambien_ante_404(self):
        self.servicio(GEO_OK, CLIMA_OK).consultar("Arequipa", "PE")
        resultado = self.servicio(GEO_OK, SolicitudRechazadaError("404", 404)).consultar("Arequipa", "PE")
        self.assertTrue(resultado.es_respaldo)

    def test_sin_red_y_sin_datos_mensaje_controlado(self):
        with self.assertRaises(SinDatosLocalesError):
            self.servicio(ServicioNoDisponibleError("sin red"), None).consultar("Valdivia")

    def test_validacion_de_entrada_antes_de_llamar_a_la_api(self):
        geo = ClienteFalso(GEO_OK)
        servicio = ClimaServicio(geo, ClienteFalso(CLIMA_OK), self.repo_clima)
        for entrada in ("", "123", "Santiago&count=100", "../../etc", "<script>", "a" * 61):
            with self.subTest(entrada=entrada), self.assertRaises(DatoInvalidoError):
                servicio.consultar(entrada)
        with self.assertRaises(DatoInvalidoError):
            servicio.consultar("Lima", "XX")
        self.assertEqual(geo.llamadas, 0)  # ninguna entrada inválida llegó a la API

    def test_ciudades_validas(self):
        servicio = self.servicio(GEO_OK, CLIMA_OK)
        for ciudad in ("Medellín", "Puerto Montt", "San Pedro de la Paz", "O'Higgins"):
            with self.subTest(ciudad=ciudad):
                servicio.consultar(ciudad)


class PruebasDivisas(BaseBD):
    def test_idempotencia_y_plan_b(self):
        DivisasServicio(ClienteFalso(DIVISA_OK), self.repo_tc).consultar("usd")
        DivisasServicio(ClienteFalso(DIVISA_OK), self.repo_tc).consultar("USD")
        self.assertEqual(self.repo_tc.contar(), 1)
        resultado = DivisasServicio(ClienteFalso(ServicioNoDisponibleError("x")), self.repo_tc).consultar("USD")
        self.assertTrue(resultado.es_respaldo)
        self.assertEqual(resultado.dato.valor_clp, 950.0)

    def test_moneda_fuera_de_lista_blanca(self):
        cliente = ClienteFalso(DIVISA_OK)
        for moneda in ("XXX", "US", "USD; DROP TABLE", ""):
            with self.subTest(moneda=moneda), self.assertRaises(DatoInvalidoError):
                DivisasServicio(cliente, self.repo_tc).consultar(moneda)
        self.assertEqual(cliente.llamadas, 0)

    def test_calculo_de_pago(self):
        empleado = Empleado("12.345.678-5", "Camila Rojas", "c@ecotech.cl", "Gerente", 2_375_000)
        _, pagos = DivisasServicio(ClienteFalso(DIVISA_OK), self.repo_tc).calcular_pagos([empleado], "USD")
        # líquido = 2.375.000 * 0,8 = 1.900.000 CLP / 950 = 2.000,00 USD
        self.assertEqual(pagos[0].monto, Decimal("2000.00"))

    def test_sin_red_y_sin_tasa_guardada(self):
        with self.assertRaises(SinDatosLocalesError):
            DivisasServicio(ClienteFalso(ServicioNoDisponibleError("x")), self.repo_tc).consultar("EUR")


if __name__ == "__main__":
    unittest.main()
