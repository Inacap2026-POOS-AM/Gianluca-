"""Auditoría automática de las 5 señales de riesgo típicas del código generado por IA.

Uso:
    python auditoria_ia.py              # audita este proyecto
    python auditoria_ia.py --pypi       # además confirma en pypi.org que cada librería exista
    python auditoria_ia.py otra/carpeta

Señales revisadas (con el árbol sintáctico de Python, módulo 'ast'; no con
búsqueda de texto, para no confundir comentarios o strings con código real):

  1. SQL armado con f-string, +, % o .format()   -> inyección SQL
  2. verify=False en peticiones HTTP               -> sin validación de certificado (MITM)
  3. except: pass (o except X: pass)               -> errores silenciados
  4. Llamadas HTTP sin timeout                     -> el programa puede colgarse
  5. Librerías inexistentes / no declaradas        -> "alucinación" de paquetes (typosquatting)

Devuelve código de salida 1 si encuentra hallazgos (sirve para CI).
"""
from __future__ import annotations

import ast
import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CARPETAS_EXCLUIDAS = {"venv", ".venv", "env", "__pycache__", ".git", "logs"}
METODOS_SQL = {"execute", "executemany", "executescript", "_consultar_uno", "_consultar_todos"}
METODOS_HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "request"}
# Nombre del import -> nombre del paquete en PyPI cuando no coinciden
IMPORT_A_PAQUETE = {"dotenv": "python-dotenv", "yaml": "pyyaml", "PIL": "pillow", "bs4": "beautifulsoup4"}


@dataclass(frozen=True)
class Hallazgo:
    senal: str
    archivo: str
    linea: int
    detalle: str


def _es_objeto_http(nodo: ast.AST) -> bool:
    """requests.get(...), sesion.get(...), self._sesion.get(...), session.post(...)"""
    if isinstance(nodo, ast.Name):
        nombre = nodo.id.lower()
        return nombre == "requests" or "sesion" in nombre or "session" in nombre
    if isinstance(nodo, ast.Attribute):
        nombre = nodo.attr.lower()
        return "sesion" in nombre or "session" in nombre
    return False


def _sql_armado(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.JoinedStr):
        return True
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, (ast.Add, ast.Mod)):
        return True
    return isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "format"


def auditar_codigo(codigo: str, nombre_archivo: str) -> list[Hallazgo]:
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as error:
        return [Hallazgo("Sintaxis", nombre_archivo, error.lineno or 0, "el archivo no se pudo analizar")]
    hallazgos: list[Hallazgo] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            nombres_kw = {kw.arg for kw in nodo.keywords}
            # 1. SQL armado
            if isinstance(nodo.func, ast.Attribute) and nodo.func.attr in METODOS_SQL and nodo.args \
                    and _sql_armado(nodo.args[0]):
                hallazgos.append(Hallazgo("1. SQL con f-string/concatenación", nombre_archivo, nodo.lineno,
                                          f"{nodo.func.attr}() recibe SQL armado con datos"))
            # 2. verify=False
            for kw in nodo.keywords:
                if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    hallazgos.append(Hallazgo("2. verify=False", nombre_archivo, nodo.lineno,
                                              "desactiva la verificación del certificado SSL"))
            # 4. HTTP sin timeout (None en kw.arg significa **kwargs: no se puede saber, se acepta)
            es_http = (isinstance(nodo.func, ast.Attribute) and nodo.func.attr in METODOS_HTTP
                       and _es_objeto_http(nodo.func.value))
            es_urlopen = (isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "urlopen") or \
                         (isinstance(nodo.func, ast.Name) and nodo.func.id == "urlopen")
            if (es_http or es_urlopen) and "timeout" not in nombres_kw and None not in nombres_kw:
                hallazgos.append(Hallazgo("4. Llamada HTTP sin timeout", nombre_archivo, nodo.lineno,
                                          "la petición puede bloquear el programa indefinidamente"))
        # 3. except: pass
        if isinstance(nodo, ast.ExceptHandler):
            solo_pass = all(isinstance(s, ast.Pass) or
                            (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is ...)
                            for s in nodo.body)
            if solo_pass:
                tipo = "except:" if nodo.type is None else f"except {ast.unparse(nodo.type)}:"
                hallazgos.append(Hallazgo("3. except: pass", nombre_archivo, nodo.lineno,
                                          f"'{tipo} pass' silencia errores sin registrarlos"))
    return hallazgos


def _modulos_importados(codigo: str) -> set[str]:
    try:
        arbol = ast.parse(codigo)
    except SyntaxError:
        return set()
    modulos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            modulos.add(nodo.module.split(".")[0])
    return modulos


