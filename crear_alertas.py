# crear_alertas.py
# Genera contratos_alertas.csv y contratos_publicar.csv a partir de secop_andina_base.csv
# Ejecutar desde la carpeta principal: python crear_alertas.py

from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "secop_andina_base.csv"
SALIDA_ALERTAS = RAIZ / "contratos_alertas.csv"
SALIDA_PUBLICAR = RAIZ / "contratos_publicar.csv"

try:
    from procesamiento.reglas import categoria_del_contrato
except Exception:
    try:
        from reglas import categoria_del_contrato
    except Exception:
        categoria_del_contrato = None

df = pd.read_csv(ENTRADA, encoding="utf-8-sig", low_memory=False)
print(f"Leidos de {ENTRADA.name}: {len(df):,}")

if "id_contrato" not in df.columns:
    df["id_contrato"] = [f"CTR_{i + 1}" for i in range(len(df))]

df["valor_del_contrato"] = pd.to_numeric(df.get("valor_del_contrato", 0), errors="coerce").fillna(0.0).clip(lower=0.0)

if "valor_pendiente_de_pago" in df.columns:
    saldo = pd.to_numeric(df["valor_pendiente_de_pago"], errors="coerce").fillna(0.0)
elif "saldo_pendiente" in df.columns:
    saldo = pd.to_numeric(df["saldo_pendiente"], errors="coerce").fillna(0.0)
else:
    estado = df.get("estado_contrato", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    saldo = np.where(
        estado.str.contains("cerrado|terminado|liquidado"),
        0.0,
        np.where(estado.str.contains("ejecucion|ejecución|modificado"), df["valor_del_contrato"] * 0.35, df["valor_del_contrato"] * 0.20),
    )

df["saldo_pendiente"] = np.clip(saldo, 0.0, None)
df["valor_facturado"] = (df["valor_del_contrato"] - df["saldo_pendiente"]).clip(lower=0.0)

pct_saldo = np.where(df["valor_del_contrato"] > 0, df["saldo_pendiente"] / df["valor_del_contrato"], 0.0)
df["nivel_alerta"] = np.where(
    (df["saldo_pendiente"] >= 500_000_000) | (pct_saldo >= 0.75),
    "Alta",
    np.where((df["saldo_pendiente"] >= 100_000_000) | (pct_saldo >= 0.35), "Media", "Baja"),
)

if "categoria" not in df.columns:
    if categoria_del_contrato is not None and "objeto_del_contrato" in df.columns:
        df["categoria"] = df["objeto_del_contrato"].fillna("").astype(str).map(categoria_del_contrato)
    elif "tipo_de_contrato" in df.columns:
        df["categoria"] = df["tipo_de_contrato"].fillna("General").astype(str)
    else:
        df["categoria"] = "General"

df.to_csv(SALIDA_ALERTAS, index=False, encoding="utf-8-sig")
df.to_csv(SALIDA_PUBLICAR, index=False, encoding="utf-8-sig")

print(f"Guardados {len(df):,} registros en {SALIDA_ALERTAS.name} y {SALIDA_PUBLICAR.name}")
print("Distribucion nivel_alerta:")
print(df["nivel_alerta"].value_counts().to_string())