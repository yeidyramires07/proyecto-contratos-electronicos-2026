# base_de_datos/modelo_bd.py
# Genera los CSV normalizados en bd/ a partir de contratos_publicar.csv
# Ejecutar desde la carpeta principal: python base_de_datos\modelo_bd.py

from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BD_DIR = RAIZ / "bd"
BD_DIR.mkdir(parents=True, exist_ok=True)

ENTRADA = (
    RAIZ / "contratos_publicar.csv"
    if (RAIZ / "contratos_publicar.csv").exists()
    else RAIZ / "secop_andina_base.csv"
)


def limpiar_texto(serie, por_defecto="No Definido"):
    return (
        serie.fillna(por_defecto)
        .astype(str)
        .str.strip()
        .replace({"": por_defecto, "nan": por_defecto, "None": por_defecto})
    )


def limpiar_fecha(serie):
    fechas = pd.to_datetime(serie, errors="coerce")
    return fechas.dt.strftime("%Y-%m-%d").fillna("")


def main():
    if not ENTRADA.exists():
        raise FileNotFoundError(f"No se encontro el archivo de entrada: {ENTRADA}")

    df = pd.read_csv(ENTRADA, encoding="utf-8-sig", low_memory=False)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Asegurar columnas clave
    if "id_contrato" not in df.columns:
        df["id_contrato"] = [f"CTR_{i + 1}" for i in range(len(df))]

    df["departamento"] = limpiar_texto(df.get("departamento", pd.Series("No Definido", index=df.index)))
    df["categoria"] = limpiar_texto(df.get("categoria", df.get("tipo_de_contrato", pd.Series("General", index=df.index))), "General")
    df["nombre_entidad"] = limpiar_texto(df.get("nombre_entidad", pd.Series("Entidad Sin Nombre", index=df.index)))
    df["ciudad"] = limpiar_texto(df.get("ciudad", pd.Series("No Definido", index=df.index)))
    df["orden"] = limpiar_texto(df.get("orden", pd.Series("No Definido", index=df.index)))
    df["rama"] = limpiar_texto(df.get("rama", pd.Series("No Definido", index=df.index)))

    # 1) departamento.csv
    deptos_unicos = sorted(df["departamento"].unique())
    dep_df = pd.DataFrame({
        "id_departamento": range(1, len(deptos_unicos) + 1),
        "nombre": deptos_unicos,
    })
    mapa_dep = dict(zip(dep_df["nombre"], dep_df["id_departamento"]))
    dep_df.to_csv(BD_DIR / "departamento.csv", index=False, encoding="utf-8-sig")

    # 2) categoria.csv
    cats_unicas = sorted(df["categoria"].unique())
    cat_df = pd.DataFrame({
        "id_categoria": range(1, len(cats_unicas) + 1),
        "nombre": cats_unicas,
    })
    mapa_cat = dict(zip(cat_df["nombre"], cat_df["id_categoria"]))
    cat_df.to_csv(BD_DIR / "categoria.csv", index=False, encoding="utf-8-sig")

    # 3) entidad.csv
    ent_src = df[["nombre_entidad", "departamento", "ciudad", "orden", "rama"]].drop_duplicates(subset=["nombre_entidad"]).copy()
    ent_src["id_departamento"] = ent_src["departamento"].map(mapa_dep)
    ent_df = pd.DataFrame({
        "id_entidad": range(1, len(ent_src) + 1),
        "nombre": ent_src["nombre_entidad"].values,
        "id_departamento": ent_src["id_departamento"].values,
        "ciudad": ent_src["ciudad"].values,
        "orden": ent_src["orden"].values,
        "rama": ent_src["rama"].values,
    })
    mapa_ent = dict(zip(ent_df["nombre"], ent_df["id_entidad"]))
    ent_df.to_csv(BD_DIR / "entidad.csv", index=False, encoding="utf-8-sig")

    # 4) contrato.csv
    valor_contrato = pd.to_numeric(df.get("valor_del_contrato", 0), errors="coerce").fillna(0.0).round(2)
    saldo_pendiente = pd.to_numeric(df.get("saldo_pendiente", 0), errors="coerce").fillna(0.0).round(2)
    valor_facturado = pd.to_numeric(df.get("valor_facturado", valor_contrato - saldo_pendiente), errors="coerce").fillna(0.0).round(2)
    valor_pagado = pd.to_numeric(df.get("valor_pagado", valor_facturado), errors="coerce").fillna(0.0).round(2)

    con_df = pd.DataFrame({
        "id_contrato": limpiar_texto(df["id_contrato"], "SIN_ID"),
        "id_entidad": df["nombre_entidad"].map(mapa_ent),
        "id_categoria": df["categoria"].map(mapa_cat),
        "tipo_de_contrato": limpiar_texto(df.get("tipo_de_contrato", pd.Series("No Definido", index=df.index))),
        "fecha_firma": limpiar_fecha(df.get("fecha_de_firma", pd.Series("", index=df.index))),
        "fecha_inicio": limpiar_fecha(df.get("fecha_de_inicio_del_contrato", pd.Series("", index=df.index))),
        "fecha_fin": limpiar_fecha(df.get("fecha_de_fin_del_contrato", pd.Series("", index=df.index))),
        "valor_contrato": valor_contrato.values,
        "valor_facturado": valor_facturado.values,
        "valor_pagado": valor_pagado.values,
        "saldo_pendiente": saldo_pendiente.values,
        "nivel_alerta": limpiar_texto(df.get("nivel_alerta", pd.Series("Baja", index=df.index)), "Baja"),
        "estado_contrato": limpiar_texto(df.get("estado_contrato", pd.Series("No Definido", index=df.index))),
        "es_pyme": limpiar_texto(df.get("es_pyme", pd.Series("No", index=df.index)), "No"),
        "origen_recursos": limpiar_texto(df.get("origen_de_los_recursos", pd.Series("No Definido", index=df.index))),
        "destino_gasto": limpiar_texto(df.get("destino_gasto", pd.Series("No Definido", index=df.index))),
        "objeto": limpiar_texto(df.get("objeto_del_contrato", pd.Series("", index=df.index)), ""),
    })
    con_df.to_csv(BD_DIR / "contrato.csv", index=False, encoding="utf-8-sig")

    # Esquema SQL basico si no existe
    esquema_sql = BD_DIR / "esquema_mysql.sql"
    if not esquema_sql.exists():
        sql_texto = """CREATE TABLE IF NOT EXISTS departamento (
    id_departamento INT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS categoria (
    id_categoria INT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS entidad (
    id_entidad INT PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    id_departamento INT,
    ciudad VARCHAR(120),
    orden VARCHAR(100),
    rama VARCHAR(100),
    FOREIGN KEY (id_departamento) REFERENCES departamento(id_departamento)
);

CREATE TABLE IF NOT EXISTS contrato (
    id_contrato VARCHAR(100) PRIMARY KEY,
    id_entidad INT,
    id_categoria INT,
    tipo_de_contrato VARCHAR(120),
    fecha_firma VARCHAR(20),
    fecha_inicio VARCHAR(20),
    fecha_fin VARCHAR(20),
    valor_contrato DECIMAL(18,2),
    valor_facturado DECIMAL(18,2),
    valor_pagado DECIMAL(18,2),
    saldo_pendiente DECIMAL(18,2),
    nivel_alerta VARCHAR(30),
    estado_contrato VARCHAR(100),
    es_pyme VARCHAR(20),
    origen_recursos VARCHAR(150),
    destino_gasto VARCHAR(150),
    objeto TEXT,
    FOREIGN KEY (id_entidad) REFERENCES entidad(id_entidad),
    FOREIGN KEY (id_categoria) REFERENCES categoria(id_categoria)
);
"""
        esquema_sql.write_text(sql_texto, encoding="utf-8")

    print(f"Generados CSV en {BD_DIR} desde {ENTRADA.name}:")
    print(f"  departamentos: {len(dep_df):,}")
    print(f"  categorias:    {len(cat_df):,}")
    print(f"  entidades:     {len(ent_df):,}")
    print(f"  contratos:     {len(con_df):,}")


if __name__ == "__main__":
    main()