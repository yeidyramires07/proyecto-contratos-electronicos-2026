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

st.markdown(
    """
    <style>
        .stApp { background-color: #FFFFFF; color: #111827; }
        [data-testid="stSidebar"] { background-color: #F8FAFC; border-right: 1px solid #E2E8F0; }

        /* Evita que la barra superior de Streamlit tape la fecha y el encabezado */
        .block-container {
            padding-top: 3.2rem !important;
        }

        .cabecera-portal {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1.5px solid #E2E8F0;
            padding: 8px 4px 12px 4px;
            margin-bottom: 14px;
        }
        .cabecera-izq {
            min-width: 185px;
            font-size: 0.82rem;
            color: #475569;
            line-height: 1.35;
        }
        .cabecera-centro {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            text-align: center;
        }
        .cabecera-titulo {
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.48rem;
            font-weight: 500;
            color: #0F294A;
            letter-spacing: 0.01em;
            line-height: 1.15;
        }
        .cabecera-der {
            min-width: 185px;
            display: flex;
            justify-content: flex-end;
        }
        .badge-estado {
            background-color: #F8FAFC;
            color: #0F294A;
            border: 1px solid #CBD5E1;
            font-weight: 600;
            font-size: 0.73rem;
            padding: 5px 11px;
            border-radius: 999px;
        }
        .barra-resumen {
            background-color: #F8FAFC;
            border-left: 3px solid #1D4ED8;
            color: #1E293B;
            padding: 9px 14px;
            border-radius: 4px;
            margin: 10px 0 16px 0;
            font-size: 0.87rem;
        }
        .nota-fila {
            border: 1px solid #E5E7EB;
            border-left: 4px solid #1D4ED8;
            border-radius: 6px;
            padding: 13px 15px;
            margin-bottom: 12px;
            background-color: #FFFFFF;
        }
        .nota-fila.alta {
            border-left-color: #B91C1C;
            background-color: #FFFBFB;
        }
        .tarjeta-titulo {
            font-size: 0.97rem;
            font-weight: 700;
            color: #111827;
            line-height: 1.32;
            margin: 8px 0 6px 0;
        }
        .tarjeta-resumen {
            font-size: 0.85rem;
            color: #4B5563;
            line-height: 1.42;
            margin-bottom: 8px;
        }
        .tag-ods {
            display: inline-block;
            background-color: #EFF6FF;
            color: #1E3A8A;
            font-size: 0.72rem;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 4px;
            margin-right: 6px;
        }
        .credito-foto {
            font-size: 0.73rem;
            color: #6B7280;
            margin-top: 4px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def logo_minimalista(size=34):
    """Logo minimalista de trazo limpio: cumbres andinas y punto de seguimiento."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 36 36" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle;">'
        '<path d="M5 26L14.5 12L21 22L25.5 15.5L31 26" stroke="#0F294A" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="25.5" cy="10" r="2.6" fill="#1D4ED8"/>'
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
    """Busca fotografías reales y el nombre del autor en Unsplash o Wikimedia Commons."""
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
                    fotos.append({"url": url_foto, "fotografo": fotografo or "Unsplash"})
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
                intro = f"Nota de {fuente_n} sobre compras públicas y gestión en la región."

            imagen = None
            fotografo = None
            if fotos_reales:
                foto_elegida = fotos_reales[idx % len(fotos_reales)]
                imagen = foto_elegida["url"]
                fotografo = f"Foto: {foto_elegida['fotografo']}"

            notas.append({
                "titulo": titulo,
                "intro": intro[:180],
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
        return leer_csv(archivo_subido), f"archivo cargado: {archivo_subido.name}"
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
    }), "datos de respaldo"


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
            f"Contratación directa: {round(r['soporte_pct'], 1)}%<br>"
            f"HHI promedio: {round(r['hhi_promedio'], 1)}"
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
                colorscale="Blues",
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
        return f"Hola {nombre_destino} (Fiscalia). Posible irregularidad contractual en {base} Revisar soportes y procesos."
    if rol_destino == "Policia":
        return f"Hola {nombre_destino} (Policia). Alerta preventiva en {base} Apoyo en verificacion territorial."
    if rol_destino == "Juez":
        return f"Hola {nombre_destino} (Juez). Reporte de legalidad y concentracion en {base} Para control y seguimiento."
    return f"Hola {nombre_destino} (Gobierno). Alerta de gestion publica en {base} Revisar administracion y correctivos."


def leer_suscriptores():
    try:
        return [dict(p) for p in st.secrets["suscriptores"]]
    except Exception:
        return []


def telegram_ok(respuesta):
    if isinstance(respuesta, dict):
        return bool(respuesta.get("ok"))
    return bool(respuesta)


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
                st.warning("Por ahora no pudimos conectar con la base de datos. Puedes entrar como invitado.")
            else:
                st.error("Revisa el usuario y la contraseña; no coinciden.")

        if st.button("Entrar como invitado"):
            st.session_state["sesion"] = {"nombre": "Invitado", "rol": "Invitado", "departamento": None}
            st.rerun()
    st.stop()


# ----- Encabezado superior -----

fecha_texto = datetime.now().strftime("%d/%m/%Y")
st.markdown(
    f"""
    <div class="cabecera-portal">
        <div class="cabecera-izq">
            <strong>{fecha_texto}</strong><br>
            <span>Región Andina · Colombia</span>
        </div>
        <div class="cabecera-centro">
            {logo_minimalista(34)}
            <span class="cabecera-titulo">Contratación Andina</span>
        </div>
        <div class="cabecera-der">
            <span class="badge-estado">SECOP II · Consulta</span>
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

if sesion.get("departamento") and rol in ROLES_INSTITUCIONALES + ["Comprador", "EPS", "Farmacia o distribuidor", "Auditor"]:
    contratos = contratos[contratos["departamento"] == sesion["departamento"]]

st.sidebar.write(f"Sesión activa: **{sesion['nombre']}** ({rol})")
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

st.sidebar.caption(f"Origen: {fuente}")
st.sidebar.caption(f"Registros visibles: {len(filtrado)} de {len(contratos)}")

if len(filtrado) > 0:
    top3 = filtrado.sort_values("riesgo_score", ascending=False).head(3)
    focos_texto = "  ·  ".join(
        f"{r['departamento']}: puntaje {round(float(r['riesgo_score']), 1)} (HHI {round(float(r['hhi_valor']), 1)})"
        for _, r in top3.iterrows()
    )
    st.markdown(f'<div class="barra-resumen"><b>Mayor puntaje en el filtro:</b> {focos_texto}</div>', unsafe_allow_html=True)

(
    tab_noticias_rt,
    tab_resumen_mapa,
    tab_dashboard,
    tab_senales_rend,
    tab_judiciales,
    tab_red,
    tab_secop,
) = st.tabs([
    "Noticias y Tiempo Real",
    "Resumen y Mapa",
    "Dashboard interactivo",
    "Señales y Rendimiento",
    "Servicios Judiciales",
    "Red",
    "SECOP · Alertas",
])


# ----- 1. Noticias y Tiempo Real -----

with tab_noticias_rt:
    st.subheader("Noticias en tiempo real · ODS")
    st.caption("Actualidad por eje temático para contextualizar lo que ocurre en contratación pública.")

    config_ods = {
        "ODS 3 · Salud": ("salud hospitales medicamentos contratación Colombia", "hospital colombia"),
        "ODS 4 · Educación": ("educación colegios universidades contratación Colombia", "university bogota"),
        "ODS 9 · Transporte e Infraestructura": ("infraestructura vías transporte Colombia", "highway colombia"),
        "ODS 11 · Vivienda": ("vivienda obras ciudades Colombia", "bogota city"),
        "ODS 16 · Contratación y Transparencia": ("SECOP contratación pública Colombia", "courthouse law"),
    }

    c_ods_sel, c_ods_btn = st.columns([4, 1])
    with c_ods_sel:
        ods_sel = st.selectbox("Tema ODS", list(config_ods.keys()))
    with c_ods_btn:
        st.write("")
        st.write("")
        if st.button("Actualizar noticias"):
            obtener_noticias_ods.clear()
            buscar_fotos_fotografos.clear()
            st.rerun()

    consulta_rss, consulta_foto = config_ods[ods_sel]
    notas_ods = obtener_noticias_ods(consulta_rss, consulta_foto, max_notas=6)

    if notas_ods:
        for inicio in range(0, len(notas_ods), 3):
            fila_cols = st.columns(3, gap="medium")
            for pos, nota in enumerate(notas_ods[inicio : inicio + 3]):
                with fila_cols[pos]:
                    with st.container(border=True):
                        if nota["imagen"]:
                            st.image(nota["imagen"], use_container_width=True)
                        if nota["fotografo"]:
                            st.markdown(f'<div class="credito-foto">{nota["fotografo"]}</div>', unsafe_allow_html=True)
                        meta_der = f"{nota['fuente']} · {nota['fecha']}" if nota["fecha"] else nota["fuente"]
                        st.markdown(
                            f'<div style="margin-top:6px;"><span class="tag-ods">{ods_sel}</span><small><b>{meta_der}</b></small></div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(f'<div class="tarjeta-titulo">{nota["titulo"]}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="tarjeta-resumen">{nota["intro"]}</div>', unsafe_allow_html=True)
                        if nota["url"]:
                            st.link_button("Leer nota", nota["url"])
    else:
        st.info("No llegaron notas en este momento; vuelve a intentar en un rato.")

    st.divider()
    st.subheader("Panorama por departamento · Región Andina")
    st.caption("Ordenado de mayor a menor puntaje según los filtros que tengas activos.")

    if len(filtrado) == 0:
        st.info("No hay departamentos que coincidan con el filtro seleccionado.")
    else:
        for _, fila in filtrado.sort_values("riesgo_score", ascending=False).iterrows():
            alerta_txt = str(fila["nivel_alerta"])
            es_alta = alerta_txt.upper() in ["ALTO", "ALTA"]
            st.markdown(
                f"""
                <div class="nota-fila {'alta' if es_alta else ''}">
                    <small><b>{fila['departamento']}</b> · Nivel: {alerta_txt}</small><br>
                    <b>Puntaje: {round(float(fila['riesgo_score']), 1)}</b><br>
                    HHI: {round(float(fila['hhi_valor']), 1)} · CR4: {round(float(fila['cr4_valor']), 1)}% · Contratación directa: {round(float(fila['pagos_sin_soporte_pct']), 1)}%
                </div>
                """,
                unsafe_allow_html=True,
            )


# ----- 2. Resumen y Mapa -----

with tab_resumen_mapa:
    st.subheader("Mapa de contratación directa · Región Andina")
    st.caption("Pasa el cursor sobre cada departamento para ver su porcentaje de contratación directa y su HHI promedio; el tamaño del marcador responde al HHI.")

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
            color_continuous_scale="Blues",
            labels={"soporte_pct": "% Contratación directa", "departamento": "Departamento"},
            title="Contratación directa por departamento (%)",
        )
        fig_colores.update_layout(height=320)
        st.plotly_chart(fig_colores, use_container_width=True)

    st.divider()
    st.subheader("Resumen")
    st.caption("Cifras consolidadas de acuerdo con los filtros aplicados a la izquierda.")

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

    st.markdown("#### Concentración (HHI) por departamento")
    por_depto = filtrado.groupby("departamento", as_index=False).agg(
        hhi_promedio=("hhi_valor", "mean"),
    ).sort_values("hhi_promedio", ascending=False)
    st.plotly_chart(
        px.bar(
            por_depto,
            x="departamento",
            y="hhi_promedio",
            color_discrete_sequence=["#0F294A"],
            labels={"hhi_promedio": "HHI promedio", "departamento": "Departamento"},
        ),
        use_container_width=True,
    )


# ----- 3. Dashboard interactivo -----

with tab_dashboard:
    st.subheader("Dashboard interactivo")
    st.caption("Compara entidades según el indicador que elijas y explora cómo se cruzan concentración y contratación directa.")

    metrica_elegida = st.selectbox(
        "Indicador a revisar",
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
                title=f"Primeras {top_n} entidades en {metrica_elegida}",
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
                title="HHI frente a contratación directa por entidad",
            ),
            use_container_width=True,
        )
    else:
        st.info("No hay entidades para graficar con los filtros actuales.")


# ----- 4. Señales y Rendimiento -----

with tab_senales_rend:
    st.subheader("Datos y rendimiento")
    st.caption("Puedes cargar un CSV propio para probarlo o revisar el listado de señales y los tiempos de ejecución.")

    subido = st.file_uploader("Subir archivo CSV", type=["csv"])
    if subido is not None:
        st.session_state["archivo_csv_subido"] = subido
    if st.session_state.get("archivo_csv_subido") is not None and st.button("Restaurar datos iniciales"):
        st.session_state.pop("archivo_csv_subido", None)
        st.rerun()

    st.markdown("#### Señales detectadas")
    cols = ["entidad", "departamento", "sector", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct", "riesgo_score", "nivel_alerta"]
    st.dataframe(filtrado[cols].sort_values("riesgo_score", ascending=False), hide_index=True, use_container_width=True)

    st.markdown("#### Rendimiento con multiprocessing")
    if os.path.exists("rendimiento_multiprocessing.csv"):
        medidas = pd.read_csv("rendimiento_multiprocessing.csv")
        st.dataframe(medidas, hide_index=True, use_container_width=True)
        st.plotly_chart(
            px.bar(
                medidas,
                x="procesos",
                y="speedup",
                color_discrete_sequence=["#1D4ED8"],
                title="Speedup según cantidad de procesos",
            ),
            use_container_width=True,
        )
    else:
        st.info("Todavía no se ha generado `rendimiento_multiprocessing.csv`.")


# ----- 5. Servicios Judiciales -----

with tab_judiciales:
    st.subheader("Servicios Judiciales · Revisión por umbrales")
    st.caption("Define los valores mínimos de HHI, CR4 y contratación directa para ubicar casos que convenga revisar.")

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
    st.write(f"Casos que superan los umbrales: **{len(activas)}**")
    st.dataframe(activas[cols_alerta].head(25), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Envío de alertas por Telegram")

    if enviar_telegram is None:
        st.info("Aún no está disponible el módulo `enviar_telegram.py` en el proyecto.")
    elif not es_admin:
        st.info(f"Solo el perfil Administrador puede disparar envíos desde aquí (estás como {rol}).")
    else:
        tipo = st.selectbox("Rol destinatario", ROLES_INSTITUCIONALES)
        cantidad = st.slider("Alertas a enviar por persona", 1, 10, 3)

        suscriptores_todos = leer_suscriptores()
        destinatarios = [p for p in suscriptores_todos if p.get("rol") == tipo and p.get("chat_id") and p.get("nombre")]
        elegidos = activas.head(cantidad)

        st.write(f"Contactos en {tipo}: **{len(destinatarios)}** · Alertas listas: **{len(elegidos)}**")

        if len(elegidos) > 0:
            st.dataframe(
                elegidos[["entidad", "departamento", "nivel_alerta", "hhi_valor", "cr4_valor", "pagos_sin_soporte_pct"]],
                hide_index=True,
                use_container_width=True,
            )
            ejemplo_nombre = destinatarios[0]["nombre"] if destinatarios else "Destinatario"
            st.caption("Así se verá el mensaje:")
            st.code(armar_mensaje(elegidos.iloc[0], rol_destino=tipo, nombre_destino=ejemplo_nombre), language=None)

        if st.button("Enviar alertas"):
            if not leer_secreto("TELEGRAM_TOKEN"):
                st.warning("Falta configurar `TELEGRAM_TOKEN` en los secrets o en el entorno.")
            elif len(destinatarios) == 0:
                st.warning(f"No hay contactos con rol '{tipo}' configurados en `st.secrets['suscriptores']`.")
            elif len(elegidos) == 0:
                st.warning("No hay casos que cumplan los umbrales con los filtros actuales.")
            else:
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

                st.success(f"Mensajes enviados: {enviadas} de {total}")
                if fallidas > 0:
                    st.warning(f"Hubo {fallidas} envíos sin confirmar; revisa el token o los `chat_id`.")


# ----- 6. Red -----

with tab_red:
    st.subheader("Red y arquitectura")
    st.caption("Esquema de conexión entre componentes, datos y servicios del proyecto.")
    if os.path.exists("topologia_red.png"):
        st.image("topologia_red.png", caption="Topología de red")
    else:
        st.info("Agrega `topologia_red.png` en la carpeta del proyecto cuando quieras mostrar el diagrama aquí.")


# ----- 7. SECOP · Alertas -----

with tab_secop:
    if mostrar_dashboard_secop is None:
        st.info("No se encontró `modulo_secop_original.py` para mostrar esta vista.")
    else:
        mostrar_dashboard_secop()
