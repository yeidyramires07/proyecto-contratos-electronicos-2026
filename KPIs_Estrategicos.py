# -*- coding: utf-8 -*-
"""Página Streamlit unificada: KPI estratégicos + 13 KPI y 7 métricas por entidad.

Ubicar en: proyecto/pages/KPIs_Estrategicos.py
El app.py principal NO necesita importar este archivo.
"""
from pathlib import Path
import csv
import gzip
import os
import re
import tempfile
import unicodedata
import zlib

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="KPIs Estratégicos · Región Andina", layout="wide")
RAIZ = Path(__file__).resolve().parent.parent  # pages/ -> raíz del proyecto


@st.cache_data(ttl=600, show_spinner=False)
def cargar_fuente_kpis():
    """Conserva la lógica del dashboard estratégico original (CSV de la raíz)."""
    candidatos = [
        "metricas_andina.csv", "contratos_publicar.csv", "secop_andina_base.csv",
        "secop2_2020_2025.csv",
    ]
    for nombre in candidatos:
        ruta = RAIZ / nombre
        if ruta.is_file():
            df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
            df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
            return df, nombre
    raise FileNotFoundError(
        "No se encontró un CSV estratégico en la raíz del proyecto. "
        "Esta pestaña utiliza metricas_andina.csv, contratos_publicar.csv, "
        "secop_andina_base.csv o secop2_2020_2025.csv. "
        "El análisis por entidad sí funciona independientemente desde GitHub Releases."
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
    except (TypeError, ValueError):
        return "$0"


CAMPOS_SECOP_LECTURA = frozenset({
    "nombre_entidad", "entidad", "nombre_de_la_entidad", "nombre_entidad_norm", "entidad_norm",
    "proveedor_adjudicado", "proveedor", "nombre_proveedor", "proveedor_adjudicado_norm",
    "valor_del_contrato", "valor_contrato", "valor_contrato_pesos", "valor",
    "id_contrato", "id_del_contrato", "codigo_contrato", "referencia_del_contrato",
    "fecha_de_firma", "fecha_firma", "fecha_de_firma_del_contrato",
    "fecha_de_inicio_del_contrato", "fecha_inicio", "fecha_inicio_del_contrato",
    "fecha_de_fin_del_contrato", "fecha_fin", "fecha_fin_del_contrato",
    "modalidad_de_contratacion", "modalidad_contratacion", "modalidad",
    "tipo_de_contrato", "tipo_contrato", "es_pyme", "pyme", "es_mipyme",
    "destino_gasto", "destino_del_gasto", "estado_contrato", "estado_del_contrato", "estado",
    "n_mero_de_documento_ordenador_del_gasto", "numero_de_documento_del_ordenador_del_gasto",
    "numero_documento_ordenador_del_gasto", "documento_ordenador_del_gasto",
})

COLUMNAS_PCA = [
    "hhi_valor", "hhi_n", "pct_valor_directa", "pct_valor_regimen_esp",
    "pct_contratos_ops", "pct_valor_pyme", "pct_valor_ene_feb_anual",
    "pct_valor_nov_dic_anual", "hhi_ordenador", "duracion_mediana_dias",
    "log_valor_total", "pct_valor_inversion", "tasa_contratos_modificados",
]

def _normalizar_nombre_columna(nombre):
    texto = unicodedata.normalize("NFKD", str(nombre))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto

def _normalizar_columnas_secop(df):
    out = df.copy()
    out.columns = [_normalizar_nombre_columna(c) for c in out.columns]
    # Alias frecuentes entre descargas SECOP y el notebook original.
    alias = {
        "nombre_entidad": ["entidad", "nombre_de_la_entidad", "nombre_entidad_norm"],
        "proveedor_adjudicado": ["proveedor", "nombre_proveedor", "proveedor_adjudicado_norm"],
        "valor_del_contrato": ["valor_contrato", "valor_contrato_pesos", "valor"],
        "id_contrato": ["id_del_contrato", "codigo_contrato", "referencia_del_contrato"],
        "fecha_de_firma": ["fecha_firma", "fecha_de_firma_del_contrato"],
        "fecha_de_inicio_del_contrato": ["fecha_inicio", "fecha_inicio_del_contrato"],
        "fecha_de_fin_del_contrato": ["fecha_fin", "fecha_fin_del_contrato"],
        "modalidad_de_contratacion": ["modalidad_contratacion", "modalidad"],
        "tipo_de_contrato": ["tipo_contrato"],
        "es_pyme": ["pyme", "es_mipyme"],
        "destino_gasto": ["destino_del_gasto"],
        "estado_contrato": ["estado_del_contrato", "estado"],
        "n_mero_de_documento_ordenador_del_gasto": [
            "numero_de_documento_del_ordenador_del_gasto",
            "numero_documento_ordenador_del_gasto",
            "documento_ordenador_del_gasto",
            "n_mero_de_documento_ordenador_del_gasto",
        ],
    }
    for destino, opciones in alias.items():
        if destino not in out.columns:
            for opcion in opciones:
                if opcion in out.columns:
                    out[destino] = out[opcion]
                    break
    # Los archivos preparados por el notebook ya pueden traer entidad_norm.
    if "nombre_entidad" not in out.columns and "entidad_norm" in out.columns:
        out["nombre_entidad"] = out["entidad_norm"]
    if "proveedor_adjudicado" not in out.columns and "proveedor_adjudicado_norm" in out.columns:
        out["proveedor_adjudicado"] = out["proveedor_adjudicado_norm"]
    return out

ENLACE_DATASET_KPI = "https://github.com/yeidyramires07/proyecto-contratos-electronicos-2026/releases/download/datos-kpi-v1/datos_region_andina.csv.gz"

NOMBRE_ARCHIVO_KPI = "datos_region_andina.csv.gz"

def _ruta_cache_kpi():
    carpeta = os.path.join(tempfile.gettempdir(), "secop_kpi_descargas")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, NOMBRE_ARCHIVO_KPI)

