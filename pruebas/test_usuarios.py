"""Pruebas de autenticación: hash bcrypt con salt, login, bloqueo y control de acceso."""
import sqlite3
import unittest

from dominio.excepciones import (AccesoDenegadoError, CredencialesInvalidasError, CuentaBloqueadaError,
                                 DatoInvalidoError)
from main import SistemaEcoTech
from repositorio import UsuarioRepositorio
from repositorio.conexion import inicializar_bd, obtener_conexion
from seguridad.autenticacion import MENSAJE_GENERICO, ServicioAutenticacion

CLAVE = "Ecotech2026"


class PruebasUsuarios(unittest.TestCase):
    def setUp(self):
        self.conexion = obtener_conexion(":memory:")
        inicializar_bd(self.conexion)
        self.repo = UsuarioRepositorio(self.conexion)
        self.auth = ServicioAutenticacion(self.repo, rondas_bcrypt=4)  # 4 rondas: rápido para pruebas
        self.admin = self.auth.registrar("admin", CLAVE, rol="admin")

    def tearDown(self):
        self.conexion.close()

    def hashes(self) -> list[str]:
        return [f[0] for f in self.conexion.execute("SELECT hash_contrasena FROM usuario")]

    def test_no_hay_contrasenas_en_texto_plano(self):
        self.auth.registrar("operador1", CLAVE, solicitante=self.admin)
        for hash_guardado in self.hashes():
            self.assertNotEqual(hash_guardado, CLAVE)
            self.assertNotIn(CLAVE, hash_guardado)
            self.assertTrue(hash_guardado.startswith("$2b$"))
            self.assertEqual(len(hash_guardado), 60)

    def test_salt_distinto_misma_clave(self):
        self.auth.registrar("operador1", CLAVE, solicitante=self.admin)
        primero, segundo = self.hashes()
        self.assertNotEqual(primero, segundo)  # mismo texto, hashes distintos gracias al salt

    def test_bd_rechaza_texto_plano(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conexion.execute("INSERT INTO usuario (nombre_usuario, hash_contrasena, rol, creado_en) "
                                  "VALUES (?, ?, ?, ?)", ("hacker", "clave123", "admin", "2026-01-01"))

    def test_login_correcto_e_incorrecto(self):
        self.assertEqual(self.auth.iniciar_sesion("ADMIN ", CLAVE).nombre_usuario, "admin")
        with self.assertRaises(CredencialesInvalidasError) as contexto:
            self.auth.iniciar_sesion("admin", "otraClave1")
        self.assertEqual(str(contexto.exception), MENSAJE_GENERICO)

    def test_usuario_inexistente_mismo_mensaje(self):
        with self.assertRaises(CredencialesInvalidasError) as contexto:
            self.auth.iniciar_sesion("noexiste", CLAVE)
        self.assertEqual(str(contexto.exception), MENSAJE_GENERICO)  # no revela si el usuario existe

    def test_credenciales_vacias(self):
        for usuario, clave in (("", CLAVE), ("   ", CLAVE), ("admin", ""), (None, None)):
            with self.subTest(usuario=usuario), self.assertRaises(CredencialesInvalidasError):
                self.auth.iniciar_sesion(usuario, clave)

    def test_inyeccion_en_login(self):
        with self.assertRaises(CredencialesInvalidasError):
            self.auth.iniciar_sesion("admin' --", "' OR '1'='1")

    def test_bloqueo_por_intentos(self):
        for _ in range(ServicioAutenticacion.MAX_INTENTOS):
            with self.assertRaises(CredencialesInvalidasError):
                self.auth.iniciar_sesion("admin", "Incorrecta1")
        with self.assertRaises(CuentaBloqueadaError):
            self.auth.iniciar_sesion("admin", CLAVE)  # bloqueada aunque ahora la clave sea correcta

    def test_politica_de_contrasena(self):
        for clave in ("corta1A", "sinnumerosAA", "SINMINUSCULA1", "sinmayuscula1", "Operador1x", " Espacios1 "):
            with self.subTest(clave=clave), self.assertRaises(DatoInvalidoError):
                self.auth.registrar("operador1", clave, solicitante=self.admin)

    def test_solo_admin_crea_usuarios(self):
        operador = self.auth.registrar("operador1", CLAVE, solicitante=self.admin)
        with self.assertRaises(AccesoDenegadoError):
            self.auth.registrar("operador2", CLAVE, solicitante=operador)
        with self.assertRaises(AccesoDenegadoError):
            self.auth.registrar("operador3", CLAVE)  # sin sesión

    def test_menu_exige_usuario_autenticado(self):
        with self.assertRaises(AccesoDenegadoError):
            SistemaEcoTech(self.conexion).ejecutar()


if __name__ == "__main__":
    unittest.main()
