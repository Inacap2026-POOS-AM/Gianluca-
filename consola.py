"""Lectura segura de datos por teclado: ninguna función deja caer el programa."""
import getpass
import warnings

def pedir_texto(mensaje: str, obligatorio: bool = True, actual: str | None = None) -> str:
    """Si se pasa 'actual', presionar Enter conserva ese valor (modo edición)."""
    while True:
        valor = input(mensaje).strip()
        if valor:
            return valor
        if actual is not None:
            return actual
        if not obligatorio:
            return ""
        print("  ! Este dato es obligatorio.")


def pedir_entero(mensaje: str, minimo: int = 0, permitir_vacio: bool = False) -> int | None:
    while True:
        texto = input(mensaje).strip()
        if not texto and permitir_vacio:
            return None
        try:
            valor = int(texto)
        except ValueError:
            print("  ! Debe ingresar un número entero.")
            continue
        if valor < minimo:
            print(f"  ! El número debe ser mayor o igual a {minimo}.")
            continue
        return valor


def pedir_monto(mensaje: str, actual: float | None = None) -> float:
    """Acepta '850000', '850.000' o '$850.000' (montos en pesos, sin decimales)."""
    while True:
        texto = input(mensaje).strip().replace("$", "").replace(".", "").replace(" ", "")
        if not texto and actual is not None:
            return actual
        try:
            return float(int(texto))
        except ValueError:
            print("  ! Ingrese un monto en pesos, solo números (ej. 850000).")


def pedir_confirmacion(mensaje: str) -> bool:
    return input(f"{mensaje} (s/n): ").strip().lower() in ("s", "si", "sí")


def titulo(texto: str) -> None:
    print("\n" + "=" * 60)
    print(f" {texto}")
    print("=" * 60)


def pedir_contrasena(mensaje: str = "Contraseña: ") -> str:
    """Lee la contraseña sin mostrarla en pantalla (getpass). No se hace strip a propósito."""
    with warnings.catch_warnings():
        # Algunas consolas de IDE no permiten ocultar la escritura: getpass avisa y sigue funcionando
        warnings.simplefilter("ignore", getpass.GetPassWarning)
        return getpass.getpass(mensaje)


def pedir_opcional_mayus(mensaje: str) -> str | None:
    valor = input(mensaje).strip().upper()
    return valor or None
