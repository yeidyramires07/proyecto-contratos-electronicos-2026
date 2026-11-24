# preparar_base_andina.py
# Ejecutar desde la carpeta principal: python preparar_base_andina.py

from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "secop2_2020_2025.csv"
SALIDA = RAIZ / "secop_andina_base.csv"

DEPARTAMENTOS_ANDINA = {
    "antioquia",
    "boyaca",
    "boyacá",
    "caldas",
    "caqueta",
    "caquetá",
    "cauca",
    "cesar",
    "huila",
    "norte de santander",
    "quindio",
    "quindío",
    "risaralda",
    "santander",
    "tolima",
    "bogota",
    "bogotá",
    "bogota d.c.",
    "bogotá d.c.",
    "distrito capital de bogota",
    "distrito capital de bogotá",
}


def canonizar_depto(val):
    texto = str(val or "").strip()
    baja = texto.lower()
    if baja in {
        "bogota",
        "bogotá",
        "bogota d.c.",
        "bogotá d.c.",
        "distrito capital de bogota",
        "distrito capital de bogotá",
    }:
        return "Distrito Capital de Bogotá"
    return texto if texto else "Sin departamento"


df = pd.read_csv(ENTRADA, encoding="utf-8-sig", low_memory=False)
total_inicial = len(df)

if "departamento" in df.columns:
    mascara = df["departamento"].fillna("").astype(str).str.strip().str.lower().isin(DEPARTAMENTOS_ANDINA)
    df = df[mascara].copy()
    df["departamento"] = df["departamento"].map(canonizar_depto)

if "valor_del_contrato" in df.columns:
    df["valor_del_contrato"] = pd.to_numeric(df["valor_del_contrato"], errors="coerce").fillna(0.0)
    df = df[df["valor_del_contrato"] > 0].copy()

df.to_csv(SALIDA, index=False, encoding="utf-8-sig")
print(f"Leidas: {total_inicial:,} | Guardadas en {SALIDA.name}: {len(df):,}")
if "departamento" in df.columns:
    print(df["departamento"].value_counts().to_string())