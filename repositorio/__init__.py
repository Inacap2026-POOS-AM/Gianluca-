"""Capa de persistencia: conexión y repositorios (todo el SQL vive aquí)."""
from repositorio.clima_repo import ClimaRepositorio
from repositorio.departamento_repo import DepartamentoRepositorio
from repositorio.empleado_repo import EmpleadoRepositorio
from repositorio.proyecto_repo import ProyectoRepositorio
from repositorio.tipo_cambio_repo import TipoCambioRepositorio
from repositorio.ubicacion_repo import UbicacionRepositorio
from repositorio.usuario_repo import UsuarioRepositorio

__all__ = ["ClimaRepositorio", "DepartamentoRepositorio", "EmpleadoRepositorio", "ProyectoRepositorio",
           "TipoCambioRepositorio", "UbicacionRepositorio", "UsuarioRepositorio"]