def _descargar_kpi_release(enlace, ruta):
    """Descarga por bloques y publica el archivo solo cuando termina correctamente."""
    temporal = ruta + ".part"
    try:
        with requests.get(enlace, stream=True, timeout=(30, 180)) as respuesta:
            respuesta.raise_for_status()
            longitud = respuesta.headers.get("Content-Length")
            with open(temporal, "wb") as archivo:
                for bloque in respuesta.iter_content(chunk_size=1024 * 1024):
                    if bloque:
                        archivo.write(bloque)

        if longitud and os.path.getsize(temporal) != int(longitud):
            raise ValueError("La descarga de GitHub Releases terminó incompleta.")
        with open(temporal, "rb") as archivo:
            if archivo.read(2) != b"\x1f\x8b":
                raise ValueError("El enlace no devolvió un GZIP; revisa la URL del Release.")
        os.replace(temporal, ruta)
    except Exception:
        if os.path.isfile(temporal):
            os.remove(temporal)
        raise

def _leer_kpi_gzip(ruta):
    """Detecta el separador del CSV y utiliza el lector rápido de pandas."""
    with gzip.open(ruta, "rb") as archivo:
        encabezado = archivo.readline().decode("utf-8-sig", errors="replace")
    try:
        separador = csv.Sniffer().sniff(encabezado, delimiters=",;\t|").delimiter
    except csv.Error:
        separador = max((",", ";", "\t", "|"), key=encabezado.count)

    ultimo_error = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            datos = pd.read_csv(
                ruta,
                compression="gzip",
                sep=separador,
                encoding=codificacion,
                low_memory=False,
                usecols=lambda c: _normalizar_nombre_columna(c) in CAMPOS_SECOP_LECTURA,
            )
            if len(datos.columns) < 2:
                raise ValueError("El CSV comprimido no contiene varias columnas.")
            return _normalizar_columnas_secop(datos)
        except (UnicodeError, pd.errors.ParserError) as exc:
            ultimo_error = exc
    raise ValueError(f"No se pudo interpretar el CSV del Release: {ultimo_error}")

def cargar_dataset_kpi_release(enlace):
    """Carga datos SECOP II desde GitHub Releases, con caché local recuperable."""
    ruta = _ruta_cache_kpi()
    estaba_guardado = os.path.isfile(ruta)

    if not estaba_guardado:
        _descargar_kpi_release(enlace, ruta)

    try:
        return _leer_kpi_gzip(ruta)
    except (EOFError, OSError, zlib.error) as exc:
        # Un GZIP incompleto previo no debe bloquear permanentemente el módulo.
        if os.path.isfile(ruta):
            os.remove(ruta)
        if estaba_guardado:
            _descargar_kpi_release(enlace, ruta)
            try:
                return _leer_kpi_gzip(ruta)
            except (EOFError, OSError, zlib.error) as nuevo_error:
                if os.path.isfile(ruta):
                    os.remove(ruta)
                raise ValueError(f"GZIP dañado o incompleto: {nuevo_error}") from nuevo_error
        raise ValueError(f"GZIP dañado o incompleto: {exc}") from exc

