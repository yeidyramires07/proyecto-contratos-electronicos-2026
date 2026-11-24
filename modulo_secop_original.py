"""
Dashboard de alertas de concentración en contratación pública
SECOP II · Región Andina (11 departamentos) · 2020-2025

Versión importable de app_dashboard.py (mismo diseño, textos, gráficas y filtros).
Para usarlo dentro de otro tablero de Streamlit:
    from modulo_secop_original import mostrar_dashboard_secop
    mostrar_dashboard_secop()

Para verlo solo:
    streamlit run modulo_secop_original.py

Lee las tablas de la carpeta dashboard_datos (generadas por KPIs_corregidos_dashboard.ipynb).
Requiere: streamlit, plotly, pandas, pyarrow.
"""
import json
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, "dashboard_datos")

# ----------------------------------------------------------------------------- estilo
AZUL, AZUL_CLARO, AZUL_PALIDO = "#0b3c5d", "#5499C7", "#DCE9F5"
GRIS, GRIS_OSCURO, TEXTO = "#A0AEC0", "#4A5568", "#2D3748"
VERDE_AZUL = "#2A9D8F"
COLOR_ARQ = {"C0 Inversión tardía": "#1f77b4", "C1 Nómina OPS": "#2ca02c",
             "C2 Mega-ejecutores": "#0b3c5d", "C3 Régimen especial": "#d95f02"}
ORDEN_ARQ = list(COLOR_ARQ)
COLOR_MODALIDAD = {"Contratación directa": AZUL, "Régimen especial": AZUL_CLARO,
                   "Competitiva": VERDE_AZUL, "Otra": GRIS}
COLOR_PERIODO = {"Normal": GRIS,
                 "4 semanas antes de veda 2022": AZUL, "4 semanas antes de veda 2023": AZUL,
                 "Veda directa 2022": AZUL_CLARO, "Veda interadministrativos 2023": AZUL_CLARO}
DANE = {"Antioquia": "05", "Bogotá D.C.": "11", "Boyacá": "15", "Caldas": "17", "Cundinamarca": "25",
        "Huila": "41", "Norte de Santander": "54", "Quindío": "63", "Risaralda": "66", "Santander": "68",
        "Tolima": "73"}
FUENTE = "Región Andina, 11 departamentos · 2020–2025 · SECOP II · cálculo propio"

