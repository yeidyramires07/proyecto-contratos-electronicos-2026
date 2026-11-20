import os
import time
import hashlib
import hmac
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pymysql
import requests
import streamlit as st

try:
    from enviar_telegram import enviar_telegram
except Exception:
    enviar_telegram = None

st.set_page_config(page_title="CONTRATACIÓN ANDINA", layout="wide")

COORDENADAS = {
    "Antioquia": (6.244, -75.574),
    "Boyacá": (5.535, -73.367),
    "Caldas": (5.070, -75.517),
    "Cundinamarca": (4.860, -74.030),
    "Distrito Capital de Bogotá": (4.711, -74.072),
    "Bogotá, D.C.": (4.711, -74.072),
    "Huila": (2.927, -75.282),
    "Norte de Santander": (7.894, -72.507),
    "Quindío": (4.534, -75.681),
    "Risaralda": (4.813, -75.696),
    "Santander": (7.119, -73.122),
    "Tolima": (4.438, -75.232),
}

CONEXIONES_ANDINA = [
    ("Distrito Capital de Bogotá", "Cundinamarca"),
    ("Cundinamarca", "Boyacá"),
    ("Boyacá", "Santander"),
    ("Santander", "Norte de Santander"),
    ("Cundinamarca", "Tolima"),
    ("Tolima", "Huila"),
    ("Tolima", "Quindío"),
    ("Quindío", "Risaralda"),
    ("Risaralda", "Caldas"),
    ("Caldas", "Antioquia"),
    ("Antioquia", "Santander"),
]

