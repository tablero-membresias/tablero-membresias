"""
pagoya.py — Pestaña "PagoYa" (Etapa 3)

- Resumen: solicitudes, valor desembolsado, comisión, IVA, ticket promedio
- Controles: Pagar = NO, GPS falso, Black list, cancelación alta
- Tendencia semanal de valor, comisión e IVA (clic en una semana = detalle)
- Valor por ciudad (clic en una ciudad = detalle) y por vehículo
- Descarga de todas las solicitudes del periodo
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as c

DINERO = st.column_config.NumberColumn(format="localized")


def _vista_solicitudes(d):
    d = d.sort_values(["fecha", "valor"], ascending=[False, False])
    return pd.DataFrame({
        "Fecha": d["fecha"], "Fecha validación": d["fecha_validacion"], "Semana": d["semana"].map(c.semana_corta),
        "Aliado": d["nombre"], "Ciudad": d["ciudad"], "País": d["pais"], "Vehículo": d["vehiculo"],
        "Valor": d["valor"], "Comisión": d["comision"], "IVA": d["iva"], "Pagar": d["pagar"],
    })


def _detalle(titulo, d, key):
    with st.container(border=True):
        st.markdown(f"**{titulo}: {c.fmt_num(len(d))} solicitudes · {c.fmt_dinero(d['valor'].sum())}**")
        vista = _vista_solicitudes(d)
        st.dataframe(vista, hide_index=True, width="stretch", height=300,
                     column_config={"Valor": DINERO, "Comisión": DINERO, "IVA": DINERO})
        c.boton_excel(vista, key, key=f"xl_{key}")


def seccion_resumen(p):
    c.titulo("Resumen PagoYa", "Totales del periodo filtrado.")
    paises = c.orden_paises(p["pais"].unique())
    for pais in paises:
        x = p[p["pais"] == pais]
        c.encabezado_pais(pais, len(paises) > 1)
        k = st.columns(6)
        k[0].metric("Solicitudes", c.fmt_num(len(x)))
        k[1].metric("Aliados", c.fmt_num(x["clave"].nunique()))
        k[2].metric("Valor desembolsado", c.fmt_dinero(x["valor"].sum()))
        k[3].metric("Comisión MU", c.fmt_dinero(x["comision"].sum()))
        k[4].metric("IVA", c.fmt_dinero(x["iva"].sum()))
        k[5].metric("Ticket promedio", c.fmt_dinero(x["valor"].mean()))


def seccion_controles(p):
    motivos = {
        "Pagar = NO": p["pagar"] == "NO",
        "GPS falso": p["gps_falso"].fillna(0) > 0,
        "Black list": p["black_list"].fillna("").str.upper().str.startswith("SI"),
        "Cancelación > 70%": p["cancelacion"].fillna(0) > 0.7,
    }
    c.titulo("Controles de las solicitudes")
    k = st.columns(4)
    for i, (nombre, mascara) in enumerate(motivos.items()):
        k[i].metric(nombre, c.fmt_num(int(mascara.sum())))
    alguna = pd.concat(motivos, axis=1)
    casos = p[alguna.any(axis=1)]
    if not casos.empty:
        with st.expander(f"Ver las {c.fmt_num(len(casos))} solicitudes con algún control"):
            motivo = alguna.loc[casos.index].apply(lambda r: ", ".join(n for n, v in r.items() if v), axis=1)
            vista = _vista_solicitudes(casos).assign(Motivo=motivo.reindex(casos.sort_values(
                ["fecha", "valor"], ascending=[False, False]).index).values)
            st.dataframe(vista, hide_index=True, width="stretch", height=300,
                         column_config={"Valor": DINERO, "Comisión": DINERO, "IVA": DINERO})
            c.boton_excel(vista, "pagoya_controles", key="xl_pg_controles")


def seccion_tendencia(x, pais):
    c.titulo(f"Tendencia semanal de recaudo · {pais}",
             "Barras: valor desembolsado (eje izquierdo) · Líneas: comisión e IVA (eje derecho). "
             "Haz clic en una semana para ver sus solicitudes.")
    sem = (x.groupby("semana").agg(valor=("valor", "sum"), comision=("comision", "sum"),
                                   iva=("iva", "sum"), solicitudes=("valor", "size"))
            .reset_index().sort_values("semana"))
    ejex = sem["semana"].map(c.semana_corta)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=ejex, y=sem["valor"], name="Valor", marker_color=c.AZUL, opacity=0.85,
                         customdata=sem["semana"],
                         hovertemplate="Valor: $%{y:,.0f}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=ejex, y=sem["comision"], name="Comisión", mode="lines+markers",
                             line=dict(color=c.ROSADO, width=3), customdata=sem["semana"],
                             hovertemplate="Comisión: $%{y:,.0f}<extra></extra>"), secondary_y=True)
    fig.add_trace(go.Scatter(x=ejex, y=sem["iva"], name="IVA", mode="lines+markers",
                             line=dict(color=c.ROJO, width=2, dash="dot"), customdata=sem["semana"],
                             hovertemplate="IVA: $%{y:,.0f}<extra></extra>"), secondary_y=True)
    c.estilo(fig, 380).update_layout(hovermode="x unified", bargap=0.25, separators=",.")
    fig.update_yaxes(title_text="Valor", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Comisión / IVA", secondary_y=True, rangemode="tozero", showgrid=False)
    cd = c.punto_elegido(st.plotly_chart(fig, key="pg_tendencia", on_select="rerun", selection_mode="points"))
    semana = cd[0] if isinstance(cd, (list, tuple)) else cd
    if semana:
        _detalle(c.semana_corta(semana), x[x["semana"] == semana], f"pagoya_{semana}")


def seccion_ciudad_vehiculo(x, pais):
    col1, col2 = st.columns([3, 2])
    with col1:
        c.titulo(f"Valor por ciudad · {pais}", "Haz clic en una barra para ver las solicitudes de esa ciudad.")
        ciu = (x.groupby("ciudad").agg(valor=("valor", "sum"), solicitudes=("valor", "size"))
                .reset_index().sort_values("valor").tail(12))
        fig = go.Figure(go.Bar(x=ciu["valor"], y=ciu["ciudad"], orientation="h", marker_color=c.AZUL,
                               customdata=ciu["ciudad"], text=ciu["solicitudes"].map(lambda n: f"{n} solic."),
                               textposition="auto",
                               hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>"))
        c.estilo(fig, max(280, 32 * len(ciu) + 60)).update_layout(separators=",.", yaxis=dict(automargin=True))
        cd = c.punto_elegido(st.plotly_chart(fig, key="pg_ciudad", on_select="rerun", selection_mode="points"))
        ciudad = cd[0] if isinstance(cd, (list, tuple)) else cd
    with col2:
        c.titulo(f"Por vehículo · {pais}", "Número de solicitudes.")
        veh = x["vehiculo"].fillna("Sin dato").value_counts()
        fig = go.Figure(go.Pie(labels=veh.index, values=veh.values, hole=0.55, sort=False,
                               marker=dict(colors=[c.ROSADO, c.AZUL, c.GRIS, c.ROJO, "#C9C9C9"])))
        st.plotly_chart(c.estilo(fig, 320), key="pg_vehiculo")
    if ciudad:
        _detalle(ciudad, x[x["ciudad"] == ciudad], f"pagoya_{ciudad}")


def mostrar(pagoya, f: c.Filtro):
    p = c.aplicar(pagoya, f)
    if p.empty:
        st.info("No hay solicitudes PagoYa para los filtros elegidos.")
        return
    st.caption(f"Mostrando: **{f.texto()}**")
    seccion_resumen(p)
    st.divider()
    seccion_controles(p)
    st.divider()
    pais = c.elegir_pais_grafico(p, f, key="pg_pais_graf")
    x = p[p["pais"] == pais]
    seccion_tendencia(x, pais)
    st.divider()
    seccion_ciudad_vehiculo(x, pais)
    st.divider()
    c.titulo("Todas las solicitudes del periodo")
    c.boton_excel(_vista_solicitudes(p), "pagoya_solicitudes", key="xl_pg_todas")