def leer_requirements(ruta: Path) -> dict[str, str]:
    """{'requests': '2.32.5', ...} (nombre normalizado en minúsculas)."""
    paquetes = {}
    if not ruta.exists():
        return paquetes
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#")[0].strip()
        if not linea:
            continue
        coincidencia = re.match(r"^([A-Za-z0-9_.\-]+)\s*(?:==\s*([\w.]+))?", linea)
        if coincidencia:
            paquetes[coincidencia.group(1).lower().replace("_", "-")] = coincidencia.group(2) or ""
    return paquetes


def auditar_dependencias(raiz: Path, archivos: list[Path], consultar_pypi: bool) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    requirements = leer_requirements(raiz / "requirements.txt")
    locales = {p.stem for p in raiz.glob("*.py")} | {p.name for p in raiz.iterdir() if p.is_dir()}
    estandar = set(sys.stdlib_module_names)

    # 5a. Cada import externo debe estar declarado en requirements.txt
    for archivo in archivos:
        for modulo in sorted(_modulos_importados(archivo.read_text(encoding="utf-8"))):
            if modulo in estandar or modulo in locales or modulo == "__future__":
                continue
            paquete = IMPORT_A_PAQUETE.get(modulo, modulo).lower().replace("_", "-")
            if paquete not in requirements:
                hallazgos.append(Hallazgo("5. Librería no declarada/inexistente", archivo.name, 0,
                                          f"import '{modulo}' no está en requirements.txt"))

    # 5b. Cada paquete declarado debe estar instalado (y existir en PyPI si se pide)
    cliente = None
    if consultar_pypi:
        from api_cliente import ClienteAPI  # import tardío: la auditoría básica no necesita red
        cliente = ClienteAPI("PyPI", "https://pypi.org/pypi", timeout=(3.05, 10), max_intentos=2)
    for paquete, version in requirements.items():
        try:
            instalada = importlib.metadata.version(paquete)
        except importlib.metadata.PackageNotFoundError:
            hallazgos.append(Hallazgo("5. Librería no declarada/inexistente", "requirements.txt", 0,
                                      f"'{paquete}' no está instalado (pip install -r requirements.txt)"))
            instalada = None
        if instalada and version and instalada != version:
            print(f"  (aviso) {paquete}: instalada {instalada}, requirements pide {version}")
        if cliente is not None:
            hallazgos.extend(_verificar_en_pypi(cliente, paquete, version))
    if cliente is not None:
        cliente.cerrar()
    return hallazgos


def _verificar_en_pypi(cliente, paquete: str, version: str) -> list[Hallazgo]:
    from dominio.excepciones import ServicioExternoError
    ruta = f"{paquete}/{version}/json" if version else f"{paquete}/json"
    try:
        cliente.obtener_json(ruta)
        print(f"  PyPI OK: {paquete} {version}")
        return []
    except ServicioExternoError as error:
        if error.codigo_http == 404:
            return [Hallazgo("5. Librería no declarada/inexistente", "requirements.txt", 0,
                             f"'{paquete}=={version}' NO existe en PyPI")]
        print(f"  (aviso) no se pudo verificar {paquete} en PyPI: {error}")
        return []


def archivos_python(raiz: Path) -> list[Path]:
    return sorted(p for p in raiz.rglob("*.py") if not CARPETAS_EXCLUIDAS.intersection(p.relative_to(raiz).parts))


def auditar_proyecto(raiz: Path, consultar_pypi: bool = False) -> list[Hallazgo]:
    archivos = archivos_python(raiz)
    hallazgos: list[Hallazgo] = []
    for archivo in archivos:
        hallazgos.extend(auditar_codigo(archivo.read_text(encoding="utf-8"), str(archivo.relative_to(raiz))))
    hallazgos.extend(auditar_dependencias(raiz, archivos, consultar_pypi))
    return hallazgos


def main(argumentos: list[str]) -> int:
    consultar_pypi = "--pypi" in argumentos
    rutas = [a for a in argumentos if not a.startswith("--")]
    raiz = Path(rutas[0]).resolve() if rutas else Path(__file__).resolve().parent
    print(f"Auditoría de señales de riesgo IA en: {raiz.name}/  ({len(archivos_python(raiz))} archivos .py)")
    hallazgos = auditar_proyecto(raiz, consultar_pypi)
    senales = ["1. SQL con f-string/concatenación", "2. verify=False", "3. except: pass",
               "4. Llamada HTTP sin timeout", "5. Librería no declarada/inexistente"]
    print("-" * 70)
    for senal in senales:
        cantidad = sum(1 for h in hallazgos if h.senal == senal)
        print(f"  {'OK ' if cantidad == 0 else '!! '} {senal:<42} {cantidad} hallazgo(s)")
    print("-" * 70)
    for h in hallazgos:
        ubicacion = f"{h.archivo}:{h.linea}" if h.linea else h.archivo
        print(f"  {ubicacion:<35} {h.senal}: {h.detalle}")
    if not hallazgos:
        print("  Sin hallazgos. El código no presenta las 5 señales de riesgo.")
    return 1 if hallazgos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