st.markdown(
    """
    <style>
        .stApp { background-color: #FFFFFF; color: #111827; }
        [data-testid="stSidebar"] { background-color: #F8FAFC; border-right: 1px solid #E2E8F0; }
        .cabecera-portal {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #E5E7EB;
            padding: 10px 4px 14px 4px;
            margin-bottom: 14px;
        }
        .cabecera-izq {
            min-width: 170px;
            font-size: 0.84rem;
            color: #1E3A8A;
            line-height: 1.25;
        }
        .cabecera-centro {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            text-align: center;
        }
        .cabecera-titulo {
            font-size: 1.45rem;
            font-weight: 900;
            color: #0F294A;
            letter-spacing: 0.02em;
        }
        .cabecera-der {
            min-width: 170px;
            display: flex;
            justify-content: flex-end;
        }
        .badge-vivo {
            background-color: #DC2626;
            color: #FFFFFF;
            font-weight: 800;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            padding: 7px 14px;
            border-radius: 999px;
            text-transform: uppercase;
        }
        .barra-azul {
            background-color: #0F294A;
            color: #FFFFFF;
            padding: 9px 14px;
            border-radius: 5px;
            margin: 10px 0 16px 0;
            font-size: 0.9rem;
        }
        .nota-fila {
            border: 1px solid #E5E7EB;
            border-left: 4px solid #0F294A;
            border-radius: 6px;
            padding: 14px;
            margin-bottom: 14px;
            background-color: #FFFFFF;
        }
        .nota-fila.alta { border-left-color: #C81E1E; }
        .tag-ods {
            display: inline-block;
            background-color: #0F294A;
            color: #FFFFFF;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 3px;
            margin-right: 8px;
        }
        .credito-foto {
            font-size: 0.78rem;
            color: #6B7280;
            margin-top: 4px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def leer_secreto(nombre):
    try:
        return str(st.secrets[nombre])
    except Exception:
        return os.environ.get(nombre)


token_telegram = leer_secreto("TELEGRAM_TOKEN")
if token_telegram:
    os.environ["TELEGRAM_TOKEN"] = token_telegram


def conectar():
    ssl_ca = leer_secreto("MYSQL_CA")
    ssl_cfg = {"ca": ssl_ca} if ssl_ca else {}
    return pymysql.connect(
        host=leer_secreto("MYSQL_HOST"),
        port=int(leer_secreto("MYSQL_PORT")),
        user=leer_secreto("MYSQL_USER"),
        password=leer_secreto("MYSQL_PASSWORD"),
        database=leer_secreto("MYSQL_DB"),
        ssl=ssl_cfg,
        charset="utf8mb4",
        connect_timeout=8,
    )


def clave_correcta(clave_escrita, huella_guardada):
    try:
        _, vueltas, sal, huella = huella_guardada.split("$")
        huella_nueva = hashlib.pbkdf2_hmac(
            "sha256", clave_escrita.encode("utf-8"), bytes.fromhex(sal), int(vueltas)
        ).hex()
        return hmac.compare_digest(huella_nueva, huella)
    except Exception:
        return False


def iniciar_sesion(usuario, clave):
    try:
        conexion = conectar()
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT u.nombre, u.password_hash, r.nombre, d.nombre "
            "FROM usuario u JOIN rol r ON u.id_rol = r.id_rol "
            "LEFT JOIN departamento d ON u.id_departamento = d.id_departamento "
            "WHERE u.login = %s AND u.activo = TRUE",
            (usuario,),
        )
        fila = cursor.fetchone()
        conexion.close()
    except Exception:
        return "sin_base", None

    if fila is None or not clave_correcta(clave, fila[1]):
        return "incorrecto", None
    return "ok", {"nombre": fila[0], "rol": fila[2], "departamento": fila[3]}


@st.cache_data(ttl=1800)
def buscar_fotos_fotografos(termino_foto, max_fotos=6):
    """Busca fotografías reales y el nombre del fotógrafo/autor en Unsplash o Wikimedia Commons."""
    access_key = leer_secreto("UNSPLASH_ACCESS_KEY")
    if access_key:
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": termino_foto, "per_page": max_fotos, "lang": "es"},
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=8,
            )
            resp.raise_for_status()
            fotos = []
            for item in resp.json().get("results", []):
                url_foto = (item.get("urls") or {}).get("regular")
                fotografo = ((item.get("user") or {}).get("name") or "").strip()
                if url_foto:
                    fotos.append({"url": url_foto, "fotografo": fotografo or "Fotógrafo Unsplash"})
            if fotos:
                return fotos
        except Exception:
            pass

    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": f"{termino_foto} filetype:bitmap",
                "gsrlimit": max_fotos * 2,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 800,
                "format": "json",
            },
            headers={"User-Agent": "ContratacionAndinaApp/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        pages = ((resp.json().get("query") or {}).get("pages") or {}).values()
        fotos = []
        for p in pages:
            infos = p.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            url_foto = info.get("thumburl") or info.get("url")
            meta = info.get("extmetadata") or {}
            autor_html = ((meta.get("Artist") or {}).get("value") or "").strip()
            while "<" in autor_html and ">" in autor_html:
                i, j = autor_html.find("<"), autor_html.find(">", autor_html.find("<"))
                autor_html = autor_html[:i] + " " + autor_html[j + 1 :] if j != -1 else autor_html
            autor = " ".join(autor_html.split()).strip() or "Wikimedia Commons"
            if url_foto and not url_foto.lower().endswith(".svg"):
                fotos.append({"url": url_foto, "fotografo": autor[:60]})
            if len(fotos) >= max_fotos:
                break
        return fotos
    except Exception:
        return []


@st.cache_data(ttl=900)
def obtener_noticias_ods(consulta, termino_foto, max_notas=6):
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(consulta)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )
    fotos_reales = buscar_fotos_fotografos(termino_foto, max_fotos=max_notas)
    notas = []
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall("./channel/item")[:max_notas]
        for idx, item in enumerate(items):
            titulo = (item.findtext("title") or "").strip()
            enlace = (item.findtext("link") or "").strip()
            fuente_n = (item.findtext("source") or "Prensa").strip()
            fecha_pub = (item.findtext("pubDate") or "").strip()[:16]
            desc = item.findtext("description") or ""
            while "<" in desc and ">" in desc:
                i, j = desc.find("<"), desc.find(">", desc.find("<"))
                desc = desc[:i] + " " + desc[j + 1 :] if j != -1 else desc
            intro = " ".join(desc.replace("&nbsp;", " ").replace("&amp;", "&").split()).strip()
            if not intro or intro.lower() == titulo.lower():
                intro = f"Nota informativa publicada por {fuente_n} sobre gestión y contratación pública."

            imagen = None
            fotografo = None
            if fotos_reales:
                foto_elegida = fotos_reales[idx % len(fotos_reales)]
                imagen = foto_elegida["url"]
                fotografo = f"Fotografía: {foto_elegida['fotografo']}"

            notas.append({
                "titulo": titulo,
                "intro": intro[:230],
                "url": enlace,
                "fuente": fuente_n,
                "fecha": fecha_pub,
                "imagen": imagen,
                "fotografo": fotografo,
            })
    except Exception:
        pass
    return notas


@st.cache_data(ttl=600)
def leer_csv(archivo):
    df = pd.read_csv(archivo, encoding="utf-8-sig", low_memory=False)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df


def cargar_datos(archivo_subido=None):
    if archivo_subido is not None:
        return leer_csv(archivo_subido), f"subido: {archivo_subido.name}"
    for archivo in ["metricas_andina.csv", "entidades_auditoria_kpis.csv", "secop2_4sectores_limpio.csv"]:
        if os.path.exists(archivo):
            return leer_csv(archivo), archivo
    return pd.DataFrame({
        "departamento": ["Huila", "Quindío", "Caldas"],
        "entidad": ["Consolidado Huila", "Consolidado Quindío", "Consolidado Caldas"],
        "sector": ["Región Andina"] * 3,
        "hhi_valor": [980.5, 340.3, 518.0],
        "cr4_valor": [37.6, 33.4, 31.7],
        "pagos_sin_soporte_pct": [73.8, 89.0, 70.5],
        "riesgo_score": [75.3, 60.9, 55.7],
        "nivel_alerta": ["Alta", "Alta", "Alta"],
    }), "respaldo"


def preparar_datos(df):
    out = df.copy()
    out["departamento"] = out.get("departamento", "Sin departamento")
    out["departamento"] = out["departamento"].fillna("Sin departamento").astype(str).str.strip()
    out["entidad"] = out.get("entidad", out.get("nombre_entidad_limpio", "Sin entidad"))
    out["entidad"] = out["entidad"].fillna("Sin entidad").astype(str).str.strip()
    out["sector"] = out.get("sector", "General")
    out["sector"] = out["sector"].fillna("General").astype(str).str.strip()
    out["hhi_valor"] = pd.to_numeric(out.get("hhi_valor", out.get("hhi", 0.0)), errors="coerce").fillna(0.0)
    out["cr4_valor"] = pd.to_numeric(out.get("cr4_valor", out.get("cr4", 0.0)), errors="coerce").fillna(0.0)
    out["pagos_sin_soporte_pct"] = pd.to_numeric(
        out.get("pagos_sin_soporte_pct", out.get("pct_contratacion_directa", 0.0)), errors="coerce"
    ).fillna(0.0)
    if "riesgo_score" not in out.columns:
        out["riesgo_score"] = (
            (out["hhi_valor"] / 1000.0).clip(0, 1) * 50.0
            + (out["pagos_sin_soporte_pct"] / 100.0).clip(0, 1) * 50.0
        ).round(2)
    out["riesgo_score"] = pd.to_numeric(out["riesgo_score"], errors="coerce").fillna(0.0)
    out["nivel_alerta"] = out.get("nivel_alerta", "Sin alerta")
    out["nivel_alerta"] = out["nivel_alerta"].fillna("Sin alerta").astype(str).str.strip()
    return out


def svg_logo_andina(size=44):
    return (
        f'<svg width="{size}" height="{int(size * 1.15)}" viewBox="0 0 46 52" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M18 3L27 6L24 14L33 19L30 28L36 35L28 48L19 49L14 39L9 31L13 21L10 12L18 3Z" '
        'fill="#0F294A" stroke="#C81E1E" stroke-width="2"/>'
        '<circle cx="22" cy="24" r="3.5" fill="#FFFFFF"/>'
        "</svg>"
    )


def construir_mapa_andina(df_depto):
    lats, lons, idx = [], [], []
    for i, nombre in enumerate(df_depto["departamento"]):
        if nombre in COORDENADAS:
            lats.append(COORDENADAS[nombre][0])
            lons.append(COORDENADAS[nombre][1])
            idx.append(i)

    sub = df_depto.iloc[idx].copy()
    sub["lat"] = lats
    sub["lon"] = lons

    fig = go.Figure()
    for origen, destino in CONEXIONES_ANDINA:
        if origen in COORDENADAS and destino in COORDENADAS:
            fig.add_trace(go.Scattermap(
                lat=[COORDENADAS[origen][0], COORDENADAS[destino][0]],
                lon=[COORDENADAS[origen][1], COORDENADAS[destino][1]],
                mode="lines",
                line=dict(width=1.5, color="#94A3B8"),
                hoverinfo="skip",
                showlegend=False,
            ))

    if len(sub) > 0:
        max_hhi = max(float(sub["hhi_promedio"].max()), 1.0)
        textos = [
            f"<b>{r['departamento']}</b><br>"
            f"% Contratación directa: {round(r['soporte_pct'], 1)}%<br>"
            f"HHI: {round(r['hhi_promedio'], 1)}"
            for _, r in sub.iterrows()
        ]
        fig.add_trace(go.Scattermap(
            lat=sub["lat"],
            lon=sub["lon"],
            mode="markers+text",
            text=sub["departamento"],
            textposition="top center",
            hovertext=textos,
            hoverinfo="text",
            marker=dict(
                size=14 + 30 * sub["hhi_promedio"] / max_hhi,
                color=sub["soporte_pct"],
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="% Directa"),
            ),
        ))

    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=4.7, lon=-74.3), zoom=5.6),
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def armar_mensaje(fila):
    return (
        f"Alerta {fila['nivel_alerta']}: {str(fila['entidad']).title()} ({fila['departamento']}) "
        f"| HHI: {round(float(fila['hhi_valor']), 1)} | CR4: {round(float(fila['cr4_valor']), 1)}% "
        f"| Directa: {round(float(fila['pagos_sin_soporte_pct']), 1)}%."
    )


def leer_suscriptores():
    try:
        return [dict(p) for p in st.secrets["suscriptores"]]
    except Exception:
        return []


# ----- Inicio antes de ingresar -----

if "sesion" not in st.session_state:
    _, col_centro, _ = st.columns([1, 2, 1])
    with col_centro:
        st.markdown(f"<div style='text-align:center;'>{svg_logo_andina(170)}</div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center; color:#0F294A;'>CONTRATACIÓN ANDINA</h1>", unsafe_allow_html=True)

        usuario_escrito = st.text_input("Usuario")
        clave_escrita = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            resultado, datos_usuario = iniciar_sesion(usuario_escrito.strip().lower(), clave_escrita)
            if resultado == "ok":
                st.session_state["sesion"] = datos_usuario
                st.rerun()
            elif resultado == "sin_base":
                st.warning("La base de datos no está disponible. Puedes entrar como invitado.")
            else:
                st.error("Usuario o contraseña incorrectos.")

        if st.button("Entrar como invitado"):
            st.session_state["sesion"] = {"nombre": "Invitado", "rol": "Invitado", "departamento": None}
            st.rerun()
    st.stop()


# ----- App principal con barra superior tipo portal (logo en el centro) -----

fecha_texto = datetime.now().strftime("%d/%m/%Y")
st.markdown(
    f"""
    <div class="cabecera-portal">
        <div class="cabecera-izq">
            <strong>{fecha_texto}</strong><br>
            <span>Región Andina</span>
        </div>
        <div class="cabecera-centro">
            {svg_logo_andina(42)}
            <span class="cabecera-titulo">CONTRATACIÓN ANDINA</span>
        </div>
        <div class="cabecera-der">
            <span class="badge-vivo">ALERTAS ANDINAS</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

sesion = st.session_state["sesion"]
rol = sesion["rol"]
es_admin = rol == "Administrador"

datos_crudos, fuente = cargar_datos(st.session_state.get("archivo_csv_subido"))
contratos = preparar_datos(datos_crudos)

if sesion.get("departamento") and rol in ["Comprador", "EPS", "Farmacia o distribuidor", "Auditor"]:
    contratos = contratos[contratos["departamento"] == sesion["departamento"]]

st.sidebar.write("Sesión: " + sesion["nombre"] + " (" + rol + ")")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear()
    st.rerun()

st.sidebar.header("Filtros")
departamentos = st.sidebar.multiselect("Departamento", sorted(contratos["departamento"].unique()))
sectores = st.sidebar.multiselect("Sector / Categoría", sorted(contratos["sector"].unique()))
niveles = st.sidebar.multiselect("Nivel de alerta", sorted(contratos["nivel_alerta"].unique()))

filtrado = contratos.copy()
if departamentos:
    filtrado = filtrado[filtrado["departamento"].isin(departamentos)]
if sectores:
    filtrado = filtrado[filtrado["sector"].isin(sectores)]
if niveles:
    filtrado = filtrado[filtrado["nivel_alerta"].isin(niveles)]

st.sidebar.write("Datos: " + fuente)
st.sidebar.write(f"Registros: {len(filtrado)} de {len(contratos)}")

if len(filtrado) > 0:
    top3 = filtrado.sort_values("riesgo_score", ascending=False).head(3)
    focos_texto = " | ".join(
        f"{r['departamento']}: Riesgo {round(float(r['riesgo_score']), 1)} (HHI {round(float(r['hhi_valor']), 1)})"
        for _, r in top3.iterrows()
    )
    st.markdown(f'<div class="barra-azul"><b>Focos Andinos:</b> {focos_texto}</div>', unsafe_allow_html=True)

tab_noticias, tab_resumen, tab_mapa, tab_dashboard, tab_senales_rend, tab_judiciales, tab_red, tab_ods = st.tabs([
    "Noticias Andina",
    "Resumen",
    "Mapa",
    "Dashboard interactivo",
    "Señales y Rendimiento",
    "Servicios Judiciales",
    "Red",
    "Noticias en tiempo real",
])


# ----- Noticias Andina -----

with tab_noticias:
    st.subheader("Noticias de la Región Andina")
    for _, fila in filtrado.sort_values("riesgo_score", ascending=False).iterrows():
        alerta_txt = str(fila["nivel_alerta"])
        es_alta = alerta_txt.upper() in ["ALTO", "ALTA"]
        st.markdown(
            f"""
            <div class="nota-fila {'alta' if es_alta else ''}">
                <small><b>{fila['departamento']} · Alerta {alerta_txt}</b></small><br>
                <b>{fila['departamento']}: puntaje de riesgo {round(float(fila['riesgo_score']), 1)}</b><br>
                HHI: {round(float(fila['hhi_valor']), 1)} · CR4: {round(float(fila['cr4_valor']), 1)}% · Directa: {round(float(fila['pagos_sin_soporte_pct']), 1)}%
            </div>
            """,
            unsafe_allow_html=True,
        )


# ----- Resumen -----

with tab_resumen:
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(filtrado))
    c2.metric("HHI promedio", round(float(filtrado["hhi_valor"].mean()), 1) if len(filtrado) else 0.0)
    c3.metric("Alertas altas", int(filtrado["nivel_alerta"].str.upper().isin(["ALTO", "ALTA"]).sum()))

    st.subheader("Por sector / categoría")
    por_sector = filtrado.groupby("sector", as_index=False).agg(
        registros=("entidad", "count"),
        hhi_promedio=("hhi_valor", "mean"),
        contratacion_directa_pct=("pagos_sin_soporte_pct", "mean"),
    )
    por_sector["hhi_promedio"] = por_sector["hhi_promedio"].round(1)
    por_sector["contratacion_directa_pct"] = por_sector["contratacion_directa_pct"].round(1)
    st.dataframe(por_sector, hide_index=True, use_container_width=True)

    st.subheader("Por departamento")
    por_depto = filtrado.groupby("departamento", as_index=False).agg(
        hhi_promedio=("hhi_valor", "mean"),
    ).sort_values("hhi_promedio", ascending=False)
    st.plotly_chart(px.bar(por_depto, x="departamento", y="hhi_promedio", color_discrete_sequence=["#0F294A"]), use_container_width=True)


