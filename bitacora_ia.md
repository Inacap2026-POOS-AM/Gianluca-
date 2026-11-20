# Bitácora de IA — Auditoría técnica del código generado (ES3 · TI3021)

| | |
|---|---|
| **Estudiante** | _[Nombre Apellido]_ — rama `e3/[apellido]` |
| **Herramienta de IA** | Claude (Anthropic), chat |
| **Alcance** | `api_cliente.py`, servicios de clima y divisas, deserializadores, persistencia, login con bcrypt |
| **Método** | 1) pedir un fragmento a la IA → 2) leerlo línea a línea y probarlo → 3) buscar las 5 señales de riesgo → 4) decidir **aceptar / modificar / descartar** → 5) verificar con `python auditoria_ia.py` y las pruebas de `pruebas/` |

## 1. Resumen de las 5 señales de riesgo

| # | Señal | ¿Apareció en código IA? | Decisión | Dónde quedó resuelto | Cómo se verifica |
|---|---|---|---|---|---|
| 1 | f-strings / concatenación en SQL | Sí, al guardar el clima | **Modificado** | `repositorio/clima_repo.py` (`?` + UPSERT) | `test_ningun_execute_usa_sql_armado`, auditor señal 1 |
| 2 | `verify=False` | Sí, como "solución" a un error SSL | **Descartado** | `api_cliente.py` (captura `SSLError`, no continúa) | `test_error_ssl_no_se_reintenta`, auditor señal 2 |
| 3 | `except: pass` | Sí, en la función de consulta HTTP | **Modificado** | `api_cliente.py`, `clima_servicio.py` (excepciones específicas + log + Plan B) | `test_plan_b_sin_red_usa_datos_locales`, auditor señal 3 |
| 4 | Llamadas sin `timeout` | Sí, `requests.get(url)` | **Modificado** | `api_cliente.py` (`timeout=(3.05, 10)` siempre) | `test_200_devuelve_json_y_usa_timeout`, auditor señal 4 |
| 5 | Librerías inexistentes en PyPI | Sí, `mindicador-api` | **Descartado** | `requirements.txt` solo con `requests`, `bcrypt`, `python-dotenv` | `pip index versions`, `python auditoria_ia.py --pypi` |

Resultado final de `python auditoria_ia.py`:
```
  OK  1. SQL con f-string/concatenación          0 hallazgo(s)
  OK  2. verify=False                            0 hallazgo(s)
  OK  3. except: pass                            0 hallazgo(s)
  OK  4. Llamada HTTP sin timeout                0 hallazgo(s)
  OK  5. Librería no declarada/inexistente       0 hallazgo(s)
```

---

## 2. Detalle de cada señal

### Señal 1 — SQL armado con f-string → MODIFICADO

**Prompt:** "Guarda en SQLite los datos de clima que devuelve la API."

**Propuesta de la IA:**
```python
cursor.execute(f"INSERT INTO clima VALUES ('{ciudad}', {temp}, {humedad})")
```
**Riesgo:** `ciudad` viene del usuario o de la API. Un texto como `x'); DROP TABLE usuario;--` se ejecutaría como SQL (**inyección SQL**). Además, cada ejecución insertaba otra fila igual (sin idempotencia).

**Código final** (`repositorio/clima_repo.py`):
```python
INSERT INTO registro_clima (clave_ciudad, ciudad, ...) VALUES (?, ?, ...)
ON CONFLICT (clave_ciudad, codigo_pais, medido_en) DO UPDATE SET ... obtenido_en = excluded.obtenido_en
```
**Justificación:** los marcadores `?` envían los valores separados del SQL, así el motor los trata solo como datos. La restricción `UNIQUE` + `ON CONFLICT` hace que correr el script dos veces no duplique filas (prueba en vivo 1).

### Señal 2 — `verify=False` → DESCARTADO

**Prompt:** "Me sale `SSLError: certificate verify failed` al llamar a la API, ¿cómo lo arreglo?"

**Propuesta de la IA:**
```python
respuesta = requests.get(url, verify=False)
```
**Riesgo:** desactiva la comprobación del certificado: cualquiera en la misma red (WiFi pública) puede hacerse pasar por la API y entregar datos falsos de tipo de cambio (**ataque de intermediario, MITM**). Esconde el problema en vez de resolverlo.

**Decisión:** se descartó por completo. La causa real de ese error suele ser un reloj del PC desfasado o certificados raíz desactualizados (`pip install --upgrade certifi`).

**Código final** (`api_cliente.py`): se captura `requests.exceptions.SSLError` **antes** que `ConnectionError`, no se reintenta y se informa "no se pudo verificar el certificado de seguridad; por seguridad no se continúa". El sistema sigue con el Plan B.

### Señal 3 — `except: pass` → MODIFICADO

**Prompt:** "Haz que el programa no se caiga si la API falla."

**Propuesta de la IA:**
```python
try:
    datos = requests.get(url).json()
except:
    pass
```
**Riesgo:** el `except:` desnudo atrapa *todo* (incluso Ctrl+C y errores de programación) y el `pass` lo oculta. Después `datos` no existe → `NameError` más adelante, o se muestra una pantalla vacía sin explicación. Imposible de depurar.

