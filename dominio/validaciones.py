"""Funciones de validación reutilizadas por todas las clases del dominio.

Se centralizan aquí para no repetir la misma lógica en Persona, Empleado,
Departamento y Proyecto (principio DRY).
"""
import re
import unicodedata
from datetime import date

from dominio.excepciones import DatoInvalidoError, RutInvalidoError

_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def validar_texto(valor, campo: str, largo_maximo: int = 100) -> str:
    """Devuelve el texto sin espacios sobrantes o lanza DatoInvalidoError."""
    if not isinstance(valor, str) or not valor.strip():
        raise DatoInvalidoError(f"El campo '{campo}' no puede estar vacío.")
    valor = valor.strip()
    if len(valor) > largo_maximo:
        raise DatoInvalidoError(f"El campo '{campo}' admite máximo {largo_maximo} caracteres.")
    return valor


def validar_email(valor) -> str:
    valor = validar_texto(valor, "email", 120).lower()
    if not _PATRON_EMAIL.match(valor):
        raise DatoInvalidoError(f"El email '{valor}' no tiene un formato válido.")
    return valor


def validar_fecha(valor, campo: str) -> str:
    """Acepta 'AAAA-MM-DD', no permite fechas futuras y devuelve el texto ISO."""
    try:
        fecha = date.fromisoformat(str(valor).strip())
    except ValueError as error:
        raise DatoInvalidoError(f"El campo '{campo}' debe tener formato AAAA-MM-DD.") from error
    if fecha > date.today():
        raise DatoInvalidoError(f"El campo '{campo}' no puede ser una fecha futura.")
    return fecha.isoformat()


def validar_numero_positivo(valor, campo: str, permitir_cero: bool = False) -> float:
    # bool es subclase de int en Python, por eso se excluye explícitamente
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise DatoInvalidoError(f"El campo '{campo}' debe ser numérico.")
    if valor < 0 or (valor == 0 and not permitir_cero):
        raise DatoInvalidoError(f"El campo '{campo}' debe ser mayor que cero.")
    return float(valor)


def calcular_digito_verificador(numero: int) -> str:
    """Algoritmo módulo 11 usado por el Registro Civil de Chile."""
    suma = 0
    factor = 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def normalizar_rut(valor) -> str:
    """Valida un RUT chileno y lo devuelve como '12345678-5'.

    Acepta '12.345.678-5', '12345678-5' o '123456785'.
    """
    if not isinstance(valor, str):
        raise RutInvalidoError("El RUT debe ingresarse como texto.")
    limpio = valor.strip().upper().replace(".", "").replace("-", "")
    if not re.fullmatch(r"\d{7,8}[0-9K]", limpio):
        raise RutInvalidoError(f"El RUT '{valor}' no tiene un formato válido.")
    cuerpo, dv = limpio[:-1], limpio[-1]
    if calcular_digito_verificador(int(cuerpo)) != dv:
        raise RutInvalidoError(f"El dígito verificador del RUT '{valor}' no es correcto.")
    return f"{int(cuerpo)}-{dv}"


# =====================================================================
# Unidad 3: validación de entradas para las consultas a las APIs
# =====================================================================
# Países donde EcoTech ejecuta proyectos y la moneda en que se paga a los trabajadores.
# Funciona como lista blanca: solo se consultan a la API valores conocidos.
PAIS_A_MONEDA = {
    "CL": "CLP", "PE": "PEN", "AR": "ARS", "CO": "COP", "MX": "MXN", "BR": "BRL",
    "BO": "BOB", "UY": "UYU", "PY": "PYG", "EC": "USD", "US": "USD", "ES": "EUR",
    "DE": "EUR", "CA": "CAD",
}
MONEDAS_SOPORTADAS = frozenset(PAIS_A_MONEDA.values()) | {"EUR", "USD", "GBP", "CNY", "JPY"}

# Letras de cualquier idioma (incluye tildes y ñ) separadas por espacio, guion, punto o apóstrofo
_PATRON_CIUDAD = re.compile(r"^[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?$")
_PATRON_USUARIO = re.compile(r"^[a-z0-9._]{3,30}$")


def validar_ciudad(valor) -> str:
    """Nombre de ciudad: 2 a 60 caracteres, solo letras y separadores comunes.

    Bloquea números, símbolos y textos tipo  "Santiago&count=100"  o  "../../",
    que podrían alterar la consulta enviada a la API.
    """
    ciudad = validar_texto(valor, "ciudad", 60)
    ciudad = re.sub(r"\s+", " ", ciudad)
    if len(ciudad) < 2 or not _PATRON_CIUDAD.match(ciudad):
        raise DatoInvalidoError("La ciudad solo puede contener letras, espacios y guiones (ej. 'Puerto Montt').")
    return ciudad


def validar_codigo_pais(valor) -> str:
    codigo = validar_texto(valor, "país", 2).upper()
    if codigo not in PAIS_A_MONEDA:
        permitidos = ", ".join(sorted(PAIS_A_MONEDA))
        raise DatoInvalidoError(f"País no soportado. Use un código ISO de 2 letras: {permitidos}.")
    return codigo


def validar_moneda(valor) -> str:
    codigo = validar_texto(valor, "moneda", 3).upper()
    if codigo not in MONEDAS_SOPORTADAS:
        permitidas = ", ".join(sorted(MONEDAS_SOPORTADAS))
        raise DatoInvalidoError(f"Moneda no soportada. Use un código ISO 4217: {permitidas}.")
    return codigo


def moneda_de_pais(codigo_pais: str) -> str:
    return PAIS_A_MONEDA[validar_codigo_pais(codigo_pais)]


def normalizar_clave(texto: str) -> str:
    """'Medellín ' -> 'medellin'. Sirve para buscar en la BD sin depender de tildes o mayúsculas."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sin_tildes).strip().casefold()


# ----------------------------- Usuarios -----------------------------
LARGO_MAXIMO_CONTRASENA_BYTES = 72  # bcrypt solo considera los primeros 72 bytes


def validar_nombre_usuario(valor) -> str:
    nombre = validar_texto(valor, "usuario", 30).lower()
    if not _PATRON_USUARIO.match(nombre):
        raise DatoInvalidoError("El usuario debe tener 3 a 30 caracteres: letras minúsculas, números, '.' o '_'.")
    return nombre


def validar_contrasena_nueva(contrasena, nombre_usuario: str = "") -> str:
    """Política mínima: 8+ caracteres, mayúscula, minúscula y número; no puede contener el usuario."""
    if not isinstance(contrasena, str) or not contrasena:
        raise DatoInvalidoError("La contraseña no puede estar vacía.")
    if contrasena != contrasena.strip():
        raise DatoInvalidoError("La contraseña no puede empezar ni terminar con espacios.")
    if len(contrasena) < 8:
        raise DatoInvalidoError("La contraseña debe tener al menos 8 caracteres.")
    if len(contrasena.encode("utf-8")) > LARGO_MAXIMO_CONTRASENA_BYTES:
        raise DatoInvalidoError("La contraseña es demasiado larga (máximo 72 bytes).")
    if not (re.search(r"[a-z]", contrasena) and re.search(r"[A-Z]", contrasena) and re.search(r"\d", contrasena)):
        raise DatoInvalidoError("La contraseña debe incluir mayúsculas, minúsculas y números.")
    if nombre_usuario and nombre_usuario.lower() in contrasena.lower():
        raise DatoInvalidoError("La contraseña no puede contener el nombre de usuario.")
    return contrasena
