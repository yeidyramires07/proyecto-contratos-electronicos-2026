# spark_resumen.py
# Computacion Distribuida: resumen por departamento en Apache Spark con 1, 2 y 4 nucleos.
# Se ejecuta desde la carpeta principal:  python procesamiento\spark_resumen.py

from pathlib import Path
import time
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
ARCHIVO_ENTRADA = RAIZ_PROYECTO / "secop2_2020_2025.csv"
SALIDA_RENDIMIENTO = RAIZ_PROYECTO / "rendimiento_spark.csv"

# Pon en False para contar TODOS los contratos de la Region Andina (recomendado para ver volumen real y Bogota).
# Pon en True solo si quieres filtrar por palabras clave de medicamentos/insumos medicos.
SOLO_MEDICAMENTOS = False

DEPARTAMENTOS_ANDINA = [
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
]

PALABRAS_SI = [
    "medicamento", "medicamentos", "farmaceutic", "farmacéutic",
    "insumo medico", "insumo médico", "insumos medicos", "insumos médicos",
    "dispositivo medico", "dispositivo médico", "dispositivos medicos", "dispositivos médicos",
    "vacuna", "vacunas", "biologico", "biológico", "biologicos", "biológicos",
    "reactivo", "reactivos", "material quirurgico", "material quirúrgico",
    "oncologic", "oncológic", "antirretroviral", "hemoderivado",
]

PALABRAS_NO = [
    "aseo", "limpieza", "cafeteria", "cafetería", "vigilancia",
    "transporte", "combustible", "software", "licencia", "publicidad",
]


def crear_sesion(nucleos):
    spark = (
        SparkSession.builder
        .appName("ResumenAndinaSECOP")
        .master(f"local[{nucleos}]")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.extraJavaOptions", "-Dlog4j.rootCategory=ERROR,console")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def preparar_df(spark):
    df = (
        spark.read
        .option("header", "true")
        .option("inferSchema", "false")
        .option("multiLine", "true")
        .option("escape", '"')
        .csv(str(ARCHIVO_ENTRADA))
    )

    total_cargado = df.count()

    # Normalizacion segura de departamento y objeto
    df_limpio = (
        df
        .withColumn(
            "depto_norm",
            F.lower(F.trim(F.coalesce(F.col("departamento"), F.lit(""))))
        )
        .withColumn(
            "depto_canonico",
            F.when(
                F.col("depto_norm").isin(
                    "bogota", "bogotá", "bogota d.c.", "bogotá d.c.",
                    "distrito capital de bogota", "distrito capital de bogotá"
                ),
                F.lit("Distrito Capital de Bogotá")
            ).otherwise(F.trim(F.coalesce(F.col("departamento"), F.lit("Sin departamento"))))
        )
        .withColumn(
            "objeto_norm",
            F.lower(F.coalesce(F.col("objeto_del_contrato"), F.lit("")))
        )
    )

    # Filtro Region Andina (incluyendo Distrito Capital de Bogota)
    df_andina = df_limpio.filter(F.col("depto_norm").isin(DEPARTAMENTOS_ANDINA))

    if SOLO_MEDICAMENTOS:
        cond_si = F.lit(False)
        for p in PALABRAS_SI:
            cond_si = cond_si | F.col("objeto_norm").contains(p.lower())

        cond_no = F.lit(False)
        for p in PALABRAS_NO:
            cond_no = cond_no | F.col("objeto_norm").contains(p.lower())

        df_andina = df_andina.filter(cond_si & (~cond_no))

    return df_limpio, df_andina, total_cargado


def ejecutar_prueba(nucleos):
    spark = crear_sesion(nucleos)
    try:
        inicio = time.time()
        df_todos, df_andina, total_cargado = preparar_df(spark)
        resumen = (
            df_andina.groupBy("depto_canonico")
            .agg(F.count("*").alias("contratos"))
            .orderBy(F.desc("contratos"))
            .collect()
        )
        total_andina = sum(r["contratos"] for r in resumen)
        duracion = time.time() - inicio
        return duracion, total_cargado, total_andina, resumen
    finally:
        spark.stop()


if __name__ == "__main__":
    print(f"Archivo de entrada: {ARCHIVO_ENTRADA}")
    print(f"Modo SOLO_MEDICAMENTOS: {SOLO_MEDICAMENTOS}")

    tiempos = {}
    ultimo_resumen = []
    total_cargado_final = 0
    total_andina_final = 0

    for nucleos in [1, 2, 4]:
        t, tot_c, tot_a, res = ejecutar_prueba(nucleos)
        tiempos[nucleos] = t
        total_cargado_final = tot_c
        total_andina_final = tot_a
        ultimo_resumen = res
        print(f"Con {nucleos} nucleo(s): {t:.2f} segundos | leidos: {tot_c:,} | contratos Andina: {tot_a:,}")

    t1 = tiempos[1]
    filas_csv = []
    for nucleos in [1, 2, 4]:
        tn = tiempos[nucleos]
        speedup = t1 / tn if tn > 0 else 1.0
        eficiencia = speedup / nucleos
        if nucleos > 1:
            print(f"Con {nucleos} nucleos: speedup {speedup:.2f} | eficiencia {eficiencia:.2f}")
        filas_csv.append({
            "nucleos": nucleos,
            "tiempo_segundos": round(tn, 2),
            "total_leidos": total_cargado_final,
            "contratos_andina": total_andina_final,
            "speedup": round(speedup, 2),
            "eficiencia": round(eficiencia, 2),
        })

    pd.DataFrame(filas_csv).to_csv(SALIDA_RENDIMIENTO, index=False)
    print(f"Total contratos cargados: {total_cargado_final:,} | Guardados/Contados Andina: {total_andina_final:,}")

    # Diagnostico de departamentos distintos presentes en el CSV para verificar nombres exactos
    spark_diag = crear_sesion(1)
    try:
        deptos_en_csv = (
            spark_diag.read.option("header", "true").option("multiLine", "true").option("escape", '"')
            .csv(str(ARCHIVO_ENTRADA))
            .groupBy("departamento")
            .count()
            .orderBy(F.desc("count"))
            .toPandas()
        )
        print("\nConteo por departamento en TODO el CSV (sin filtrar):")
        print(deptos_en_csv.to_string(index=False))
    finally:
        spark_diag.stop()

    print("\nDepartamentos andinos con mas contratos (segun filtro actual):")
    for fila in ultimo_resumen[:12]:
        print(f"  {fila['depto_canonico']}: {fila['contratos']:,}")