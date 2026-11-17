import pandas as pd
import streamlit as st

st.title("Tablero de KPIs Estratégicos - Contratos")
st.markdown(
    "Indicadores clave de rendimiento basados en los datos del sistema."
)


@st.cache_data
def cargar_datos_externos():
  url_csv = "https://drive.google.com/uc?export=download&id=1tHzoqaE4xOcr64ZCUTnoChm2owPbqzCH"
  df = pd.read_csv(url_csv, low_memory=False)
  # Convertir la fecha a formato datetime por si se usa en gráficos temporales
  df["fecha_de_firma"] = pd.to_datetime(df["fecha_de_firma"], errors="coerce")
  return df


df = cargar_datos_externos()

# --- FILTROS EN LA BARRA LATERAL (Opcionales para dinamizar los KPIs) ---
st.sidebar.header("Filtros del Tablero")
departamentos_disponibles = sorted(df["departamento"].unique())
dep_seleccionado = st.sidebar.selectbox(
  "Filtrar por Departamento", ["Todos"] + departamentos_disponibles
)

# Aplicar filtro
if dep_seleccionado != "Todos":
  df_filtrado = df[df["departamento"] == dep_seleccionado]
else:
  df_filtrado = df

# --- CÁLCULO DE MÉTRICAS (KPIs) CON LOS DATOS REALES ---
valor_total = df_filtrado["valor_del_contrato"].sum()
total_contratos = df_filtrado["id_contrato"].nunique()
total_entidades = df_filtrado["nombre_entidad"].nunique()

# Cálculo del Índice HHI (Concentración de mercado por Entidad)
market_share = (
    df_filtrado.groupby("nombre_entidad")["valor_del_contrato"].sum()
    / valor_total
) * 100
hhi = (market_share**2).sum()

# --- DISEÑO DE TARJETAS DE MÉTRICAS EN COLUMNAS ---
col1, col2, col3, col4 = st.columns(4)

with col1:
  st.metric(label="Valor Total Contratado", value=f"${valor_total:,.2f}")

with col2:
  st.metric(label="Total de Contratos", value=f"{total_contratos:,}")

with col3:
  st.metric(label="Entidades Activas", value=f"{total_entidades:,}")

with col4:
  st.metric(
      label="Índice HHI (Concentración)",
      value=f"{hhi:,.1f}",
      help=(
          "Mide la concentración de los contratos entre las entidades/proveedores"
          " (Valores altos indican mayor concentración)."
      ),
  )

st.divider()

# --- ESPACIO PARA GRÁFICOS VISUALES ---
st.subheader("Evolución Temporal de Contratos")

if "fecha_de_firma" in df_filtrado.columns:
  # Agrupar por mes para la tendencia temporal
  df_temporal = (
      df_filtrado.dropna(subset=["fecha_de_firma"])
      .set_index("fecha_de_firma")
      .resample("ME")["valor_del_contrato"]
      .sum()
  )
  st.line_chart(df_temporal)
else:
  st.info("No se encontró la columna de fecha para graficar la tendencia.")

# Gráfico adicional: Top entidades con mayor presupuesto contratado
st.subheader("Top 5 Entidades con Mayor Contratación")
top_entidades = (
    df_filtrado.groupby("nombre_entidad")["valor_del_contrato"]
    .sum()
    .nlargest(5)
)
st.bar_chart(top_entidades)
