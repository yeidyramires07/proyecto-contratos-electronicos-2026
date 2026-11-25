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

try:
    from modulo_secop_original import mostrar_dashboard_secop
except Exception:
    mostrar_dashboard_secop = None

st.set_page_config(page_title="Contratación Andina", layout="wide")

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

ROLES_INSTITUCIONALES = ["Fiscalia", "Policia", "Juez", "Gobierno"]

PALETA_ALERTAS = {
    "Alta": "#E11D48",
    "Alto": "#E11D48",
    "Media": "#D97706",
    "Medio": "#D97706",
    "Baja": "#0284C7",
    "Bajo": "#0284C7",
    "Sin alerta": "#94A3B8",
}

ESCALA_AZUL_CLARA = [
    [0.0, "#DBEAFE"],
    [0.5, "#60A5FA"],
    [1.0, "#1D4ED8"],
]

st.markdown(
    """
    <style>
        .stApp { background-color: #FFFFFF; color: #111827; }
        [data-testid="stSidebar"] { background-color: #F8FAFC; border-right: 1px solid #E2E8F0; }

        .block-container {
            padding-top: 2.7rem !important;
        }

        .cabecera-portal {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1.5px solid #E2E8F0;
            padding: 6px 4px 10px 4px;
            margin-bottom: 10px;
        }
        .fecha-sub {
            font-size: 0.78rem;
            color: #475569;
            margin-top: 2px;
        }
        .badge-estado {
            background-color: #F8FAFC;
            color: #0F294A;
            border: 1px solid #CBD5E1;
            font-weight: 600;
            font-size: 0.7rem;
            padding: 4px 10px;
            border-radius: 999px;
        }
        .hero-topologia {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 6px;
            background-color: #F8FAFC;
            margin-bottom: 8px;
        }
        .seccion-mini-titulo {
            font-size: 0.82rem;
            font-weight: 700;
            color: #0F294A;
            margin: 8px 0 4px 0;
        }
        .tira-noticias {
            display: flex;
            flex-direction: row;
            gap: 8px;
            overflow-x: auto;
            padding: 2px 0 6px 0;
            margin-bottom: 6px;
        }
        .nota-mini {
            flex: 1 1 0;
            min-width: 165px;
            max-width: 230px;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 5px 7px;
            background-color: #FFFFFF;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .nota-mini img {
            width: 100%;
            height: 44px;
            object-fit: cover;
            border-radius: 4px;
            margin-bottom: 3px;
        }
        .nota-mini-meta {
            font-size: 0.62rem;
            color: #64748B;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .nota-mini-titulo {
            font-size: 0.72rem;
            font-weight: 600;
            color: #111827;
            line-height: 1.18;
            margin: 2px 0 4px 0;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .nota-mini-link {
            font-size: 0.68rem;
            font-weight: 600;
            color: #1D4ED8;
            text-decoration: none;
        }
        div[data-testid="stButton"] > button[kind="secondary"] {
            border-radius: 6px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def logo_minimalista(size=34):
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 36 36" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle;">'
        '<path d="M5 26L14.5 12L21 22L25.5 15.5L31 26" stroke="#0F294A" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="25.5" cy="10" r="2.6" fill="#2563EB"/>'
        "</svg>"
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
            fotos = [
                (item.get("urls") or {}).get("regular")
                for item in resp.json().get("results", [])
                if (item.get("urls") or {}).get("regular")
            ]
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
                "iiprop": "url",
                "iiurlwidth": 360,
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
            url_foto = infos[0].get("thumburl") or infos[0].get("url")
            if url_foto and not url_foto.lower().endswith(".svg"):
                fotos.append(url_foto)
            if len(fotos) >= max_fotos:
                break
        return fotos
    except Exception:
        return []


@st.cache_data(ttl=900)
def obtener_noticias_rss(consulta, termino_foto, max_notas=6):
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
            fecha_pub = (item.findtext("pubDate") or "").strip()[:11]
            imagen = fotos_reales[idx % len(fotos_reales)] if fotos_reales else None
            notas.append({
                "titulo": titulo,
                "url": enlace,
                "fuente": fuente_n,
                "fecha": fecha_pub,
                "imagen": imagen,
            })
    except Exception:
        pass
    return notas


def render_tira_noticias(notas):
    if not notas:
        return
    bloques = ['<div class="tira-noticias">']
    for nota in notas:
        img_tag = f'<img src="{nota["imagen"]}" alt="">' if nota["imagen"] else ""
        meta = f"{nota['fuente']} · {nota['fecha']}" if nota["fecha"] else nota["fuente"]
        enlace_tag = (
            f'<a class="nota-mini-link" href="{nota["url"]}" target="_blank">Leer →</a>'
            if nota["url"] else ""
        )
        tarjeta = (
            f'<div class="nota-mini">'
            f'<div>{img_tag}<div class="nota-mini-meta">{meta}</div>'
            f'<div class="nota-mini-titulo">{nota["titulo"]}</div></div>'
            f'<div>{enlace_tag}</div></div>'
        )
        bloques.append(tarjeta)
    bloques.append("</div>")
    st.markdown("".join(bloques), unsafe_allow_html=True)


@st.cache_data(ttl=600)
def leer_csv(archivo):
    df = pd.read_csv(archivo, encoding="utf-8-sig", low_memory=False)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df


def cargar_datos(archivo_subido=None):
    if archivo_subido is not None:
        return leer_csv(archivo_subido), archivo_subido.name
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
    if "pct_contratacion_directa" not in out.columns:
        out["pct_contratacion_directa"] = out["pagos_sin_soporte_pct"]
    else:
        out["pct_contratacion_directa"] = pd.to_numeric(out["pct_contratacion_directa"], errors="coerce").fillna(out["pagos_sin_soporte_pct"])
    if "pct_modificados" in out.columns:
        out["pct_modificados"] = pd.to_numeric(out["pct_modificados"], errors="coerce").fillna(0.0)
    if "contratos" in out.columns:
        out["contratos"] = pd.to_numeric(out["contratos"], errors="coerce").fillna(0.0)
    if "valor_total_cop" in out.columns:
        out["valor_total_cop"] = pd.to_numeric(out["valor_total_cop"], errors="coerce").fillna(0.0)
    if "riesgo_score" not in out.columns:
        out["riesgo_score"] = (
            (out["hhi_valor"] / 1000.0).clip(0, 1) * 50.0
            + (out["pagos_sin_soporte_pct"] / 100.0).clip(0, 1) * 50.0
        ).round(2)
    out["riesgo_score"] = pd.to_numeric(out["riesgo_score"], errors="coerce").fillna(0.0)
    out["nivel_alerta"] = out.get("nivel_alerta", "Sin alerta")
    out["nivel_alerta"] = out["nivel_alerta"].fillna("Sin alerta").astype(str).str.strip()
    return out


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
    except Exception:
        return "$0"


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

    if len(sub) > 0:
        max_hhi = max(float(sub["hhi_promedio"].max()), 1.0)
        textos = [
            f"<b>{r['departamento']}</b><br>"
            f"Directa: {round(r['soporte_pct'], 1)}%<br>"
            f"HHI: {round(r['hhi_promedio'], 1)}"
            for _, r in sub.iterrows()
        ]
        fig.add_trace(go.Scattermap(
            lat=sub["lat"],
            lon=sub["lon"],
            mode="markers",
            hovertext=textos,
            hoverinfo="text",
            marker=dict(
                size=13 + 22 * (sub["hhi_promedio"] / max_hhi),
                color=sub["soporte_pct"],
                colorscale=ESCALA_AZUL_CLARA,
                showscale=True,
                colorbar=dict(title="% Directa"),
            ),
        ))

    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=5.2, lon=-74.1), zoom=5.5),
        height=490,
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def filtrar_por_umbral(df, umb_hhi, umb_cr4, umb_directa, regla="Cualquiera (OR)"):
    cond_hhi = df["hhi_valor"] >= umb_hhi
    cond_cr4 = df["cr4_valor"] >= umb_cr4
    cond_dir = df["pagos_sin_soporte_pct"] >= umb_directa
    if regla == "Todos (AND)":
        return df[cond_hhi & cond_cr4 & cond_dir]
    return df[cond_hhi | cond_cr4 | cond_dir]


def armar_mensaje(fila, rol_destino="Gobierno", nombre_destino="funcionario"):
    entidad = str(fila["entidad"]).title()
    depto = fila["departamento"]
    sector = fila["sector"]
    alerta = fila["nivel_alerta"]
    hhi = round(float(fila["hhi_valor"]), 1)
    cr4 = round(float(fila["cr4_valor"]), 1)
    directa = round(float(fila["pagos_sin_soporte_pct"]), 1)
    base = (
        f"Entidad: {entidad} ({depto}) | Sector: {sector} | Alerta: {alerta} "
        f"| HHI: {hhi} | CR4: {cr4}% | Directa: {directa}%."
    )

    if rol_destino == "Fiscalia":
        return f"Hola {nombre_destino} (Fiscalia). {base}"
    if rol_destino == "Policia":
        return f"Hola {nombre_destino} (Policia). {base}"
    if rol_destino == "Juez":
        return f"Hola {nombre_destino} (Juez). {base}"
    return f"Hola {nombre_destino} (Gobierno). {base}"


def leer_suscriptores():
    try:
        return [dict(p) for p in st.secrets["suscriptores"]]
    except Exception:
        return []


def telegram_ok(respuesta):
    if isinstance(respuesta, dict):
        return bool(respuesta.get("ok"))
    return bool(respuesta)


def localizar_imagen_red():
    carpeta_app = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(carpeta_app, "topologia_red.png"),
        os.path.join(carpeta_app, "topologia_red.png.png"),
        os.path.join(carpeta_app, "topologia_red.jpg"),
        os.path.join(carpeta_app, "topologia_red.jpeg"),
    ]
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta

    try:
        for nombre in os.listdir(carpeta_app):
            base, ext = os.path.splitext(nombre)
            if base.lower().startswith("topologia_red") and ext.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                ruta_completa = os.path.join(carpeta_app, nombre)
                if os.path.isfile(ruta_completa):
                    return ruta_completa
    except Exception:
        pass
    return None


# ----- Acceso a la plataforma -----

if "sesion" not in st.session_state:
    _, col_centro, _ = st.columns([1, 2, 1])
    with col_centro:
        st.markdown(
            f"""
            <div style="text-align:center; padding-top:20px; margin-bottom:16px;">
                <div style="margin-bottom:8px;">{logo_minimalista(46)}</div>
                <div style="font-family: Georgia, 'Times New Roman', serif; font-size:1.85rem; font-weight:500; color:#0F294A; letter-spacing:0.01em;">
                    Contratación Andina
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        usuario_escrito = st.text_input("Usuario")
        clave_escrita = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            resultado, datos_usuario = iniciar_sesion(usuario_escrito.strip().lower(), clave_escrita)
            if resultado == "ok":
                st.session_state["sesion"] = datos_usuario
                st.rerun()
            elif resultado == "sin_base":
                st.warning("Sin conexión a base de datos.")
            else:
                st.error("Usuario o contraseña incorrectos.")

        if st.button("Entrar como invitado"):
            st.session_state["sesion"] = {"nombre": "Invitado", "rol": "Invitado", "departamento": None}
            st.rerun()
    st.stop()


if "vista_activa" not in st.session_state:
    st.session_state["vista_activa"] = "inicio"

NOMBRES_PESTANAS = [
    "SECOP · Alertas",
    "Mapa Andino",
    "Dashboard interactivo",
    "Riesgo y Cómputo",
    "Servicios Judiciales",
]


# ----- Encabezado: título + logo arriba de la fecha, clicables para volver al inicio -----

fecha_texto = datetime.now().strftime("%d/%m/%Y")
c_izq, c_der = st.columns([4, 1])
with c_izq:
    if st.button("▲ Contratación Andina", key="btn_titulo_inicio"):
        st.session_state["vista_activa"] = "inicio"
        st.rerun()
    st.markdown(f'<div class="fecha-sub"><strong>{fecha_texto}</strong> · Región Andina</div>', unsafe_allow_html=True)
with c_der:
    st.markdown('<div style="display:flex;justify-content:flex-end;padding-top:4px;"><span class="badge-estado">SECOP II</span></div>', unsafe_allow_html=True)

st.markdown('<div style="border-bottom:1.5px solid #E2E8F0;margin-bottom:8px;"></div>', unsafe_allow_html=True)

sesion = st.session_state["sesion"]
rol = sesion["rol"]
es_admin = rol == "Administrador"

datos_crudos, fuente = cargar_datos(st.session_state.get("archivo_csv_subido"))
contratos = preparar_datos(datos_crudos)

if sesion.get("departamento") and rol in ROLES_INSTITUCIONALES + ["Comprador", "EPS", "Farmacia o distribuidor", "Auditor"]:
    contratos = contratos[contratos["departamento"] == sesion["departamento"]]

st.sidebar.write(f"**{sesion['nombre']}** · {rol}")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear()
    st.rerun()

st.sidebar.header("Filtros")
departamentos = st.sidebar.multiselect("Departamento", sorted(contratos["departamento"].unique()))
sectores = st.sidebar.multiselect("Sector", sorted(contratos["sector"].unique()))
niveles = st.sidebar.multiselect("Alerta", sorted(contratos["nivel_alerta"].unique()))

filtrado = contratos.copy()
if departamentos:
    filtrado = filtrado[filtrado["departamento"].isin(departamentos)]
if sectores:
    filtrado = filtrado[filtrado["sector"].isin(sectores)]
if niveles:
    filtrado = filtrado[filtrado["nivel_alerta"].isin(niveles)]

st.sidebar.caption(f"{fuente} · {len(filtrado)}/{len(contratos)}")


# ----- Imagen de topología de red (clic para volver al inicio) -----

ruta_imagen_red = localizar_imagen_red()
if ruta_imagen_red:
    st.markdown('<div class="hero-topologia">', unsafe_allow_html=True)
    st.image(ruta_imagen_red, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Inicio · Topología", key="btn_topologia_inicio"):
        st.session_state["vista_activa"] = "inicio"
        st.rerun()


# ----- Pestañas justo debajo de la imagen de topología -----

pestana_elegida = st.radio(
    "Secciones",
    NOMBRES_PESTANAS,
    index=None,
    horizontal=True,
    label_visibility="collapsed",
    key="selector_pestana_top",
)

if pestana_elegida is not None and pestana_elegida != st.session_state.get("ultimo_radio"):
    st.session_state["ultimo_radio"] = pestana_elegida
    st.session_state["vista_activa"] = pestana_elegida
    st.rerun()

vista = st.session_state["vista_activa"]


# ----- Vista de inicio: noticias Región Andina y luego tiempo real -----

if vista == "inicio":
    st.markdown('<div class="seccion-mini-titulo">Noticias · Región Andina</div>', unsafe_allow_html=True)
    notas_andina = obtener_noticias_rss(
        "contratación pública Antioquia Boyacá Caldas Cundinamarca Huila Santander Tolima",
        "colombia mountains city",
        max_notas=6,
    )
    render_tira_noticias(notas_andina)

    st.markdown('<div class="seccion-mini-titulo">Noticias · Tiempo real</div>', unsafe_allow_html=True)
    notas_rt = obtener_noticias_rss(
        "SECOP contratación pública Colombia hoy",
        "office government building",
        max_notas=6,
    )
    render_tira_noticias(notas_rt)


# ----- Pestaña 1: SECOP · Alertas -----

elif vista == "SECOP · Alertas":
    if mostrar_dashboard_secop is not None:
        mostrar_dashboard_secop()
    else:
        st.info("No se encontró `modulo_secop_original.py`.")


# ----- Pestaña 2: Mapa Andino -----

elif vista == "Mapa Andino":
    df_kpi = filtrado if len(filtrado) > 0 else contratos

    if len(df_kpi) > 0:
        k1, k2, k3, k4, k5 = st.columns(5)
        total_contratos_txt = f"{int(df_kpi['contratos'].sum()):,}" if "contratos" in df_kpi.columns else f"{len(df_kpi):,}"
        total_valor_txt = formato_cop(df_kpi["valor_total_cop"].sum()) if "valor_total_cop" in df_kpi.columns else f"{len(df_kpi):,}"
        k1.metric("Contratos", total_contratos_txt)
        k2.metric("Valor total", total_valor_txt)
        k3.metric("HHI promedio", f"{df_kpi['hhi_valor'].mean():,.1f}")
        k4.metric("CR4 promedio", f"{df_kpi['cr4_valor'].mean():,.1f}%")
        k5.metric("Riesgo promedio", f"{df_kpi['riesgo_score'].mean():,.2f}")

    st.divider()
    por_depto_mapa = filtrado.groupby("departamento", as_index=False).agg(
        hhi_promedio=("hhi_valor", "mean"),
        soporte_pct=("pagos_sin_soporte_pct", "mean"),
    ).sort_values("soporte_pct", ascending=False)

    st.plotly_chart(construir_mapa_andina(por_depto_mapa), use_container_width=True)

    if len(por_depto_mapa) > 0:
        fig_colores = px.bar(
            por_depto_mapa,
            x="departamento",
            y="soporte_pct",
            color="soporte_pct",
            color_continuous_scale=ESCALA_AZUL_CLARA,
            labels={"soporte_pct": "% Directa", "departamento": "Departamento"},
            title="Contratación directa (%)",
        )
        fig_colores.update_layout(height=320)
        st.plotly_chart(fig_colores, use_container_width=True)

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(filtrado))
    c2.metric("HHI promedio", round(float(filtrado["hhi_valor"].mean()), 1) if len(filtrado) else 0.0)
    c3.metric("Alertas altas", int(filtrado["nivel_alerta"].str.upper().isin(["ALTO", "ALTA"]).sum()))

    st.markdown("#### Por sector")
    por_sector = filtrado.groupby("sector", as_index=False).agg(
        registros=("entidad", "count"),
        hhi_promedio=("hhi_valor", "mean"),
        contratacion_directa_pct=("pagos_sin_soporte_pct", "mean"),
    )
    por_sector["hhi_promedio"] = por_sector["hhi_promedio"].round(1)
    por_sector["contratacion_directa_pct"] = por_sector["contratacion_directa_pct"].round(1)
    st.dataframe(por_sector, hide_index=True, use_container_width=True)

    st.markdown("#### HHI por departamento")
    por_depto = filtrado.groupby("departamento", as_index=False).agg(
        hhi_promedio=("hhi_valor", "mean"),
    ).sort_values("hhi_promedio", ascending=False)
    st.plotly_chart(
        px.bar(
            por_depto,
            x="departamento",
            y="hhi_promedio",
            color_discrete_sequence=["#2563EB"],
            labels={"hhi_promedio": "HHI", "departamento": "Departamento"},
        ),
        use_container_width=True,
    )


# ----- Pestaña 3: Dashboard interactivo -----

elif vista == "Dashboard interactivo":
    metrica_elegida = st.selectbox(
        "Indicador",
        ["riesgo_score", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct"],
    )
    top_n = st.slider("Entidades", 5, 30, 10)

    top_dash = filtrado.sort_values(metrica_elegida, ascending=False).head(top_n)
    if len(top_dash) > 0:
        st.plotly_chart(
            px.bar(
                top_dash,
                x="entidad",
                y=metrica_elegida,
                color="nivel_alerta",
                color_discrete_map=PALETA_ALERTAS,
                hover_data=["departamento", "sector"],
                title=f"Top {top_n} · {metrica_elegida}",
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
                color_discrete_map=PALETA_ALERTAS,
                hover_name="entidad",
                title="HHI vs % Directa",
            ),
            use_container_width=True,
        )


# ----- Pestaña 4: Riesgo y Cómputo -----

elif vista == "Riesgo y Cómputo":
    subido = st.file_uploader("CSV", type=["csv"])
    if subido is not None:
        st.session_state["archivo_csv_subido"] = subido
    if st.session_state.get("archivo_csv_subido") is not None and st.button("Restaurar"):
        st.session_state.pop("archivo_csv_subido", None)
        st.rerun()

    cols = ["entidad", "departamento", "sector", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct", "riesgo_score", "nivel_alerta"]
    st.dataframe(filtrado[cols].sort_values("riesgo_score", ascending=False), hide_index=True, use_container_width=True)

    if os.path.exists("rendimiento_multiprocessing.csv"):
        st.markdown("#### Multiprocessing")
        medidas = pd.read_csv("rendimiento_multiprocessing.csv")
        st.dataframe(medidas, hide_index=True, use_container_width=True)
        st.plotly_chart(
            px.bar(
                medidas,
                x="procesos",
                y="speedup",
                color_discrete_sequence=["#3B82F6"],
                title="Speedup",
            ),
            use_container_width=True,
        )


# ----- Pestaña 5: Servicios Judiciales -----

elif vista == "Servicios Judiciales":
    c_u1, c_u2, c_u3, c_u4 = st.columns(4)
    umb_hhi = c_u1.number_input("Umbral HHI", min_value=0.0, max_value=10000.0, value=1000.0, step=50.0)
    umb_cr4 = c_u2.number_input("Umbral CR4 (%)", min_value=0.0, max_value=100.0, value=40.0, step=5.0)
    umb_directa = c_u3.number_input("Umbral Directa (%)", min_value=0.0, max_value=100.0, value=30.0, step=5.0)
    regla_umbral = c_u4.selectbox("Condición", ["Cualquiera (OR)", "Todos (AND)"])

    activas = filtrar_por_umbral(filtrado, umb_hhi, umb_cr4, umb_directa, regla_umbral)
    activas = activas.sort_values(["riesgo_score", "hhi_valor"], ascending=False)

    cols_alerta = [
        "entidad",
        "departamento",
        "sector",
        "nivel_alerta",
        "hhi_valor",
        "cr4_valor",
        "pagos_sin_soporte_pct",
        "riesgo_score",
    ]
    st.dataframe(activas[cols_alerta].head(25), hide_index=True, use_container_width=True)

    if enviar_telegram is not None and es_admin:
        st.divider()
        tipo = st.selectbox("Rol", ROLES_INSTITUCIONALES)
        cantidad = st.slider("Alertas por contacto", 1, 10, 3)

        suscriptores_todos = leer_suscriptores()
        destinatarios = [p for p in suscriptores_todos if p.get("rol") == tipo and p.get("chat_id") and p.get("nombre")]
        elegidos = activas.head(cantidad)

        if len(elegidos) > 0:
            ejemplo_nombre = destinatarios[0]["nombre"] if destinatarios else "Destinatario"
            st.code(armar_mensaje(elegidos.iloc[0], rol_destino=tipo, nombre_destino=ejemplo_nombre), language=None)

        if st.button("Enviar alertas"):
            if leer_secreto("TELEGRAM_TOKEN") and destinatarios and len(elegidos) > 0:
                enviadas = 0
                fallidas = 0
                total = len(destinatarios) * len(elegidos)
                progreso = st.progress(0)
                paso = 0

                for persona in destinatarios:
                    for _, fila in elegidos.iterrows():
                        texto = armar_mensaje(fila, rol_destino=tipo, nombre_destino=persona["nombre"])
                        try:
                            respuesta = enviar_telegram(str(persona["chat_id"]), texto)
                            if telegram_ok(respuesta):
                                enviadas += 1
                            else:
                                fallidas += 1
                        except Exception:
                            fallidas += 1
                        paso += 1
                        progreso.progress(min(paso / total, 1.0))
                        time.sleep(0.4)

                st.success(f"{enviadas}/{total}")