def calcular_kpis_secop(datos):
    """Replica los 13 indicadores usados como variables de entrada del PCA."""
    df = _normalizar_columnas_secop(datos)
    requeridas = ["valor_del_contrato", "nombre_entidad", "proveedor_adjudicado"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError("Faltan columnas necesarias para calcular los KPI: " + ", ".join(faltantes))

    # Completar columnas opcionales: su ausencia se trata como dato no disponible,
    # no como una razón para detener todo el análisis.
    opcionales = [
        "id_contrato", "fecha_de_firma", "fecha_de_inicio_del_contrato",
        "fecha_de_fin_del_contrato", "modalidad_de_contratacion", "tipo_de_contrato",
        "es_pyme", "destino_gasto", "estado_contrato",
        "n_mero_de_documento_ordenador_del_gasto",
    ]
    for col in opcionales:
        if col not in df.columns:
            df[col] = np.nan

    df["valor_del_contrato"] = pd.to_numeric(df["valor_del_contrato"], errors="coerce")
    for col in ["fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato"]:
        try:
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
        except (ValueError, TypeError):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ["nombre_entidad", "proveedor_adjudicado"]:
        df[col + "_norm"] = df[col].astype("string").str.strip()
        df.loc[df[col + "_norm"].isin(["", "nan", "None", "<NA>"]), col + "_norm"] = pd.NA

    if df["id_contrato"].isna().all():
        df["id_contrato"] = [f"FILA_{i}" for i in range(len(df))]
    else:
        df["id_contrato"] = df["id_contrato"].astype("string").str.strip()
        nulos_id = df["id_contrato"].isna() | df["id_contrato"].isin(["", "nan", "None"])
        df.loc[nulos_id, "id_contrato"] = [f"FILA_{i}" for i in df.index[nulos_id]]

    # El notebook elimina únicamente filas totalmente idénticas.
    df = df.drop_duplicates().copy()
    df_clean = df[
        (df["valor_del_contrato"] > 0)
        & df["nombre_entidad_norm"].notna()
    ].copy()
    if df_clean.empty:
        raise ValueError("No quedaron contratos válidos: revise valor_del_contrato y nombre_entidad.")

    # Base de entidades: cantidad de contratos únicos y valor acumulado.
    entidades = df_clean.groupby("nombre_entidad_norm").agg(
        total_contratos=("id_contrato", "nunique"),
        total_valor=("valor_del_contrato", "sum"),
    )
    # KPI 1 y 2: concentración de valor y de número de contratos por proveedor.
    prov_valor = df_clean.dropna(subset=["proveedor_adjudicado_norm"]).groupby(
        ["nombre_entidad_norm", "proveedor_adjudicado_norm"]
    )["valor_del_contrato"].sum()
    participacion_valor = prov_valor / entidades["total_valor"]
    entidades["hhi_valor"] = (participacion_valor.pow(2).groupby(level=0).sum()).reindex(entidades.index).fillna(0)

    prov_n = df_clean.dropna(subset=["proveedor_adjudicado_norm"]).groupby(
        ["nombre_entidad_norm", "proveedor_adjudicado_norm"]
    )["id_contrato"].nunique()
    participacion_n = prov_n / entidades["total_contratos"]
    entidades["hhi_n"] = (participacion_n.pow(2).groupby(level=0).sum()).reindex(entidades.index).fillna(0)

    modalidad = df_clean["modalidad_de_contratacion"].astype("string").fillna("")
    directa = modalidad.str.contains("directa", case=False, na=False)
    regimen = modalidad.str.contains("regimen especial|régimen especial", case=False, na=False)
    valor_directa = df_clean.loc[directa].groupby("nombre_entidad_norm")["valor_del_contrato"].sum()
    valor_regimen = df_clean.loc[regimen].groupby("nombre_entidad_norm")["valor_del_contrato"].sum()
    entidades["pct_valor_directa"] = valor_directa.reindex(entidades.index, fill_value=0) / entidades["total_valor"]
    entidades["pct_valor_regimen_esp"] = valor_regimen.reindex(entidades.index, fill_value=0) / entidades["total_valor"]

    tipo = df_clean["tipo_de_contrato"].astype("string").fillna("")
    ops = tipo.str.contains("prestacion de servicios|prestación de servicios", case=False, na=False)
    conteo_ops = df_clean.loc[ops].groupby("nombre_entidad_norm")["id_contrato"].nunique()
    entidades["pct_contratos_ops"] = conteo_ops.reindex(entidades.index, fill_value=0) / entidades["total_contratos"]

    pyme = df_clean["es_pyme"].astype("string").str.strip().str.upper().isin(["SI", "SÍ", "TRUE", "1"])
    valor_pyme = df_clean.loc[pyme].groupby("nombre_entidad_norm")["valor_del_contrato"].sum()
    entidades["pct_valor_pyme"] = valor_pyme.reindex(entidades.index, fill_value=0) / entidades["total_valor"]

    # KPI 7 y 8: promedio de la proporción anual en enero-febrero y noviembre-diciembre.
    df_clean["anio_firma"] = df_clean["fecha_de_firma"].dt.year
    df_clean["mes_firma"] = df_clean["fecha_de_firma"].dt.month
    for nombre, meses, salida in [
        ("ene_feb", [1, 2], "pct_valor_ene_feb_anual"),
        ("nov_dic", [11, 12], "pct_valor_nov_dic_anual"),
    ]:
        df_clean["valor_temporal"] = np.where(df_clean["mes_firma"].isin(meses), df_clean["valor_del_contrato"], 0)
        anual = df_clean.dropna(subset=["anio_firma"]).groupby(["nombre_entidad_norm", "anio_firma"]).agg(
            total_anio=("valor_del_contrato", "sum"), valor_periodo=("valor_temporal", "sum")
        )
        anual["proporcion"] = anual["valor_periodo"] / anual["total_anio"].replace(0, np.nan)
        entidades[salida] = anual.groupby(level=0)["proporcion"].mean().reindex(entidades.index).fillna(0)
    df_clean.drop(columns=["valor_temporal"], inplace=True, errors="ignore")

    # KPI 9: HHI del ordenador del gasto por año, promediado por entidad.
    doc = df_clean["n_mero_de_documento_ordenador_del_gasto"].astype("string").str.strip()
    df_clean["doc_ordenador_clean"] = doc.mask(doc.isin(["", "nan", "None", "0", "<NA>"]))
    ord_anual = df_clean.dropna(subset=["doc_ordenador_clean", "anio_firma"]).groupby(
        ["nombre_entidad_norm", "anio_firma", "doc_ordenador_clean"]
    )["valor_del_contrato"].sum()
    if len(ord_anual):
        total_ordenadores = ord_anual.groupby(level=[0, 1]).sum()
        hhi_anual = (ord_anual / total_ordenadores).pow(2).groupby(level=[0, 1]).sum()
        hhi_ordenador = hhi_anual.groupby(level=0).mean()
        entidades["hhi_ordenador"] = hhi_ordenador.reindex(entidades.index).fillna(1.0)
    else:
        entidades["hhi_ordenador"] = 1.0

    # KPI 10: mediana de duración válida (0 a 3650 días).
    dias = (df_clean["fecha_de_fin_del_contrato"] - df_clean["fecha_de_inicio_del_contrato"]).dt.days
    dias = dias.where((dias >= 0) & (dias <= 3650))
    df_clean["dias_reales"] = dias
    duracion = df_clean.groupby("nombre_entidad_norm")["dias_reales"].median()
    mediana_general = duracion.median()
    entidades["duracion_mediana_dias"] = duracion.reindex(entidades.index).fillna(0 if pd.isna(mediana_general) else mediana_general)

    # KPI 11: escala presupuestal e inversión.
    entidades["log_valor_total"] = np.log1p(entidades["total_valor"])
    destino = df_clean["destino_gasto"].astype("string").fillna("")
    inversion = destino.str.contains("inversi[oó]n", case=False, na=False)
    valor_inversion = df_clean.loc[inversion].groupby("nombre_entidad_norm")["valor_del_contrato"].sum()
    entidades["pct_valor_inversion"] = valor_inversion.reindex(entidades.index, fill_value=0) / entidades["total_valor"]

    # KPI 12: proporción de contratos modificados, cedidos o suspendidos.
    estado = df_clean["estado_contrato"].astype("string").fillna("")
    desviados = estado.str.contains("modificad|cedid|suspendid", case=False, na=False)
    conteo_desviados = df_clean.loc[desviados].groupby("nombre_entidad_norm")["id_contrato"].nunique()
    entidades["tasa_contratos_modificados"] = conteo_desviados.reindex(entidades.index, fill_value=0) / entidades["total_contratos"]

    entidades = entidades.replace([np.inf, -np.inf], np.nan)
    entidades[COLUMNAS_PCA] = entidades[COLUMNAS_PCA].fillna(0)
    entidades.index.name = "entidad"
    return df_clean, entidades.reset_index().rename(columns={"nombre_entidad_norm": "entidad"})

def ejecutar_pca_kmeans(tabla_kpi):
    """Escala los 13 KPI, calcula PCA y prepara métricas y clústeres."""
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    modelo = tabla_kpi[tabla_kpi["total_contratos"] >= 10].copy()
    if len(modelo) < 3:
        raise ValueError(
            "Se necesitan al menos 3 entidades con 10 contratos o más para ejecutar PCA y K-Means. "
            "El análisis KPI sí puede consultarse con menos registros."
        )
    X = modelo[COLUMNAS_PCA].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    escalador = StandardScaler()
    X_scaled = escalador.fit_transform(X)
    n_componentes = min(len(COLUMNAS_PCA), X_scaled.shape[0], X_scaled.shape[1])
    pca = PCA(n_components=n_componentes)
    X_pca = pca.fit_transform(X_scaled)
    varianza = pd.DataFrame({
        "Componente": [f"PC{i+1}" for i in range(n_componentes)],
        "Valor_Propio": pca.explained_variance_,
        "Varianza_%": pca.explained_variance_ratio_ * 100,
        "Acumulada_%": np.cumsum(pca.explained_variance_ratio_) * 100,
    })
    k_kaiser = int((varianza["Valor_Propio"] > 1).sum())
    n_cluster_pc = min(4, n_componentes, max(1, k_kaiser))
    if n_cluster_pc < 1:
        n_cluster_pc = min(2, n_componentes)
    X_cluster = X_pca[:, :n_cluster_pc]

    max_k = min(8, len(modelo) - 1)
    filas_metricas = []
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=20)
        etiquetas = km.fit_predict(X_cluster)
        silueta = silhouette_score(X_cluster, etiquetas) if len(set(etiquetas)) > 1 else np.nan
        filas_metricas.append({"k": k, "Inercia": km.inertia_, "Silhouette_Score": silueta})
    metricas_k = pd.DataFrame(filas_metricas)

    k_final = min(4, len(modelo) - 1)
    k_final = max(2, k_final)
    km_final = KMeans(n_clusters=k_final, random_state=42, n_init=30)
    modelo["Cluster"] = km_final.fit_predict(X_cluster)
    modelo["PC1"] = X_pca[:, 0]
    modelo["PC2"] = X_pca[:, 1] if X_pca.shape[1] > 1 else 0.0
    cargas = pd.DataFrame(
        pca.components_[:max(1, k_kaiser)].T,
        index=COLUMNAS_PCA,
        columns=[f"PC{i+1}" for i in range(max(1, k_kaiser))],
    )
    perfil = modelo.groupby("Cluster")[COLUMNAS_PCA].mean().reset_index()
    return modelo, varianza, cargas, metricas_k, perfil, k_kaiser, n_cluster_pc

