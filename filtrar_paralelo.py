# filtrar_paralelo.py
# Computacion Paralela: aqui se usa multiprocessing sobre todo el dataset.
# Se ejecuta desde la carpeta principal:  python procesamiento\filtrar_paralelo.py

from pathlib import Path
import time
from multiprocessing import Pool
import pandas as pd
from reglas import categoria_del_contrato, es_de_medicamentos

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
ARCHIVO_ENTRADA = RAIZ_PROYECTO / "secop2_2020_2025.csv"
SALIDA_RENDIMIENTO = RAIZ_PROYECTO / "rendimiento_multiprocessing.csv"
SALIDA_CONTRATOS = RAIZ_PROYECTO / "contratos_medicamentos.csv"

# Si quieres conservar TODOS los contratos de la Region Andina sin filtrar solo medicamentos,
# deja SOLO_MEDICAMENTOS = False. Pon True solo si quieres filtrar por reglas de medicamentos.
SOLO_MEDICAMENTOS = False

# Si quieres conservar todos los valores positivos sin tope superior, deja TOPE_VALOR_MAX = None.
TOPE_VALOR_MAX = None

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


def normalizar_depto(valor):
    texto = str(valor or "").strip()
    clave = texto.lower()
    if clave in {
        "bogota",
        "bogotá",
        "bogota d.c.",
        "bogotá d.c.",
        "distrito capital de bogota",
        "distrito capital de bogotá",
    }:
        return "Distrito Capital de Bogotá"
    return texto if texto else "Sin departamento"


def evaluar_lote(textos):
    es_med = []
    cats = []
    for texto in textos:
        es_med.append(es_de_medicamentos(texto))
        cats.append(categoria_del_contrato(texto))
    return es_med, cats


def partir_en_pedazos(lista, cantidad):
    if not lista:
        return []
    tamano = (len(lista) + cantidad - 1) // cantidad
    return [lista[i:i + tamano] for i in range(0, len(lista), tamano)]


if __name__ == "__main__":
    t0 = time.time()
    datos = pd.read_csv(ARCHIVO_ENTRADA, encoding="utf-8-sig", low_memory=False)
    total_csv = len(datos)
    print(f"CSV cargado en {time.time() - t0:.2f} s | Total de filas leidas del CSV: {total_csv:,}")

    # Analizamos TODOS los contratos leidos del CSV sin recortar antes de medir
    textos = datos["objeto_del_contrato"].fillna("").astype(str).tolist()
    print(f"Total de contratos enviados a medicion (serie y paralelo): {len(textos):,}")

    # 1) En serie (1 proceso) sobre el 100% del dataset leido
    inicio = time.time()
    marcas_serie, cats_serie = evaluar_lote(textos)
    tiempo_serie = time.time() - inicio
    print(f"En serie (1 proceso) - {len(textos):,} contratos analizados: {tiempo_serie:.2f} segundos")

    mediciones = [{
        "procesos": 1,
        "contratos_analizados": len(textos),
        "tiempo_segundos": round(tiempo_serie, 2),
        "speedup": 1.0,
        "eficiencia": 1.0,
    }]

    # 2) En paralelo (2 y 4 procesos) sobre el 100% del dataset leido
    marcas_paralelo = marcas_serie
    cats_paralelo = cats_serie

    for procesos in [2, 4]:
        pedazos = partir_en_pedazos(textos, procesos)
        total_pedazos = sum(len(p) for p in pedazos)
        inicio = time.time()
        with Pool(processes=procesos) as grupo:
            respuestas = grupo.map(evaluar_lote, pedazos)
        tiempo = time.time() - inicio

        marcas_p = []
        cats_p = []
        for m_part, c_part in respuestas:
            marcas_p.extend(m_part)
            cats_p.extend(c_part)

        marcas_paralelo = marcas_p
        cats_paralelo = cats_p

        speedup = tiempo_serie / tiempo if tiempo > 0 else 1.0
        eficiencia = speedup / procesos
        print(
            f"Con {procesos} procesos - {total_pedazos:,} contratos analizados: "
            f"{tiempo:.2f} segundos | speedup {speedup:.2f} | eficiencia {eficiencia:.2f}"
        )
        mediciones.append({
            "procesos": procesos,
            "contratos_analizados": total_pedazos,
            "tiempo_segundos": round(tiempo, 2),
            "speedup": round(speedup, 2),
            "eficiencia": round(eficiencia, 2),
        })

    print("Resultados iguales entre serie y paralelo:", marcas_serie == marcas_paralelo)
    pd.DataFrame(mediciones).to_csv(SALIDA_RENDIMIENTO, index=False)

    # 3) Asignamos resultados a TODOS los contratos leidos y aplicamos filtros seleccionados
    df = datos.copy()
    df["es_medicamento_regla"] = marcas_paralelo
    df["categoria"] = cats_paralelo

    if "departamento" in df.columns:
        dept_limpio = df["departamento"].fillna("").astype(str).str.strip().str.lower()
        df = df[dept_limpio.isin(DEPARTAMENTOS_ANDINA)].copy()
        df["departamento"] = df["departamento"].map(normalizar_depto)

    if SOLO_MEDICAMENTOS:
        df = df[df["es_medicamento_regla"] == True].copy()

    if "valor_del_contrato" in df.columns:
        valores = pd.to_numeric(df["valor_del_contrato"], errors="coerce")
        if TOPE_VALOR_MAX is not None:
            df = df[(valores > 0) & (valores < TOPE_VALOR_MAX)].copy()
        else:
            df = df[valores > 0].copy()

    df.to_csv(SALIDA_CONTRATOS, index=False, encoding="utf-8-sig")

    print(
        f"Resumen final -> Leidos del CSV: {total_csv:,} | "
        f"Analizados en paralelo: {len(textos):,} | Guardados: {len(df):,}"
    )
    if "departamento" in df.columns and len(df) > 0:
        print("\nConteo por departamento en el archivo guardado:")
        print(df["departamento"].value_counts().to_string())