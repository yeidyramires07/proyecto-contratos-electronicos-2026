# calcular_metricas.py
# Calcula metricas de concentracion (HHI, CR4) y riesgo por departamento a partir de secop_andina_base.csv
# Ejecutar desde la carpeta principal: python calcular_metricas.py

from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "secop_andina_base.csv" if (RAIZ / "secop_andina_base.csv").exists() else RAIZ / "secop2_2020_2025.csv"
SALIDA = RAIZ / "metricas_andina.csv"

df = pd.read_csv(ENTRADA, encoding="utf-8-sig", low_memory=False)

df["departamento"] = df.get("departamento", "Sin departamento").fillna("Sin departamento").astype(str).str.strip()
df["proveedor_adjudicado"] = df.get("proveedor_adjudicado", "Sin proveedor").fillna("Sin proveedor").astype(str).str.strip().str.upper()
df["modalidad_de_contratacion"] = df.get("modalidad_de_contratacion", "").fillna("").astype(str).str.strip().str.lower()
df["estado_contrato"] = df.get("estado_contrato", "").fillna("").astype(str).str.strip().str.lower()
df["valor_del_contrato"] = pd.to_numeric(df.get("valor_del_contrato", 0), errors="coerce").fillna(0.0)
df = df[df["valor_del_contrato"] > 0].copy()

filas = []
for depto, g in df.groupby("departamento"):
    total_val = float(g["valor_del_contrato"].sum())
    if total_val <= 0:
        continue
    por_prov = g.groupby("proveedor_adjudicado")["valor_del_contrato"].sum().sort_values(ascending=False)
    shares_pct = (por_prov / total_val) * 100.0
    hhi = float((shares_pct ** 2).sum())
    cr4 = float(shares_pct.head(4).sum())

    pct_contratacion_directa = float(g["modalidad_de_contratacion"].str.contains("directa", na=False).mean() * 100.0)
    pct_modificados = float((g["estado_contrato"] == "modificado").mean() * 100.0)

    score_hhi = min((hhi / 1000.0) * 40.0, 40.0)
    score_dir = min((pct_contratacion_directa / 100.0) * 40.0, 40.0)
    score_mod = min((pct_modificados / 30.0) * 20.0, 20.0)
    riesgo_score = round(score_hhi + score_dir + score_mod, 2)

    if riesgo_score >= 55:
        alerta = "Alta"
    elif riesgo_score >= 42:
        alerta = "Media"
    elif riesgo_score >= 30:
        alerta = "Baja"
    else:
        alerta = "Sin alerta"

    filas.append({
        "departamento": depto,
        "entidad": f"Consolidado {depto}",
        "sector": "Región Andina",
        "contratos": int(len(g)),
        "valor_total_cop": round(total_val, 2),
        "hhi_valor": round(hhi, 2),
        "cr4_valor": round(cr4, 2),
        "pct_contratacion_directa": round(pct_contratacion_directa, 2),
        "pct_modificados": round(pct_modificados, 2),
        "riesgo_score": riesgo_score,
        "nivel_alerta": alerta,
    })

out = pd.DataFrame(filas).sort_values("riesgo_score", ascending=False)
out.to_csv(SALIDA, index=False, encoding="utf-8-sig")
print(f"Generado {SALIDA.name} desde {ENTRADA.name} ({len(out)} departamentos):")
print(out.to_string(index=False))