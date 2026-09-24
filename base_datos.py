"""
base_datos.py
-------------
Todo lo que tiene que ver con guardar, leer y borrar datos en Neon (PostgreSQL).
La dirección de conexión NO está aquí: se lee de los "Secrets" de Streamlit.

PRIVACIDAD: la cédula/CURP nunca se guarda tal cual. Antes de guardarla se
convierte en un código irreversible (ej. "h_3f9a...") usando CLAVE_PRIVACIDAD,
que vive solo en los Secrets. El mismo aliado siempre da el mismo código, así
que los cruces entre PagoYa, Membresías y Saldos siguen funcionando.
"""

import hashlib
import hmac
import io

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

MAX_CARGAS_SALDOS = 8   # se conservan solo las últimas 8 cargas de Saldos

COLUMNAS = {
    "membresias": ["semana", "fecha_deposito", "nombre", "identificacion",
                   "tipo_plan", "valor_plan", "saldo_actual", "disponible", "ciudad",
                   "pais", "estado_retiro", "estado_aliado", "membresia_activa", "origen"],
    "pagoya": ["semana", "id_retiro", "nombre", "identificacion", "ciudad",
               "pais", "fecha", "fecha_validacion", "vehiculo", "valor",
               "comision", "iva", "estado", "gps_falso", "black_list", "cancelacion",
               "pago_parcial", "pagar", "estado_aliado", "origen"],
    "saldos": ["fecha_corte", "semana", "identificacion", "nombre", "ciudad",
               "pais", "saldo", "origen"],
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS membresias (
    id BIGSERIAL PRIMARY KEY,
    semana TEXT NOT NULL,
    fecha_deposito DATE,
    nombre TEXT,
    identificacion TEXT,
    tipo_plan TEXT,
    valor_plan NUMERIC,
    saldo_actual NUMERIC,
    disponible NUMERIC,
    ciudad TEXT,
    pais TEXT,
    estado_retiro TEXT,
    estado_aliado TEXT,
    membresia_activa TEXT,
    origen TEXT NOT NULL DEFAULT 'archivo',
    cargado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_memb_semana ON membresias (semana);
CREATE INDEX IF NOT EXISTS ix_memb_ident ON membresias (identificacion);

CREATE TABLE IF NOT EXISTS pagoya (
    id BIGSERIAL PRIMARY KEY,
    semana TEXT NOT NULL,
    id_retiro TEXT,
    nombre TEXT,
    identificacion TEXT,
    ciudad TEXT,
    pais TEXT,
    fecha DATE,
    fecha_validacion DATE,
    vehiculo TEXT,
    valor NUMERIC,
    comision NUMERIC,
    iva NUMERIC,
    estado TEXT,
    gps_falso NUMERIC,
    black_list TEXT,
    cancelacion NUMERIC,
    pago_parcial NUMERIC,
    pagar TEXT,
    estado_aliado TEXT,
    origen TEXT NOT NULL DEFAULT 'archivo',
    cargado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pago_semana ON pagoya (semana);
CREATE INDEX IF NOT EXISTS ix_pago_ident ON pagoya (identificacion);
CREATE INDEX IF NOT EXISTS ix_pago_retiro ON pagoya (id_retiro);

CREATE TABLE IF NOT EXISTS saldos (
    id BIGSERIAL PRIMARY KEY,
    fecha_corte DATE NOT NULL,
    semana TEXT NOT NULL,
    identificacion TEXT,
    nombre TEXT,
    ciudad TEXT,
    pais TEXT,
    saldo NUMERIC,
    origen TEXT NOT NULL DEFAULT 'archivo',
    cargado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_saldos_corte ON saldos (fecha_corte);

"""


@st.cache_resource(show_spinner="Conectando con la base de datos...")
def motor():
    """Crea la conexión una sola vez y deja listas las tablas."""
    url = st.secrets["DATABASE_URL"].strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    eng = create_engine(url, pool_pre_ping=True, pool_recycle=280)
    with eng.begin() as con:
        con.execute(text(ESQUEMA))
        con.execute(text(MIGRACION))
        _cifrar_identificaciones_viejas(con)
    return eng


# Limpieza de versiones anteriores de la app (no hace nada si ya está todo limpio).
MIGRACION = """
ALTER TABLE membresias DROP COLUMN IF EXISTS id_user;
ALTER TABLE pagoya DROP COLUMN IF EXISTS id_user;
ALTER TABLE pagoya DROP COLUMN IF EXISTS codigo_banco;
ALTER TABLE saldos DROP COLUMN IF EXISTS id_user;
DROP TABLE IF EXISTS precios_planes;
DELETE FROM saldos WHERE origen = 'html';
UPDATE membresias SET valor_plan = CASE
    WHEN lower(tipo_plan) LIKE '%blue%' AND lower(tipo_plan) NOT LIKE '%winback%' THEN 64900
    WHEN lower(tipo_plan) LIKE '%sico%' THEN 44900 END
WHERE valor_plan IS NULL AND pais = 'Colombia';
"""


def _clave_privacidad() -> bytes:
    return str(st.secrets["CLAVE_PRIVACIDAD"]).encode("utf-8")


def seudonimo(valor):
    """Convierte una cédula/CURP en un código irreversible. Siempre da el mismo código."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    v = str(valor)
    if v.startswith("h_"):
        return v
    return "h_" + hmac.new(_clave_privacidad(), v.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _cifrar_identificaciones_viejas(con):
    """Si hay identificaciones guardadas sin cifrar (versión anterior), las cifra."""
    for tabla in ("membresias", "pagoya", "saldos"):
        viejas = [r[0] for r in con.execute(text(
            f"SELECT DISTINCT identificacion FROM {tabla} "
            "WHERE identificacion IS NOT NULL AND identificacion NOT LIKE 'h\\_%'"))]
        if not viejas:
            continue
        mapa = pd.DataFrame({"orig": viejas, "cod": [seudonimo(v) for v in viejas]})
        con.execute(text("CREATE TEMP TABLE IF NOT EXISTS mapa_ids (orig TEXT, cod TEXT) ON COMMIT DROP"))
        con.execute(text("TRUNCATE mapa_ids"))
        buf = io.StringIO()
        mapa.to_csv(buf, index=False, header=False)
        buf.seek(0)
        con.connection.cursor().copy_expert("COPY mapa_ids (orig, cod) FROM STDIN WITH (FORMAT csv)", buf)
        con.execute(text(f"UPDATE {tabla} t SET identificacion = m.cod FROM mapa_ids m "
                         "WHERE t.identificacion = m.orig"))


def _copiar(con, tabla, df):
    """Inserta muchas filas de una vez (mucho más rápido que fila por fila)."""
    if df.empty:
        return
    cols = COLUMNAS[tabla]
    df = df.assign(identificacion=df["identificacion"].map(seudonimo))
    buf = io.StringIO()
    df[cols].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cursor = con.connection.cursor()
    cursor.copy_expert(
        f"COPY {tabla} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)


def _lista(serie):
    return sorted({v for v in serie.dropna().tolist()})


def limpiar_cache():
    st.cache_data.clear()


# ----------------------------------------------------------------------
# Guardar cargas semanales
# ----------------------------------------------------------------------

def guardar_membresias(df: pd.DataFrame):
    df = df.assign(origen="archivo")
    with motor().begin() as con:
        fechas = _lista(df["fecha_deposito"])
        semanas = _lista(df["semana"])
        # Si vuelves a subir el mismo archivo, se reemplaza (no se duplica).
        if fechas:
            con.execute(text("DELETE FROM membresias WHERE fecha_deposito = ANY(:f)"), {"f": fechas})
        sin_fecha = _lista(df.loc[df["fecha_deposito"].isna(), "semana"])
        if sin_fecha:
            con.execute(text("DELETE FROM membresias WHERE fecha_deposito IS NULL AND origen = 'archivo' "
                             "AND semana = ANY(:s)"), {"s": sin_fecha})
        # El histórico traído del HTML se reemplaza por el archivo real de esa semana.
        con.execute(text("DELETE FROM membresias WHERE origen = 'html' AND semana = ANY(:s)"),
                    {"s": semanas})
        _copiar(con, "membresias", df)
    limpiar_cache()


def guardar_pagoya(df: pd.DataFrame):
    df = df.assign(origen="archivo")
    with motor().begin() as con:
        # Cada retiro tiene un id único: si ya existía, se reemplaza por la versión nueva.
        ids = _lista(df["id_retiro"])
        if ids:
            con.execute(text("DELETE FROM pagoya WHERE id_retiro = ANY(:i)"), {"i": ids})
        # Histórico del HTML (no tiene id_retiro): se reemplaza en las mismas semanas y fechas.
        fechas = df["fecha"].dropna()
        if not fechas.empty:
            con.execute(text("""
                DELETE FROM pagoya WHERE origen = 'html' AND semana = ANY(:s)
                AND fecha BETWEEN :desde AND :hasta
            """), {"s": _lista(df["semana"]), "desde": fechas.min(), "hasta": fechas.max()})
        _copiar(con, "pagoya", df)
    limpiar_cache()


def guardar_saldos(df: pd.DataFrame):
    df = df.assign(origen="archivo")
    corte = df["fecha_corte"].iloc[0]
    with motor().begin() as con:
        con.execute(text("DELETE FROM saldos WHERE fecha_corte = :f"), {"f": corte})
        _copiar(con, "saldos", df)
        con.execute(text(f"""
            DELETE FROM saldos WHERE fecha_corte NOT IN (
                SELECT DISTINCT fecha_corte FROM saldos ORDER BY fecha_corte DESC LIMIT {MAX_CARGAS_SALDOS}
            )
        """))
    limpiar_cache()


def historico_ya_importado() -> bool:
    with motor().connect() as con:
        for tabla in ("membresias", "pagoya"):
            if con.execute(text(f"SELECT 1 FROM {tabla} WHERE origen = 'html' LIMIT 1")).first():
                return True
    return False


def importar_historico(datos: dict):
    """Pasa a la base de datos todo lo que tenía guardado el tablero HTML."""
    with motor().begin() as con:
        for tabla in ("membresias", "pagoya"):
            df = datos[tabla]
            if df.empty:
                continue
            df = df.assign(origen="html")
            # Solo semanas que todavía no tengan un archivo real cargado.
            existentes = {r[0] for r in con.execute(
                text(f"SELECT DISTINCT semana FROM {tabla} WHERE origen = 'archivo'"))}
            df = df[~df["semana"].isin(existentes)]
            _copiar(con, tabla, df)
    limpiar_cache()


# ----------------------------------------------------------------------
# Consultar y borrar cargas
# ----------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def resumen_cargas(tipo: str) -> pd.DataFrame:
    consultas = {
        "membresias": """
            SELECT semana, COUNT(*) AS registros, COUNT(DISTINCT identificacion) AS aliados,
                   MIN(fecha_deposito) AS primera_fecha, MAX(fecha_deposito) AS ultima_fecha,
                   STRING_AGG(DISTINCT origen, ', ') AS origen, MAX(cargado_en) AS cargado_en
            FROM membresias GROUP BY semana ORDER BY semana DESC""",
        "pagoya": """
            SELECT semana, COUNT(*) AS registros, SUM(valor)::float8 AS valor_total,
                   MIN(COALESCE(fecha_validacion, fecha)) AS primera_fecha,
                   MAX(COALESCE(fecha_validacion, fecha)) AS ultima_fecha,
                   STRING_AGG(DISTINCT origen, ', ') AS origen, MAX(cargado_en) AS cargado_en
            FROM pagoya GROUP BY semana ORDER BY semana DESC""",
        "saldos": """
            SELECT fecha_corte, semana, COUNT(*) AS aliados,
                   (SUM(saldo) FILTER (WHERE pais = 'Colombia'))::float8 AS saldo_colombia,
                   (SUM(saldo) FILTER (WHERE pais = 'México'))::float8 AS saldo_mexico,
                   STRING_AGG(DISTINCT origen, ', ') AS origen, MAX(cargado_en) AS cargado_en
            FROM saldos GROUP BY fecha_corte, semana ORDER BY fecha_corte DESC""",
    }
    with motor().connect() as con:
        return pd.read_sql(text(consultas[tipo]), con)


def borrar_semana(tipo: str, semana: str):
    if tipo not in ("membresias", "pagoya"):
        raise ValueError("Tipo no válido")
    with motor().begin() as con:
        con.execute(text(f"DELETE FROM {tipo} WHERE semana = :s"), {"s": semana})
    limpiar_cache()


def borrar_corte_saldos(fecha_corte):
    with motor().begin() as con:
        con.execute(text("DELETE FROM saldos WHERE fecha_corte = :f"), {"f": fecha_corte})
    limpiar_cache()