def aplicar_estilos():
    st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem;}
      h1 {font-size: 1.7rem !important; color: #0b3c5d;}
      h3 {font-size: 1.05rem !important; color: #2D3748; margin-bottom: 0.2rem;}
      [data-testid="stMetricValue"] {color: #0b3c5d;}
      .nota {color: #4A5568; font-size: 0.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
    )


def num(x, dec=0):
    """Número con formato colombiano: 1.234,5"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, dec=1):
    return "—" if x is None or pd.isna(x) else f"{num(x * 100, dec)} %"


def mostrar(fig):
    fig.update_layout(font=dict(family="Segoe UI, Arial", color=TEXTO, size=12),
                      plot_bgcolor="white", paper_bgcolor="white",
                      margin=dict(l=10, r=10, t=40, b=10), separators=",.")
    try:
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def tabla(df, **kw):
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def titulo_grafica(texto):
    st.markdown(f"### {texto}")



def color_escala(v, vmin, vmax):
    """Interpola entre azul pálido y azul oscuro."""
    t = 0 if vmax == vmin else min(max((v - vmin) / (vmax - vmin), 0), 1)
    a, b = (220, 233, 245), (11, 60, 93)
    return "rgb({},{},{})".format(*[int(a[i] + (b[i] - a[i]) * t) for i in range(3)])


def mapa_departamentos(g):
    """Mapa coroplético dibujado con polígonos (no necesita internet)."""
    datos = g.set_index("cod")
    vmin, vmax = datos["directa"].min() * 100, datos["directa"].max() * 100
    fig = go.Figure()
    xs_dato, ys_dato = [], []
    for ft in geo["features"]:
        cod = ft["properties"]["DPTO"]
        geom = ft["geometry"]
        poligonos = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        tiene = cod in datos.index
        relleno = color_escala(datos.loc[cod, "directa"] * 100, vmin, vmax) if tiene else "#EDF2F7"
        for k, poli in enumerate(poligonos):
            x = [p[0] for p in poli[0]]
            y = [p[1] for p in poli[0]]
            if tiene:
                xs_dato += x
                ys_dato += y
            fig.add_trace(go.Scatter(
                x=x, y=y, fill="toself", mode="lines", fillcolor=relleno,
                line=dict(color="white", width=1), showlegend=False,
                hoverinfo="text" if tiene else "skip",
                text=datos.loc[cod, "texto"] if tiene else None, hoveron="fills"))
    for cod, r in datos.iterrows():  # etiqueta con el %
        ft = next((x for x in geo["features"] if x["properties"]["DPTO"] == cod), None)
        if ft is None:
            continue
        geom = ft["geometry"]
        poli = max(geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]],
                   key=lambda p: len(p[0]))[0]
        cx, cy = np.mean([p[0] for p in poli]), np.mean([p[1] for p in poli])
        claro = (r["directa"] * 100 - vmin) / max(vmax - vmin, 1e-9) > 0.55
        fig.add_annotation(x=cx, y=cy, text=pct(r["directa"], 0), showarrow=False,
                           font=dict(size=10, color="white" if claro else TEXTO))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(colorscale=[[0, AZUL_PALIDO], [1, AZUL]], cmin=vmin, cmax=vmax,
                                         color=[vmin], showscale=True,
                                         colorbar=dict(title="% directa", ticksuffix=" %", thickness=12))))
    pad = 0.4
    fig.update_xaxes(visible=False, range=[min(xs_dato) - pad, max(xs_dato) + pad])
    fig.update_yaxes(visible=False, range=[min(ys_dato) - pad, max(ys_dato) + pad], scaleanchor="x", scaleratio=1)
    fig.update_layout(height=500, hovermode="closest")
    return fig


# ----------------------------------------------------------------------------- datos
@st.cache_data(show_spinner="Cargando datos…")
def cargar():
    def leer(n):
        """Lee el parquet; si falla (p. ej. pyarrow 19.0.0), intenta con el CSV equivalente."""
        try:
            return pd.read_parquet(os.path.join(DATOS, f"{n}.parquet"))
        except Exception as error:
            csv = os.path.join(DATOS, f"{n}.csv")
            if os.path.exists(csv):
                return pd.read_csv(csv, encoding="utf-8-sig")
            raise RuntimeError(
                f"No se pudo leer {n}.parquet ({error}). Si tu pyarrow es 19.0.0, actualízalo: "
                "pip install -U pyarrow  (o vuelve a ejecutar KPIs_corregidos_dashboard.ipynb).") from error
    fact = leer("fact_contratos")[["entidad", "proveedor", "tipo_proveedor", "valor", "fecha_firma", "anio", "mes",
                                   "modalidad_grupo", "es_decreto_092", "es_pyme", "departamento",
                                   "periodo_electoral"]]
    fact["fecha_firma"] = pd.to_datetime(fact["fecha_firma"])
    fact["mes_firma"] = fact["fecha_firma"].dt.to_period("M").dt.to_timestamp()
    for c in ["tipo_proveedor", "modalidad_grupo", "departamento", "periodo_electoral"]:
        fact[c] = fact[c].astype("category")
    ent = leer("dim_entidad")
    geo_path = os.path.join(DATOS, "colombia_departamentos.geojson")
    geo = json.load(open(geo_path, encoding="utf-8")) if os.path.exists(geo_path) else None
    return (fact, ent, leer("dim_arquetipo"), leer("agg_curva_mensual"), leer("agg_garantias"),
            leer("agg_alertas_arquetipo"), leer("agg_proveedores"), geo)


# ----------------------------------------------------------------------------- barra lateral
PAGINAS = ["1 · Panorama", "2 · No todas contratan igual", "3 · Alertas",
           "4 · Patrones entre entidades", "5 · Ficha de entidad"]


def share(df, mascara):
    total = df["valor"].sum()
    return df.loc[mascara, "valor"].sum() / total if total else np.nan


def abrir_ficha(nombre):
    st.session_state.secop_entidad_ficha = nombre
    st.session_state.secop_pagina = PAGINAS[4]


# ============================================================================= PÁGINA 1
def pagina_panorama():
    st.title("¿Cuánto y cómo contrata la Región Andina?")
    st.caption(FUENTE + " · cifras ponderadas por valor")

    k = st.columns(5)
    k[0].metric("Billones de $ contratados", num(f["valor"].sum() / 1e12, 1),
                help=f"{num(len(f))} contratos")
    k[1].metric("% del valor por directa", pct(share(f, f["modalidad_grupo"] == "Contratación directa")),
                help=f"{pct((f['modalidad_grupo'] == 'Contratación directa').mean())} de los contratos")
    k[2].metric("% del valor a Pymes", pct(share(f, f["es_pyme"])))
    k[3].metric("HHI típico con empresas", num(evaluables["hhi_mercado"].median(), 3),
                help="HHI mediano (0 a 1) del gasto con empresas u organizaciones")
    k[4].metric("Alertas alta · media",
                f"{(evaluables['prioridad'] == 'Alta').sum()} · {(evaluables['prioridad'] == 'Media').sum()}",
                help="Evaluación 2020–2025; no cambia con el filtro de años")

    izq, der = st.columns([1.05, 1])
    with izq:
        titulo_grafica("% del valor por contratación directa, por departamento")
        tmp = f.assign(v_dir=f["valor"].where(f["modalidad_grupo"] == "Contratación directa", 0),
                       v_pyme=f["valor"].where(f["es_pyme"], 0),
                       v_emp=f["valor"].where(f["tipo_proveedor"] == "Empresa u organización", 0))
        g = tmp.groupby("departamento", observed=True).agg(
            valor=("valor", "sum"), v_dir=("v_dir", "sum"), v_pyme=("v_pyme", "sum"), v_emp=("v_emp", "sum"),
            contratos=("valor", "size")).reset_index()
        g["directa"], g["pymes"], g["empresas"] = g["v_dir"] / g["valor"], g["v_pyme"] / g["valor"], g["v_emp"] / g["valor"]
        g["valor"] = g["valor"] / 1e12
        g["cod"] = g["departamento"].map(DANE)
        g["texto"] = (g["departamento"].astype(str) + "<br>Directa: " + g["directa"].map(pct)
                      + "<br>Pymes: " + g["pymes"].map(pct) + "<br>Empresas: " + g["empresas"].map(pct)
                      + "<br>Contratos: " + g["contratos"].map(num) + "<br>Billones: " + g["valor"].map(lambda v: num(v, 2)))
        if geo:
            fig = mapa_departamentos(g)
        else:
            g = g.sort_values("directa")
            fig = px.bar(g, x="directa", y="departamento", orientation="h", text=g["directa"].map(pct),
                         color_discrete_sequence=[AZUL], height=470)
            fig.update_layout(xaxis_tickformat=".0%", xaxis_title=None, yaxis_title=None)
        mostrar(fig)

    with der:
        titulo_grafica("La mayoría de contratos son de personas; la mayor parte del dinero va a empresas")
        t = (f[f["tipo_proveedor"] != "Sin dato"].groupby("tipo_proveedor", observed=True)
             .agg(contratos=("valor", "size"), valor=("valor", "sum")))
        t = (t / t.sum()).reset_index().melt(id_vars="tipo_proveedor", var_name="medida", value_name="parte")
        t["medida"] = t["medida"].map({"contratos": "% de los contratos", "valor": "% del valor"})
        fig = px.bar(t, x="parte", y="tipo_proveedor", color="medida", orientation="h", barmode="group",
                     text=t["parte"].map(pct), height=230,
                     color_discrete_map={"% de los contratos": GRIS, "% del valor": AZUL},
                     category_orders={"tipo_proveedor": ["Persona natural", "Empresa u organización", "Entidad pública"]})
        fig.update_layout(xaxis_visible=False, yaxis_title=None, legend_title=None,
                          legend=dict(orientation="h", y=1.15, x=0))
        fig.update_traces(textposition="outside", cliponaxis=False)
        mostrar(fig)

        titulo_grafica("Valor firmado por año (billones de $)")
        a = f.groupby("anio")["valor"].sum().div(1e12).reset_index()
        fig = px.bar(a, x="anio", y="valor", text=a["valor"].map(lambda v: num(v, 1)),
                     color_discrete_sequence=[AZUL], height=220)
        fig.update_layout(xaxis_type="category", xaxis_title=None, yaxis_visible=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        mostrar(fig)
        st.markdown('<span class="nota">2025 incluye la logística electoral 2026 de la Registraduría '
                    '($3,3 billones).</span>', unsafe_allow_html=True)


# ============================================================================= PÁGINA 2
def pagina_arquetipos():
    st.title("¿Por qué no sirve medir a todas con la misma vara?")
    st.caption("Región Andina completa: esta página no responde a los filtros de departamento ni de años. "
               "Arquetipos de K-Means sobre 13 KPIs (1.317 entidades con 10 o más contratos).")

    c1, c2 = st.columns(2)
    with c1:
        titulo_grafica("1.317 entidades, 4 formas de contratar")
        d = arq.sort_values("arquetipo_id")
        fig = px.bar(d, x="entidades", y="arquetipo", orientation="h", color="arquetipo", text="entidades",
                     color_discrete_map=COLOR_ARQ, category_orders={"arquetipo": ORDEN_ARQ}, height=300,
                     hover_data={"descripcion": True, "entidades": False, "arquetipo": False})
        fig.update_layout(showlegend=False, xaxis_visible=False, yaxis_title=None)
        fig.update_traces(textposition="outside", cliponaxis=False)
        mostrar(fig)
        for _, r in d.iterrows():
            st.markdown(f'<span class="nota"><b style="color:{r["color_hex"]}">{r["codigo"]}</b> · {r["descripcion"]}</span>',
                        unsafe_allow_html=True)

    with c2:
        titulo_grafica("Qué distingue a cada arquetipo (promedio por entidad)")
        cols = {"pct_valor_directa": "Directa", "pct_valor_regimen_esp": "Régimen<br>especial",
                "pct_valor_pyme": "Pymes", "pct_valor_ene_feb_anual": "Ene-Feb", "pct_valor_nov_dic_anual": "Nov-Dic",
                "pct_valor_inversion": "Inversión", "tasa_contratos_modificados": "Modificados"}
        m = arq.sort_values("arquetipo_id").set_index("arquetipo")[list(cols)]
        z = (m - m.min()) / (m.max() - m.min())
        fig = go.Figure(go.Heatmap(z=z.values, x=list(cols.values()), y=m.index, colorscale=[[0, "white"], [1, AZUL_CLARO]],
                                   text=(m * 100).round(0).astype(int).astype(str) + " %", texttemplate="%{text}",
                                   showscale=False, hoverinfo="skip", xgap=2, ygap=2))
        fig.update_layout(height=330, yaxis_autorange="reversed", xaxis_side="top")
        mostrar(fig)
        st.markdown('<span class="nota">El color compara los arquetipos dentro de cada columna; '
                    'el número es el valor real.</span>', unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        titulo_grafica("C1 firma el 42 % de su presupuesto en enero y febrero; C0 y C2 cargan el cierre del año")
        fig = px.line(curva, x="mes", y="pct_promedio_valor", color="arquetipo", markers=True,
                      color_discrete_map=COLOR_ARQ, category_orders={"arquetipo": ORDEN_ARQ}, height=360)
        fig.add_hline(y=100 / 12, line_dash="dot", line_color=GRIS,
                      annotation_text="reparto parejo (1/12)", annotation_position="bottom right")
        fig.update_layout(xaxis=dict(tickmode="array", tickvals=list(range(1, 13)),
                                     ticktext=["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]),
                          xaxis_title=None, yaxis_title="% del valor anual", yaxis_ticksuffix=" %",
                          legend_title=None, legend=dict(orientation="h", y=-0.15))
        mostrar(fig)

    with c4:
        titulo_grafica("Un umbral único alerta al 23 % del régimen especial y solo al 3 % de nómina OPS")
        d = alertas_arq.melt(id_vars="arquetipo", value_vars=["pct_alerta_umbral_unico", "pct_senal_concentracion_pares"],
                             var_name="metodo", value_name="pct")
        d["metodo"] = d["metodo"].map({"pct_alerta_umbral_unico": "Umbral único (HHI ≥ 0,25)",
                                       "pct_senal_concentracion_pares": "Comparado con sus pares"})
        fig = px.bar(d, x="pct", y="arquetipo", color="metodo", orientation="h", barmode="group",
                     text=d["pct"].map(lambda v: num(v, 1) + " %"), height=360,
                     color_discrete_map={"Umbral único (HHI ≥ 0,25)": GRIS, "Comparado con sus pares": AZUL},
                     category_orders={"arquetipo": ORDEN_ARQ})
        fig.update_layout(xaxis_visible=False, yaxis_title=None, legend_title=None,
                          legend=dict(orientation="h", y=-0.1))
        fig.update_traces(textposition="outside", cliponaxis=False)
        mostrar(fig)
        st.markdown('<span class="nota">% de entidades evaluables en alerta. Comparar con pares reparte la atención '
                    'de forma justa: el 10 % más concentrado de cada grupo.</span>', unsafe_allow_html=True)


# ============================================================================= PÁGINA 3
def pagina_alertas():
    st.title("¿Qué entidades conviene revisar primero?")
    st.caption("Entidades con al menos 10 contratos con empresas · evaluación 2020–2025")

    prioridades = st.multiselect("Prioridad", ["Alta", "Media", "Sin alerta"], default=["Alta", "Media"])
    k = st.columns(3)
    k[0].metric("Prioridad alta", int((evaluables["prioridad"] == "Alta").sum()))
    k[1].metric("Prioridad media", int((evaluables["prioridad"] == "Media").sum()))
    k[2].metric("Entidades evaluables", len(evaluables))

    sel = evaluables[evaluables["prioridad"].isin(prioridades)].copy()
    sel["orden_p"] = sel["prioridad"].map({"Alta": 0, "Media": 1, "Sin alerta": 2})
    sel = sel.sort_values(["orden_p", "percentil_en_arquetipo"], ascending=[True, False])

    izq, der = st.columns([2, 1])
    with izq:
        titulo_grafica(f"{len(sel)} entidades: concentración atípica para su tipo y/o el mismo proveedor dominando")
        vista = pd.DataFrame({
            "Entidad": sel["entidad"], "Departamento": sel["departamento"], "Arquetipo": sel["arquetipo"],
            "Prioridad": sel["prioridad"], "Proveedor dominante": sel["top1_proveedor"],
            "% del gasto con empresas": sel["top1_participacion"] * 100,
            "Años dominando": sel["anios_mismo_dominante"].astype(int),
            "Posición frente a pares": sel["percentil_en_arquetipo"] * 100,
            "HHI empresas": sel["hhi_mercado"],
        })
        tabla(vista, height=430, column_config={
            "% del gasto con empresas": st.column_config.ProgressColumn(format="%.0f %%", min_value=0, max_value=100),
            "Posición frente a pares": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100, help="Percentil del HHI con empresas dentro de su arquetipo"),
            "HHI empresas": st.column_config.NumberColumn(format="%.3f"),
        })
        e1, e2 = st.columns([3, 1])
        elegida = e1.selectbox("Ver la ficha de", sel["entidad"].tolist() or ["—"], label_visibility="collapsed")
        e2.button("Abrir ficha →", on_click=abrir_ficha, args=(elegida,), disabled=sel.empty)

    with der:
        bajar = st.selectbox("Bajar a", ["Todos los departamentos"] + sorted(sel["departamento"].dropna().unique()))
        nivel = "departamento" if bajar == "Todos los departamentos" else "ciudad"
        base = sel if nivel == "departamento" else sel[sel["departamento"] == bajar]
        titulo_grafica("Alertas por " + ("departamento" if nivel == "departamento" else f"municipio · {bajar}"))
        d = base.groupby([nivel, "prioridad"]).size().rename("n").reset_index()
        orden = d.groupby(nivel)["n"].sum().sort_values().index.tolist()
        fig = px.bar(d, x="n", y=nivel, color="prioridad", orientation="h", text="n",
                     color_discrete_map={"Alta": AZUL, "Media": AZUL_CLARO, "Sin alerta": GRIS},
                     category_orders={nivel: orden[::-1], "prioridad": ["Alta", "Media", "Sin alerta"]},
                     height=max(300, 26 * len(orden) + 80))
        fig.update_layout(xaxis_visible=False, yaxis_title=None, legend_title=None,
                          legend=dict(orientation="h", y=1.08, x=0))
        mostrar(fig)

    st.info("**Cómo leer una alerta.** *Alta* = su concentración con empresas está en el 10 % más alto de su "
            "arquetipo **y** el mismo proveedor se llevó al menos el 40 % de ese gasto en 2 años o más. "
            "*Media* = una de las dos. Una alerta no prueba una irregularidad: indica dónde mirar primero.")


# ============================================================================= PÁGINA 4
def pagina_patrones():
    st.title("¿Qué no se ve mirando entidad por entidad?")
    st.caption(FUENTE)

    c1, c2 = st.columns(2)
    with c1:
        titulo_grafica("La Ley de Garantías concentra la firma en las 4 semanas previas a cada restricción")
        series = ["Contratación directa, 1-28 ene", "Interadministrativos territoriales, 1-28 jun"]
        fig = make_subplots(rows=1, cols=2, subplot_titles=["Directa, 1–28 ene", "Interadministrativos territoriales, 1–28 jun"])
        for i, s in enumerate(series, start=1):
            d = garantias[garantias["serie"] == s]
            fig.add_trace(go.Bar(x=d["anio"].astype(str), y=d["pct_del_anio"],
                                 marker_color=np.where(d["restriccion"], AZUL, GRIS),
                                 text=d["pct_del_anio"].map(lambda v: num(v, 1) + " %"), textposition="outside",
                                 cliponaxis=False, hovertemplate="%{x}: %{y:.1f} % del año<extra></extra>"), row=1, col=i)
        fig.update_yaxes(visible=False, range=[0, 60])
        fig.update_layout(showlegend=False, height=330)
        fig.update_annotations(font_size=11)
        mostrar(fig)
        st.markdown('<span class="nota">% de los contratos del año firmados en esas 4 semanas. Vedas desde el '
                    '29 ene 2022 (directa) y el 29 jun 2023 (interadministrativos territoriales). '
                    'Región completa; no responde a los filtros.</span>', unsafe_allow_html=True)

    with c2:
        titulo_grafica("Contratos directos por mes: los picos son la víspera de cada veda")
        d = (f[f["modalidad_grupo"] == "Contratación directa"]
             .groupby(["mes_firma", "periodo_electoral"], observed=True).size().rename("contratos").reset_index())
        fig = px.bar(d, x="mes_firma", y="contratos", color="periodo_electoral", height=330,
                     color_discrete_map=COLOR_PERIODO)
        fig.update_layout(bargap=0.1, xaxis_title=None, yaxis_title="Contratos directos", legend_title=None,
                          legend=dict(orientation="h", y=-0.2, font_size=10))
        mostrar(fig)

    c3, c4 = st.columns(2)
    with c3:
        titulo_grafica("Proveedores que son el n.º 1 en varias entidades a la vez")
        p = proveedores[proveedores["entidades_donde_es_n1"] >= 2].sort_values(
            ["entidades_donde_es_n1", "valor"], ascending=False)
        tabla(pd.DataFrame({
            "Proveedor": p["proveedor"], "Entidades donde es n.º 1": p["entidades_donde_es_n1"],
            "Entidades donde contrata": p["entidades"], "Departamentos": p["departamentos"],
            "Contratos": p["contratos"], "Valor (millones $)": p["valor"] / 1e6,
            "% por Decreto 092": p["pct_contratos_decreto_092"] * 100,
        }), height=360, column_config={
            "Valor (millones $)": st.column_config.NumberColumn(format="%.0f"),
            "% por Decreto 092": st.column_config.ProgressColumn(format="%.0f %%", min_value=0, max_value=100),
        })
        st.markdown('<span class="nota">Empresas u organizaciones privadas · región completa.</span>',
                    unsafe_allow_html=True)

    with c4:
        titulo_grafica("Los municipios de Boyacá canalizan el 27,7 % de su gasto con empresas en convenios con fundaciones")
        m = fact[(fact["tipo_proveedor"] == "Empresa u organización")
                 & fact["entidad"].str.contains("MUNICIPIO|ALCALDIA", na=False)]
        m = m.assign(v092=m["valor"].where(m["es_decreto_092"], 0))
        d = m.groupby("departamento", observed=True)[["v092", "valor"]].sum()
        d = (d["v092"] / d["valor"]).rename("pct").reset_index().sort_values("pct")
        fig = px.bar(d, x="pct", y="departamento", orientation="h", text=d["pct"].map(pct), height=360)
        fig.update_traces(marker_color=np.where(d["departamento"] == "Boyacá", AZUL, GRIS),
                          textposition="outside", cliponaxis=False)
        fig.update_layout(xaxis_visible=False, yaxis_title=None)
        mostrar(fig)
        st.markdown('<span class="nota">% del valor contratado con empresas u organizaciones por convenios del '
                    'Decreto 092 de 2017 (entidades sin ánimo de lucro), solo alcaldías y municipios, 2020–2025.</span>',
                    unsafe_allow_html=True)


# ============================================================================= PÁGINA 5
def pagina_ficha():
    lista = ents.sort_values("valor_total", ascending=False)["entidad"].tolist()
    if not lista:
        st.warning("No hay entidades con estos filtros.")
        return
    previa = st.session_state.get("secop_entidad_ficha")
    if previa not in lista:
        altas = ents[ents["prioridad"] == "Alta"]["entidad"].tolist()
        previa = altas[0] if altas else lista[0]
    nombre = st.selectbox("Entidad", lista, index=lista.index(previa))
    st.session_state.secop_entidad_ficha = nombre
    e = ent[ent["entidad"] == nombre].iloc[0]
    fe = fact[(fact["entidad"] == nombre) & fact["anio"].between(*anios)]

    st.title(nombre.title())
    st.caption(f"{e['departamento']} · {e['ciudad']} · orden {e['orden']} · {e['arquetipo']}")

    k = st.columns(5)
    k[0].metric("Prioridad", e["prioridad"])
    k[1].metric("Valor contratado", f"$ {num(fe['valor'].sum() / 1e6)} M")
    k[2].metric("Contratos", num(len(fe)))
    k[3].metric("% por contratación directa", pct(share(fe, fe["modalidad_grupo"] == "Contratación directa")))
    k[4].metric("% a Pymes", pct(share(fe, fe["es_pyme"])))

    if e["en_modelo"] and pd.notna(e["arquetipo_id"]):
        st.markdown("### ¿Qué tan distinta es de las entidades que contratan como ella?")
        pares = ent[(ent["arquetipo_id"] == e["arquetipo_id"])]
        pares_ev = pares[pares["evaluable_alerta"] == True]
        p = st.columns(4)
        if e["evaluable_alerta"]:
            med = pares_ev["hhi_mercado"].median()
            p[0].metric("Concentración con empresas (HHI)", num(e["hhi_mercado"], 3),
                        delta=f"{num(e['hhi_mercado'] - med, 3)} vs. pares ({num(med, 3)})",
                        delta_color="inverse")
            p[1].metric("Posición frente a sus pares", f"percentil {num(e['percentil_en_arquetipo'] * 100)}")
            p[2].metric("Años con proveedor dominante", int(e["anios_mismo_dominante"]),
                        help=f"Proveedor dominante: {e['top1_proveedor']} ({pct(e['top1_participacion'], 0)} del gasto con empresas)")
        else:
            p[0].info("Menos de 10 contratos con empresas: no se evalúa la concentración.")
        med_d = pares["pct_valor_directa"].median()
        p[3].metric("% directa (2020–2025)", pct(e["pct_valor_directa"]),
                    delta=f"{num((e['pct_valor_directa'] - med_d) * 100, 1)} pts vs. pares ({pct(med_d)})",
                    delta_color="inverse")

    c1, c2 = st.columns([1, 1.15])
    with c1:
        titulo_grafica("Valor firmado por año y modalidad (millones de $)")
        d = fe.groupby(["anio", "modalidad_grupo"], observed=True)["valor"].sum().div(1e6).rename("valor").reset_index()
        fig = px.bar(d, x="anio", y="valor", color="modalidad_grupo", color_discrete_map=COLOR_MODALIDAD, height=360)
        fig.update_layout(xaxis_type="category", xaxis_title=None, yaxis_title=None, legend_title=None,
                          legend=dict(orientation="h", y=-0.15))
        mostrar(fig)
    with c2:
        titulo_grafica("Principales proveedores")
        t = (fe.groupby(["proveedor", "tipo_proveedor"], observed=True)
             .agg(Contratos=("valor", "size"), valor=("valor", "sum")).reset_index())
        t["% del valor"] = t["valor"] / t["valor"].sum() * 100
        t = t.sort_values("valor", ascending=False).head(10)
        tabla(pd.DataFrame({"Proveedor": t["proveedor"], "Tipo": t["tipo_proveedor"], "Contratos": t["Contratos"],
                            "Valor (millones $)": t["valor"] / 1e6, "% del valor": t["% del valor"]}),
              height=360, column_config={
                  "Valor (millones $)": st.column_config.NumberColumn(format="%.0f"),
                  "% del valor": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100)})
        st.markdown('<span class="nota">Las personas naturales aparecen agrupadas en "Persona natural".</span>',
                    unsafe_allow_html=True)

    if pd.notna(e["garantias22_pct"]):
        st.markdown(f'<span class="nota"><b>Ley de Garantías 2022:</b> firmó el {pct(e["garantias22_pct"])} de su '
                    f'contratación directa de 2022 entre el 1 y el 28 de enero; en sus otros años, el '
                    f'{pct(e["garantias22_base"])} en esas mismas fechas.</span>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------- función principal
def mostrar_dashboard_secop():
    """Dibuja el dashboard completo: estilos, barra lateral con filtros, las 5 páginas y el pie."""
    global fact, ent, arq, curva, garantias, alertas_arq, proveedores, geo, anios, ents, f, evaluables

    aplicar_estilos()
    fact, ent, arq, curva, garantias, alertas_arq, proveedores, geo = cargar()

    if "secop_pagina" not in st.session_state:
        st.session_state.secop_pagina = PAGINAS[0]

    with st.sidebar:
        st.markdown("## Alertas de concentración")
        st.caption("Contratación pública · SECOP II · Región Andina")
        st.radio("Página", PAGINAS, key="secop_pagina", label_visibility="collapsed")
        st.divider()
        st.markdown("**Filtros**")
        anios = st.slider("Años de firma", 2020, 2025, (2020, 2025), key="secop_anios")
        deptos = st.multiselect("Departamento", sorted(ent["departamento"].dropna().unique()),
                                placeholder="Todos", key="secop_deptos")
        arqs = st.multiselect("Arquetipo", ORDEN_ARQ, placeholder="Todos", key="secop_arquetipos")
        st.caption("El filtro de años cambia las cifras de contratos. Arquetipos y alertas resumen 2020–2025.")

    ents = ent.copy()
    if deptos:
        ents = ents[ents["departamento"].isin(deptos)]
    if arqs:
        ents = ents[ents["arquetipo"].isin(arqs)]
    f = fact[fact["entidad"].isin(ents["entidad"]) & fact["anio"].between(*anios)]
    evaluables = ents[ents["evaluable_alerta"] == True]

    if f.empty:
        st.warning("No hay contratos con esa combinación de filtros.")
        return   # en lugar de st.stop(), para no detener el tablero principal

    {PAGINAS[0]: pagina_panorama, PAGINAS[1]: pagina_arquetipos, PAGINAS[2]: pagina_alertas,
     PAGINAS[3]: pagina_patrones, PAGINAS[4]: pagina_ficha}[st.session_state.secop_pagina]()

    st.divider()
    st.caption("Fuente: SECOP II (Colombia Compra Eficiente), cálculo propio. Una alerta no prueba una irregularidad. "
               "Mapa: jacasta2/colombian_map (licencia MIT).")


# ----------------------------------------------------------------------------- uso independiente
if __name__ == "__main__":
    st.set_page_config(page_title="Alertas de concentración · SECOP II Región Andina",
                       page_icon="📊", layout="wide")
    mostrar_dashboard_secop()
