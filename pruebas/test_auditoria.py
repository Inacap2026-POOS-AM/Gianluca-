"""El auditor detecta las 5 señales de riesgo y el proyecto actual no tiene ninguna."""
import unittest
from pathlib import Path

from auditoria_ia import auditar_codigo, auditar_proyecto

RAIZ = Path(__file__).resolve().parent.parent

# Código "típico de IA" con las señales 1 a 4 (solo se analiza, nunca se ejecuta)
CODIGO_INSEGURO = '''
import requests

def guardar(cursor, ciudad, temp):
    cursor.execute(f"INSERT INTO clima VALUES ('{ciudad}', {temp})")
    cursor.execute("SELECT * FROM usuario WHERE nombre = '" + ciudad + "'")

def obtener(url):
    try:
        return requests.get(url, verify=False).json()
    except:
        pass
'''


class PruebasAuditoria(unittest.TestCase):
    def test_detecta_las_senales(self):
        senales = {h.senal for h in auditar_codigo(CODIGO_INSEGURO, "ia.py")}
        self.assertEqual(senales, {"1. SQL con f-string/concatenación", "2. verify=False",
                                   "3. except: pass", "4. Llamada HTTP sin timeout"})

    def test_codigo_corregido_no_tiene_hallazgos(self):
        corregido = '''
import logging, requests
def obtener(sesion, url):
    try:
        return sesion.get(url, timeout=(3.05, 10)).json()
    except requests.exceptions.RequestException:
        logging.exception("falló")
        raise
'''
        self.assertEqual(auditar_codigo(corregido, "ok.py"), [])

    def test_proyecto_sin_senales_de_riesgo(self):
        hallazgos = auditar_proyecto(RAIZ)
        self.assertEqual(hallazgos, [], "\n".join(f"{h.archivo}:{h.linea} {h.detalle}" for h in hallazgos))


if __name__ == "__main__":
    unittest.main()
