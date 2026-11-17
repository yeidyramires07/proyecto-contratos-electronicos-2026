import os
import gdown
import pandas as pd
import streamlit as st


@st.cache_data
def cargar_datos_externos():
  # ID de tu archivo en Google Drive (el código largo entre /d/ y /view)
  file_id = "1tHzoqaE4xOcr64ZCUTnoChm2owPbqzCH"
  url = f"https://drive.google.com/uc?id={file_id}"
  output = "SECOP_FINAL_23_COLS.csv"

  # Si el archivo no está descargado localmente en el servidor de Streamlit, lo bajamos con gdown
  if not os.path.exists(output):
    gdown.download(url, output, quiet=False, fuzzy=True)

  # Leer el archivo CSV completo
  df = pd.read_csv(output, low_memory=False)

  # Limpiar y asegurar formato numérico en la columna de valores
  if "valor_del_contrato" in df.columns:
    df["valor_del_contrato"] = pd.to_numeric(
        df["valor_del_contrato"], errors="coerce"
    ).fillna(0)

  return df


# Mostrar un mensaje mientras procesa los 300,000+ registros
with st.spinner(
    "Descargando y procesando el dataset completo desde Google Drive..."
):
  df = cargar_datos_externos()

st.title("Módulo de KPIs y Tablas de Contratación")
st.markdown(
    "Análisis cuantitativo y métricas estratégicas basadas en el volumen"
    " total de registros."
)

# --- DEBUG RÁPIDO (Opcional): Descomenta la siguiente línea si quieres verificar en pantalla qué columnas leyó ---
# st.write("Columnas detectadas:", df.columns.tolist())

# --- 1. FILTROS EN LA BARRA LATERAL ---
st.sidebar.header("Filtros de Datos")
if "departamento" in df.columns:
  departamentos = sorted(df["departamento"].dropna().unique())
  dep_elegido = st.sidebar.selectbox(
      "Departamento", ["Todos los departamentos"] + departamentos
  )

  if dep_elegido != "Todos los departamentos":
    df_f = df[df["departamento"] == dep_elegido]
  else:
    df_f = df
else:
  df_f = df

# --- 2. CÁLCULO DE KPIs PRINCIPALES ---
val_total = (
    df_f["valor_del_contrato"].sum()
    if "valor_del_contrato" in df_f.columns
    else 0
)
cant_contratos = (
    df_f["id_contrato"].nunique()
    if "id_contrato" in df_f.columns
    else len(df_f)
)
costo_promedio = val_total / cant_contratos if cant_contratos > 0 else 0

# Cálculo del Índice HHI (Concentración de mercado por Entidad)
if (
    "nombre_entidad" in df_f.columns
    and "valor_del_contrato" in df_f.columns
    and val_total > 0
):
  market_share = (
      df_f.groupby("nombre_entidad")["valor_del_contrato"].sum() / val_total
  ) * 100
  hhi_index = (market_share**2).sum()
else:
  hhi_index = 0

# --- MOSTRAR TARJETAS DE KPIs ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Valor Total Contratado", f"${val_total:,.2f}")
c2.metric("Total de Contratos", f"{cant_contratos:,}")
c3.metric("Costo Promedio / Contrato", f"${costo_promedio:,.2f}")
c4.metric(
    "Índice HHI (Concentración)",
    f"{hhi_index:,.1f}",
    help="Mide la concentración de presupuesto entre entidades.",
)

st.divider()

# --- 3. TABLAS DE RESUMEN Y AGREGACIONES ---
st.subheader("📋 Tablas de Resultados y Agregaciones")

# Tabla 1: Resumen por Entidad
if "nombre_entidad" in df_f.columns:
  st.markdown("### Top Entidades con Mayor Asignación Presupuestal")
  tabla_entidades = (
      df_f.groupby("nombre_entidad")
      .agg(
          total_contratos=("id_contrato", "count"),
          valor_acumulado=("valor_del_contrato", "sum"),
      )
      .reset_index()
  )
  tabla_entidades = tabla_entidades.sort_values(
      by="valor_acumulado", ascending=False
  ).head(10)
  tabla_entidades["valor_acumulado"] = tabla_entidades[
      "valor_acumulado"
  ].apply(lambda x: f"${x:,.2f}")
  st.dataframe(tabla_entidades, use_container_width=True)

# Tabla 2: Resumen por Tipo de Contrato
if "tipo_de_contrato" in df_f.columns:
  st.markdown("### Distribución por Tipo de Contrato")
  tabla_modalidad = (
      df_f.groupby("tipo_de_contrato")
      .agg(
          cantidad=("id_contrato", "count"),
          valor_total=("valor_del_contrato", "sum"),
      )
      .reset_index()
  )
  tabla_modalidad = tabla_modalidad.sort_values(
      by="valor_total", ascending=False
  )
  tabla_modalidad["valor_total"] = tabla_modalidad["valor_total"].apply(
      lambda x: f"${x:,.2f}"
  )
  st.dataframe(tabla_modalidad, use_container_width=True)
