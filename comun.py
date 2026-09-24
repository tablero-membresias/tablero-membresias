"""
comun.py
--------
Piezas que usan todas las pestañas: leer los datos guardados, los filtros
(año, mes, país, ciudad), formatos de números y el botón de descarga a Excel.
"""

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text

import base_datos as bd
import lectores

ROSADO = "#D6537E"
AZUL = "#3B82C4"
GRIS = "#8A8A8A"
ROJO = "#B23A2E"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MONEDA = {"Colombia": "COP", "México": "MXN"}
COLORES_ESTADO = {"Retiro Aprobado": AZUL, "Fondos insuficientes": ROSADO,
                  "Pagoya": GRIS, "Aliado bloqueado": ROJO}


# ----------------------------------------------------------------------
# Formatos
# ----------------------------------------------------------------------

def fmt_num(n, dec=0):
    if n is None or pd.isna(n):
        return "—"
    s = f"{n:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_dinero(n):
    if n is None or pd.isna(n):
        return "—"
    return ("-" if n < 0 else "") + "$" + fmt_num(abs(n))


def fmt_pct(n):
    return "—" if n is None or pd.isna(n) else fmt_num(n, 1) + "%"


def fmt_fecha(d):
    if d is None or pd.isna(d):
        return "—"
    d = pd.Timestamp(d)
    return f"{d.day} {lectores.MESES_CORTOS[d.month - 1]} {d.year}"


def semana_corta(clave):
    """'2026-W36' -> 'S36 (31 ago)'"""
    lunes = lectores.lunes_de_semana(clave)
    return f"S{clave.split('-W')[1]} ({lunes.day} {lectores.MESES_CORTOS[lunes.month - 1]})"


def orden_paises(paises):
    prioridad = {"Colombia": 0, "México": 1}
    return sorted(paises, key=lambda p: (prioridad.get(p, 9), str(p)))


# ----------------------------------------------------------------------
# Carga de datos (se guarda en memoria 10 minutos o hasta la próxima carga)
# ----------------------------------------------------------------------

def _periodo(df):
    """Una semana pertenece al mes donde cae su jueves (donde está la mayoría de sus días)."""
    if df.empty:
        return df.assign(anio=pd.Series(dtype="int"), mes=pd.Series(dtype="int"))
    jueves = {s: date.fromisocalendar(int(s[:4]), int(s.split("-W")[1]), 4) for s in df["semana"].unique()}
    return df.assign(anio=df["semana"].map(lambda s: jueves[s].year),
                     mes=df["semana"].map(lambda s: jueves[s].month))


def _preparar(df):
    df["clave"] = df["identificacion"].fillna("n_" + df["nombre"].fillna("desconocido").str.upper())
    df["nombre"] = df["nombre"].fillna("(sin nombre)").str.strip().str.title()
    df["ciudad"] = df["ciudad"].fillna("Sin ciudad").str.strip()
    df["pais"] = df["pais"].fillna("Sin país (revisar dato)")
    return df


@st.cache_data(ttl=600, show_spinner="Cargando PagoYa...")
def cargar_pagoya() -> pd.DataFrame:
    q = """SELECT semana, id_retiro, nombre, identificacion, ciudad, pais, fecha, fecha_validacion,
                  vehiculo, valor::float8 AS valor, comision::float8 AS comision, iva::float8 AS iva,
                  gps_falso::float8 AS gps_falso, black_list, cancelacion::float8 AS cancelacion,
                  pagar, estado_aliado
           FROM pagoya"""
    with bd.motor().connect() as con:
        df = pd.read_sql(text(q), con)
    return _periodo(_preparar(df))


@st.cache_data(ttl=600, show_spinner="Cargando Membresías...")
def cargar_membresias() -> pd.DataFrame:
    q = """SELECT semana, fecha_deposito, nombre, identificacion, tipo_plan, valor_plan::float8 AS valor_plan,
                  saldo_actual::float8 AS saldo_actual, disponible::float8 AS disponible, ciudad, pais,
                  estado_retiro, estado_aliado, membresia_activa
           FROM membresias"""
    with bd.motor().connect() as con:
        df = pd.read_sql(text(q), con)
    return _periodo(_preparar(df))


@st.cache_data(ttl=600, show_spinner="Cargando saldos...")
def cargar_saldos_ultimo():
    """Devuelve (tabla, fecha_corte) de la carga de saldos más reciente."""
    q = """SELECT fecha_corte, nombre, identificacion, ciudad, pais, saldo::float8 AS saldo
           FROM saldos WHERE fecha_corte = (SELECT MAX(fecha_corte) FROM saldos)"""
    with bd.motor().connect() as con:
        df = pd.read_sql(text(q), con)
    fecha = df["fecha_corte"].iloc[0] if not df.empty else None
    return _preparar(df), fecha


# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------

