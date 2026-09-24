"""
membresias.py — Pestaña "Membresías" (Etapa 4)

La Lista Oro es mensual: los mismos aliados aparecen todas las semanas del mes
y lo que cambia es su estado y su saldo. Por eso:
- "Aliados con membresía" cuenta cada aliado una sola vez.
- El recaudo cuenta cada aliado UNA vez por mes (valor del plan: $44.900 Básico, $64.900 Blue).
- Saldos y estados se toman de la última semana del periodo.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import comun as c

DINERO = st.column_config.NumberColumn(format="localized")


def recaudo_mensual(m):
    """Una fila por aliado y mes, con el valor de su plan."""
    return (m.sort_values("semana")
             .groupby(["pais", "anio", "mes", "clave"])
             .agg(valor_plan=("valor_plan", "last"), plan=("tipo_plan", "last"))
             .reset_index())


def _vista(d):
    d = d.sort_values(["semana", "nombre"], ascending=[False, True])
    return pd.DataFrame({
        "Semana": d["semana"].map(c.semana_corta), "Fecha depósito": d["fecha_deposito"],
        "Aliado": d["nombre"], "Ciudad": d["ciudad"], "País": d["pais"], "Plan": d["tipo_plan"],
        "Valor plan": d["valor_plan"], "Estado retiro": d["estado_retiro"],
        "Saldo actual": d["saldo_actual"], "Disponible": d["disponible"], "Estado aliado": d["estado_aliado"],
    })


def seccion_resumen(m, men):
    ultima = m["semana"].max()
    c.titulo("Resumen de membresías",
             f"Aliados y recaudo sin duplicar. Saldos y estados de la última semana del periodo: "
             f"{c.semana_corta(ultima)}.")
    paises = c.orden_paises(m["pais"].unique())
    for pais in paises:
        x, r = m[m["pais"] == pais], men[men["pais"] == pais]
        u = x[x["semana"] == x["semana"].max()]
        c.encabezado_pais(pais, len(paises) > 1)
        k = st.columns(6)
        k[0].metric("Aliados con membresía", c.fmt_num(x["clave"].nunique()),
                    help="Aliados distintos en el periodo (cada uno cuenta una vez).")
        k[1].metric("Recaudo estimado", c.fmt_dinero(r["valor_plan"].sum()),
                    help="Cada aliado cuenta una vez por mes, con el valor de su plan.")
        k[2].metric("Aliados última semana", c.fmt_num(u["clave"].nunique()))
        k[3].metric("Saldo total (última semana)", c.fmt_dinero(u["saldo_actual"].sum()))
        k[4].metric("Disponible para retiro", c.fmt_dinero(u["disponible"].sum()),
                    help="Suma de 'Disponible para retiro' en la última semana del periodo.")
        fondos = (u["estado_retiro"] == "Fondos insuficientes").mean() * 100 if len(u) else None
        k[5].metric("% con fondos insuficientes", c.fmt_pct(fondos), help="En la última semana del periodo.")


def seccion_recaudo(men, pais):
    c.titulo(f"Recaudo estimado por mes · {pais}",
             "Barras: recaudo (cada aliado una vez por mes) · Línea: aliados con membresía ese mes.")
    r = men[men["pais"] == pais]
    mes = (r.groupby(["anio", "mes"]).agg(recaudo=("valor_plan", "sum"), aliados=("clave", "nunique"))
            .reset_index().sort_values(["anio", "mes"]))
    etiquetas = mes.apply(lambda f: f"{c.MESES[int(f['mes']) - 1][:3]} {int(f['anio'])}", axis=1)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=etiquetas, y=mes["recaudo"], name="Recaudo", marker_color=c.AZUL,
                         text=mes["recaudo"].map(c.fmt_dinero), textposition="outside",
                         hovertemplate="Recaudo: $%{y:,.0f}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=etiquetas, y=mes["aliados"], name="Aliados", mode="lines+markers",
                             line=dict(color=c.ROSADO, width=3),
                             hovertemplate="Aliados: %{y}<extra></extra>"), secondary_y=True)
    c.estilo(fig, 360).update_layout(hovermode="x unified", separators=",.")
    fig.update_yaxes(title_text="Recaudo", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Aliados", secondary_y=True, rangemode="tozero", showgrid=False)
    st.plotly_chart(fig, key="mb_recaudo")


def seccion_semanal(x, pais):
    c.titulo(f"Aliados activos por semana y estado del retiro · {pais}",
             "Cada barra es una semana (un depósito). Haz clic en un color para ver esos aliados.")
    tabla = (x.assign(estado=x["estado_retiro"].fillna("Sin dato"))
              .groupby(["semana", "estado"])["clave"].nunique().unstack(fill_value=0).sort_index())
    ejex = [c.semana_corta(s) for s in tabla.index]
    orden = [e for e in c.COLORES_ESTADO if e in tabla.columns] + \
            [e for e in tabla.columns if e not in c.COLORES_ESTADO]
    fig = go.Figure()
    for estado in orden:
        fig.add_trace(go.Bar(
            x=ejex, y=tabla[estado], name=estado, marker_color=c.COLORES_ESTADO.get(estado, "#C9C9C9"),
            customdata=np.column_stack([tabla.index, [estado] * len(tabla)]),
            hovertemplate=f"{estado}: %{{y}}<extra></extra>"))
    activos = x[x["estado_aliado"] == "activo"].groupby("semana")["clave"].nunique().reindex(tabla.index)
    fig.add_trace(go.Scatter(x=ejex, y=activos, name="Aliados activos", mode="lines+markers",
                             line=dict(color="#9CA3AF", width=2, dash="dot"), marker=dict(size=5),
                             hovertemplate="Activos: %{y}<extra></extra>"))
    c.estilo(fig, 400).update_layout(barmode="stack", hovermode="x unified", bargap=0.2)
    cd = c.punto_elegido(st.plotly_chart(fig, key="mb_semanal", on_select="rerun", selection_mode="points"))
    if isinstance(cd, (list, tuple)) and len(cd) == 2:
        semana, estado = cd
        d = x[(x["semana"] == semana) & (x["estado_retiro"].fillna("Sin dato") == estado)]
        with st.container(border=True):
            st.markdown(f"**{c.semana_corta(semana)} · {estado}: {c.fmt_num(len(d))} aliados**")
            vista = _vista(d)
            st.dataframe(vista, hide_index=True, width="stretch", height=300,
                         column_config={"Valor plan": DINERO, "Saldo actual": DINERO, "Disponible": DINERO})
            c.boton_excel(vista, f"membresia_{semana}_{estado}", key=f"xl_mb_{semana}_{estado}")


def seccion_plan_ciudad(x, men, pais):
    col1, col2 = st.columns([2, 3])
    with col1:
        c.titulo(f"Por plan · {pais}", "Aliados distintos según su último plan.")
        planes = (x.sort_values("semana").groupby("clave")["tipo_plan"].last()
                   .fillna("Sin plan").str.strip().value_counts())
        fig = go.Figure(go.Pie(labels=planes.index, values=planes.values, hole=0.55, sort=False,
                               marker=dict(colors=[c.AZUL, c.ROSADO, c.GRIS, c.ROJO])))
        st.plotly_chart(c.estilo(fig, 320), key="mb_plan")
    with col2:
        c.titulo(f"Por ciudad · {pais}", "Aliados distintos con membresía.")
        ciu = x.groupby("ciudad")["clave"].nunique().sort_values().tail(10)
        fig = go.Figure(go.Bar(x=ciu.values, y=ciu.index, orientation="h", marker_color=c.ROSADO,
                               text=ciu.values, textposition="auto",
                               hovertemplate="%{y}: %{x} aliados<extra></extra>"))
        c.estilo(fig, max(280, 32 * len(ciu) + 60)).update_layout(yaxis=dict(automargin=True))
        st.plotly_chart(fig, key="mb_ciudad")


def mostrar(memb, f: c.Filtro):
    m = c.aplicar(memb, f)
    if m.empty:
        st.info("No hay datos de Membresías para los filtros elegidos.")
        return
    st.caption(f"Mostrando: **{f.texto()}**")
    men = recaudo_mensual(m)
    seccion_resumen(m, men)
    st.divider()
    pais = c.elegir_pais_grafico(m, f, key="mb_pais_graf")
    x = m[m["pais"] == pais]
    seccion_recaudo(men, pais)
    st.divider()
    seccion_semanal(x, pais)
    st.divider()
    seccion_plan_ciudad(x, men, pais)
    st.divider()
    c.titulo("Todos los registros de membresía del periodo")
    c.boton_excel(_vista(m), "membresias_periodo", key="xl_mb_todas")