# ----- Mapa + Gráfico interactivo de colores debajo -----

with tab_mapa:
    st.subheader("Mapa de la Región Andina")
    por_depto_mapa = filtrado.groupby("departamento", as_index=False).agg(
        hhi_promedio=("hhi_valor", "mean"),
        soporte_pct=("pagos_sin_soporte_pct", "mean"),
    ).sort_values("soporte_pct", ascending=False)

    st.plotly_chart(construir_mapa_andina(por_depto_mapa), use_container_width=True)

    st.markdown("**Guía interactiva de color (% de contratación directa)**")
    st.write("- Amarillo claro: menor % de contratación directa")
    st.write("- Naranja: % intermedio de contratación directa")
    st.write("- Rojo oscuro: mayor % de contratación directa")

    if len(por_depto_mapa) > 0:
        fig_colores = px.bar(
            por_depto_mapa,
            x="departamento",
            y="soporte_pct",
            color="soporte_pct",
            color_continuous_scale="YlOrRd",
            labels={"soporte_pct": "% Contratación directa", "departamento": "Departamento"},
        )
        fig_colores.update_layout(height=320)
        st.plotly_chart(fig_colores, use_container_width=True)


# ----- Dashboard interactivo -----

with tab_dashboard:
    st.subheader("Dashboard interactivo")
    metrica_elegida = st.selectbox(
        "Métrica a comparar",
        ["riesgo_score", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct"],
    )
    top_n = st.slider("Cantidad de entidades a mostrar", 5, 30, 10)

    top_dash = filtrado.sort_values(metrica_elegida, ascending=False).head(top_n)
    if len(top_dash) > 0:
        st.plotly_chart(
            px.bar(
                top_dash,
                x="entidad",
                y=metrica_elegida,
                color="nivel_alerta",
                hover_data=["departamento", "sector"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            px.scatter(
                filtrado,
                x="hhi_valor",
                y="pagos_sin_soporte_pct",
                size="riesgo_score",
                color="nivel_alerta",
                hover_name="entidad",
            ),
            use_container_width=True,
        )


# ----- Señales y Rendimiento -----

with tab_senales_rend:
    st.subheader("Subir CSV o datos actualizados")
    subido = st.file_uploader("Seleccionar CSV", type=["csv"])
    if subido is not None:
        st.session_state["archivo_csv_subido"] = subido
    if st.session_state.get("archivo_csv_subido") is not None and st.button("Restaurar archivo original"):
        st.session_state.pop("archivo_csv_subido", None)
        st.rerun()

    st.subheader("Señales")
    cols = ["entidad", "departamento", "sector", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct", "riesgo_score", "nivel_alerta"]
    st.dataframe(filtrado[cols].sort_values("riesgo_score", ascending=False), hide_index=True, use_container_width=True)

    st.subheader("Rendimiento")
    if os.path.exists("rendimiento_multiprocessing.csv"):
        medidas = pd.read_csv("rendimiento_multiprocessing.csv")
        st.dataframe(medidas, hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(medidas, x="procesos", y="speedup", color_discrete_sequence=["#0F294A"]), use_container_width=True)
    else:
        st.write("Sin datos de rendimiento.")


# ----- Servicios Judiciales (envío de alertas) -----

with tab_judiciales:
    st.subheader("Servicios Judiciales")
    activas = filtrado[filtrado["nivel_alerta"].str.upper().isin(["ALTO", "ALTA", "MEDIA", "ATENCIÓN", "ATENCION"])]
    st.dataframe(activas.sort_values("riesgo_score", ascending=False), hide_index=True, use_container_width=True)

    if enviar_telegram is None:
        st.info("Módulo enviar_telegram.py no disponible.")
    elif not es_admin:
        st.info("Solo el Administrador puede enviar alertas.")
    else:
        tipo = st.selectbox("Enviar a", ["Comprador", "EPS", "Farmacia o distribuidor", "Auditor"])
        cantidad = st.slider("Cantidad por persona", 1, 10, 3)
        destinatarios = [p for p in leer_suscriptores() if p.get("rol") == tipo]
        elegidos = activas.sort_values("riesgo_score", ascending=False).head(cantidad)
        if st.button("Enviar alertas") and destinatarios and len(elegidos) > 0:
            enviadas = 0
            for p in destinatarios:
                for _, fila in elegidos.iterrows():
                    try:
                        if enviar_telegram(str(p["chat_id"]), f"Hola {p['nombre']}. {armar_mensaje(fila)}").get("ok"):
                            enviadas += 1
                    except Exception:
                        pass
                    time.sleep(0.4)
            st.success(f"Alertas enviadas: {enviadas}")


# ----- Red -----

with tab_red:
    st.subheader("Red")
    if os.path.exists("topologia_red.png"):
        st.image("topologia_red.png", caption="Topología de red")
    else:
        st.write("No se encontró topologia_red.png")


# ----- Noticias en tiempo real · ODS (al final, después de Red) -----

with tab_ods:
    st.subheader("Noticias en tiempo real · ODS")
    config_ods = {
        "ODS 3 · Salud": ("salud hospitales medicamentos contratación Colombia", "hospital colombia"),
        "ODS 4 · Educación": ("educación colegios universidades contratación Colombia", "university bogota"),
        "ODS 9 · Transporte e Infraestructura": ("infraestructura vías transporte Colombia", "highway colombia"),
        "ODS 11 · Vivienda": ("vivienda obras ciudades Colombia", "bogota city"),
        "ODS 16 · Contratación y Transparencia": ("SECOP contratación pública Colombia", "courthouse law"),
    }
    ods_sel = st.selectbox("ODS", list(config_ods.keys()))
    if st.button("Actualizar"):
        obtener_noticias_ods.clear()
        buscar_fotos_fotografos.clear()
        st.rerun()

    consulta_rss, consulta_foto = config_ods[ods_sel]
    for nota in obtener_noticias_ods(consulta_rss, consulta_foto, max_notas=6):
        st.markdown('<div class="nota-fila">', unsafe_allow_html=True)
        col_foto, col_cuerpo = st.columns([1.2, 2.8], gap="medium")
        with col_foto:
            if nota["imagen"]:
                st.image(nota["imagen"], use_container_width=True)
            if nota["fotografo"]:
                st.markdown(f'<div class="credito-foto">{nota["fotografo"]}</div>', unsafe_allow_html=True)
        with col_cuerpo:
            meta_der = f"{nota['fuente']} · {nota['fecha']}" if nota["fecha"] else nota["fuente"]
            st.markdown(f'<span class="tag-ods">{ods_sel}</span> <small><b>{meta_der}</b></small>', unsafe_allow_html=True)
            st.markdown(f"#### {nota['titulo']}")
            st.write(nota["intro"])
            if nota["url"]:
                st.link_button("Leer noticia", nota["url"])
        st.markdown("</div>", unsafe_allow_html=True)

#==========KPIs, PCA y Kmeans==========

FEATURES_PCA = [
    "hhi_valor",
    "hhi_n",
    "pct_valor_directa",
    "pct_valor_regimen_esp",
    "pct_contratos_ops",
    "pct_valor_pyme",
    "pct_valor_ene_feb_anual",
    "pct_valor_nov_dic_anual",
    "hhi_ordenador",
    "duracion_mediana_dias",
    "log_valor_total",
    "pct_valor_inversion",
    "tasa_contratos_modificados",
]

ETIQUETAS_KPI = {
    "hhi_valor": "Concentración de proveedores por valor (HHI)",
    "hhi_n": "Concentración de proveedores por # contratos (HHI)",
    "pct_valor_directa": "% del valor en contratación directa",
    "pct_valor_regimen_esp": "% del valor en régimen especial",
    "pct_contratos_ops": "% de contratos de prestación de servicios",
    "pct_valor_pyme": "% del valor adjudicado a Pymes",
    "pct_valor_ene_feb_anual": "% firmado en enero-febrero (prom. anual)",
    "pct_valor_nov_dic_anual": "% firmado en noviembre-diciembre (prom. anual)",
    "hhi_ordenador": "Concentración de ordenadores del gasto (HHI)",
    "duracion_mediana_dias": "Duración mediana del contrato (días)",
    "log_valor_total": "Escala presupuestal (log del valor total)",
    "pct_valor_inversion": "% del valor destinado a inversión",
    "tasa_contratos_modificados": "Tasa de contratos modificados/cedidos/suspendidos",
}

RUTA_KPIS = "kpis_entidades.csv"  # tabla ya calculada (1 fila por entidad)
RUTAS_RAW = ["datos_region_andina.xls", "datos_region_andina.csv", "datos_region_andina.xlsx"]

COLS_RAW_OBLIGATORIAS = [
    "id_contrato", "nombre_entidad", "proveedor_adjudicado", "valor_del_contrato",
    "fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato",
    "modalidad_de_contratacion", "tipo_de_contrato", "es_pyme", "destino_gasto",
    "estado_contrato", "n_mero_de_documento_ordenador_del_gasto",
]


# ---------- Preparación (misma lógica del notebook) ----------

def _normalizar_texto(texto):
    """MAYÚSCULAS, sin tildes ni puntuación, espacios colapsados."""
    if pd.isna(texto):
        return np.nan
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.upper().replace(".", "")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if t else np.nan


def _normalizar_serie(s):
    mapa = {v: _normalizar_texto(v) for v in s.dropna().unique()}
    return s.map(mapa)


def _a_fecha(s):
    try:
        return pd.to_datetime(s, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return pd.to_datetime(s, errors="coerce")


def _leer_tabla(origen):
    """Lee un CSV (aunque se llame .xls, como el del notebook) o un Excel real."""
    try:
        df = pd.read_csv(origen, dtype=str, low_memory=False, encoding="utf-8-sig")
        if df.shape[1] < 3:
            raise ValueError("no parece CSV")
    except Exception:
        if hasattr(origen, "seek"):
            origen.seek(0)
        df = pd.read_excel(origen, dtype=str)  # .xls real requiere xlrd; .xlsx requiere openpyxl
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df


def calcular_kpis_entidades(df):
    """Del archivo de contratos (1 fila por contrato) a la tabla de 13 KPIs por entidad."""
    faltan = [c for c in COLS_RAW_OBLIGATORIAS if c not in df.columns]
    if faltan:
        raise ValueError("Faltan columnas en el archivo de contratos: " + ", ".join(faltan))

    d = df.drop_duplicates().copy()
    d["valor_del_contrato"] = pd.to_numeric(d["valor_del_contrato"], errors="coerce")
    for c in ["fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato"]:
        d[c] = _a_fecha(d[c])
    d["entidad_norm"] = _normalizar_serie(d["nombre_entidad"])
    d["proveedor_norm"] = _normalizar_serie(d["proveedor_adjudicado"])
    d = d[d["valor_del_contrato"] > 0].copy()  # = df_clean del notebook

    ent = d.groupby("entidad_norm").agg(
        total_contratos=("id_contrato", "nunique"),
        total_valor=("valor_del_contrato", "sum"),
    )
    idx = ent.index
    val = "valor_del_contrato"

    def valor_por_entidad(mascara):
        return d[mascara].groupby("entidad_norm")[val].sum().reindex(idx, fill_value=0)

    # KPI 1 y 2: HHI por valor y por número de contratos
    prov_valor = d.groupby(["entidad_norm", "proveedor_norm"])[val].sum()
    ent["hhi_valor"] = ((prov_valor / ent["total_valor"]) ** 2).groupby("entidad_norm").sum()
    prov_n = d.groupby(["entidad_norm", "proveedor_norm"])["id_contrato"].nunique()
    ent["hhi_n"] = ((prov_n / ent["total_contratos"]) ** 2).groupby("entidad_norm").sum()

    # KPI 3 y 4: contratación directa y régimen especial
    modalidad = d["modalidad_de_contratacion"]
    ent["pct_valor_directa"] = valor_por_entidad(modalidad.str.contains("directa", case=False, na=False)) / ent["total_valor"]
    ent["pct_valor_regimen_esp"] = valor_por_entidad(
        modalidad.str.contains("régimen especial|regimen especial", case=False, na=False)
    ) / ent["total_valor"]

    # KPI 5: prestación de servicios (OPS)
    es_ops = d["tipo_de_contrato"].str.contains("Prestación de servicios|Prestacion de servicios", case=False, na=False)
    conteo_ops = d[es_ops].groupby("entidad_norm")["id_contrato"].count().reindex(idx, fill_value=0)
    ent["pct_contratos_ops"] = conteo_ops / ent["total_contratos"]

    # KPI 6: Pymes
    es_pyme = d["es_pyme"].astype(str).str.strip().str.upper().isin(["SI", "SÍ", "TRUE", "1"])
    ent["pct_valor_pyme"] = valor_por_entidad(es_pyme) / ent["total_valor"]

    # KPI 7 y 8: estacionalidad (promedio de porcentajes anuales)
    d["anio_firma"] = d["fecha_de_firma"].dt.year
    d["mes_firma"] = d["fecha_de_firma"].dt.month
    d["_v_ef"] = np.where(d["mes_firma"].isin([1, 2]), d[val], 0)
    d["_v_nd"] = np.where(d["mes_firma"].isin([11, 12]), d[val], 0)
    anual = d.groupby(["entidad_norm", "anio_firma"]).agg(
        tot=(val, "sum"), ef=("_v_ef", "sum"), nd=("_v_nd", "sum")
    )
    ent["pct_valor_ene_feb_anual"] = (anual["ef"] / anual["tot"]).groupby("entidad_norm").mean().reindex(idx, fill_value=0)
    ent["pct_valor_nov_dic_anual"] = (anual["nd"] / anual["tot"]).groupby("entidad_norm").mean().reindex(idx, fill_value=0)

    # KPI 9: concentración de ordenadores del gasto (promedio anual)
    d["doc_ord"] = (
        d["n_mero_de_documento_ordenador_del_gasto"].astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": np.nan, "None": np.nan, "": np.nan, "0": np.nan})
    )
    ord_anual = d.dropna(subset=["doc_ord"]).groupby(["entidad_norm", "anio_firma", "doc_ord"])[val].sum()
    tot_ord = ord_anual.groupby(["entidad_norm", "anio_firma"]).sum()
    hhi_ord = ((ord_anual / tot_ord) ** 2).groupby(["entidad_norm", "anio_firma"]).sum()
    ent["hhi_ordenador"] = hhi_ord.groupby("entidad_norm").mean().reindex(idx, fill_value=1.0)

    # KPI 10: duración mediana (días)
    d["dias_reales"] = (d["fecha_de_fin_del_contrato"] - d["fecha_de_inicio_del_contrato"]).dt.days
    d.loc[(d["dias_reales"] < 0) | (d["dias_reales"] > 3650), "dias_reales"] = np.nan
    ent["duracion_mediana_dias"] = d.groupby("entidad_norm")["dias_reales"].median()
    ent["duracion_mediana_dias"] = ent["duracion_mediana_dias"].fillna(ent["duracion_mediana_dias"].median())

    # KPI 11: escala presupuestal e inversión
    ent["log_valor_total"] = np.log1p(ent["total_valor"])
    es_inv = d["destino_gasto"].astype(str).str.contains("Inversión|Inversion", case=False, na=False)
    ent["pct_valor_inversion"] = valor_por_entidad(es_inv) / ent["total_valor"]

    # KPI 12: contratos modificados / cedidos / suspendidos
    es_desv = d["estado_contrato"].astype(str).str.contains("modificad|cedid|suspendid", case=False, na=False)
    desv = d[es_desv].groupby("entidad_norm")["id_contrato"].nunique().reindex(idx, fill_value=0)
    ent["tasa_contratos_modificados"] = desv / ent["total_contratos"]

    # Departamento más frecuente de cada entidad (para filtrar en la app)
    if "departamento" in d.columns:
        ent["departamento"] = d.groupby("entidad_norm")["departamento"].agg(
            lambda s: s.mode().iat[0] if s.notna().any() else "Sin departamento"
        )
    else:
        ent["departamento"] = "Sin departamento"
    return ent


def _tabla_kpis(df):
    """Acepta el CSV de contratos (se calculan los KPIs) o la tabla de KPIs ya lista."""
    if {"total_contratos", "hhi_valor"}.issubset(df.columns):
        if "entidad_norm" not in df.columns:
            raise ValueError("La tabla de KPIs debe tener la columna 'entidad_norm'.")
        ent = df.set_index("entidad_norm").copy()
        for c in ["total_contratos", "total_valor"] + FEATURES_PCA:
            if c not in ent.columns:
                raise ValueError(f"Falta la columna '{c}' en la tabla de KPIs.")
            ent[c] = pd.to_numeric(ent[c], errors="coerce")
        if "departamento" not in ent.columns:
            ent["departamento"] = "Sin departamento"
        return ent
    return calcular_kpis_entidades(df)


@st.cache_data(show_spinner="Procesando archivo (los contratos crudos pueden tardar 1-3 minutos)...")
def _tabla_desde_ruta(ruta, fecha_modif):
    return _tabla_kpis(_leer_tabla(ruta))


# ---------- Modelo: PCA + K-Means ----------

@st.cache_data(show_spinner="Ajustando PCA y K-Means...")
def ejecutar_pca_kmeans(ent, min_contratos, k):
    dfm = ent[ent["total_contratos"] >= min_contratos].copy()
    if len(dfm) < max(k, 8):
        raise ValueError("Muy pocas entidades con ese mínimo de contratos. Baja el filtro.")
    dfm["duracion_mediana_dias"] = dfm["duracion_mediana_dias"].clip(lower=0)
    X = dfm[FEATURES_PCA].fillna(0)
    corr = X.corr()

    X_esc = StandardScaler().fit_transform(X)
    pca = PCA()
    X_pca = pca.fit_transform(X_esc)

    tabla = pd.DataFrame({
        "Componente": [f"PC{i + 1}" for i in range(len(FEATURES_PCA))],
        "Valor propio": pca.explained_variance_,
        "Varianza %": pca.explained_variance_ratio_ * 100,
        "Acumulada %": np.cumsum(pca.explained_variance_ratio_) * 100,
    })
    k_kaiser = int((tabla["Valor propio"] > 1).sum())
    n_comp = max(2, k_kaiser)
    cargas = pd.DataFrame(
        pca.components_[:n_comp].T,
        columns=[f"PC{i + 1}" for i in range(n_comp)],
        index=FEATURES_PCA,
    )

    Z = X_pca[:, :n_comp]
    filas = []
    for kk in range(2, 9):
        km = KMeans(n_clusters=kk, random_state=42, n_init=20)
        etiquetas = km.fit_predict(Z)
        filas.append({"k": kk, "Inercia": km.inertia_, "Silhouette": silhouette_score(Z, etiquetas)})
    metricas_k = pd.DataFrame(filas)

    km_final = KMeans(n_clusters=k, random_state=42, n_init=30)
    dfm["Cluster"] = km_final.fit_predict(Z)
    for i in range(n_comp):
        dfm[f"PC{i + 1}"] = X_pca[:, i]

    return {
        "dfm": dfm, "corr": corr, "tabla": tabla, "cargas": cargas,
        "k_kaiser": k_kaiser, "n_comp": n_comp, "metricas_k": metricas_k,
    }


# ---------- Interfaz ----------

with tab_kpi:
    st.subheader("KPIs, PCA y K-Means de entidades públicas")
    st.caption(
        "Trece indicadores de contratación por entidad → PCA (componentes con valor propio > 1) "
        "→ K-Means sobre esos componentes."
    )

    # 1) Origen de los datos
    kp_tabla = st.session_state.get("kp_tabla")
    kp_origen = st.session_state.get("kp_origen", "")

    if kp_tabla is None and os.path.exists(RUTA_KPIS):
        try:
            kp_tabla = _tabla_desde_ruta(RUTA_KPIS, os.path.getmtime(RUTA_KPIS))
            kp_origen = RUTA_KPIS
        except Exception as e:
            st.error(f"No se pudo leer {RUTA_KPIS}: {e}")

    kp_raw_local = next((r for r in RUTAS_RAW if os.path.exists(r)), None)

    with st.expander("Datos de esta sección (cargar o recalcular)", expanded=kp_tabla is None):
        st.write(
            "Se acepta **(a)** `kpis_entidades.csv` (una fila por entidad, carga instantánea) o "
            "**(b)** el archivo de contratos `datos_region_andina.xls` (es un CSV con extensión .xls; "
            "los KPIs se calculan aquí y tarda unos minutos)."
        )
        kp_subido = st.file_uploader("Subir archivo", type=["csv", "xls", "xlsx"], key="kp_uploader")
        if kp_subido is not None and st.button("Procesar archivo subido"):
            try:
                with st.spinner("Procesando..."):
                    st.session_state["kp_tabla"] = _tabla_kpis(_leer_tabla(kp_subido))
                    st.session_state["kp_origen"] = f"subido: {kp_subido.name}"
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo procesar el archivo: {e}")

        if kp_raw_local and st.button(f"Calcular KPIs desde {kp_raw_local}"):
            try:
                st.session_state["kp_tabla"] = _tabla_desde_ruta(kp_raw_local, os.path.getmtime(kp_raw_local))
                st.session_state["kp_origen"] = kp_raw_local
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo calcular: {e}")

        if "kp_tabla" in st.session_state and st.button("Quitar datos cargados"):
            st.session_state.pop("kp_tabla", None)
            st.session_state.pop("kp_origen", None)
            st.rerun()

    if kp_tabla is None:
        st.info("Sube `kpis_entidades.csv` o el archivo de contratos para ver esta sección.")
    else:
        st.sidebar.write("KPIs: " + kp_origen)
        st.download_button(
            "Descargar tabla de KPIs por entidad (kpis_entidades.csv)",
            kp_tabla.reset_index().to_csv(index=False).encode("utf-8-sig"),
            file_name="kpis_entidades.csv",
            mime="text/csv",
        )

        # 2) Parámetros
        p1, p2 = st.columns(2)
        kp_min = p1.slider("Mínimo de contratos por entidad", 1, 100, 10)
        kp_k = p2.slider("Número de clústeres (k)", 2, 8, 4)

        try:
            res = ejecutar_pca_kmeans(kp_tabla, kp_min, kp_k)
        except Exception as e:
            st.error(str(e))
            st.stop()

        dfm = res["dfm"]
        n_comp = res["n_comp"]
        var_pc = res["tabla"]["Varianza %"].tolist()

        m1, m2, m3 = st.columns(3)
        m1.metric("Entidades en el modelo", len(dfm))
        m2.metric("Componentes (Kaiser)", res["k_kaiser"])
        m3.metric("Varianza explicada", f"{res['tabla']['Acumulada %'].iloc[n_comp - 1]:.1f}%")

        sub_kpi, sub_pca, sub_k, sub_cl = st.tabs(["KPIs", "PCA", "Elegir k", "Clústeres"])

        # --- KPIs ---
        with sub_kpi:
            st.markdown("**Descripción de los 13 indicadores**")
            st.dataframe(
                pd.DataFrame({"KPI": FEATURES_PCA, "Qué mide": [ETIQUETAS_KPI[c] for c in FEATURES_PCA]}),
                hide_index=True, use_container_width=True,
            )
            kp_sel = st.selectbox("Distribución de un KPI", FEATURES_PCA, format_func=lambda c: ETIQUETAS_KPI[c])
            st.plotly_chart(
                px.histogram(dfm, x=kp_sel, nbins=40, color_discrete_sequence=["#0F294A"],
                             labels={kp_sel: ETIQUETAS_KPI[kp_sel]}),
                use_container_width=True,
            )
            st.markdown("**Matriz de correlación** (se busca que no haya pares con |r| > 0.85)")
            st.plotly_chart(
                px.imshow(res["corr"].round(2), text_auto=True, zmin=-1, zmax=1,
                          color_continuous_scale="RdBu_r", aspect="auto", height=560),
                use_container_width=True,
            )
            c = res["corr"].abs().where(~np.eye(len(res["corr"]), dtype=bool))
            fuertes = [(a, b) for a in c.index for b in c.columns if a < b and c.loc[a, b] > 0.85]
            if fuertes:
                st.warning("Pares con colinealidad alta: " + ", ".join(f"{a} / {b}" for a, b in fuertes))
            else:
                st.success("Ningún par de KPIs supera |r| > 0.85.")

        # --- PCA ---
        with sub_pca:
            tabla = res["tabla"]
            fig_sc = go.Figure()
            fig_sc.add_bar(x=tabla["Componente"], y=tabla["Valor propio"], marker_color="#0F294A", name="Valor propio")
            fig_sc.add_hline(y=1, line_dash="dash", line_color="#C81E1E", annotation_text="Kaiser (λ = 1)")
            fig_sc.update_layout(title="Valores propios (scree plot)", height=360, yaxis_title="Valor propio")
            st.plotly_chart(fig_sc, use_container_width=True)
            st.dataframe(tabla.round(3), hide_index=True, use_container_width=True)

            st.markdown(f"**Cargas de los {n_comp} componentes retenidos**")
            st.dataframe(res["cargas"].round(3), use_container_width=True)
            st.plotly_chart(
                px.imshow(res["cargas"].round(2), text_auto=True, zmin=-1, zmax=1,
                          color_continuous_scale="RdBu_r", aspect="auto", height=520),
                use_container_width=True,
            )

        # --- Elegir k ---
        with sub_k:
            mk = res["metricas_k"]
            ca, cb = st.columns(2)
            ca.plotly_chart(
                px.line(mk, x="k", y="Inercia", markers=True, title="Método del codo"),
                use_container_width=True,
            )
            cb.plotly_chart(
                px.line(mk, x="k", y="Silhouette", markers=True, title="Coeficiente de silueta"),
                use_container_width=True,
            )
            st.dataframe(mk.round(4), hide_index=True, use_container_width=True)
            st.caption(f"Mayor silueta: k = {int(mk.loc[mk['Silhouette'].idxmax(), 'k'])}. "
                       f"Actualmente seleccionado: k = {kp_k}.")

        # --- Clústeres ---
        with sub_cl:
            deptos_kp = sorted(dfm["departamento"].dropna().astype(str).unique())
            if sesion.get("departamento") and rol in ["Comprador", "EPS", "Farmacia o distribuidor", "Auditor"]:
                mis = _normalizar_texto(sesion["departamento"])
                dfm_v = dfm[dfm["departamento"].astype(str).map(_normalizar_texto) == mis]
            else:
                dfm_v = dfm
            sel_depto = st.multiselect("Filtrar por departamento (solo la vista; los clústeres no cambian)", deptos_kp)
            if sel_depto:
                dfm_v = dfm_v[dfm_v["departamento"].isin(sel_depto)]

            pcs = [f"PC{i + 1}" for i in range(n_comp)]
            ex, ey = st.columns(2)
            eje_x = ex.selectbox("Eje X", pcs, index=0)
            eje_y = ey.selectbox("Eje Y", pcs, index=1)
            graf = dfm_v.reset_index().rename(columns={"entidad_norm": "entidad"})
            graf["Cluster"] = graf["Cluster"].astype(str)
            fig_cl = px.scatter(
                graf, x=eje_x, y=eje_y, color="Cluster", hover_name="entidad",
                hover_data=["departamento", "total_contratos"],
                category_orders={"Cluster": [str(i) for i in range(kp_k)]},
                labels={eje_x: f"{eje_x} ({var_pc[pcs.index(eje_x)]:.1f}%)",
                        eje_y: f"{eje_y} ({var_pc[pcs.index(eje_y)]:.1f}%)"},
                height=520,
            )
            st.plotly_chart(fig_cl, use_container_width=True)

            st.markdown("**Entidades por clúster**")
            st.dataframe(
                dfm["Cluster"].value_counts().sort_index().rename("Entidades").rename_axis("Cluster").reset_index(),
                hide_index=True, use_container_width=True,
            )

            st.markdown("**Perfil de cada clúster** (desviaciones estándar frente al promedio general; rojo = por encima)")
            perfil = dfm.groupby("Cluster")[FEATURES_PCA].mean()
            z = (perfil - dfm[FEATURES_PCA].mean()) / dfm[FEATURES_PCA].std().replace(0, 1)
            st.plotly_chart(
                px.imshow(z.T.round(2), text_auto=True, color_continuous_scale="RdBu_r", zmin=-2, zmax=2,
                          aspect="auto", height=540, labels=dict(x="Cluster", y="KPI")),
                use_container_width=True,
            )
            st.dataframe(perfil.T.round(3), use_container_width=True)

            cl_ver = st.selectbox("Ver entidades de mayor presupuesto del clúster", sorted(dfm["Cluster"].unique()))
            top_cl = (
                dfm_v[dfm_v["Cluster"] == cl_ver]
                .sort_values("total_valor", ascending=False)
                .head(15)[["departamento", "total_contratos", "total_valor"] + FEATURES_PCA]
                .reset_index()
                .rename(columns={"entidad_norm": "entidad"})
            )
            st.dataframe(top_cl, hide_index=True, use_container_width=True)

            st.download_button(
                "Descargar resultado completo (entidad, clúster, componentes)",
                dfm.reset_index().to_csv(index=False).encode("utf-8-sig"),
                file_name="entidades_clusters.csv",
                mime="text/csv",
            )
