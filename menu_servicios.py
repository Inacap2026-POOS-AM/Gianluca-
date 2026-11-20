"""Menús de la Unidad 3: servicios externos (clima, divisas, pagos) y usuarios, más el login."""
from config import Configuracion
from consola import pedir_confirmacion, pedir_contrasena, pedir_entero, pedir_opcional_mayus, pedir_texto, titulo
from dominio.excepciones import (AccesoDenegadoError, CredencialesInvalidasError, CuentaBloqueadaError,
                                 DatoInvalidoError, EcoTechError)
from dominio.ubicacion import UbicacionProyecto
from dominio.usuario import Usuario
from dominio.validaciones import PAIS_A_MONEDA
from repositorio import EmpleadoRepositorio, ProyectoRepositorio, UbicacionRepositorio
from seguridad.autenticacion import ServicioAutenticacion
from servicios import ServiciosExternos
from servicios.resultado import ResultadoConsulta, fecha_local
from servicios.sincronizacion import sincronizar

INTENTOS_POR_SESION = 3


# =====================================================================
# Inicio de sesión
# =====================================================================
def crear_administrador_inicial(auth: ServicioAutenticacion) -> None:
    titulo("Configuración inicial: crear usuario administrador")
    print(" No hay usuarios registrados. Cree el administrador del sistema.")
    print(" La contraseña debe tener 8+ caracteres, mayúsculas, minúsculas y números.")
    while True:
        nombre = pedir_texto("Nuevo usuario administrador: ")
        contrasena = pedir_contrasena("Contraseña: ")
        if contrasena != pedir_contrasena("Repita la contraseña: "):
            print("  ! Las contraseñas no coinciden.")
            continue
        try:
            auth.registrar(nombre, contrasena, rol="admin")
        except EcoTechError as error:
            print(f"  ! {error}")
            continue
        print("  Administrador creado. La contraseña se guardó como hash bcrypt (nunca en texto plano).")
        return


def iniciar_sesion(auth: ServicioAutenticacion) -> Usuario | None:
    """Devuelve el usuario autenticado o None si se agotan los intentos."""
    if not auth.hay_usuarios():
        crear_administrador_inicial(auth)
    titulo("EcoTech Solutions - Inicio de sesión")
    for intento in range(1, INTENTOS_POR_SESION + 1):
        nombre = input("Usuario: ").strip()
        contrasena = pedir_contrasena("Contraseña: ")
        try:
            usuario = auth.iniciar_sesion(nombre, contrasena)
        except CuentaBloqueadaError as error:
            print(f"  ! {error}")
            return None
        except CredencialesInvalidasError as error:
            print(f"  ! {error} (intento {intento}/{INTENTOS_POR_SESION})")
            continue
        print(f"  Bienvenido/a, {usuario.nombre_usuario} ({usuario.rol}).")
        return usuario
    print("  ! Demasiados intentos fallidos. El sistema se cerrará.")
    return None


# =====================================================================
# Servicios externos
# =====================================================================
def mostrar_clima(resultado: ResultadoConsulta) -> None:
    r = resultado.dato
    print(f"  {resultado.encabezado()}")
    print(f"  Ciudad:       {r.ciudad} ({r.codigo_pais})  lat {r.latitud:.2f}, lon {r.longitud:.2f}")
    print(f"  Temperatura:  {r.temperatura:.1f} °C")
    print(f"  Humedad:      {r.humedad} %")
    print(f"  Estado:       {r.descripcion}")
    print(f"  Viento:       {r.viento_kmh:.0f} km/h")
    print(f"  Medición:     {r.medido_en} (hora local de la ciudad)")
    print(f"  Planificación -> {r.evaluar_operacion()}")


def mostrar_tasa(resultado: ResultadoConsulta) -> None:
    t = resultado.dato
    print(f"  {resultado.encabezado()}")
    print(f"  1 {t.moneda} = ${t.valor_clp:,.4f} CLP   (publicado por la API: {fecha_local(t.actualizado_api)})")