IDS_VALORES_IMPOSIBLES_NOTEBOOK = frozenset({
    "CO1.PCCNTR.8396157", "CO1.PCCNTR.5128168", "CO1.PCCNTR.4695928",
    "CO1.PCCNTR.7313948", "CO1.PCCNTR.4377709", "CO1.PCCNTR.4551965",
    "CO1.PCCNTR.1515650", "CO1.PCCNTR.8135725",
})

def normalizar_texto_entidad_notebook(valor):
    """Normalizacion usada en el notebook: mayusculas, tildes y puntuacion."""
    if pd.isna(valor):
        return pd.NA
    texto = "".join(
        c for c in unicodedata.normalize("NFKD", str(valor))
        if not unicodedata.combining(c)
    )
    texto = re.sub(r"[^\w\s]", " ", texto.upper().replace(".", ""))
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if texto else pd.NA

def preparar_datos_adicionales_por_entidad(registros_limpios):
    """Crea una vista independiente del dataframe original sin modificarlo.

    Replica el filtrado de ocho IDs y la normalizacion de nombres del cuaderno.
    Las 13 variables siguen calculandose por calcular_kpis_secop(), de forma
    que la ampliacion no reescribe las formulas vigentes del portal.
    """
    campos = [
        "id_contrato", "nombre_entidad", "proveedor_adjudicado", "valor_del_contrato",
        "fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato",
        "modalidad_de_contratacion", "tipo_de_contrato", "es_pyme", "destino_gasto",
        "estado_contrato", "n_mero_de_documento_ordenador_del_gasto",
    ]
    columnas = [c for c in campos if c in registros_limpios.columns]
    base_adicional = registros_limpios[columnas].copy()
    antes = len(base_adicional)
    if "id_contrato" in base_adicional.columns:
        base_adicional = base_adicional.loc[
            ~base_adicional["id_contrato"].astype("string").str.strip().isin(
                IDS_VALORES_IMPOSIBLES_NOTEBOOK
            )
        ].copy()
    excluidos = antes - len(base_adicional)

    for columna in ("nombre_entidad", "proveedor_adjudicado"):
        if columna in base_adicional.columns:
            # Mapear valores unicos reduce trabajo con CSV grandes de SECOP II.
            serie = base_adicional[columna].astype("string")
            equivalencias = {
                texto: normalizar_texto_entidad_notebook(texto)
                for texto in serie.dropna().unique()
            }
            base_adicional[columna] = serie.map(equivalencias).astype("string")

    documento = "n_mero_de_documento_ordenador_del_gasto"
    if documento in base_adicional.columns:
        base_adicional[documento] = (
            base_adicional[documento].astype("string").str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

    # calculo original intacto, aplicado solamente a una copia normalizada.
    registros_notebook, tabla_13_notebook = calcular_kpis_secop(base_adicional)
    return registros_notebook, tabla_13_notebook, excluidos

def calcular_siete_metricas_adicionales(registros_notebook, tabla_13_notebook):
    """Siete metricas nuevas, distintas de las 13 variables del PCA.

    * pct_valor_ene_feb_periodo y pct_valor_nov_dic_periodo son los acumulados
      del periodo completo, diferentes de los PROMEDIOS ANUALES del PCA.
    * valor_mediano_registro es la mediana de los importes por fila validada.
    """
    df = registros_notebook
    grupo = df.groupby("nombre_entidad_norm")
    indice = tabla_13_notebook.set_index("entidad").index

    resultado = pd.DataFrame(index=indice)
    resultado.index.name = "entidad"
    resultado["proveedores_distintos"] = (
        grupo["proveedor_adjudicado_norm"].nunique(dropna=True).reindex(indice)
    )
    resultado["valor_medio_contrato"] = (
        tabla_13_notebook.set_index("entidad")["total_valor"] /
        tabla_13_notebook.set_index("entidad")["total_contratos"].replace(0, np.nan)
    ).reindex(indice)
    resultado["valor_mediano_registro"] = (
        grupo["valor_del_contrato"].median().reindex(indice)
    )

    modalidad = df["modalidad_de_contratacion"].astype("string")
    es_directa = modalidad.str.contains("directa", case=False, na=False)
    n_directos = df.loc[es_directa].groupby("nombre_entidad_norm")["id_contrato"].nunique()
    denominador = tabla_13_notebook.set_index("entidad")["total_contratos"]
    resultado["pct_contratos_directos"] = (
        n_directos.reindex(indice, fill_value=0) / denominador.reindex(indice).replace(0, np.nan)
    )
    # Si no existe ninguna modalidad informada para una entidad, el indicador
    # no se conoce: NaN es mas fiel que asignar 0%.
    modalidades_informadas = (
        modalidad.fillna("").str.strip().ne("")
        .groupby(df["nombre_entidad_norm"]).sum().reindex(indice, fill_value=0)
    )
    resultado.loc[modalidades_informadas.eq(0), "pct_contratos_directos"] = np.nan

    mes = df["fecha_de_firma"].dt.month
    valor = df["valor_del_contrato"]
    total = tabla_13_notebook.set_index("entidad")["total_valor"].reindex(indice)
    for nombre, meses in [
        ("pct_valor_ene_feb_periodo", (1, 2)),
        ("pct_valor_nov_dic_periodo", (11, 12)),
    ]:
        valor_en_meses = valor.where(mes.isin(meses), 0).groupby(
            df["nombre_entidad_norm"]
        ).sum().reindex(indice, fill_value=0)
        resultado[nombre] = valor_en_meses / total.replace(0, np.nan)

    resultado["anios_con_firma"] = (
        df["fecha_de_firma"].dt.year.groupby(df["nombre_entidad_norm"])
        .nunique().reindex(indice).fillna(0).astype(int)
    )
    resultado.loc[resultado["anios_con_firma"].eq(0), [
        "pct_valor_ene_feb_periodo", "pct_valor_nov_dic_periodo"
    ]] = np.nan
    return resultado.reset_index()

def analizar_arquetipos_notebook_aditivo(tabla_13_notebook):
    """Replica el PCA/K-Means/arquetipos del notebook en una vista separada.

    Las etiquetas C0..C3 son nombres descriptivos asignados por reglas
    sobre el perfil de los grupos, no clasificaciones oficiales de SECOP.
    """
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.preprocessing import StandardScaler

    kpis = list(COLUMNAS_PCA)
    modelo = tabla_13_notebook.loc[tabla_13_notebook["total_contratos"] >= 10].copy()
    if len(modelo) < 5:
        raise ValueError("Se necesitan al menos cinco entidades con 10 contratos o mas.")

    X = modelo[kpis].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
    X["duracion_mediana_dias"] = X["duracion_mediana_dias"].clip(lower=0)
    Z = StandardScaler().fit_transform(X)
    if np.allclose(Z, 0):
        raise ValueError("Los 13 KPI son constantes: no hay variacion para un PCA util.")

    pca = PCA().fit(Z)
    componentes = pca.transform(Z)
    num_kaiser = int((pca.explained_variance_ > 1).sum())
    # Fallback de 2 componentes cuando Kaiser retiene menos de 2.
    n_retenidos = min(max(num_kaiser, 2), componentes.shape[1])
    P = componentes[:, :n_retenidos]

    cargas = pd.DataFrame(
        pca.components_[:n_retenidos].T,
        index=kpis,
        columns=[f"PC{i+1}" for i in range(n_retenidos)],
    )
    if cargas.loc["pct_valor_directa", "PC1"] < 0:
        cargas["PC1"] *= -1
        componentes[:, 0] *= -1
    if cargas.loc["log_valor_total", "PC2"] < 0:
        cargas["PC2"] *= -1
        componentes[:, 1] *= -1

    varianza = pd.DataFrame({
        "Componente": [f"PC{i+1}" for i in range(componentes.shape[1])],
        "Valor propio": pca.explained_variance_,
        "Varianza (%)": pca.explained_variance_ratio_ * 100,
        "Acumulada (%)": np.cumsum(pca.explained_variance_ratio_) * 100,
    })
    eval_k = []
    for k in range(2, min(8, len(modelo) - 1) + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=30)
        etiquetas = km.fit_predict(P)
        silueta = (
            silhouette_score(P, etiquetas) if 1 < len(set(etiquetas)) < len(P)
            else np.nan
        )
        eval_k.append({"k": k, "Inercia": km.inertia_, "Silueta": silueta})

    final = KMeans(n_clusters=4, random_state=42, n_init=30)
    etiquetas_final = final.fit_predict(P)
    if len(set(etiquetas_final)) != 4:
        raise ValueError("No hay cuatro grupos diferenciables con estos registros.")
    modelo["cluster_km"] = etiquetas_final
    semillas = [
        KMeans(n_clusters=4, random_state=s, n_init=30).fit_predict(P)
        for s in range(10)
    ]
    ari_minimo = min(adjusted_rand_score(semillas[0], et) for et in semillas[1:])
    silueta_final = silhouette_score(P, etiquetas_final)

    perfil_crudo = modelo.groupby("cluster_km")[kpis].mean()
    asignacion = {}
    pendientes = list(perfil_crudo.index)
    for codigo, indicador in (
        (3, "pct_valor_regimen_esp"),
        (2, "log_valor_total"),
        (1, "pct_valor_ene_feb_anual"),
    ):
        ganador = perfil_crudo.loc[pendientes, indicador].idxmax()
        asignacion[ganador] = codigo
        pendientes.remove(ganador)
    asignacion[pendientes[0]] = 0
    etiquetas = {
        0: "C0 Inversión tardía",
        1: "C1 Nómina OPS",
        2: "C2 Mega-ejecutores",
        3: "C3 Régimen especial",
    }
    modelo["arquetipo"] = modelo["cluster_km"].map(asignacion).map(etiquetas)
    modelo["PC1"] = componentes[:, 0]
    modelo["PC2"] = componentes[:, 1]
    orden = [etiquetas[i] for i in range(4)]
    Z_df = pd.DataFrame(Z, index=modelo.index, columns=kpis)
    huella = Z_df.groupby(modelo["arquetipo"]).mean().T.reindex(columns=orden)
    resumen = modelo.groupby("arquetipo").agg(
        Entidades=("entidad", "count"),
        Valor_contratado=("total_valor", "sum"),
    ).reindex(orden)
    resumen["Porcentaje_del_valor"] = (
        resumen["Valor_contratado"] / resumen["Valor_contratado"].sum() * 100
    )

    return {
        "modelo": modelo,
        "correlacion": X.corr(),
        "varianza": varianza,
        "cargas": cargas,
        "metricas_k": pd.DataFrame(eval_k),
        "huella": huella,
        "resumen": resumen,
        "kaiser": num_kaiser,
        "componentes_usados": n_retenidos,
        "ari": ari_minimo,
        "silueta": silueta_final,
    }


def serie_numerica(df, nombre):
    """Devuelve una serie incluso si la columna opcional no existe."""
    if nombre not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[nombre], errors="coerce").fillna(0.0)


