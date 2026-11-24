# analisis/eda.py
# Genera los 6 graficos exploratorios en la carpeta graficos/ a partir de contratos_publicar.csv
# Ejecutar desde la carpeta principal: python analisis\eda.py

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = (
    RAIZ / "contratos_publicar.csv"
    if (RAIZ / "contratos_publicar.csv").exists()
    else RAIZ / "secop_andina_base.csv"
)
SALIDA_DIR = RAIZ / "graficos"
SALIDA_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")

df = pd.read_csv(ENTRADA, encoding="utf-8-sig", low_memory=False)
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

df["valor_millones"] = (
    pd.to_numeric(df.get("valor_del_contrato", 0.0), errors="coerce").fillna(0.0) / 1e6
)

if "saldo_pendiente" in df.columns:
    saldo_serie = pd.to_numeric(df["saldo_pendiente"], errors="coerce").fillna(0.0)
else:
    estado = df.get("estado_contrato", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    valor_raw = pd.to_numeric(df.get("valor_del_contrato", 0.0), errors="coerce").fillna(0.0)
    saldo_serie = np.where(estado.str.contains("cerrado|terminado|liquidado"), 0.0, valor_raw * 0.20)

df["saldo_millones"] = pd.Series(saldo_serie, index=df.index).clip(lower=0.0) / 1e6

if "categoria" not in df.columns:
    df["categoria"] = (
        df["tipo_de_contrato"].fillna("General").astype(str)
        if "tipo_de_contrato" in df.columns
        else "General"
    )
else:
    df["categoria"] = df["categoria"].fillna("General").astype(str)

if "nivel_alerta" not in df.columns:
    df["nivel_alerta"] = "Sin alerta"
else:
    df["nivel_alerta"] = df["nivel_alerta"].fillna("Sin alerta").astype(str)

if "departamento" not in df.columns:
    df["departamento"] = "Sin departamento"
else:
    df["departamento"] = df["departamento"].fillna("Sin departamento").astype(str)

df["anio_firma"] = pd.to_datetime(df.get("fecha_de_firma"), errors="coerce").dt.year


def guardar(nombre):
    plt.tight_layout()
    plt.savefig(SALIDA_DIR / f"{nombre}.png", dpi=150)
    plt.close()


# 1. Histograma valor del contrato
plt.figure(figsize=(8, 5))
valores_pos = df[df["valor_millones"] > 0]["valor_millones"]
if not valores_pos.empty:
    sns.histplot(valores_pos, bins=40, log_scale=True)
plt.title("1. Distribucion del valor de los contratos (escala logaritmica)")
plt.xlabel("Valor del contrato (millones COP)")
plt.ylabel("Cantidad de contratos")
guardar("01_histograma_valor")

# 2. Boxplot por categoria
plt.figure(figsize=(9, 5))
box_df = df[df["valor_millones"] > 0]
if not box_df.empty:
    sns.boxplot(data=box_df, x="categoria", y="valor_millones")
    plt.yscale("log")
    plt.xticks(rotation=20, ha="right")
plt.title("2. Valor del contrato por categoria (Contratacion Andina)")
plt.xlabel("Categoria")
plt.ylabel("Valor (millones COP, escala log)")
guardar("02_boxplot_categoria")

# 3. Top 10 departamentos por cantidad de contratos
plt.figure(figsize=(9, 5))
orden = df["departamento"].value_counts().head(10).index
sns.countplot(data=df, y="departamento", order=orden)
plt.title("3. Top 10 departamentos por cantidad de contratos")
plt.xlabel("Cantidad de contratos")
plt.ylabel("Departamento")
guardar("03_barras_departamentos")

# 4. Heatmap categoria vs nivel de alerta
plt.figure(figsize=(8, 5))
tabla = pd.crosstab(df["categoria"], df["nivel_alerta"])
cols_alerta = [c for c in ["Alta", "Media", "Baja", "Sin alerta"] if c in tabla.columns]
if cols_alerta:
    tabla = tabla[cols_alerta]
sns.heatmap(tabla, annot=True, fmt="d", cmap="YlOrRd")
plt.title("4. Contratos por categoria y nivel de alerta")
plt.xlabel("Nivel de alerta")
plt.ylabel("Categoria")
guardar("04_heatmap_categoria_alerta")

# 5. Dispersion valor vs saldo pendiente
plt.figure(figsize=(8, 6))
con_saldo = df[(df["valor_millones"] > 0) & (df["saldo_millones"] > 0)]
if not con_saldo.empty:
    muestra = con_saldo.sample(min(len(con_saldo), 15000), random_state=42)
    sns.scatterplot(data=muestra, x="valor_millones", y="saldo_millones", hue="categoria", alpha=0.6)
    plt.xscale("log")
    plt.yscale("log")
plt.title("5. Valor del contrato vs saldo pendiente")
plt.xlabel("Valor (millones COP, escala log)")
plt.ylabel("Saldo pendiente (millones COP, escala log)")
guardar("05_dispersion_valor_saldo")

# 6. Contratos firmados por anio
plt.figure(figsize=(8, 5))
por_anio = df.dropna(subset=["anio_firma"]).groupby("anio_firma").size().reset_index(name="contratos")
if not por_anio.empty:
    sns.lineplot(data=por_anio, x="anio_firma", y="contratos", marker="o")
plt.title("6. Contratos firmados por anio")
plt.xlabel("Anio de firma")
plt.ylabel("Cantidad de contratos")
guardar("06_linea_contratos_por_anio")

print(f"Listo: 6 graficos guardados en {SALIDA_DIR} desde {ENTRADA.name}")