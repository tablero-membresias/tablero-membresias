"""
aliados.py — Pestaña "Aliados" (Etapa 2)

- Indicadores de retiro acumulados
- Tendencia semanal de aliados que retiran (clic en una semana = detalle)
- Saldo pendiente por pagar (cruce Saldos vs PagoYa)
- Ranking acumulado y aliados más recurrentes (clic = detalle del aliado)
- Alerta de fraude: siempre el mismo monto (3+ solicitudes)
- Alerta de bloqueos por fondos insuficientes en membresía (2+ semanas)
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as c

DINERO = st.column_config.NumberColumn(format="localized")
ENTERO = st.column_config.NumberColumn(format="localized")


# ----------------------------------------------------------------------
# Cálculos
# ----------------------------------------------------------------------

def acumulado_por_aliado(p: pd.DataFrame) -> pd.DataFrame:
    columnas = ["clave", "nombre", "ciudad", "pais", "solicitudes", "semanas", "valor",
                "comision", "montos_distintos", "monto", "primera", "ultima"]
    if p.empty:
        return pd.DataFrame(columns=columnas)
    p = p.assign(monto_red=p["valor"].round(0)).sort_values("fecha", na_position="first")
    return (p.groupby("clave")
             .agg(nombre=("nombre", "last"), ciudad=("ciudad", "last"), pais=("pais", "last"),
                  solicitudes=("valor", "size"), semanas=("semana", "nunique"),
                  valor=("valor", "sum"), comision=("comision", "sum"),
                  montos_distintos=("monto_red", "nunique"), monto=("monto_red", "first"),
                  primera=("fecha", "min"), ultima=("fecha", "max"))
             .reset_index())


def bloqueos_recurrentes(m: pd.DataFrame) -> pd.DataFrame:
    b = m[m["estado_retiro"] == "Fondos insuficientes"] if not m.empty else m
    if b.empty:
        return pd.DataFrame(columns=["clave", "nombre", "ciudad", "pais", "semanas", "cuales", "disponible"])
    b = b.sort_values("semana")
    g = (b.groupby("clave")
          .agg(nombre=("nombre", "last"), ciudad=("ciudad", "last"), pais=("pais", "last"),
               semanas=("semana", "nunique"),
               cuales=("semana", lambda s: ", ".join(sorted({x.split("-W")[1] for x in s}))),
               disponible=("disponible", "last"))
          .reset_index())
    return g[g["semanas"] >= 2].sort_values(["semanas", "disponible"], ascending=[False, True])


# ----------------------------------------------------------------------
# Piezas de pantalla
# ----------------------------------------------------------------------

def _titulo(texto, ayuda=None):
    st.markdown(f"#### {texto}")
    if ayuda:
        st.caption(ayuda)


def _encabezado_pais(pais, varios):
    if varios:
        st.markdown(f"**{c.BANDERA.get(pais, '🌎')} {pais}** · cifras en {c.MONEDA.get(pais, 'moneda local')}")


def _tabla_seleccionable(vista: pd.DataFrame, key: str, config: dict, alto=None):
    """Tabla donde se puede hacer clic en una fila. Devuelve la 'clave' del aliado elegido."""
    ev = st.dataframe(
        vista, hide_index=True, width="stretch", key=key, height=alto,
        on_select="rerun", selection_mode="single-row",
        column_order=[col for col in vista.columns if col != "clave"],
        column_config=config,
    )
    filas = ev.selection.rows if ev and ev.selection else []
    return vista.iloc[filas[0]]["clave"] if filas else None


def detalle_aliado(clave, p, m, s):
    """Todo lo que sabemos de un aliado, en un recuadro."""
    pa = p[p["clave"] == clave].sort_values("fecha", ascending=False)
    ma = m[m["clave"] == clave].sort_values("semana", ascending=False)
    sa = s[s["clave"] == clave] if not s.empty else s
    nombre = next((d["nombre"].iloc[0] for d in (pa, ma, sa) if not d.empty), "Aliado")
    with st.container(border=True):
        st.markdown(f"**🔎 Detalle: {nombre}**")
        k1, k2, k3 = st.columns(3)
        k1.metric("Solicitudes PagoYa (periodo)", c.fmt_num(len(pa)))
        k2.metric("Retirado (periodo)", c.fmt_dinero(pa["valor"].sum()) if not pa.empty else "—")
        k3.metric("Saldo actual (último corte)", c.fmt_dinero(sa["saldo"].sum()) if not sa.empty else "—")
        if not pa.empty:
            st.caption("Solicitudes PagoYa")
            st.dataframe(pd.DataFrame({
                "Fecha": pa["fecha"], "Semana": pa["semana"].map(c.semana_corta),
                "Valor": pa["valor"], "Comisión": pa["comision"], "Ciudad": pa["ciudad"],
                "Pagar": pa["pagar"],
            }), hide_index=True, width="stretch", height=min(35 * len(pa) + 38, 260),
                column_config={"Valor": DINERO, "Comisión": DINERO})
        if not ma.empty:
            st.caption("Membresía por semana")
            st.dataframe(pd.DataFrame({
                "Semana": ma["semana"].map(c.semana_corta), "Plan": ma["tipo_plan"],
                "Estado retiro": ma["estado_retiro"], "Saldo actual": ma["saldo_actual"],
                "Disponible": ma["disponible"],
            }), hide_index=True, width="stretch", height=min(35 * len(ma) + 38, 260),
                column_config={"Saldo actual": DINERO, "Disponible": DINERO})


# ----------------------------------------------------------------------
# Secciones
# ----------------------------------------------------------------------

def seccion_indicadores(acum):
    _titulo("📊 Indicadores de retiro", "Acumulado de todas las semanas del periodo filtrado.")
    paises = c.orden_paises(acum["pais"].unique())
    for pais in paises:
        a = acum[acum["pais"] == pais]
        _encabezado_pais(pais, len(paises) > 1)
        positivos = a.loc[a["valor"] > 0, "valor"]
        k = st.columns(5)
        k[0].metric("Total de retiros", c.fmt_num(a["solicitudes"].sum()), help="Número de solicitudes PagoYa")
        k[1].metric("Aliados que retiraron", c.fmt_num(len(a)))
        k[2].metric("Promedio de retiros por aliado",
                    c.fmt_num(a["solicitudes"].mean(), 1) if len(a) else "—")
        k[3].metric("Monto mínimo acumulado", c.fmt_dinero(positivos.min()) if len(positivos) else "—",
                    help="El aliado que menos ha retirado en total en el periodo")
        k[4].metric("Monto máximo acumulado", c.fmt_dinero(positivos.max()) if len(positivos) else "—",
                    help="El aliado que más ha retirado en total en el periodo")


def seccion_tendencia(p):
    _titulo("📈 Tendencia semanal",
            "Barras: solicitudes · Línea: aliados distintos que retiraron. "
            "Haz clic en una semana para ver sus solicitudes.")
    sem = (p.groupby("semana")
            .agg(solicitudes=("valor", "size"), aliados=("clave", "nunique"))
            .reset_index().sort_values("semana"))
    x = sem["semana"].map(c.semana_corta)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=x, y=sem["solicitudes"], name="Solicitudes", marker_color=c.AZUL,
                         customdata=sem["semana"], opacity=0.85), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=sem["aliados"], name="Aliados distintos", mode="lines+markers",
                             line=dict(color=c.ROSADO, width=3), customdata=sem["semana"]),
                  secondary_y=True)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.1, x=0), bargap=0.25)
    fig.update_yaxes(title_text="Solicitudes", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Aliados", secondary_y=True, rangemode="tozero", showgrid=False)
    ev = st.plotly_chart(fig, key="al_tendencia", on_select="rerun", selection_mode="points")
    puntos = ev.selection.points if ev and ev.selection else []
    if puntos:
        cd = puntos[0].get("customdata")
        semana = cd[0] if isinstance(cd, (list, tuple)) else cd
        if semana:
            d = p[p["semana"] == semana].sort_values("valor", ascending=False)
            with st.container(border=True):
                st.markdown(f"**🔎 {c.semana_corta(semana)}: {c.fmt_num(len(d))} solicitudes de "
                            f"{c.fmt_num(d['clave'].nunique())} aliados**")
                vista = pd.DataFrame({"Fecha": d["fecha"], "Aliado": d["nombre"], "Ciudad": d["ciudad"],
                                      "País": d["pais"], "Valor": d["valor"], "Comisión": d["comision"]})
                st.dataframe(vista, hide_index=True, width="stretch", height=300,
                             column_config={"Valor": DINERO, "Comisión": DINERO})
                c.boton_excel(vista, f"solicitudes_{semana}", key=f"xl_sem_{semana}")


def seccion_saldos(s, fecha_corte, acum, p, m):
    _titulo("💰 Saldo pendiente por pagar a los aliados")
    if s.empty:
        st.info("Aún no hay archivo de saldos. Súbelo en la pestaña 📤 Cargar datos.")
        return
    st.caption(f"Saldos del último corte ({c.fmt_fecha(fecha_corte)}), cruzados aliado por aliado con lo "
               "retirado en PagoYa durante el periodo filtrado.")
    cruce = s.merge(acum[["clave", "solicitudes", "valor"]], on="clave", how="left")
    cruce["solicitudes"] = cruce["solicitudes"].fillna(0).astype(int)
    cruce["retirado"] = cruce["valor"].fillna(0)

    paises = c.orden_paises(cruce["pais"].unique())
    for pais in paises:
        x = cruce[cruce["pais"] == pais]
        _encabezado_pais(pais, len(paises) > 1)
        saldo_total = x["saldo"].sum()
        retirado = x["retirado"].sum()
        negativos = x[x["saldo"] < 0]
        k = st.columns(5)
        k[0].metric("Saldo total de los aliados", c.fmt_dinero(saldo_total),
                    help="Lo que la empresa tiene comprometido con los aliados (suma de todos los saldos).")
        k[1].metric("Aliados con saldo", c.fmt_num(len(x)),
                    help=f"{c.fmt_num(len(negativos))} con saldo negativo por {c.fmt_dinero(negativos['saldo'].sum())}")
        k[2].metric("Retirado por PagoYa", c.fmt_dinero(retirado),
                    help="Lo que esos mismos aliados han retirado por PagoYa en el periodo filtrado.")
        k[3].metric("% retirado vs. saldo", c.fmt_pct(retirado / saldo_total * 100) if saldo_total > 0 else "—",
                    help="Agregado, no por aliado individual.")
        k[4].metric("Saldo de aliados recurrentes", c.fmt_dinero(x.loc[x["solicitudes"] >= 3, "saldo"].sum()),
                    help="Saldo de los aliados con 3 o más solicitudes PagoYa en el periodo.")

    orden = cruce.sort_values("saldo", ascending=False)
    vista = pd.DataFrame({
        "clave": orden["clave"], "Aliado": orden["nombre"], "Ciudad": orden["ciudad"], "País": orden["pais"],
        "Saldo (deuda)": orden["saldo"].round(0), "Solicitudes PagoYa": orden["solicitudes"],
        "Retirado acumulado": orden["retirado"].round(0),
    })
    st.caption("Mayores saldos pendientes. Haz clic en una fila para ver el detalle del aliado. "
               "Usa la lupa 🔍 de la tabla para buscar un nombre.")
    elegido = _tabla_seleccionable(vista.head(300), "al_tabla_saldos",
                                   {"Saldo (deuda)": DINERO, "Retirado acumulado": DINERO,
                                    "Solicitudes PagoYa": ENTERO}, alto=320)
    c.boton_excel(vista, "saldos_vs_pagoya", key="xl_saldos")
    if elegido:
        detalle_aliado(elegido, p, m, s)


def seccion_ranking(acum, p, m, s):
    _titulo("🏆 Ranking acumulado PagoYa", "Aliados ordenados por valor total retirado en el periodo. "
                                          "Haz clic en una fila para ver el detalle.")
    orden = acum.sort_values("valor", ascending=False)
    vista = pd.DataFrame({
        "clave": orden["clave"], "Aliado": orden["nombre"], "Ciudad": orden["ciudad"], "País": orden["pais"],
        "Solicitudes": orden["solicitudes"], "Semanas activas": orden["semanas"],
        "Valor acumulado": orden["valor"].round(0), "Comisión acumulada": orden["comision"].round(0),
    })
    elegido = _tabla_seleccionable(vista.head(20), "al_tabla_ranking",
                                   {"Valor acumulado": DINERO, "Comisión acumulada": DINERO}, alto=420)
    c.boton_excel(vista, "ranking_pagoya", key="xl_ranking")
    if elegido:
        detalle_aliado(elegido, p, m, s)


def seccion_recurrentes(acum, p, m, s):
    _titulo("🔁 Aliados más recurrentes", "Los 15 aliados con más solicitudes. Haz clic en una barra para ver el detalle.")
    top = acum.sort_values(["solicitudes", "valor"], ascending=False).head(15).iloc[::-1]
    etiquetas = top["nombre"] + " · " + top["ciudad"]
    fig = go.Figure(go.Bar(
        x=top["solicitudes"], y=etiquetas, orientation="h", marker_color=c.ROSADO,
        customdata=top["clave"], text=top["solicitudes"], textposition="outside",
        hovertemplate="%{y}<br>%{x} solicitudes<extra></extra>"))
    fig.update_layout(height=max(300, 28 * len(top) + 60), margin=dict(l=10, r=40, t=10, b=10),
                      xaxis_title="Solicitudes", yaxis=dict(automargin=True))
    ev = st.plotly_chart(fig, key="al_recurrentes", on_select="rerun", selection_mode="points")
    puntos = ev.selection.points if ev and ev.selection else []
    if puntos:
        cd = puntos[0].get("customdata")
        clave = cd[0] if isinstance(cd, (list, tuple)) else cd
        if clave:
            detalle_aliado(clave, p, m, s)


def seccion_fraude(acum, p, m, s):
    alerta = acum[(acum["solicitudes"] >= 3) & (acum["montos_distintos"] == 1)] \
        .sort_values(["solicitudes", "valor"], ascending=False)
    _titulo(f"🚨 Alerta de fraude: siempre el mismo monto ({c.fmt_num(len(alerta))})",
            "Aliados con 3 o más solicitudes en el periodo, todas exactamente por el mismo valor.")
    if alerta.empty:
        st.success("No se detectaron aliados con montos idénticos repetidos.")
        return
    vista = pd.DataFrame({
        "clave": alerta["clave"], "Aliado": alerta["nombre"], "Ciudad": alerta["ciudad"], "País": alerta["pais"],
        "Solicitudes": alerta["solicitudes"], "Monto repetido": alerta["monto"],
        "Semanas": alerta["semanas"], "Valor total": alerta["valor"].round(0),
        "Primera": alerta["primera"], "Última": alerta["ultima"],
    })
    elegido = _tabla_seleccionable(vista, "al_tabla_fraude",
                                   {"Monto repetido": DINERO, "Valor total": DINERO},
                                   alto=min(35 * len(vista) + 38, 360))
    c.boton_excel(vista, "alerta_fraude_montos_iguales", key="xl_fraude")
    if elegido:
        detalle_aliado(elegido, p, m, s)


def seccion_bloqueos(m, p, s):
    b = bloqueos_recurrentes(m)
    _titulo(f"⛔ Bloqueos recurrentes en membresía ({c.fmt_num(len(b))})",
            "Aliados con 'Fondos insuficientes' en el estado de retiro en 2 o más semanas del periodo.")
    if m.empty:
        st.info("No hay datos de Membresías para este filtro.")
        return
    if b.empty:
        st.success("Sin aliados con bloqueos repetidos en las semanas del periodo.")
        return
    vista = pd.DataFrame({
        "clave": b["clave"], "Aliado": b["nombre"], "Ciudad": b["ciudad"], "País": b["pais"],
        "Semanas bloqueado": b["semanas"], "Números de semana": b["cuales"],
        "Disponible (última semana)": b["disponible"].round(0),
    })
    elegido = _tabla_seleccionable(vista, "al_tabla_bloqueos", {"Disponible (última semana)": DINERO},
                                   alto=min(35 * len(vista) + 38, 360))
    c.boton_excel(vista, "bloqueos_fondos_insuficientes", key="xl_bloqueos")
    if elegido:
        detalle_aliado(elegido, p, m, s)


# ----------------------------------------------------------------------
# Pestaña completa
# ----------------------------------------------------------------------

def mostrar(pagoya, memb, saldos, fecha_corte, f: c.Filtro):
    p = c.aplicar(pagoya, f)
    m = c.aplicar(memb, f)
    s = c.aplicar_lugar(saldos, f)
    if p.empty and m.empty:
        st.info("No hay datos para los filtros elegidos. Prueba con otro año, mes, país o ciudad.")
        return
    st.caption(f"Mostrando: **{f.texto()}**")
    acum = acumulado_por_aliado(p)

    if not p.empty:
        seccion_indicadores(acum)
        seccion_tendencia(p)
    else:
        st.info("No hay solicitudes PagoYa en este periodo.")
    st.divider()
    seccion_saldos(s, fecha_corte, acum, p, m)
    st.divider()
    if not p.empty:
        seccion_ranking(acum, p, m, s)
        st.divider()
        seccion_recurrentes(acum, p, m, s)
        st.divider()
        seccion_fraude(acum, p, m, s)
        st.divider()
    seccion_bloqueos(m, p, s)