def mostrar_kpis_estrategicos():
    st.subheader("Indicadores estratégicos · vista original")
    try:
        df, fuente_usada = cargar_fuente_kpis()
    except Exception as exc:
        st.error(str(exc))
        return

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
        return

    # Modo consolidado por departamento (metricas_andina.csv) vs. detalle por contrato
    es_consolidado = {"hhi_valor", "riesgo_score"}.issubset(df_vista.columns)

    c1, c2, c3, c4 = st.columns(4)

    if es_consolidado:
        total_contratos = int(serie_numerica(df_vista, "contratos").sum())
        total_valor = float(serie_numerica(df_vista, "valor_total_cop").sum())
        hhi_prom = float(serie_numerica(df_vista, "hhi_valor").mean())
        riesgo_prom = float(serie_numerica(df_vista, "riesgo_score").mean())

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
        valores = serie_numerica(df_vista, "valor_del_contrato")
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




@st.cache_data(ttl=86400, show_spinner=False)
def cargar_resultados_por_entidad(enlace):
    """Cachea tablas agregadas (pequeñas), no el DataFrame bruto (grande)."""
    bruto = cargar_dataset_kpi_release(enlace)
    n_filas = len(bruto)
    contratos_validos, kpi_base = calcular_kpis_secop(bruto)
    del bruto

    registros_nb, kpi_nb, excluidos = preparar_datos_adicionales_por_entidad(
        contratos_validos
    )
    # KPI 5: el notebook cuenta filas de contratos OPS (en su versión original).
    # Los KPI originales de la plataforma no se alteran.
    ops = registros_nb["tipo_de_contrato"].astype("string").str.contains(
        r"prestaci[oó]n de servicios", case=False, na=False
    )
    n_ops = registros_nb.loc[ops].groupby("nombre_entidad_norm")["id_contrato"].count()
    kpi_nb["pct_contratos_ops"] = (
        kpi_nb["entidad"].map(n_ops).fillna(0) / kpi_nb["total_contratos"].replace(0, np.nan)
    )
    adicionales = calcular_siete_metricas_adicionales(registros_nb, kpi_nb)
    n_validos = len(contratos_validos)
    n_nb = len(registros_nb)
    del contratos_validos, registros_nb

    # Evita volver a descargar el Release en cada cambio de control en Streamlit.
    return {
        "filas": n_filas, "validos": n_validos, "validos_nb": n_nb,
        "excluidos": excluidos, "base": kpi_base,
        "notebook": kpi_nb, "adicionales": adicionales,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def calcular_resultados_modelos(tabla, tipo):
    """El modelado solo se ejecuta cuando se abre el módulo PCA/K-Means."""
    if tipo == "original":
        return ejecutar_pca_kmeans(tabla)
    return analizar_arquetipos_notebook_aditivo(tabla)


def descargar_csv(df, nombre, etiqueta):
    st.download_button(
        etiqueta,
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=nombre,
        mime="text/csv",
        use_container_width=True,
    )


NOMBRES_KPI = {
    "hhi_valor": "HHI por valor",
    "hhi_n": "HHI por número de contratos",
    "pct_valor_directa": "% valor contratación directa",
    "pct_valor_regimen_esp": "% valor régimen especial",
    "pct_contratos_ops": "% contratos OPS",
    "pct_valor_pyme": "% valor adjudicado a PYME",
    "pct_valor_ene_feb_anual": "% valor enero-febrero (media anual)",
    "pct_valor_nov_dic_anual": "% valor noviembre-diciembre (media anual)",
    "hhi_ordenador": "HHI ordenador del gasto",
    "duracion_mediana_dias": "Duración mediana (días)",
    "log_valor_total": "Log del valor total",
    "pct_valor_inversion": "% valor de inversión",
    "tasa_contratos_modificados": "% contratos modificados",
}

NOMBRES_ADICIONALES = {
    "proveedores_distintos": "Proveedores distintos",
    "valor_medio_contrato": "Valor medio por contrato",
    "valor_mediano_registro": "Valor mediano por registro",
    "pct_contratos_directos": "% número de contratos directos",
    "pct_valor_ene_feb_periodo": "% valor enero-febrero (período completo)",
    "pct_valor_nov_dic_periodo": "% valor noviembre-diciembre (período completo)",
    "anios_con_firma": "Años con contratos firmados",
}


def mostrar_indicadores_por_entidad(resultados):
    tab_13, tab_7, tab_base = st.tabs([
        "13 KPI del notebook", "7 métricas complementarias", "13 KPI originales",
    ])
    nb = resultados["notebook"]
    base = resultados["base"]
    ad = resultados["adicionales"]

    with tab_13:
        st.caption("Indicadores calculados por entidad tras normalización del notebook. "
                   "No son 13 KPI nuevos distintos de los 13 originales.")
        vista = nb.rename(columns=NOMBRES_KPI).copy()
        porcentuales = [n for n in COLUMNAS_PCA if n.startswith("pct_") or n == "tasa_contratos_modificados"]
        for nombre in porcentuales:
            vista[NOMBRES_KPI[nombre]] = (vista[NOMBRES_KPI[nombre]] * 100).round(2)
        st.dataframe(vista, use_container_width=True, hide_index=True)
        descargar_csv(nb, "kpi_13_por_entidad.csv", "Descargar 13 KPI por entidad")
        indicador = st.selectbox("Comparar indicador", COLUMNAS_PCA,
                                  format_func=lambda k: NOMBRES_KPI[k], key="comp_kpi_13")
        mayores = nb.nlargest(20, indicador)
        st.plotly_chart(px.bar(mayores, x="entidad", y=indicador,
                               title=f"20 entidades con mayor {NOMBRES_KPI[indicador]}",
                               labels={indicador:NOMBRES_KPI[indicador]}), use_container_width=True)
    with tab_7:
        st.caption("Métricas exploratorias añadidas; no pertenecen a las 13 variables originales del PCA.")
        tabla = ad.rename(columns=NOMBRES_ADICIONALES).copy()
        for nombre in ("pct_contratos_directos", "pct_valor_ene_feb_periodo", "pct_valor_nov_dic_periodo"):
            tabla[NOMBRES_ADICIONALES[nombre]] = (tabla[NOMBRES_ADICIONALES[nombre]] * 100).round(2)
        st.dataframe(tabla, hide_index=True, use_container_width=True)
        descargar_csv(ad, "metricas_complementarias_por_entidad.csv", "Descargar 7 métricas complementarias")
        nombres = list(NOMBRES_ADICIONALES)
        variable = st.selectbox("Métrica complementaria", nombres,
                                format_func=lambda k: NOMBRES_ADICIONALES[k], key="comp_7")
        destacados = ad.nlargest(20, variable)
        st.plotly_chart(px.bar(destacados, x="entidad", y=variable,
                               title=f"20 entidades con mayor {NOMBRES_ADICIONALES[variable]}"),
                        use_container_width=True)
    with tab_base:
        st.caption("Cálculo existente de la plataforma, sin normalización adicional. "
                   "Se mantiene como referencia para comparar cambios en el agrupamiento.")
        st.dataframe(base, hide_index=True, use_container_width=True)
        descargar_csv(base, "kpi_13_originales.csv", "Descargar KPI originales")


def mostrar_pca_clusters(resultados):
    st.caption("El modelo utiliza únicamente los 13 KPI del notebook, en entidades con al menos 10 contratos. "
               "Las siete métricas adicionales no entran al PCA para conservar la metodología.")
    notebook = resultados["notebook"]
    opcion = st.radio("Modelo", ["Arquetipos del notebook", "PCA/K-Means original"], horizontal=True)
    if opcion == "PCA/K-Means original":
        try:
            modelo, varianza, cargas, metricas, perfil, k_kaiser, n_componentes = calcular_resultados_modelos(resultados["base"], "original")
        except Exception as exc:
            st.warning(f"No fue posible calcular PCA/K-Means original: {exc}")
            return
        a,b,c=st.columns(3)
        a.metric("Entidades en PCA", len(modelo))
        b.metric("Componentes (Kaiser)", k_kaiser)
        c.metric("Componentes usados", n_componentes)
        st.dataframe(varianza, hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(varianza, x="Componente", y="Varianza_%", title="Varianza por componente"), use_container_width=True)
        st.plotly_chart(px.line(metricas, x="k", y="Silhouette_Score", markers=True, title="Silueta por k"), use_container_width=True)
        st.plotly_chart(px.scatter(modelo, x="PC1", y="PC2", color=modelo["Cluster"].astype(str),
                                   hover_name="entidad", title="Clústeres originales en el plano PCA"), use_container_width=True)
        st.dataframe(perfil.round(4), hide_index=True, use_container_width=True)
        descargar_csv(modelo, "pca_kmeans_original.csv", "Descargar clústeres originales")
        return

    try:
        r = calcular_resultados_modelos(notebook, "notebook")
    except Exception as exc:
        st.warning(f"No fue posible construir los arquetipos: {exc}")
        return
    a, b, c, d = st.columns(4)
    a.metric("Entidades evaluadas", len(r["modelo"]))
    b.metric("Componentes retenidos", r["componentes_usados"])
    c.metric("Silueta k=4", f"{r['silueta']:.3f}")
    d.metric("Estabilidad ARI mínima", f"{r['ari']:.3f}")
    st.markdown("#### PCA · varianza y correlaciones")
    st.dataframe(r["varianza"].round(3), hide_index=True, use_container_width=True)
    st.plotly_chart(px.line(r["varianza"], x="Componente", y="Acumulada (%)", markers=True,
                            title="Varianza acumulada del PCA"), use_container_width=True)
    st.plotly_chart(px.imshow(r["correlacion"], text_auto=".2f", aspect="auto",
                             title="Correlación entre los 13 KPI"), use_container_width=True)
    st.markdown("#### K-Means · evaluación y arquetipos")
    e1, e2 = st.columns(2)
    with e1:
        st.plotly_chart(px.line(r["metricas_k"], x="k", y="Inercia", markers=True, title="Método del codo"), use_container_width=True)
    with e2:
        st.plotly_chart(px.line(r["metricas_k"], x="k", y="Silueta", markers=True, title="Coeficiente de silueta"), use_container_width=True)
    st.plotly_chart(px.scatter(r["modelo"], x="PC1", y="PC2", color="arquetipo", hover_name="entidad",
                               hover_data=["total_contratos","total_valor"], title="Arquetipos contractuales por entidad"), use_container_width=True)
    st.dataframe(r["resumen"].reset_index(), hide_index=True, use_container_width=True)
    st.plotly_chart(px.imshow(r["huella"], text_auto=".2f", aspect="auto",
                             title="Mapa de calor: perfil estandarizado de los arquetipos"), use_container_width=True)
    descargar_csv(r["modelo"], "arquetipos_por_entidad.csv", "Descargar entidades y arquetipos")


# ------------------------- Interfaz única en pages/ -------------------------
st.title("KPIs Estratégicos · Contratación Región Andina")
st.caption("Se conservan los KPI departamentales y se agregan los análisis por entidad desde GitHub Releases.")
SECCIONES = ["Estratégicos (actuales)", "13 KPI + 7 métricas por entidad", "PCA y K-Means"]
seccion = st.radio("Vista de indicadores", SECCIONES, horizontal=True)

if seccion == SECCIONES[0]:
    mostrar_kpis_estrategicos()
else:
    if st.button("Actualizar datos del Release", key="kpi_actualizar_release"):
        ruta = _ruta_cache_kpi()
        if os.path.isfile(ruta):
            os.remove(ruta)
        cargar_resultados_por_entidad.clear()
        calcular_resultados_modelos.clear()
        st.session_state["kpi_entidad_activado"] = False
        st.rerun()

    if st.button("Cargar / calcular análisis por entidad", key="kpi_entidad_cargar"):
        st.session_state["kpi_entidad_activado"] = True

    if not st.session_state.get("kpi_entidad_activado", False):
        st.info("Pulsa «Cargar / calcular análisis por entidad» para leer el dataset de GitHub Releases. "
                "La primera ejecución descarga el archivo; las siguientes reutilizan la caché.")
    else:
        try:
            with st.spinner("Calculando resultados por entidad desde SECOP II..."):
                resultados = cargar_resultados_por_entidad(ENLACE_DATASET_KPI)
        except Exception as exc:
            st.error(f"No se pudo leer o procesar el dataset: {exc}")
            st.caption("Comprueba la conexión a GitHub Releases y que el archivo sea un CSV GZIP válido.")
        else:
            st.caption(f"Fuente: GitHub Releases · {resultados['filas']:,} registros de entrada · "
                       f"{resultados['validos']:,} registros válidos · "
                       f"{len(resultados['notebook']):,} entidades normalizadas · "
                       f"{resultados['excluidos']} exclusiones del notebook")
            if seccion == SECCIONES[1]:
                mostrar_indicadores_por_entidad(resultados)
            else:
                mostrar_pca_clusters(resultados)
