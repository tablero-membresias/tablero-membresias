"""
app.py — Tablero Membresías & PagoYa
Etapa 1: contraseña, conexión a Neon, pestaña "Cargar datos" e importación del histórico.
Etapa 2: filtros (año, mes, país, ciudad) y pestaña "Aliados".
Etapas 3 y 4: pestañas "PagoYa" y "Membresías".
Etapa 5: colores de marca en botones y tarjetas, guía de uso y cerrar sesión.
"""

import hmac
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ICONO = Path(__file__).parent / "icono.png"
st.set_page_config(page_title="Membresías & PagoYa", page_icon=str(ICONO) if ICONO.exists() else "📊",
                   layout="wide",
                   initial_sidebar_state="collapsed")

import aliados            # noqa: E402
import base_datos as bd   # noqa: E402
import comun              # noqa: E402
import lectores           # noqa: E402
import membresias         # noqa: E402
import pagoya             # noqa: E402

ROSADO = "#D6537E"
AZUL = "#3B82C4"

st.markdown(f"""
<style>
  /* Ocultar la barra de íconos de Streamlit (Share, estrella, GitHub, menú en inglés) */
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display: none !important; }}
  [data-testid="stMainBlockContainer"], .block-container {{ padding-top: 1.6rem !important; }}

  /* Barra superior: nombre a la izquierda, menú a la derecha */
  .st-key-barra_superior {{ border-bottom: 1px solid rgba(128,128,128,.28); padding: 4px 0 10px 0; margin-bottom: 4px; }}
  .logo {{ font-size: 1.75rem; font-weight: 800; line-height: 1.1; white-space: nowrap; }}
  .logo .r {{ color: {ROSADO}; }} .logo .a {{ color: {AZUL}; }}
  .logo .sub {{ display: block; font-size: .82rem; font-weight: 500; opacity: .6; margin-top: 2px; }}
  [class*="st-key-nav_"] button {{ background: transparent !important; border: none !important;
                                   box-shadow: none !important; border-radius: 0 !important;
                                   border-bottom: 2px solid transparent !important; padding: 6px 4px !important; }}
  [class*="st-key-nav_"] button p {{ font-size: 1.08rem !important; font-weight: 500; }}
  [class*="st-key-nav_"] button:hover p {{ color: {AZUL} !important; }}
  [class*="st-key-nav_"][class*="_on"] button {{ border-bottom: 2px solid {AZUL} !important; }}
  [class*="st-key-nav_"][class*="_on"] button p {{ color: {AZUL} !important; font-weight: 700; }}
  .encabezado .titulo {{ font-size: 2.2rem; font-weight: 800; }}
  .encabezado .r {{ color: {ROSADO}; }} .encabezado .a {{ color: {AZUL}; }}
  .encabezado .sub {{ opacity: .65; margin-bottom: 16px; }}

  /* Barra de filtros compacta */
  .st-key-barra_filtros {{ background: rgba(128,128,128,.06); border: 1px solid rgba(128,128,128,.22);
                           border-radius: 12px; padding: 10px 16px 2px 16px; margin: 14px 0 4px 0; }}
  .st-key-barra_filtros label p {{ font-size: .75rem !important; text-transform: uppercase;
                                   letter-spacing: .07em; opacity: .65; }}
  .estado-datos {{ font-size: .82rem; opacity: .7; line-height: 1.5; padding-top: 6px; }}

  /* Indicadores en tarjetas, sin textos cortados */
  [data-testid="stMetric"] {{ border: 1px solid rgba(128,128,128,.22); border-radius: 12px;
                             padding: 12px 16px; background: rgba(128,128,128,.05); height: 100%; }}
  [data-testid="stMetricLabel"] p {{ white-space: normal !important; font-size: .85rem !important; opacity: .75; }}
  [data-testid="stMetricLabel"] div {{ overflow: visible !important; }}
  [data-testid="stMetricValue"] {{ font-size: clamp(1.1rem, 1.5vw, 1.7rem) !important; }}
  [data-testid="stMetricValue"] div {{ overflow: visible !important; text-overflow: clip !important; }}

  /* Títulos de sección */
  .titulo-seccion {{ font-size: 1.45rem; font-weight: 700; border-bottom: 1px solid rgba(128,128,128,.25);
                     padding-bottom: 6px; margin: 18px 0 6px 0; }}
  [data-testid="stHeaderActionElements"] {{ display: none !important; }}
  .pais {{ font-weight: 700; font-size: .95rem; color: {AZUL}; margin: 12px 0 4px 0;
           text-transform: uppercase; letter-spacing: .05em; }}

  /* Botones */
  [data-testid^="stBaseButton-primary"], button[kind^="primary"] {{
      background-color: {ROSADO} !important; border-color: {ROSADO} !important; color: #FFFFFF !important; }}
  [data-testid^="stBaseButton-primary"]:hover, button[kind^="primary"]:hover {{
      background-color: #B8446A !important; border-color: #B8446A !important; }}
  [data-testid="stDownloadButton"] button {{ border: 1.5px solid {AZUL} !important; color: {AZUL} !important; }}
  [data-testid="stDownloadButton"] button:hover {{ background: {AZUL} !important; color: #FFFFFF !important; }}

  /* Cuadro para subir archivos, en español */
  [data-testid="stFileUploaderDropzoneInstructions"] {{ display: none !important; }}
  [data-testid="stFileUploaderDropzone"] button {{ font-size: 0 !important; }}
  [data-testid="stFileUploaderDropzone"] button * {{ display: none !important; }}
  [data-testid="stFileUploaderDropzone"] button::after {{ content: "Seleccionar archivo"; font-size: 1rem; }}
  [data-testid="stFileUploaderDropzone"]::after {{ content: "o arrástralo aquí · archivos Excel";
      font-size: .85rem; opacity: .6; margin-left: 12px; }}

  /* Tarjetas de la pantalla de carga */
  .tarjeta {{ border-left: 5px solid var(--c); background: rgba(128,128,128,.07); padding: 12px 16px;
             border-radius: 8px; margin-bottom: 8px; }}
  .tarjeta b {{ color: var(--c); letter-spacing: .5px; }}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Utilidades de formato
# ----------------------------------------------------------------------

def fmt_num(n):
    return "—" if n is None or pd.isna(n) else f"{n:,.0f}".replace(",", ".")


def fmt_dinero(n):
    if n is None or pd.isna(n):
        return "—"
    signo = "-" if n < 0 else ""
    return f"{signo}${abs(n):,.0f}".replace(",", ".")


def fmt_fecha(d):
    if d is None or pd.isna(d):
        return "—"
    d = pd.Timestamp(d)
    return f"{d.day} {lectores.MESES_CORTOS[d.month - 1]} {d.year}"


ENCABEZADO = ('<div class="encabezado"><div class="titulo"><span class="r">Membresías</span> &amp; '
              '<span class="a">PagoYa</span></div><div class="sub">Torre de control semanal · '
              'Colombia y México</div></div>')


# ----------------------------------------------------------------------
# Contraseña
# ----------------------------------------------------------------------

def pedir_contrasena():
    if st.session_state.get("autenticado"):
        return True
    st.markdown(ENCABEZADO, unsafe_allow_html=True)
    if "APP_PASSWORD" not in st.secrets:
        st.error("Falta configurar APP_PASSWORD en los Secrets de Streamlit.")
        return False
    with st.form("entrar"):
        clave = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            clave_admin = str(st.secrets.get("ADMIN_PASSWORD", ""))
            if clave_admin and hmac.compare_digest(clave, clave_admin):
                st.session_state.autenticado, st.session_state.rol = True, "admin"
                st.rerun()
            elif hmac.compare_digest(clave, str(st.secrets["APP_PASSWORD"])):
                # Si aún no existe ADMIN_PASSWORD, la clave general sigue pudiendo cargar datos.
                st.session_state.autenticado = True
                st.session_state.rol = "lector" if clave_admin else "admin"
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    return False


if not pedir_contrasena():
    st.stop()

for secreto, para_que in [("DATABASE_URL", "la dirección de Neon"),
                          ("CLAVE_PRIVACIDAD", "la clave que cifra las cédulas")]:
    if secreto not in st.secrets:
        st.error(f"Falta configurar {secreto} ({para_que}) en los Secrets de Streamlit.")
        st.stop()

try:
    bd.motor()
except Exception as e:
    st.error("No pude conectarme a la base de datos Neon. Copia el detalle de abajo y pégaselo a Claude.")
    st.exception(e)
    st.stop()


# ----------------------------------------------------------------------
# Encabezado y pestañas
# ----------------------------------------------------------------------

try:
    datos_pagoya = comun.cargar_pagoya()
    datos_memb = comun.cargar_membresias()
    datos_saldos, fecha_corte = comun.cargar_saldos_ultimo()
except Exception as e:
    st.error("No pude leer los datos guardados. Copia el detalle de abajo y pégaselo a Claude.")
    st.exception(e)
    st.stop()

ES_ADMIN = st.session_state.get("rol") == "admin"
PAGINAS = ["Aliados", "PagoYa", "Membresías"] + (["Cargar datos"] if ES_ADMIN else [])
if st.session_state.get("pagina") not in PAGINAS:
    st.session_state["pagina"] = PAGINAS[0]

with st.container(key="barra_superior"):
    col_logo, col_menu = st.columns([2.3, 5], vertical_alignment="center")
    col_logo.markdown('<div class="logo"><span class="r">Membresías</span> &amp; <span class="a">PagoYa</span>'
                      '<span class="sub">Torre de control semanal · Colombia y México</span></div>',
                      unsafe_allow_html=True)
    with col_menu:
        cols_menu = st.columns([1, 1, 1.15, 1.25], vertical_alignment="center")
        for i, nombre in enumerate(PAGINAS):
            estado_nav = "on" if st.session_state["pagina"] == nombre else "off"
            with cols_menu[i].container(key=f"nav_{i}_{estado_nav}"):
                if st.button(nombre, key=f"boton_nav_{i}", width="stretch"):
                    st.session_state["pagina"] = nombre
                    st.rerun()

pagina = st.session_state["pagina"]

if pagina != "Cargar datos":
    with st.container(key="barra_filtros"):
        cols = st.columns([1, 1, 1, 1.3, 1.6], vertical_alignment="center")
        filtro = comun.dibujar_filtros(datos_pagoya, datos_memb, cols[:4])
        ultimas = [s for s in (datos_pagoya["semana"].max() if not datos_pagoya.empty else None,
                               datos_memb["semana"].max() if not datos_memb.empty else None) if s]
        estado = []
        if ultimas:
            estado.append(f"Datos hasta la {lectores.etiqueta_semana(max(ultimas))}")
        if fecha_corte is not None:
            estado.append(f"Saldos al {fmt_fecha(fecha_corte)}")
        cols[4].markdown(f'<div class="estado-datos">{"<br>".join(estado)}</div>', unsafe_allow_html=True)


def pagina_segura(nombre, funcion, *args):
    try:
        funcion(*args)
    except Exception as e:
        st.error(f"Algo falló en la sección {nombre}. Copia el detalle de abajo y pégaselo a Claude tal cual.")
        st.exception(e)


if pagina == "Aliados":
    pagina_segura("Aliados", aliados.mostrar, datos_pagoya, datos_memb, datos_saldos, fecha_corte, filtro)
elif pagina == "PagoYa":
    pagina_segura("PagoYa", pagoya.mostrar, datos_pagoya, filtro)
elif pagina == "Membresías":
    pagina_segura("Membresías", membresias.mostrar, datos_memb, filtro)


# ----------------------------------------------------------------------
# Pestaña: Cargar datos
# ----------------------------------------------------------------------

def mostrar_error(e):
    if isinstance(e, lectores.ErrorLectura):
        st.error(str(e))
    else:
        st.error("Ocurrió un error inesperado. Copia TODO el detalle de abajo y pégaselo a Claude tal cual.")
        st.exception(e)


def clave_uploader(tipo):
    return f"subida_{tipo}_{st.session_state.get(f'ver_{tipo}', 0)}"


def reiniciar_uploader(tipo):
    st.session_state[f"ver_{tipo}"] = st.session_state.get(f"ver_{tipo}", 0) + 1
    st.session_state.pop(f"lectura_{tipo}", None)


def leer_una_vez(tipo, archivo, funcion, *args):
    """Lee el Excel una sola vez aunque la página se recargue."""
    marca = (archivo.file_id, args)
    guardado = st.session_state.get(f"lectura_{tipo}")
    if guardado and guardado[0] == marca:
        return guardado[1]
    with st.spinner("Leyendo el archivo... (los archivos grandes pueden tardar un poco)"):
        res = funcion(archivo.getvalue(), *args)
    st.session_state[f"lectura_{tipo}"] = (marca, res)
    return res


def sin_identificacion(df):
    """Para mostrar en pantalla sin la cédula/CURP."""
    return df.drop(columns=["identificacion"], errors="ignore").head(20)


def vista_previa_semanas(df, tipo_bd, con_valor=False):
    grupos = df.groupby("semana").agg(registros=("semana", "size"))
    if con_valor:
        grupos["valor"] = df.groupby("semana")["valor"].sum()
    grupos = grupos.reset_index().sort_values("semana")
    existentes = set(bd.resumen_cargas(tipo_bd)["semana"])
    grupos["Semana"] = grupos["semana"].map(lectores.etiqueta_semana)
    grupos["Estado"] = grupos["semana"].map(
        lambda s: "Se actualizará (ya existía)" if s in existentes else "Nueva")
    grupos["Registros"] = grupos["registros"].map(fmt_num)
    columnas = ["Semana", "Registros", "Estado"]
    if con_valor:
        grupos["Valor"] = grupos["valor"].map(fmt_dinero)
        columnas.insert(2, "Valor")
    st.dataframe(grupos[columnas], hide_index=True, width="stretch")


def boton_guardar(tipo, funcion_guardar, *args, etiqueta="Guardar en el tablero"):
    if st.button(etiqueta, type="primary", key=f"guardar_{tipo}"):
        try:
            with st.spinner("Guardando en la base de datos..."):
                funcion_guardar(*args)
            st.session_state["mensaje_ok"] = "Datos guardados. El tablero ya los incluye."
            reiniciar_uploader(tipo)
            st.rerun()
        except Exception as e:
            mostrar_error(e)


def mostrar_avisos(res):
    for a in res.avisos:
        st.warning(a)


if pagina == "Cargar datos" and ES_ADMIN:
    if msg := st.session_state.pop("mensaje_ok", None):
        st.success(msg)

    with st.expander("Cómo cargar los datos cada semana"):
        st.markdown(
            "1. **Membresías:** sube la Lista Oro de la semana. Revisa que la *fecha de depósito* sea el "
            "día real (se toma del nombre del archivo, ej. `20260910_...`) y haz clic en **Guardar**.\n"
            "2. **PagoYa:** sube el archivo *Consulta fraude* del mes (aunque sea el mismo mes de la semana "
            "pasada: los retiros repetidos se reemplazan, no se duplican) y haz clic en **Guardar**.\n"
            "3. **Saldos:** pon la *fecha de corte* del archivo, súbelo y haz clic en **Guardar**.\n"
            "4. Revisa abajo en **Semanas cargadas** que aparezca la semana nueva.\n\n"
            "Si sale un cuadro rojo, copia el mensaje completo y pégaselo a Claude tal cual. "
            "Si llega un tipo de archivo nuevo o cambian las columnas, adjunta un ejemplo real.")
    st.subheader("Cargar archivos de la semana", anchor=False)
    st.caption("Sube cada Excel tal como lo recibes. Si subes un archivo que ya habías cargado, "
               "sus datos se reemplazan: nunca se duplican.")

    col1, col2 = st.columns(2)

    # ---------- MEMBRESÍAS ----------
    with col1:
        st.markdown(f'<div class="tarjeta" style="--c:{ROSADO}"><b>MEMBRESÍAS</b><br>'
                    'Archivo "Lista Oro" (hoja <i>Lista Oro</i>).</div>', unsafe_allow_html=True)
        arch = st.file_uploader("Excel de Membresías", type=["xlsx", "xlsm", "xls"],
                                key=clave_uploader("membresias"), label_visibility="collapsed")
        if arch:
            try:
                res = leer_una_vez("membresias", arch, lectores.leer_membresias)
                st.success(f"Leí {fmt_num(len(res.tabla))} aliados de la hoja '{res.extra['hoja']}'.")
                mostrar_avisos(res)
                f_nombre = lectores.fecha_desde_nombre(arch.name)
                f_columna = res.extra.get("fecha_columna")
                fecha_dep = st.date_input(
                    "Fecha de depósito de esta lista", value=f_nombre or f_columna or date.today(),
                    format="DD/MM/YYYY", key=f"fecha_{clave_uploader('membresias')}",
                    help="Define a qué semana pertenece la lista. Se toma de la fecha al inicio "
                         "del nombre del archivo (ej. 20260827_...).")
                if f_columna and f_columna != fecha_dep:
                    st.warning(f"Ojo: la columna 'Fecha deposito' del Excel dice {fmt_fecha(f_columna)}, "
                               f"pero se guardará con {fmt_fecha(fecha_dep)}. Cámbiala arriba si no es correcta.")
                tabla = lectores.asignar_fecha_deposito(res.tabla, fecha_dep)
                vista_previa_semanas(tabla, "membresias")
                with st.expander("Ver primeras filas"):
                    st.dataframe(sin_identificacion(tabla), hide_index=True)
                boton_guardar("membresias", bd.guardar_membresias, tabla)
            except Exception as e:
                mostrar_error(e)

    # ---------- PAGOYA ----------
    with col2:
        st.markdown(f'<div class="tarjeta" style="--c:{AZUL}"><b>PAGOYA</b><br>'
                    'Archivo "Consulta fraude" (hoja <i>Validación</i>).</div>', unsafe_allow_html=True)
        arch = st.file_uploader("Excel de PagoYa", type=["xlsx", "xlsm", "xls"],
                                key=clave_uploader("pagoya"), label_visibility="collapsed")
        if arch:
            try:
                res = leer_una_vez("pagoya", arch, lectores.leer_pagoya)
                st.success(f"Leí {fmt_num(len(res.tabla))} solicitudes de la hoja '{res.extra['hoja']}' · "
                           f"Valor {fmt_dinero(res.tabla['valor'].sum())} · "
                           f"Comisión {fmt_dinero(res.tabla['comision'].sum())}")
                mostrar_avisos(res)
                vista_previa_semanas(res.tabla, "pagoya", con_valor=True)
                with st.expander("Ver primeras filas"):
                    st.dataframe(sin_identificacion(res.tabla), hide_index=True)
                boton_guardar("pagoya", bd.guardar_pagoya, res.tabla)
            except Exception as e:
                mostrar_error(e)

    # ---------- SALDOS ----------
    st.markdown('<div class="tarjeta" style="--c:#6B7280"><b>SALDOS DE ALIADOS</b><br>'
                'Archivo con el saldo de cada aliado. Se cruza con PagoYa en la pestaña Aliados. '
                f'Se guardan las últimas {bd.MAX_CARGAS_SALDOS} cargas.</div>', unsafe_allow_html=True)
    c_fecha, c_arch = st.columns([1, 3])
    with c_fecha:
        corte = st.date_input("Fecha de corte del archivo", value=date.today(), format="DD/MM/YYYY",
                              help="El día al que corresponden esos saldos. Por defecto, hoy.")
    with c_arch:
        arch = st.file_uploader("Excel de Saldos", type=["xlsx", "xlsm", "xls"],
                                key=clave_uploader("saldos"))
    if arch:
        try:
            res = leer_una_vez("saldos", arch, lectores.leer_saldos, corte)
            t = res.tabla
            por_pais = " · ".join(f"{p}: {fmt_dinero(v)}" for p, v in t.groupby("pais")["saldo"].sum().items())
            st.success(f"Leí {fmt_num(len(t))} aliados con saldo · {por_pais} · "
                       f"{fmt_num((t['saldo'] < 0).sum())} con saldo negativo · corte {fmt_fecha(corte)}")
            mostrar_avisos(res)
            if corte in set(bd.resumen_cargas("saldos")["fecha_corte"]):
                st.warning("Ya existe una carga con esa fecha de corte: se reemplazará.")
            with st.expander("Ver primeras filas"):
                st.dataframe(sin_identificacion(t), hide_index=True)
            boton_guardar("saldos", bd.guardar_saldos, t)
        except Exception as e:
            mostrar_error(e)

    # ---------- HISTÓRICO DEL HTML ----------
    st.divider()
    with st.expander("Importar el histórico de tu tablero HTML (se hace una sola vez)"):
        try:
            if bd.historico_ya_importado():
                st.success("El histórico del HTML ya está importado.")
            else:
                st.write("Sube el archivo **torre_control.html**. Se importarán todas las semanas "
                         "que tenía guardadas, excepto las que ya hayas cargado con un Excel real.")
                arch = st.file_uploader("Tablero HTML", type=["html", "htm"],
                                        key=clave_uploader("historico"))
                if arch:
                    datos = leer_una_vez("historico", arch, lectores.leer_historico_html)
                    m, p = datos["membresias"], datos["pagoya"]
                    st.info(f"Encontré: {m['semana'].nunique()} semanas de Membresías "
                            f"({fmt_num(len(m))} registros) · {p['semana'].nunique()} semanas de PagoYa "
                            f"({fmt_num(len(p))} solicitudes). Los saldos del HTML no se importan "
                            "porque estaban desactualizados.")
                    boton_guardar("historico", bd.importar_historico, datos,
                                  etiqueta="Importar histórico")
        except Exception as e:
            mostrar_error(e)

    # ---------- SEMANAS CARGADAS ----------
    st.divider()
    st.subheader("Semanas cargadas", anchor=False)

    def lista_semanas(tipo, titulo, con_valor=False):
        st.markdown(f"**{titulo}**")
        res = bd.resumen_cargas(tipo)
        if res.empty:
            st.caption("Aún no hay semanas cargadas.")
            return
        vista = pd.DataFrame({
            "Semana": res["semana"].map(lectores.etiqueta_semana),
            "Registros": res["registros"].map(fmt_num),
        })
        if con_valor:
            vista["Valor"] = res["valor_total"].map(fmt_dinero)
        vista["Origen"] = res["origen"].str.replace("html", "histórico HTML").str.replace("archivo", "Excel")
        st.dataframe(vista, hide_index=True, width="stretch", height=min(35 * len(vista) + 38, 380))
        with st.popover("Eliminar una semana"):
            opciones = dict(zip(vista["Semana"], res["semana"]))
            elegida = st.selectbox("Semana a eliminar", list(opciones), key=f"sel_borrar_{tipo}")
            seguro = st.checkbox("Sí, quiero eliminarla (no se puede deshacer)", key=f"ok_borrar_{tipo}")
            if st.button("Eliminar", disabled=not seguro, key=f"btn_borrar_{tipo}"):
                bd.borrar_semana(tipo, opciones[elegida])
                st.session_state["mensaje_ok"] = f"Semana eliminada: {elegida}"
                st.rerun()

    try:
        c1, c2 = st.columns(2)
        with c1:
            lista_semanas("membresias", "Membresías")
        with c2:
            lista_semanas("pagoya", "PagoYa", con_valor=True)

        st.markdown("**Saldos de aliados**")
        sal = bd.resumen_cargas("saldos")
        if sal.empty:
            st.caption("Aún no hay cargas de saldos.")
        else:
            vista = pd.DataFrame({
                "Fecha de corte": sal["fecha_corte"].map(fmt_fecha),
                "Aliados": sal["aliados"].map(fmt_num),
                "Saldo Colombia (COP)": sal["saldo_colombia"].map(fmt_dinero),
                "Saldo México (MXN)": sal["saldo_mexico"].map(fmt_dinero),
                "Origen": sal["origen"].str.replace("html", "histórico HTML").str.replace("archivo", "Excel"),
            })
            st.dataframe(vista, hide_index=True, width="stretch")
            with st.popover("Eliminar una carga de saldos"):
                opciones = dict(zip(vista["Fecha de corte"], sal["fecha_corte"]))
                elegida = st.selectbox("Carga a eliminar", list(opciones), key="sel_borrar_saldos")
                seguro = st.checkbox("Sí, quiero eliminarla (no se puede deshacer)", key="ok_borrar_saldos")
                if st.button("Eliminar", disabled=not seguro, key="btn_borrar_saldos"):
                    bd.borrar_corte_saldos(opciones[elegida])
                    st.session_state["mensaje_ok"] = f"Carga de saldos eliminada: {elegida}"
                    st.rerun()
    except Exception as e:
        mostrar_error(e)