**Código final:** cada excepción se captura por su tipo y tiene una acción:
- `Timeout` / `ConnectionError` / 5xx → se reintenta con backoff y, si se agota, `ServicioNoDisponibleError`.
- 4xx → `SolicitudRechazadaError` sin reintento.
- JSON inválido → `RespuestaInvalidaError`.
- En `ClimaServicio.consultar()` cualquier `ServicioExternoError` activa el **Plan B** (datos de la BD con `obtenido_en`), y se registra en `logs/ecotech.log`.
- La única captura general (`except Exception`) está en el menú como última barrera: **registra la traza en el log** y muestra un mensaje amable; no la oculta.

### Señal 4 — llamada HTTP sin `timeout` → MODIFICADO

**Prompt:** "Consulta el clima de una ciudad con Open-Meteo."

**Propuesta de la IA:**
```python
r = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
r.raise_for_status()
```
**Riesgo:** `requests` **no tiene timeout por defecto**: si la API acepta la conexión y nunca responde, el programa queda congelado para siempre. Además `raise_for_status()` trata igual un 404 que un 503 y no permite decidir qué reintentar.

**Código final** (`api_cliente.py`): `self._sesion.get(url, params=params, timeout=self._timeout)` con `(3.05, 10)` (3 s para conectar, 10 s para leer), configurable en `.env`. Los códigos se evalúan uno por uno (ver sección 3).

### Señal 5 — librería inexistente → DESCARTADO

**Prompt:** "¿Qué librería de Python uso para obtener el dólar e indicadores de Chile?"

**Propuesta de la IA:** `pip install mindicador-api` y `from mindicador_api import Indicadores`.

**Verificación:**
```
> pip index versions mindicador-api
ERROR: No matching distribution found for mindicador-api
```
**Riesgo:** un paquete "alucinado" no existe hoy, pero un atacante puede registrarlo mañana con ese nombre y código malicioso (*slopsquatting / typosquatting*). Instalarlo a ciegas ejecutaría ese código en el PC.

**Decisión:** se descartó. Las APIs se consumen directamente con `requests` (librería oficial y mantenida). `requirements.txt` contiene solo 3 paquetes con versión fija, verificados en pypi.org. `auditoria_ia.py` revisa además que cada `import` externo esté declarado en `requirements.txt`.

---

## 3. Otros ajustes al código de la IA

| Fragmento de la IA | Problema detectado | Decisión | Resultado final |
|---|---|---|---|
| Reintentar dentro de `while True:` ante cualquier error | Bucle infinito; reintenta también 400/404, que nunca se arreglan solos | **Modificado** | Máx. 3 intentos (`max_intentos` 1–4), 4xx sin reintento, 429 con `Retry-After`, 5xx/red con backoff 1 s → 2 s |
| Espera fija `time.sleep(5)` entre intentos | Todos los clientes reintentan al mismo tiempo y saturan al servidor | **Modificado** | Backoff exponencial + azar ≤10 % (`_calcular_backoff`) |
| `hashlib.sha256(password.encode()).hexdigest()` para contraseñas | Sin salt (claves iguales → hash igual) y demasiado rápido (fuerza bruta barata) | **Descartado** | `bcrypt.hashpw(..., bcrypt.gensalt(rounds=12))`; la tabla `usuario` tiene un `CHECK` que solo acepta hashes `$2...` de 60 caracteres |
| Mensajes distintos "usuario no existe" / "contraseña incorrecta" | Permite descubrir qué usuarios existen (enumeración) | **Modificado** | Mensaje único "Usuario o contraseña incorrectos" + hash señuelo para igualar el tiempo de respuesta |
| `print(f"Error: {e}")` mostrando la excepción completa | Expone URLs, rutas del PC y, con plan pago, la llave de API | **Modificado** | Mensajes propios sin datos internos; detalle técnico solo en `logs/ecotech.log` (y `urllib3` silenciado en el log) |
| Llave de API en la URL `.../v6/{API_KEY}/latest/USD` | La URL queda en logs e historial | **Modificado** | Llave en `.env` y enviada como cabecera `Authorization: Bearer` (soportado por ExchangeRate-API) |
| `data["current"]["temperature_2m"]` directo | `KeyError`/`TypeError` si la API cambia el formato → caída del programa | **Modificado** | Clase `DeserializadorClima`: valida existencia, tipo (rechaza `bool`) y rango de cada campo |
| `float` para convertir sueldos | Errores de redondeo en montos de dinero | **Modificado** | `Decimal` + `ROUND_HALF_UP` en `TipoCambio.convertir_desde_clp` |
| `requests.Session` reutilizable | Correcto: reutiliza conexiones y centraliza cabeceras | **Aceptado** | `ClienteAPI` usa una sesión por servicio |
| `email.utils.parsedate_to_datetime` para fechas HTTP | Correcto, es de la librería estándar | **Aceptado** | Usado en `Retry-After` y en la fecha de ExchangeRate-API |
| `HTTPAdapter(max_retries=Retry(...))` de urllib3 | Funciona, pero oculta la lógica y no permite explicar/controlar cada código | **Descartado** | Reintentos escritos explícitamente en `ClienteAPI.obtener_json` |

## 4. Conclusión

La IA aceleró la escritura de la estructura (sesión HTTP, clases, pruebas), pero **todas** las propuestas
iniciales para consumir la API tenían al menos una de las 5 señales de riesgo. Lo más peligroso fue que el
código inseguro *funcionaba* en una prueba rápida: `verify=False` "arreglaba" el error SSL y `except: pass`
"evitaba" las caídas. Por eso cada fragmento se revisó contra la lista de señales, se probó en los casos de
falla (sin red, 404, 429, 500, JSON corrupto) y se dejó una auditoría automática (`auditoria_ia.py`) y
77 pruebas para que cualquier regresión se detecte de inmediato.