class MenuServiciosExternos:
    def __init__(self, servicios: ServiciosExternos, config: Configuracion, proyectos: ProyectoRepositorio,
                 empleados: EmpleadoRepositorio, ubicaciones: UbicacionRepositorio):
        self._servicios = servicios
        self._config = config
        self._proyectos = proyectos
        self._empleados = empleados
        self._ubicaciones = ubicaciones

    def opciones(self) -> dict:
        return {
            "1": ("Consultar clima de una ciudad", self.clima_ciudad),
            "2": ("Planificación: clima de las ubicaciones de proyectos", self.clima_proyectos),
            "3": ("Consultar tipo de cambio", self.tipo_cambio),
            "4": ("Calcular pagos de un proyecto en la moneda del país", self.pagos_proyecto),
            "5": ("Calcular pago de un empleado en otra moneda", self.pago_empleado),
            "6": ("Asignar ubicación (ciudad/país) a un proyecto", self.asignar_ubicacion),
            "7": ("Sincronizar datos externos (idempotente)", self.sincronizar),
            "8": ("Diagnóstico: simular endpoint inválido (404)", self.diagnostico),
        }

    def clima_ciudad(self) -> None:
        ciudad = pedir_texto("Ciudad (ej. Antofagasta): ")
        pais = pedir_opcional_mayus(f"Código de país opcional ({', '.join(sorted(PAIS_A_MONEDA))}): ")
        mostrar_clima(self._servicios.clima.consultar(ciudad, pais))

    def clima_proyectos(self) -> None:
        ubicaciones = self._ubicaciones.listar_con_proyecto()
        if not ubicaciones:
            print("  Ningún proyecto tiene ubicación. Use la opción 6 para asignarla.")
            return
        for nombre_proyecto, ubicacion in ubicaciones:
            print(f"\n  Proyecto: {nombre_proyecto}")
            try:
                mostrar_clima(self._servicios.clima.consultar(ubicacion.ciudad, ubicacion.codigo_pais))
            except EcoTechError as error:
                # Un proyecto sin datos no detiene el reporte de los demás
                print(f"  ! {error}")

    def tipo_cambio(self) -> None:
        moneda = pedir_texto("Moneda ISO 4217 (ej. USD, EUR, PEN): ").upper()
        mostrar_tasa(self._servicios.divisas.consultar(moneda))

    def pagos_proyecto(self) -> None:
        proyecto = self._proyectos.obtener_por_id(pedir_entero("Id de proyecto: ", minimo=1))
        ubicacion = self._ubicaciones.obtener(proyecto.id)
        empleados = []
        for rut in proyecto.ruts_asignados:
            empleado = self._empleados.obtener_por_rut(rut)
            if empleado.activo:
                empleados.append(empleado)
        if not empleados:
            print("  El proyecto no tiene empleados activos asignados.")
            return
        resultado, pagos = self._servicios.divisas.calcular_pagos(empleados, ubicacion.moneda)
        print(f"\n  Proyecto '{proyecto.nombre}' en {ubicacion}")
        mostrar_tasa(resultado)
        print("  " + "-" * 86)
        for pago in pagos:
            print(f"  {pago}")
        total = sum(p.monto for p in pagos)
        print("  " + "-" * 86)
        print(f"  Total a pagar: {total:,} {ubicacion.moneda}")

    def pago_empleado(self) -> None:
        empleado = self._empleados.obtener_por_rut(pedir_texto("RUT del empleado: "))
        moneda = pedir_texto("Moneda de pago (ej. USD, PEN, COP): ").upper()
        resultado, pagos = self._servicios.divisas.calcular_pagos([empleado], moneda)
        mostrar_tasa(resultado)
        print(f"  {pagos[0]}")

    def asignar_ubicacion(self) -> None:
        for proyecto in self._proyectos.listar_todos():
            print(f"   {proyecto.id}. {proyecto.nombre}")
        proyecto = self._proyectos.obtener_por_id(pedir_entero("Id de proyecto: ", minimo=1))
        ciudad = pedir_texto("Ciudad donde se ejecuta: ")
        pais = pedir_texto(f"Código de país ({', '.join(sorted(PAIS_A_MONEDA))}): ").upper()
        ubicacion = UbicacionProyecto(proyecto.id, ciudad, pais)
        self._ubicaciones.guardar(ubicacion)
        print(f"  Ubicación guardada: {ubicacion}.")

    def sincronizar(self) -> None:
        imprimir_sincronizacion(self._servicios, self._ubicaciones, self._config)

    def diagnostico(self) -> None:
        print("  Se consultará una ruta inexistente de la API de clima para verificar el manejo del 404.")
        ubicaciones = self._ubicaciones.listar_con_proyecto()
        if ubicaciones:
            ciudad, pais = ubicaciones[0][1].ciudad, ubicaciones[0][1].codigo_pais
        else:
            ciudad, pais = "Santiago", "CL"
        resultado = self._servicios.clima.probar_endpoint_invalido(ciudad, pais)
        print("  Resultado: el 404 NO se reintentó y el sistema siguió funcionando con el Plan B:")
        mostrar_clima(resultado)


def imprimir_sincronizacion(servicios: ServiciosExternos, ubicaciones: UbicacionRepositorio,
                            config: Configuracion) -> None:
    antes_clima, antes_tc = servicios.repo_clima.contar(), servicios.repo_tipo_cambio.contar()
    resumen = sincronizar(servicios, ubicaciones, config.monedas_sincronizar)
    despues_clima, despues_tc = servicios.repo_clima.contar(), servicios.repo_tipo_cambio.contar()
    titulo("Resultado de la sincronización")
    for linea in resumen.lineas:
        print(linea)
    print("-" * 60)
    print(f"  Nuevos: {resumen.nuevos} | Ya existían (sin duplicar): {resumen.actualizados} | "
          f"Plan B: {resumen.desde_respaldo} | Con error: {resumen.fallidos}")
    print(f"  Filas registro_clima: {antes_clima} -> {despues_clima}")
    print(f"  Filas tipo_cambio:    {antes_tc} -> {despues_tc}")


# =====================================================================
# Usuarios (solo administradores)
# =====================================================================
class MenuUsuarios:
    def __init__(self, auth: ServicioAutenticacion, repositorio, usuario_actual: Usuario):
        self._auth = auth
        self._repo = repositorio
        self._actual = usuario_actual

    def opciones(self) -> dict:
        return {
            "1": ("Crear usuario", self.crear),
            "2": ("Listar usuarios", self.listar),
        }

    def verificar_admin(self) -> None:
        if not self._actual.es_admin:
            raise AccesoDenegadoError("Solo un administrador puede gestionar usuarios.")

    def crear(self) -> None:
        self.verificar_admin()
        nombre = pedir_texto("Nombre de usuario: ")
        rol = "admin" if pedir_confirmacion("¿Será administrador?") else "operador"
        contrasena = pedir_contrasena("Contraseña: ")
        if contrasena != pedir_contrasena("Repita la contraseña: "):
            raise DatoInvalidoError("Las contraseñas no coinciden.")
        usuario = self._auth.registrar(nombre, contrasena, rol, solicitante=self._actual)
        print(f"  Usuario '{usuario.nombre_usuario}' creado ({usuario.rol}).")

    def listar(self) -> None:
        self.verificar_admin()
        for usuario in self._repo.listar():
            print(f"   #{usuario.id:<4} {usuario.nombre_usuario:<20} {usuario.rol}")
