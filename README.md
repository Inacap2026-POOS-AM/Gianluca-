# EcoTech Solutions — ES3 · TI3021 Programación Orientada a Objeto Seguro

Extensión del sistema de gestión de empleados y proyectos (ES2) con **consumo seguro de
APIs externas**, **inicio de sesión con contraseñas hasheadas** y **degradación controlada (Plan B)**.

| Necesidad de EcoTech | API usada (gratuita, sin registro) | Dato que se usa |
|---|---|---|
| Planificar proyectos según el clima | [Open-Meteo](https://open-meteo.com/) (geocodificación + pronóstico) | temperatura, humedad, estado del tiempo, viento |
| Pagar trabajadores en moneda local | [ExchangeRate-API](https://www.exchangerate-api.com/docs/free) (endpoint abierto) | tipo de cambio a CLP |

## Requisitos
- Python 3.10 o superior.

## Cómo ejecutar
```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Linux/Mac: cp .env.example .env
python main.py
```
1. La primera vez se pide crear el **usuario administrador** (contraseña de 8+ caracteres con mayúsculas, minúsculas y números).
2. Luego se inicia sesión (3 intentos por ejecución; 5 fallos seguidos bloquean la cuenta 5 minutos).
3. Si la base está vacía, se ofrecen datos de ejemplo: 3 proyectos con ubicación en Antofagasta (CL), Arequipa (PE) y Medellín (CO).
4. Menú **5. Servicios externos**: clima, tipo de cambio, pagos internacionales, sincronización y diagnóstico.

> Ejecútelo desde una terminal (CMD, PowerShell o la terminal de VS Code) para que la contraseña no se vea al escribirla.

## Scripts
| Comando | Para qué sirve |
|---|---|
| `python main.py` | Sistema completo con login y menús |
| `python sincronizar.py` | Descarga clima de los proyectos + tipos de cambio. **Idempotente**: correrlo 2 veces no duplica filas |
| `python demo_errores.py` | Demostración sin internet: 200, 404, 429 + Retry-After, 500, 503, timeout, JSON corrupto, sin red y Plan B |
| `python auditoria_ia.py` | Revisa todo el código buscando las 5 señales de riesgo de código IA (`--pypi` verifica además los paquetes en pypi.org) |
| `python demo_seguridad.py` | (ES2) inyección SQL bloqueada y rollback |
| `python -m unittest discover -s pruebas -t . -v` | 77 pruebas automáticas |

## Pruebas en vivo (sesión C14)
| Prueba | Cómo se demuestra | Qué debe verse |
|---|---|---|
| 1. Ejecución consecutiva | `python sincronizar.py` dos veces | 2ª vez: "Nuevos: 0", "Filas registro_clima: 3 -> 3". Restricción `UNIQUE` + `INSERT ... ON CONFLICT DO UPDATE` |
| 2. Corte de red | Desconectar WiFi y usar menú 5 → opción 2 o 4, o `sincronizar.py` | "AVISO - Fuente: BD local (Plan B)" con fecha y antigüedad (`obtenido_en`). Sin trazas |
| 3. URL inválida | Menú 5 → opción 8, o cambiar `ECOTECH_URL_CLIMA` en `.env` (ej. `https://api.open-meteo.com/v1/malo`) | "(404)… no existe": **no se reintenta** y se usa el Plan B |
| 4. Inspección de BD | `python -c "import sqlite3; [print(f) for f in sqlite3.connect('datos/ecotech.db').execute('SELECT nombre_usuario, hash_contrasena FROM usuario')]"` (o DB Browser for SQLite) | Hash `$2b$12$...` de 60 caracteres. La tabla además tiene un `CHECK` que rechaza texto plano |

## Decisiones técnicas principales
- **`api_cliente.py`** — `ClienteAPI` sobre `requests.Session`:
  - `timeout=(3.05, 10)` explícito en toda petición; HTTPS obligatorio; nunca `verify=False`.
  - **4xx no se reintenta** (el error es nuestro: repetir no lo arregla). **429** respeta `Retry-After`. **5xx, timeout y sin red** se reintentan.
  - Máximo **3 intentos** (configurable 1–4) con **backoff exponencial** 1 s → 2 s (+ azar ≤10 %).
  - Cortocircuito: tras agotar reintentos, ese servicio falla inmediato por 30 s (sin red, la sincronización tarda segundos y no minutos).
  - Errores propios (`ServicioNoDisponibleError`, `SolicitudRechazadaError`, `RespuestaInvalidaError`) con mensajes sin URLs, llaves ni trazas; el detalle va a `logs/ecotech.log`.
- **Plan B** (`servicios/clima_servicio.py`, `servicios/divisas_servicio.py`): ante cualquier falla de la API se lee el último dato guardado y se muestra su antigüedad (`obtenido_en`). Si no hay datos, mensaje claro (nunca pantalla vacía).
- **Deserialización** (`servicios/deserializadores.py`): `DeserializadorClima` y `DeserializadorTipoCambio` validan campos, tipos (rechazan `bool` como número), rangos y fechas antes de crear objetos del dominio (`RegistroClima`, `TipoCambio`).
- **Persistencia**: 100 % consultas parametrizadas `?`. Idempotencia con `UNIQUE (ciudad, país, hora de medición)` y `UNIQUE (moneda, fecha de publicación)`.
- **Validación de entradas**: ciudad (solo letras/espacios/guiones, 2–60), país y moneda por **lista blanca** ISO; ninguna entrada inválida llega a la API.
- **Seguridad de usuarios** (`seguridad/autenticacion.py`): bcrypt con salt (12 rondas), mensaje genérico "Usuario o contraseña incorrectos", hash señuelo contra enumeración de usuarios, bloqueo por intentos, rol admin para crear usuarios.
- **Secretos**: `.env` fuera de Git; llave de API opcional enviada por cabecera `Authorization: Bearer`.
- **Pagos**: `Decimal` con redondeo `ROUND_HALF_UP` (sin errores de `float`).

## Estructura
```
├── api_cliente.py          Cliente HTTP seguro (timeout, reintentos, backoff, códigos HTTP)
├── config.py               Lectura del .env y configuración de logs
├── main.py                 Menú principal (ahora exige login)
├── menu_servicios.py       Login + menús de servicios externos y usuarios
├── consola.py              Lectura segura por teclado (incluye getpass)
├── sincronizar.py          Script idempotente de sincronización
├── demo_errores.py         Demo de manejo de errores sin internet
├── auditoria_ia.py         Auditor de las 5 señales de riesgo
├── bitacora_ia.md          Bitácora de auditoría del uso de IA
├── dominio/                + clima.py, tipo_cambio.py, ubicacion.py, usuario.py
├── repositorio/            + clima_repo.py, tipo_cambio_repo.py, ubicacion_repo.py, usuario_repo.py
├── seguridad/              autenticacion.py (bcrypt)
├── servicios/              deserializadores, clima, divisas, sincronización, Plan B
├── datos/schema.sql        + tablas usuario, ubicacion_proyecto, registro_clima, tipo_cambio
└── pruebas/                + test_api_cliente, test_servicios, test_usuarios, test_auditoria
```

Datos de tipo de cambio: [Rates By Exchange Rate API](https://www.exchangerate-api.com). Datos de clima: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0).
