-- Esquema relacional de EcoTech Solutions (SQLite 3)
-- Se ejecuta con inicializar_bd(); es seguro correrlo varias veces (IF NOT EXISTS).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departamento (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT    NOT NULL UNIQUE,
    presupuesto  REAL    NOT NULL CHECK (presupuesto >= 0)
);

-- Persona (padre) y Empleado (hijo) reflejan la herencia del diagrama UML
CREATE TABLE IF NOT EXISTS persona (
    rut       TEXT PRIMARY KEY,
    nombre    TEXT NOT NULL,
    email     TEXT NOT NULL,
    telefono  TEXT
);

CREATE TABLE IF NOT EXISTS empleado (
    rut              TEXT    PRIMARY KEY,
    cargo            TEXT    NOT NULL,
    sueldo_base      REAL    NOT NULL CHECK (sueldo_base > 0),
    fecha_ingreso    TEXT    NOT NULL,
    departamento_id  INTEGER,
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    FOREIGN KEY (rut)             REFERENCES persona(rut),
    FOREIGN KEY (departamento_id) REFERENCES departamento(id)
);

CREATE TABLE IF NOT EXISTS proyecto (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT NOT NULL UNIQUE,
    descripcion   TEXT,
    fecha_inicio  TEXT NOT NULL
);

-- Tabla intermedia de la relación muchos-a-muchos Empleado <-> Proyecto
CREATE TABLE IF NOT EXISTS asignacion (
    rut_empleado  TEXT    NOT NULL,
    proyecto_id   INTEGER NOT NULL,
    PRIMARY KEY (rut_empleado, proyecto_id),
    FOREIGN KEY (rut_empleado) REFERENCES empleado(rut),
    FOREIGN KEY (proyecto_id)  REFERENCES proyecto(id)
);

-- =====================================================================
-- Unidad 3: usuarios, ubicación de proyectos y datos de APIs externas
-- =====================================================================

-- Usuarios del sistema. La BD misma rechaza contraseñas en texto plano:
-- solo acepta un hash bcrypt ($2a$/$2b$/$2y$, 60 caracteres).
CREATE TABLE IF NOT EXISTS usuario (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario     TEXT    NOT NULL UNIQUE,
    hash_contrasena    TEXT    NOT NULL
                       CHECK (length(hash_contrasena) = 60 AND substr(hash_contrasena, 1, 2) = '$2'),
    rol                TEXT    NOT NULL CHECK (rol IN ('admin', 'operador')),
    intentos_fallidos  INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta    TEXT,
    creado_en          TEXT    NOT NULL
);

-- Dónde se ejecuta cada proyecto (ciudad para el clima y país para la moneda de pago)
CREATE TABLE IF NOT EXISTS ubicacion_proyecto (
    proyecto_id  INTEGER PRIMARY KEY,
    ciudad       TEXT NOT NULL,
    codigo_pais  TEXT NOT NULL CHECK (length(codigo_pais) = 2),
    FOREIGN KEY (proyecto_id) REFERENCES proyecto(id) ON DELETE CASCADE
);

-- Clima obtenido desde Open-Meteo. La restricción UNIQUE hace la carga IDEMPOTENTE:
-- la misma medición (ciudad + país + hora de medición) nunca se guarda dos veces.
CREATE TABLE IF NOT EXISTS registro_clima (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    clave_ciudad  TEXT    NOT NULL,
    ciudad        TEXT    NOT NULL,
    codigo_pais   TEXT    NOT NULL,
    latitud       REAL    NOT NULL,
    longitud      REAL    NOT NULL,
    temperatura   REAL    NOT NULL,
    humedad       INTEGER NOT NULL CHECK (humedad BETWEEN 0 AND 100),
    codigo_clima  INTEGER NOT NULL,
    viento_kmh    REAL    NOT NULL CHECK (viento_kmh >= 0),
    medido_en     TEXT    NOT NULL,
    obtenido_en   TEXT    NOT NULL,
    UNIQUE (clave_ciudad, codigo_pais, medido_en)
);

-- Tipo de cambio obtenido desde ExchangeRate-API (1 unidad de 'moneda' = valor_clp pesos).
-- Una tasa por moneda y por fecha de publicación (idempotente).
CREATE TABLE IF NOT EXISTS tipo_cambio (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    moneda           TEXT NOT NULL CHECK (length(moneda) = 3),
    valor_clp        REAL NOT NULL CHECK (valor_clp > 0),
    actualizado_api  TEXT NOT NULL,
    obtenido_en      TEXT NOT NULL,
    UNIQUE (moneda, actualizado_api)
);
