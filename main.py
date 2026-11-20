"""Sistema de Gestión EcoTech Solutions (menú por consola) - Unidades 1, 2 y 3.

Ejecutar con:  python main.py

U3: el sistema exige inicio de sesión (bcrypt) y agrega el menú de servicios
externos (clima y tipo de cambio) con manejo de errores y Plan B.
"""
import logging
import sqlite3
import sys

from config import Configuracion, configurar_logging
from consola import pedir_confirmacion, pedir_entero, pedir_monto, pedir_texto, titulo
from dominio import Departamento, Empleado, Proyecto, Reportable
from dominio.excepciones import AccesoDenegadoError, EcoTechError
from dominio.ubicacion import UbicacionProyecto
from dominio.usuario import Usuario
from menu_servicios import MenuServiciosExternos, MenuUsuarios, iniciar_sesion
from repositorio import (DepartamentoRepositorio, EmpleadoRepositorio, ProyectoRepositorio, UbicacionRepositorio,
                         UsuarioRepositorio)
from repositorio.conexion import cargar_variables_entorno, inicializar_bd, obtener_conexion
from seguridad.autenticacion import ServicioAutenticacion
from servicios import ServiciosExternos, crear_servicios

logger = logging.getLogger(__name__)


# =====================================================================
# Aplicación de consola
# =====================================================================
class SistemaEcoTech:
    """Orquesta el menú. No contiene SQL: todo pasa por los repositorios."""

    def __init__(self, conexion: sqlite3.Connection, usuario: Usuario | None = None,
                 servicios: ServiciosExternos | None = None, config: Configuracion | None = None,
                 auth: ServicioAutenticacion | None = None):
        self.empleados = EmpleadoRepositorio(conexion)
        self.departamentos = DepartamentoRepositorio(conexion)
        self.proyectos = ProyectoRepositorio(conexion)
        self.ubicaciones = UbicacionRepositorio(conexion)
        self.usuarios = UsuarioRepositorio(conexion)
        self.usuario = usuario
        self.servicios = servicios
        self.config = config
        self.auth = auth

    def ejecutar(self) -> None:
        # Control de acceso: sin usuario autenticado no se muestra ninguna funcionalidad
        if self.usuario is None:
            raise AccesoDenegadoError("Debe iniciar sesión para usar el sistema.")
        self._ofrecer_datos_de_ejemplo()
        opciones = {
            "1": self.menu_empleados,
            "2": self.menu_departamentos,
            "3": self.menu_proyectos,
            "4": self.reporte_general,
            "5": self.menu_servicios_externos,
            "6": self.menu_usuarios,
        }
        while True:
            titulo(f"EcoTech Solutions - Sesión: {self.usuario.nombre_usuario} ({self.usuario.rol})")
            print(" 1. Empleados\n 2. Departamentos\n 3. Proyectos\n 4. Reporte general\n"
                  " 5. Servicios externos (clima, tipo de cambio, pagos)\n 6. Usuarios (admin)\n 0. Salir")
            opcion = input("Opción: ").strip()
            if opcion == "0":
                print("Hasta luego.")
                return
            accion = opciones.get(opcion)
            if accion is None:
                print("  ! Opción no válida.")
                continue
            self._ejecutar_seguro(accion)

    def _ejecutar_seguro(self, accion) -> None:
        """Ejecuta una acción del menú y muestra cualquier error sin cerrar el programa."""
        try:
            accion()
        except EcoTechError as error:
            print(f"  ! {error}")
        except Exception:  # noqa: BLE001 - última barrera: se registra la traza, no se muestra
            logger.exception("Error inesperado en el menú")
            print("  ! Ocurrió un error inesperado. El detalle quedó en logs/ecotech.log.")

    def _submenu(self, nombre: str, opciones: dict) -> None:
        while True:
            titulo(nombre)
            for clave, (texto, _) in opciones.items():
                print(f" {clave}. {texto}")
            print(" 0. Volver")
            opcion = input("Opción: ").strip()
            if opcion == "0":
                return
            if opcion not in opciones:
                print("  ! Opción no válida.")
                continue
            self._ejecutar_seguro(opciones[opcion][1])

    # -------------------- SERVICIOS EXTERNOS (U3) --------------------
    def menu_servicios_externos(self) -> None:
        if self.servicios is None or self.config is None:
            print("  ! Los servicios externos no están configurados.")
            return
        menu = MenuServiciosExternos(self.servicios, self.config, self.proyectos, self.empleados, self.ubicaciones)
        self._submenu("Servicios externos", menu.opciones())

    def menu_usuarios(self) -> None:
        menu = MenuUsuarios(self.auth, self.usuarios, self.usuario)
        try:
            menu.verificar_admin()
        except AccesoDenegadoError as error:
            print(f"  ! {error}")
            return
        self._submenu("Usuarios", menu.opciones())

    # ------------------------- EMPLEADOS -------------------------
    def menu_empleados(self) -> None:
        self._submenu("Empleados", {
            "1": ("Registrar empleado", self.registrar_empleado),
            "2": ("Listar empleados activos", self.listar_empleados),
            "3": ("Buscar por RUT", self.buscar_empleado_rut),
            "4": ("Buscar por nombre", self.buscar_empleado_nombre),
            "5": ("Actualizar empleado", self.actualizar_empleado),
            "6": ("Desvincular empleado", self.desvincular_empleado),
        })

    def registrar_empleado(self) -> None:
        rut = pedir_texto("RUT (ej. 12.345.678-5): ")
        nombre = pedir_texto("Nombre completo: ")
        email = pedir_texto("Email: ")
        telefono = pedir_texto("Teléfono (opcional): ", obligatorio=False)
        cargo = pedir_texto("Cargo: ")
        sueldo = pedir_monto("Sueldo base: $")
        departamento_id = self._elegir_departamento()
        # El constructor valida todo; si algo está mal lanza DatoInvalidoError
        empleado = Empleado(rut, nombre, email, cargo, sueldo,
                            departamento_id=departamento_id, telefono=telefono)
        self.empleados.guardar(empleado)
        print(f"  Empleado {empleado.rut} registrado. Sueldo líquido estimado: ${empleado.calcular_sueldo_liquido():,.0f}")

    def listar_empleados(self) -> None:
        empleados = self.empleados.listar_activos()
        if not empleados:
            print("  No hay empleados activos.")
        for empleado in empleados:
            print(" ", empleado)

    def buscar_empleado_rut(self) -> None:
        print(" ", self.empleados.obtener_por_rut(pedir_texto("RUT: ")))

    def buscar_empleado_nombre(self) -> None:
        resultados = self.empleados.buscar_por_nombre(pedir_texto("Nombre o parte del nombre: "))
        print(f"  {len(resultados)} resultado(s).")
        for empleado in resultados:
            print(" ", empleado)

    def actualizar_empleado(self) -> None:
        empleado = self.empleados.obtener_por_rut(pedir_texto("RUT del empleado a actualizar: "))
        print("  Presione Enter para conservar el valor actual.")
        empleado.nombre = pedir_texto(f"Nombre [{empleado.nombre}]: ", actual=empleado.nombre)
        empleado.email = pedir_texto(f"Email [{empleado.email}]: ", actual=empleado.email)
        empleado.telefono = pedir_texto(f"Teléfono [{empleado.telefono}]: ", actual=empleado.telefono)
        empleado.cargo = pedir_texto(f"Cargo [{empleado.cargo}]: ", actual=empleado.cargo)
        empleado.sueldo_base = pedir_monto(f"Sueldo base [${empleado.sueldo_base:,.0f}]: $", actual=empleado.sueldo_base)
        if pedir_confirmacion("¿Cambiar de departamento?"):
            empleado.departamento_id = self._elegir_departamento()
        self.empleados.actualizar(empleado)
        print("  Empleado actualizado.")

    def desvincular_empleado(self) -> None:
        rut = pedir_texto("RUT del empleado a desvincular: ")
        empleado = self.empleados.obtener_por_rut(rut)
        if pedir_confirmacion(f"¿Desvincular a {empleado.nombre}?"):
            self.empleados.eliminar(empleado.rut)
            print("  Empleado desvinculado (borrado lógico, se conserva el historial).")

    def _elegir_departamento(self) -> int | None:
        departamentos = self.departamentos.listar_todos()
        for departamento in departamentos:
            print(f"   {departamento.id}. {departamento.nombre}")
        return pedir_entero("Id de departamento (Enter = sin departamento): ", minimo=1, permitir_vacio=True)

    # ----------------------- DEPARTAMENTOS -----------------------
    def menu_departamentos(self) -> None:
        self._submenu("Departamentos", {
            "1": ("Crear departamento", self.crear_departamento),
            "2": ("Listar departamentos", self.listar_departamentos),
            "3": ("Ver empleados de un departamento", self.empleados_de_departamento),
            "4": ("Actualizar departamento", self.actualizar_departamento),
            "5": ("Eliminar departamento", self.eliminar_departamento),
        })

    def crear_departamento(self) -> None:
        departamento = Departamento(pedir_texto("Nombre: "), pedir_monto("Presupuesto anual: $"))
        nuevo_id = self.departamentos.guardar(departamento)
        print(f"  Departamento creado con id {nuevo_id}.")

    def listar_departamentos(self) -> None:
        departamentos = self.departamentos.listar_todos()
        if not departamentos:
            print("  No hay departamentos registrados.")
        for departamento in departamentos:
            print(" ", departamento)

    def empleados_de_departamento(self) -> None:
        departamento = self.departamentos.obtener_por_id(pedir_entero("Id de departamento: ", minimo=1))
        empleados = self.empleados.listar_por_departamento(departamento.id)
        print(f"  {departamento.nombre}: {len(empleados)} empleado(s) activo(s)")
        for empleado in empleados:
            print(" ", empleado)

    def actualizar_departamento(self) -> None:
        departamento = self.departamentos.obtener_por_id(pedir_entero("Id de departamento: ", minimo=1))
        departamento.nombre = pedir_texto(f"Nombre [{departamento.nombre}]: ", actual=departamento.nombre)
        departamento.presupuesto = pedir_monto(f"Presupuesto [${departamento.presupuesto:,.0f}]: $",
                                               actual=departamento.presupuesto)
        self.departamentos.actualizar(departamento)
        print("  Departamento actualizado.")

    def eliminar_departamento(self) -> None:
        departamento = self.departamentos.obtener_por_id(pedir_entero("Id de departamento: ", minimo=1))
        if pedir_confirmacion(f"¿Eliminar el departamento '{departamento.nombre}'?"):
            self.departamentos.eliminar(departamento.id)
            print("  Departamento eliminado.")

    # ------------------------- PROYECTOS -------------------------
    def menu_proyectos(self) -> None:
        self._submenu("Proyectos", {
            "1": ("Crear proyecto", self.crear_proyecto),
            "2": ("Listar proyectos", self.listar_proyectos),
            "3": ("Asignar empleado a proyecto", self.asignar_empleado),
            "4": ("Quitar empleado de proyecto", self.quitar_empleado),
            "5": ("Actualizar proyecto", self.actualizar_proyecto),
            "6": ("Eliminar proyecto", self.eliminar_proyecto),
        })

    def crear_proyecto(self) -> None:
        proyecto = Proyecto(
            nombre=pedir_texto("Nombre: "),
            descripcion=pedir_texto("Descripción (opcional): ", obligatorio=False),
            fecha_inicio=pedir_texto("Fecha de inicio AAAA-MM-DD (Enter = hoy): ", obligatorio=False) or None,
        )
        nuevo_id = self.proyectos.guardar(proyecto)
        print(f"  Proyecto creado con id {nuevo_id}.")

    def listar_proyectos(self) -> None:
        proyectos = self.proyectos.listar_todos()
        if not proyectos:
            print("  No hay proyectos registrados.")
        for proyecto in proyectos:
            print(" ", proyecto)
            for rut in proyecto.ruts_asignados:
                print(f"      - {rut}")

    def asignar_empleado(self) -> None:
        id_proyecto = pedir_entero("Id de proyecto: ", minimo=1)
        self.proyectos.asignar_empleado(id_proyecto, pedir_texto("RUT del empleado: "))
        print("  Empleado asignado al proyecto.")

    def quitar_empleado(self) -> None:
        id_proyecto = pedir_entero("Id de proyecto: ", minimo=1)
        self.proyectos.quitar_empleado(id_proyecto, pedir_texto("RUT del empleado: "))
        print("  Empleado quitado del proyecto.")

    def actualizar_proyecto(self) -> None:
        proyecto = self.proyectos.obtener_por_id(pedir_entero("Id de proyecto: ", minimo=1))
        proyecto.nombre = pedir_texto(f"Nombre [{proyecto.nombre}]: ", actual=proyecto.nombre)
        proyecto.descripcion = pedir_texto(f"Descripción [{proyecto.descripcion}]: ", actual=proyecto.descripcion)
        proyecto.fecha_inicio = pedir_texto(f"Fecha de inicio [{proyecto.fecha_inicio}]: ", actual=proyecto.fecha_inicio)
        self.proyectos.actualizar(proyecto)
        print("  Proyecto actualizado.")

    def eliminar_proyecto(self) -> None:
        proyecto = self.proyectos.obtener_por_id(pedir_entero("Id de proyecto: ", minimo=1))
        if pedir_confirmacion(f"¿Eliminar el proyecto '{proyecto.nombre}' y sus asignaciones?"):
            self.proyectos.eliminar(proyecto.id)
            print("  Proyecto eliminado.")

    # ---------------------- REPORTE GENERAL ----------------------
    def reporte_general(self) -> None:
        """Polimorfismo: una sola lista con objetos de 3 clases distintas.

        No se pregunta el tipo de cada objeto (sin if/isinstance): cada uno
        sabe cómo resumirse porque todos cumplen la interfaz Reportable.
        """
        try:
            empleados = self.empleados.listar_activos()
            entidades: list[Reportable] = [
                *self.departamentos.listar_todos(),
                *empleados,
                *self.proyectos.listar_todos(),
            ]
        except EcoTechError as error:
            print(f"  ! {error}")
            return
        titulo("Reporte general")
        for entidad in entidades:
            print(entidad.resumen())
        total_liquido = sum(e.calcular_sueldo_liquido() for e in empleados)
        print("-" * 60)
        print(f"Total sueldos líquidos del mes: ${total_liquido:,.0f}")

    # --------------------- DATOS DE EJEMPLO ----------------------
    def _ofrecer_datos_de_ejemplo(self) -> None:
        try:
            vacio = not self.departamentos.listar_todos() and not self.empleados.listar_activos()
            if vacio and pedir_confirmacion("La base de datos está vacía. ¿Cargar datos de ejemplo?"):
                self.cargar_datos_de_ejemplo()
                print("  Datos de ejemplo cargados.")
        except EcoTechError as error:
            print(f"  ! No se pudieron cargar los datos de ejemplo: {error}")

    def cargar_datos_de_ejemplo(self) -> None:
        ti = self.departamentos.guardar(Departamento("Tecnología", 120_000_000))
        rrhh = self.departamentos.guardar(Departamento("Recursos Humanos", 45_000_000))
        sus = self.departamentos.guardar(Departamento("Sustentabilidad", 60_000_000))
        datos = [
            ("12.345.678-5", "Camila Rojas", "camila.rojas@ecotech.cl", "Gerente de TI", 2_400_000, "2019-03-01", ti),
            ("15.678.234-3", "Diego Muñoz", "diego.munoz@ecotech.cl", "Desarrollador", 1_350_000, "2021-07-15", ti),
            ("18.234.567-9", "Valentina Soto", "valentina.soto@ecotech.cl", "Analista RR.HH.", 1_100_000, "2022-01-10", rrhh),
            ("19.876.543-0", "Matías Fuentes", "matias.fuentes@ecotech.cl", "Ingeniero Ambiental", 1_500_000, "2023-05-02", sus),
        ]
        for rut, nombre, email, cargo, sueldo, ingreso, depto in datos:
            self.empleados.guardar(Empleado(rut, nombre, email, cargo, sueldo, ingreso, depto))
        solar = self.proyectos.guardar(Proyecto("Paneles Solares Planta Sur", "Instalación de energía solar",
                                                "2026-08-01", ruts_asignados=["15.678.234-3", "19.876.543-0"]))
        eolico = self.proyectos.guardar(Proyecto("Parque Eólico Arequipa", "Montaje de aerogeneradores",
                                                 "2026-09-15", ruts_asignados=["12.345.678-5", "19.876.543-0"]))
        reciclaje = self.proyectos.guardar(Proyecto("Reciclaje Industrial Medellín", "Planta de reciclaje",
                                                    "2026-10-01", ruts_asignados=["18.234.567-9"]))
        # U3: ubicación de cada proyecto (define el clima a consultar y la moneda de pago)
        self.ubicaciones.guardar(UbicacionProyecto(solar, "Antofagasta", "CL"))
        self.ubicaciones.guardar(UbicacionProyecto(eolico, "Arequipa", "PE"))
        self.ubicaciones.guardar(UbicacionProyecto(reciclaje, "Medellín", "CO"))


def main() -> int:
    configurar_logging()
    cargar_variables_entorno()
    conexion = None
    servicios = None
    try:
        config = Configuracion.desde_entorno()
        conexion = obtener_conexion()
        inicializar_bd(conexion)
        auth = ServicioAutenticacion(UsuarioRepositorio(conexion), config.bcrypt_rondas)
        usuario = iniciar_sesion(auth)
        if usuario is None:
            return 1
        servicios = crear_servicios(conexion, config)
        SistemaEcoTech(conexion, usuario, servicios, config, auth).ejecutar()
    except (KeyboardInterrupt, EOFError):
        print("\nSaliendo del sistema...")
    except EcoTechError as error:
        print(f"No se pudo iniciar el sistema: {error}")
        return 1
    except Exception:  # noqa: BLE001 - nunca mostrar una traza al usuario
        logger.exception("Error inesperado al iniciar")
        print("Ocurrió un error inesperado. El detalle quedó en logs/ecotech.log.")
        return 1
    finally:
        if servicios is not None:
            servicios.cerrar()
        if conexion is not None:
            conexion.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