@dataclass
class Filtro:
    anio: object = "Todos"
    mes: object = "Todos"
    pais: str = "Todos"
    ciudad: str = "Todas"

    def texto(self):
        partes = []
        if self.anio != "Todos":
            partes.append(str(self.anio))
        if self.mes != "Todos":
            partes.append(MESES[self.mes - 1])
        if self.pais != "Todos":
            partes.append(self.pais)
        if self.ciudad != "Todas":
            partes.append(self.ciudad)
        return " · ".join(partes) if partes else "Todo el periodo · todos los países"


def _selector(col, etiqueta, opciones, key, **kw):
    """Selector que recuerda su valor aunque cambies de sección."""
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(f"_{key}", opciones[0])
    if st.session_state[key] not in opciones:
        st.session_state[key] = opciones[0]
    valor = col.selectbox(etiqueta, opciones, key=key, **kw)
    st.session_state[f"_{key}"] = valor
    return valor


def dibujar_filtros(pagoya, memb, columnas) -> Filtro:
    periodos = pd.concat([pagoya[["anio", "mes", "pais", "ciudad"]],
                          memb[["anio", "mes", "pais", "ciudad"]]], ignore_index=True)
    c1, c2, c3, c4 = columnas
    anios = sorted(periodos["anio"].dropna().unique().tolist(), reverse=True)
    anio = _selector(c1, "Año", ["Todos"] + anios, "f_anio")
    base = periodos if anio == "Todos" else periodos[periodos["anio"] == anio]
    meses = sorted(base["mes"].dropna().unique().tolist())
    mes = _selector(c2, "Mes", ["Todos"] + meses, "f_mes",
                    format_func=lambda m: m if m == "Todos" else MESES[int(m) - 1])
    paises = orden_paises(periodos["pais"].dropna().unique().tolist())
    pais = _selector(c3, "País", ["Todos"] + paises, "f_pais")
    base = periodos
    if anio != "Todos":
        base = base[base["anio"] == anio]
    if mes != "Todos":
        base = base[base["mes"] == mes]
    if pais != "Todos":
        base = base[base["pais"] == pais]
    ciudades = sorted(base["ciudad"].dropna().unique().tolist())
    ciudad = _selector(c4, "Ciudad", ["Todas"] + ciudades, "f_ciudad")
    return Filtro(anio, mes, pais, ciudad)


def aplicar_lugar(df, f: Filtro):
    if df.empty:
        return df
    m = pd.Series(True, index=df.index)
    if f.pais != "Todos":
        m &= df["pais"] == f.pais
    if f.ciudad != "Todas":
        m &= df["ciudad"] == f.ciudad
    return df[m]


def aplicar(df, f: Filtro):
    df = aplicar_lugar(df, f)
    if df.empty:
        return df
    m = pd.Series(True, index=df.index)
    if f.anio != "Todos":
        m &= df["anio"] == f.anio
    if f.mes != "Todos":
        m &= df["mes"] == f.mes
    return df[m]


# ----------------------------------------------------------------------
# Descarga a Excel
# ----------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=20)
def _a_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Datos")
        hoja = w.sheets["Datos"]
        for i, col in enumerate(df.columns, start=1):
            ancho = min(max(len(str(col)), 10) + 2, 45)
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = ancho
    return buf.getvalue()


def boton_excel(df: pd.DataFrame, nombre: str, key: str):
    """Botón para descargar la tabla en Excel. Las tablas grandes se preparan al pedirlas."""
    df = df.drop(columns=["clave", "identificacion"], errors="ignore")
    archivo = f"{nombre}.xlsx"
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if len(df) <= 3000 or st.session_state.get(f"prep_{key}"):
        st.download_button(f"Descargar Excel ({fmt_num(len(df))} filas)", _a_excel(df),
                           file_name=archivo, mime=mime, key=key)
    elif st.button(f"Preparar Excel ({fmt_num(len(df))} filas)", key=f"btn_{key}"):
        st.session_state[f"prep_{key}"] = True
        st.rerun()


def titulo(texto, ayuda=None):
    st.markdown(f"#### {texto}")
    if ayuda:
        st.caption(ayuda)


def encabezado_pais(pais, varios):
    if varios:
        st.markdown(f'<div class="pais">{pais} · cifras en {MONEDA.get(pais, "moneda local")}</div>',
                    unsafe_allow_html=True)


def elegir_pais_grafico(df, f, key):
    """Los gráficos de dinero muestran un país a la vez (COP y MXN no se pueden sumar)."""
    paises = orden_paises(df["pais"].unique())
    if f.pais != "Todos" or len(paises) == 1:
        return paises[0]
    return st.radio("País del gráfico", paises, horizontal=True, key=key,
                    help="Los valores de Colombia (COP) y México (MXN) no se mezclan en un mismo gráfico.")


def estilo(fig, alto=360):
    fig.update_layout(height=alto, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.12, x=0), font=dict(size=13))
    return fig


def punto_elegido(ev):
    """customdata del punto clicado en un gráfico (o None)."""
    puntos = ev.selection.points if ev and ev.selection else []
    if not puntos:
        return None
    return puntos[0].get("customdata")
