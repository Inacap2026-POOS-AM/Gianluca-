"""Persistencia de la ubicación (ciudad/país) de cada proyecto."""
from dominio.excepciones import RegistroNoEncontradoError
from dominio.ubicacion import UbicacionProyecto
from repositorio.base import RepositorioBase


class UbicacionRepositorio(RepositorioBase):
    MENSAJE_REFERENCIA = "El proyecto indicado no existe."

    def guardar(self, ubicacion: UbicacionProyecto) -> None:
        """Crea o reemplaza la ubicación del proyecto (idempotente)."""
        with self._transaccion() as cursor:
            cursor.execute(
                "INSERT INTO ubicacion_proyecto (proyecto_id, ciudad, codigo_pais) VALUES (?, ?, ?) "
                "ON CONFLICT (proyecto_id) DO UPDATE SET ciudad = excluded.ciudad, codigo_pais = excluded.codigo_pais",
                (ubicacion.proyecto_id, ubicacion.ciudad, ubicacion.codigo_pais),
            )

    def obtener(self, proyecto_id: int) -> UbicacionProyecto:
        fila = self._consultar_uno(
            "SELECT proyecto_id, ciudad, codigo_pais FROM ubicacion_proyecto WHERE proyecto_id = ?",
            (proyecto_id,),
        )
        if fila is None:
            raise RegistroNoEncontradoError(f"El proyecto {proyecto_id} no tiene ubicación registrada.")
        return UbicacionProyecto(fila["proyecto_id"], fila["ciudad"], fila["codigo_pais"])

    def listar_con_proyecto(self) -> list[tuple[str, UbicacionProyecto]]:
        filas = self._consultar_todos(
            "SELECT p.nombre, u.proyecto_id, u.ciudad, u.codigo_pais "
            "FROM ubicacion_proyecto u JOIN proyecto p ON p.id = u.proyecto_id ORDER BY p.nombre"
        )
        return [(f["nombre"], UbicacionProyecto(f["proyecto_id"], f["ciudad"], f["codigo_pais"])) for f in filas]
