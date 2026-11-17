import pandas as pd
import streamlit as st


@st.cache_data
def cargar_datos_externos():
  # URL o ruta de tu dataset
  url_csv = "https://drive.google.com/uc?export=download&id=1tHzoqaE4xOcr64ZCUTnoChm2owPbqzCH"
  df = pd.read_csv(url_csv, low_memory=False)

  # Buscar automáticamente una columna de fecha si tiene otro nombre
  col_fecha = None
  for col in df.columns:
    if "fecha" in col.lower() and "firma" in col.lower():
      col_fecha = col
      break

  if col_fecha:
    df["fecha_de_firma"] = pd.to_datetime(df[col_fecha], errors="coerce")
  else:
    df["fecha_de_firma"] = pd.NaT  # Si no existe ninguna fecha, evita el error

  return df


with st.spinner("Cargando datos del sistema..."):
  df = cargar_datos_externos()

st.title("Tablero de KPIs Estratégicos - Contratos")
st.markdown("Indicadores clave de rendimiento basados en los contratos.")

# --- FILTROS ---
st.sidebar.header("Filtros del Tablero")
if "departamento" in df.columns:
  departamentos_disponibles = sorted(df["departamento"].dropna().unique())
  dep_seleccionado = st.sidebar.selectbox(
      "Filtrar por Departamento", ["Todos"] + departamentos_disponibles
  )
  if dep_seleccionado != "Todos":
    df_filtrado = df[df["departamento"] == dep_seleccionado]
  else:
    df_filtrado = df
else:
  df_filtrado = df

# --- CÁLCULO DE KPIs ---
valor_total = (
    df_filtrado["valor_del_contrato"].sum()
    if "valor_del_contrato" in df_filtrado.columns
    else 0
)
total_contratos = (
    df_filtrado["id_contrato"].nunique()
    if "id_contrato" in df_filtrado.columns
    else len(df_filtrado)
)
total_entidades = (
    df_filtrado["nombre_entidad"].nunique()
    if "nombre_entidad" in df_filtrado.columns
    else 0
)

col1, col2, col3 = st.columns(3)
with col1:
  st.metric(label="Valor Total Contratado", value=f"${valor_total:,.2f}")
with col2:
  st.metric(label="Total de Contratos", value=f"{total_contratos:,}")
with col3:
  st.metric(label="Entidades Activas", value=f"{total_entidades:,}")

st.divider()

# --- GRÁFICOS ---
st.subheader("Evolución Temporal de Contratos")
if (
    "fecha_de_firma" in df_filtrado.columns
    and not df_filtrado["fecha_de_firma"].isna().all()
):
  df_temporal = (
      df_filtrado.dropna(subset=["fecha_de_firma"])
      .set_index("fecha_de_firma")
      .resample("ME")["valor_del_contrato"]
      .sum()
  )
  st.line_chart(df_temporal)
else:
  st.info(
      "No se encontró una columna de fecha válida para mostrar la tendencia"
      " temporal."
  )

st.subheader("Top 5 Entidades con Mayor Contratación")
if (
    "nombre_entidad" in df_filtrado.columns
    and "valor_del_contrato" in df_filtrado.columns
):
  top_entidades = (
      df_filtrado.groupby("nombre_entidad")["valor_del_contrato"]
      .sum()
      .nlargest(5)
  )
  st.bar_chart(top_entidades)
