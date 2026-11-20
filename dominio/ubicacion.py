"""Ubicación donde se ejecuta un proyecto (define el clima a consultar y la moneda de pago)."""
from dominio.excepciones import DatoInvalidoError
from dominio.validaciones import moneda_de_pais, validar_ciudad, validar_codigo_pais


class UbicacionProyecto:
    def __init__(self, proyecto_id: int, ciudad: str, codigo_pais: str):
        if isinstance(proyecto_id, bool) or not isinstance(proyecto_id, int) or proyecto_id <= 0:
            raise DatoInvalidoError("El id de proyecto debe ser un entero positivo.")
        self.proyecto_id = proyecto_id
        self.ciudad = validar_ciudad(ciudad)
        self.codigo_pais = validar_codigo_pais(codigo_pais)

    @property
    def moneda(self) -> str:
        # La moneda se deriva del país: no se puede guardar una combinación incoherente
        return moneda_de_pais(self.codigo_pais)

    def __str__(self) -> str:
        return f"{self.ciudad} ({self.codigo_pais}) - pago en {self.moneda}"
