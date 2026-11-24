from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="KPIs Estratégicos · Región Andina", layout="wide")

RAIZ = Path(__file__).resolve().parent.parent


@st.cache_data(show_spinner="Cargando fuente de datos...")
def cargar_fuente_kpis():
    candidatos = [
        "metricas_andina.csv",
        "contratos_publicar.csv",
        "secop_andina_base.csv",
        "secop2_2020_2025.csv",
    ]
    for nombre in candidatos:
        ruta = RAIZ / nombre
        if ruta.exists():
            df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
            df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
            return df, nombre
    raise FileNotFoundError(
        "No se encontró metricas_andina.csv, contratos_publicar.csv, secop_andina_base.csv ni secop2_2020_2025.csv en la raíz del proyecto."
    )


def formato_cop(valor):
    try:
        v = float(valor)
        if abs(v) >= 1e12:
            return f"${v / 1e12:,.2f} B"
        if abs(v) >= 1e9:
            return f"${v / 1e9:,.2f} MM"
        if abs(v) >= 1e6:
            return f"${v / 1e6:,.1f} M"
        return f"${v:,.0f}"
    except Exception:
        return "$0"


st.title("KPIs Estratégicos · Contratación Región Andina")

try:
    df, fuente_usada = cargar_fuente_kpis()
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.caption(f"Fuente activa: `{fuente_usada}` · Registros cargados: `{len(df):,}`")

# Filtro opcional por departamento si existe la columna
df_vista = df.copy()
if "departamento" in df_vista.columns:
    deptos = sorted(df_vista["departamento"].fillna("Sin departamento").astype(str).unique())
    sel_deptos = st.multiselect("Filtrar por departamento", deptos)
    if sel_deptos:
        df_vista = df_vista[df_vista["departamento"].fillna("Sin departamento").astype(str).isin(sel_deptos)]

if df_vista.empty:
    st.warning("No hay registros para los filtros seleccionados.")
    st.stop()

# Modo consolidado por departamento (metricas_andina.csv) vs. detalle por contrato
es_consolidado = {"hhi_valor", "riesgo_score"}.issubset(df_vista.columns)

c1, c2, c3, c4 = st.columns(4)

if es_consolidado:
    total_contratos = int(pd.to_numeric(df_vista.get("contratos", 0), errors="coerce").fillna(0).sum())
    total_valor = float(pd.to_numeric(df_vista.get("valor_total_cop", 0), errors="coerce").fillna(0).sum())
    hhi_prom = float(pd.to_numeric(df_vista.get("hhi_valor", 0), errors="coerce").fillna(0).mean())
    riesgo_prom = float(pd.to_numeric(df_vista.get("riesgo_score", 0), errors="coerce").fillna(0).mean())

    c1.metric("Contratos en selección", f"{total_contratos:,}")
    c2.metric("Valor total consolidado", formato_cop(total_valor))
    c3.metric("HHI promedio", f"{hhi_prom:,.1f}")
    c4.metric("Puntaje de riesgo promedio", f"{riesgo_prom:,.2f}")

    st.subheader("Indicadores por departamento")
    st.dataframe(df_vista, use_container_width=True, hide_index=True)

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_riesgo = px.bar(
            df_vista.sort_values("riesgo_score", ascending=True),
            x="riesgo_score",
            y="departamento",
            color="nivel_alerta" if "nivel_alerta" in df_vista.columns else None,
            orientation="h",
            title="Puntaje de riesgo por departamento",
            labels={"riesgo_score": "Puntaje de riesgo", "departamento": "Departamento"},
        )
        st.plotly_chart(fig_riesgo, use_container_width=True)

    with col_g2:
        if "pct_contratacion_directa" in df_vista.columns:
            fig_hhi = px.scatter(
                df_vista,
                x="hhi_valor",
                y="pct_contratacion_directa",
                size="contratos" if "contratos" in df_vista.columns else None,
                hover_name="departamento",
                title="Concentración (HHI) vs. % Contratación directa",
                labels={"hhi_valor": "HHI", "pct_contratacion_directa": "% Contratación directa"},
            )
            st.plotly_chart(fig_hhi, use_container_width=True)
else:
    valores = pd.to_numeric(df_vista.get("valor_del_contrato", 0), errors="coerce").fillna(0)
    c1.metric("Contratos en selección", f"{len(df_vista):,}")
    c2.metric("Valor total", formato_cop(valores.sum()))
    c3.metric("Valor promedio", formato_cop(valores.mean()))
    c4.metric("Valor mediano", formato_cop(valores.median()))

    if "departamento" in df_vista.columns:
        resumen_depto = (
            df_vista.assign(_valor=valores)
            .groupby("departamento", as_index=False)
            .agg(contratos=("_valor", "count"), valor_total=("_valor", "sum"))
            .sort_values("valor_total", ascending=False)
        )
        st.subheader("Resumen por departamento")
        st.dataframe(resumen_depto, use_container_width=True, hide_index=True)

        fig_depto = px.bar(
            resumen_depto.head(12),
            x="departamento",
            y="valor_total",
            title="Valor contratado por departamento",
            labels={"departamento": "Departamento", "valor_total": "Valor total (COP)"},
        )
        st.plotly_chart(fig_depto, use_container_width=True)