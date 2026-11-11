import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import re
import json
import os
import io
import shutil
import zipfile
import html
from datetime import datetime
from shapely.geometry import Point, shape
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from sullapps_ui import (
    inject_custom_css,
    sullapps_spinner,
    celebrate_success,
    verify_sullapps_sso,
    clear_sullapps_sso,
    render_sullapps_portal_notice,
)

st.set_page_config(
    page_title="PetroMaps | Áreas Hidrocarburíferas",
    page_icon="🛢️",
    layout="wide",
)
inject_custom_css()

# ==============================================================================
# 0. SISTEMA DE LOGIN UNIFICADO (SSO SULLAPPS + CONTROL DE ACCESO)
# ==============================================================================
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "nombre_usuario" not in st.session_state:
    st.session_state.nombre_usuario = None

# Verificar primero si viene autenticado desde el Hub SullApps (SSO firmado)
sso_identity = verify_sullapps_sso()
if sso_identity and not st.session_state.usuario:
    sso_user = sso_identity.get("username", "").lower()
    sso_role = sso_identity.get("role", "user").lower()
    if sso_role == "admin" or sso_user in ("fcendra", "admin"):
        st.session_state.usuario = "admin"
    else:
        st.session_state.usuario = "user"
    st.session_state.nombre_usuario = sso_identity.get("display_name") or sso_user


def _verificar_credenciales_locales(us: str, pw: str) -> str | None:
    """Valida credenciales contra shared/users_access.json o fallback local."""
    us_clean = (us or "").strip().lower()
    pw_clean = (pw or "").strip()
    if not us_clean or not pw_clean:
        return None

    # Intentar leer shared/users_access.json si está disponible
    posibles_rutas = [
        os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "users_access.json")),
        os.path.normpath(os.path.join(os.getcwd(), "shared", "users_access.json")),
    ]
    for ruta in posibles_rutas:
        if os.path.isfile(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                users_list = cfg.get("users", [])
                if isinstance(users_list, list):
                    for u_info in users_list:
                        if str(u_info.get("usuario", "")).strip().lower() == us_clean:
                            if not u_info.get("activo", True):
                                return None
                            apps_permitidas = u_info.get("apps", [])
                            if "*" not in apps_permitidas and "petromaps" not in apps_permitidas:
                                return None
                            pws = [str(p) for p in u_info.get("passwords", [])]
                            if u_info.get("password"):
                                pws.append(str(u_info["password"]))
                            if pw_clean in pws:
                                return "admin" if (u_info.get("rol") == "admin" or us_clean in ("fcendra", "admin")) else "user"
            except Exception:
                pass

    if us_clean == "fcendra" and pw_clean == "C4n1ch3r1426":
        return "admin"
    if us_clean == "gensullair" and pw_clean == "2026sullair!":
        return "user"
    return None


if not st.session_state.usuario:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        try:
            st.image("Logo Sullair Verde.png", width=280)
        except Exception:
            st.title("SULLAIR ARGENTINA")

        render_sullapps_portal_notice()

        with st.expander("🔑 Ingreso directo (Usuarios autorizados)", expanded=True):
            st.subheader("🔒 Acceso al Sistema")
            us = st.text_input("Usuario")
            pw = st.text_input("Contraseña", type="password")

            if st.button("Ingresar", type="primary", use_container_width=True):
                rol = _verificar_credenciales_locales(us, pw)
                if rol:
                    st.session_state.usuario = rol
                    st.session_state.nombre_usuario = us.strip()
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas o sin permiso para PetroMaps.")
    st.stop()

# ==============================================================================
# CONSTANTES DE DATOS Y PERSISTENCIA
# ==============================================================================
COL_NOMBRE = "nombre"
COL_OPERADORA = "operador"
RUTA_PUNTOS_FIJOS = "data/puntos_fijos.json"

# Paleta de colores corporativa / ejecutiva (tonos sobrios, profesionales y no chillones)
PALETA_PROFESIONAL = {
    "Azul Petróleo (#2B5B84)": "#2B5B84",
    "Verde Sullair (#1B7A43)": "#1B7A43",
    "Ámbar Ocre (#C07A28)": "#C07A28",
    "Terracota Suave (#A84A3B)": "#A84A3B",
    "Pizarra Violeta (#5E4B8B)": "#5E4B8B",
    "Turquesa Austral (#237482)": "#237482",
    "Verde Salvia (#4E7A6B)": "#4E7A6B",
    "Gris Grafito (#4A5568)": "#4A5568",
}

# Puntos fijos predeterminados (Bases Sullair)
PUNTOS_FIJOS_DEFAULT = [
    {
        "id": "base_anelo",
        "nombre": "Base Sullair Añelo",
        "coords_raw": "38°20'22.0\"S 68°49'17.9\"W",
        "lat": -38.339444,
        "lon": -68.821639,
        "categoria": "Base Operativa",
        "color": "#006837",
    },
    {
        "id": "base_neuquen",
        "nombre": "Base Sullair Neuquén",
        "coords_raw": "38°54'13.6\"S 68°05'09.7\"W",
        "lat": -38.903778,
        "lon": -68.086028,
        "categoria": "Base Central",
        "color": "#006837",
    },
]


def cargar_puntos_fijos():
    if os.path.exists(RUTA_PUNTOS_FIJOS):
        try:
            with open(RUTA_PUNTOS_FIJOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(RUTA_PUNTOS_FIJOS), exist_ok=True)
        with open(RUTA_PUNTOS_FIJOS, "w", encoding="utf-8") as f:
            json.dump(PUNTOS_FIJOS_DEFAULT, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return PUNTOS_FIJOS_DEFAULT


# ==============================================================================
# 1. ACTUALIZACIÓN DE DATOS Y GESTIÓN DE BACKUPS (ADMIN)
# ==============================================================================
DATA_DIR = "data"
BACKUP_DIR = "data_backup"
URL_AREAS_ZIP = (
    "https://portaldatosabiertos.neuquen.gov.ar/dataset/"
    "d726d6de-bf79-4302-bc5e-1f2b975fc9a3/resource/"
    "8750c10c-9ad9-473f-9862-a9b1dabaf7d4/download/areas_hidrocarburiferas.zip"
)


def _crear_backup():
    """Copia la carpeta data/ actual a data_backup/ si existe y tiene contenido."""
    if os.path.exists(DATA_DIR) and os.listdir(DATA_DIR):
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        shutil.copytree(DATA_DIR, BACKUP_DIR)
        return True
    return False


def restaurar_backup():
    """Restaura el mapa desde la copia de seguridad previa."""
    try:
        if not os.path.exists(BACKUP_DIR) or not os.listdir(BACKUP_DIR):
            st.sidebar.warning("No hay ninguna copia de seguridad guardada para restaurar.")
            return

        with sullapps_spinner("general"):
            if os.path.exists(DATA_DIR):
                shutil.rmtree(DATA_DIR)
            shutil.copytree(BACKUP_DIR, DATA_DIR)

        celebrate_success("¡Copia de seguridad restaurada correctamente!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error al restaurar el backup: {e}")


def actualizar_datos():
    """Descarga la capa oficial de áreas, genera backup y actualiza data/."""
    try:
        with sullapps_spinner("general"):
            # 1. Descarga del paquete
            r = requests.get(URL_AREAS_ZIP, timeout=45)
            r.raise_for_status()

            # 2. Validación en memoria del archivo ZIP
            z = zipfile.ZipFile(io.BytesIO(r.content))
            test_zip = z.testzip()
            if test_zip is not None:
                raise ValueError(f"El archivo ZIP descargado está corrupto (falló en {test_zip}).")

            # 3. Resguardo del mapa actual funcional
            hubo_backup = _crear_backup()

            # 4. Descompresión atómica
            os.makedirs(DATA_DIR, exist_ok=True)
            z.extractall(DATA_DIR)

        msg = "¡Datos geográficos actualizados correctamente desde el portal de Neuquén!"
        if hubo_backup:
            msg += " Se guardó un backup del mapa anterior."
        celebrate_success(msg)

        st.cache_data.clear()
        st.rerun()

    except Exception as e:
        # En caso de fallo crítico durante la actualización, intenta recuperar el backup
        if os.path.exists(BACKUP_DIR) and os.listdir(BACKUP_DIR):
            try:
                if os.path.exists(DATA_DIR):
                    shutil.rmtree(DATA_DIR)
                shutil.copytree(BACKUP_DIR, DATA_DIR)
                st.sidebar.error(f"Falló la actualización ({e}). Se restauró automáticamente el mapa anterior.")
                return
            except Exception as rb_err:
                st.sidebar.error(f"Falla crítica: no se pudo actualizar ni restaurar backup: {rb_err}")
                return
        st.sidebar.error(f"Falló la descarga o actualización de datos: {e}")


# ==============================================================================
# 2. TRANSFORMACIONES DE COORDENADAS (ULTRA ROBUSTO)
# ==============================================================================
def decimal_a_gms(lat, lon):
    """
    Convierte coordenadas en grados decimales (DD) a formato Grados, Minutos y Segundos (GMS).
    Ejemplo: (-38.9516, -68.0591) -> 38°57'05.76"S, 68°03'32.76"O
    """
    if lat is None or lon is None:
        return ""
    try:
        if pd.isna(lat) or pd.isna(lon) or np.isnan(lat) or np.isnan(lon):
            return ""

        lat_f = float(lat)
        lon_f = float(lon)

        # Latitud
        lat_dir = "S" if lat_f < 0 else "N"
        abs_lat = abs(lat_f)
        lat_deg = int(abs_lat)
        lat_min_float = (abs_lat - lat_deg) * 60.0
        lat_min = int(lat_min_float)
        lat_sec = (lat_min_float - lat_min) * 60.0
        lat_gms = f"{lat_deg:02d}°{lat_min:02d}'{lat_sec:05.2f}\"{lat_dir}"

        # Longitud
        lon_dir = "O" if lon_f < 0 else "E"
        abs_lon = abs(lon_f)
        lon_deg = int(abs_lon)
        lon_min_float = (abs_lon - lon_deg) * 60.0
        lon_min = int(lon_min_float)
        lon_sec = (lon_min_float - lon_min) * 60.0
        lon_gms = f"{lon_deg:02d}°{lon_min:02d}'{lon_sec:05.2f}\"{lon_dir}"

        return f"{lat_gms}, {lon_gms}"
    except Exception:
        return ""


def _validar_y_ajustar_lat_lon(lat, lon):
    """
    Verifica que las coordenadas sean válidas y corrige inversión accidental (Lon, Lat).
    """
    if lat is None or lon is None:
        return None, None
    try:
        lat = float(lat)
        lon = float(lon)
        if abs(lat) > 50 and abs(lon) < 50:
            lat, lon = lon, lat
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except Exception:
        pass
    return None, None


def extraer_coordenadas(texto):
    """
    Parser flexible de coordenadas para cualquier formato de DMS, Decimal o Maps.
    """
    if not texto or not isinstance(texto, str):
        return None, None

    texto = texto.strip()

    if "maps.app.goo.gl" in texto or "goo.gl/maps" in texto:
        try:
            r = requests.get(texto, allow_redirects=True, timeout=5)
            texto = r.url
        except Exception:
            pass

    match_url = re.search(r"[@?&/](-?\d{1,2}\.\d+)[,/](-?\d{1,3}\.\d+)", texto)
    if match_url:
        lat, lon = float(match_url.group(1)), float(match_url.group(2))
        return _validar_y_ajustar_lat_lon(lat, lon)

    t = texto.replace("”", '"').replace("’", "'").replace("″", '"').replace("′", "'").replace("´", "'")

    regex_dms = r'(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*([NSns])\s*[,;/]?\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*([EWOewo])'
    match_dms = re.search(regex_dms, t)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
        if lat_dir.upper() == "S":
            lat = -lat
        lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
        if lon_dir.upper() in ["W", "O"]:
            lon = -lon
        return _validar_y_ajustar_lat_lon(lat, lon)

    regex_dms_inv = r'([NSns])\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*[,;/]?\s*([EWOewo])\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]'
    match_inv = re.search(regex_dms_inv, t)
    if match_inv:
        lat_dir, lat_d, lat_m, lat_s, lon_dir, lon_d, lon_m, lon_s = match_inv.groups()
        lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
        if lat_dir.upper() == "S":
            lat = -lat
        lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
        if lon_dir.upper() in ["W", "O"]:
            lon = -lon
        return _validar_y_ajustar_lat_lon(lat, lon)

    t_dec = re.sub(r"(\d),(\d)", r"\1.\2", t)
    floats = re.findall(r"[-+]?\d{1,3}\.\d+", t_dec)
    if len(floats) >= 2:
        lat, lon = float(floats[0]), float(floats[1])
        return _validar_y_ajustar_lat_lon(lat, lon)

    return None, None


# ==============================================================================
# 3. CARGA Y PROCESAMIENTO DE GEODATOS (ULTRA OPTIMIZADO)
# ==============================================================================
@st.cache_data
def cargar_datos():
    ruta_archivo = "data/areas_hidrocarburiferas.shp"
    gdf = gpd.read_file(ruta_archivo)
    gdf = gdf.to_crs(epsg=4326)

    gdf = gdf[gdf.geometry.notnull() & ~gdf.geometry.is_empty].copy()
    try:
        gdf["geometry"] = gdf["geometry"].make_valid()
    except Exception:
        pass

    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)

    try:
        centroids_4326 = gdf.to_crs(epsg=3857).geometry.centroid.to_crs(epsg=4326)
        gdf["lat_centro"] = centroids_4326.y
        gdf["lon_centro"] = centroids_4326.x
    except Exception:
        centroids = gdf.geometry.centroid
        gdf["lat_centro"] = centroids.y
        gdf["lon_centro"] = centroids.x

    lookup_areas = {}
    for _, row in gdf.iterrows():
        nombre = str(row[COL_NOMBRE])
        operador = str(row[COL_OPERADORA]) if pd.notna(row[COL_OPERADORA]) else "Sin operadora"
        lat = row["lat_centro"] if pd.notna(row["lat_centro"]) else None
        lon = row["lon_centro"] if pd.notna(row["lon_centro"]) else None
        lookup_areas[nombre] = {
            "operador": operador,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "gms": decimal_a_gms(lat, lon) if (lat is not None and lon is not None) else "",
        }

    gdf_simplificado = gdf.copy()
    try:
        gdf_simplificado["geometry"] = gdf.geometry.simplify(tolerance=0.0005, preserve_topology=True)
    except Exception:
        pass

    minx, miny, maxx, maxy = gdf.total_bounds
    centro_inicial = [float((miny + maxy) / 2.0), float((minx + maxx) / 2.0)]

    return gdf_simplificado, gdf, lookup_areas, centro_inicial


try:
    gdf_simplificado, gdf_completo, lookup_areas, CENTRO_DEFECTO = cargar_datos()
    puntos_fijos = cargar_puntos_fijos()
except Exception as e:
    st.error(f"Error al cargar el mapa de áreas. Detalle: {e}")
    st.stop()

# ==============================================================================
# 4. MANEJO DE ESTADOS (SESSION STATE) Y CÁMARA
# ==============================================================================
if "area_elegida" not in st.session_state:
    st.session_state.area_elegida = "TODAS"
if "operadora_elegida" not in st.session_state:
    st.session_state.operadora_elegida = "TODAS"
if "punto_buscado" not in st.session_state:
    st.session_state.punto_buscado = None
if "areas_pintadas" not in st.session_state:
    st.session_state.areas_pintadas = {}
if "ultimo_dibujo_procesado" not in st.session_state:
    st.session_state.ultimo_dibujo_procesado = None
if "ultimas_coordenadas" not in st.session_state:
    st.session_state.ultimas_coordenadas = None
if "ultima_operadora" not in st.session_state:
    st.session_state.ultima_operadora = None
if "ultimo_nombre_area" not in st.session_state:
    st.session_state.ultimo_nombre_area = None
if "map_center" not in st.session_state:
    st.session_state.map_center = CENTRO_DEFECTO
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 7
if "map_theme" not in st.session_state:
    st.session_state.map_theme = "Claro (Gris Corporativo)"
if "color_picker_pincel" not in st.session_state:
    st.session_state.color_picker_pincel = "#2B5B84"
if "preset_color_pincel" not in st.session_state:
    st.session_state.preset_color_pincel = "Azul Petróleo (#2B5B84)"

# ==============================================================================
# 5. INTERCEPCIÓN DE CLICS EN EL MAPA (1 SOLO PASO)
# ==============================================================================
estado_previo_mapa = st.session_state.get("mapa_folium")
if estado_previo_mapa and estado_previo_mapa.get("last_active_drawing"):
    dibujo_activo = estado_previo_mapa["last_active_drawing"]
    props = dibujo_activo.get("properties", {})
    nombre_clic = str(props.get(COL_NOMBRE, ""))

    firma_clic = f"{nombre_clic}_{dibujo_activo.get('id', '')}"

    if firma_clic != st.session_state.ultimo_dibujo_procesado:
        st.session_state.ultimo_dibujo_procesado = firma_clic

        meta = lookup_areas.get(nombre_clic)
        if meta:
            operador_clic = meta["operador"]
            lat_clic, lon_clic = meta["lat"], meta["lon"]
            gms_clic = meta["gms"]
        else:
            try:
                geom = shape(dibujo_activo.get("geometry", {}))
                c = geom.centroid
                lat_clic, lon_clic = float(c.y), float(c.x)
                gms_clic = decimal_a_gms(lat_clic, lon_clic)
            except Exception:
                lat_clic, lon_clic, gms_clic = None, None, ""
            operador_clic = str(props.get(COL_OPERADORA, "Sin operadora"))

        if lat_clic is not None and lon_clic is not None:
            st.session_state.ultimas_coordenadas = (lat_clic, lon_clic)
            st.session_state.ultima_operadora = operador_clic
            st.session_state.ultimo_nombre_area = nombre_clic

        color_actual = st.session_state.get("color_picker_pincel", "#2B5B84")
        if nombre_clic:
            if nombre_clic in st.session_state.areas_pintadas:
                del st.session_state.areas_pintadas[nombre_clic]
            else:
                st.session_state.areas_pintadas[nombre_clic] = {
                    "color": color_actual,
                    "operadora": operador_clic,
                    "lat": lat_clic,
                    "lon": lon_clic,
                    "gms": gms_clic,
                }


# ==============================================================================
# 6. MANEJADORES DE FILTROS, PALETA Y BÚSQUEDA
# ==============================================================================
def on_preset_color_change():
    seleccion = st.session_state.get("preset_color_pincel")
    if seleccion in PALETA_PROFESIONAL:
        st.session_state.color_picker_pincel = PALETA_PROFESIONAL[seleccion]


def on_area_change():
    st.session_state.operadora_elegida = "TODAS"
    area_sel = st.session_state.area_elegida
    if area_sel != "TODAS" and area_sel in lookup_areas:
        info = lookup_areas[area_sel]
        if info["lat"] is not None and info["lon"] is not None:
            st.session_state.map_center = [info["lat"], info["lon"]]
            st.session_state.map_zoom = 10
            st.session_state.ultimas_coordenadas = (info["lat"], info["lon"])
        st.session_state.ultima_operadora = info["operador"]
        st.session_state.ultimo_nombre_area = area_sel


def on_operadora_change():
    st.session_state.area_elegida = "TODAS"


def procesar_busqueda():
    texto = st.session_state.get("input_coords", "")
    lat, lon = extraer_coordenadas(texto)

    if lat is not None and lon is not None:
        st.session_state.punto_buscado = [lat, lon]
        st.session_state.ultimas_coordenadas = (lat, lon)
        st.session_state.map_center = [lat, lon]
        st.session_state.map_zoom = 12

        punto = Point(lon, lat)
        area_encontrada = gdf_completo[gdf_completo.geometry.contains(punto)]

        if not area_encontrada.empty:
            nombre = str(area_encontrada.iloc[0][COL_NOMBRE])
            operador = str(area_encontrada.iloc[0][COL_OPERADORA])
            st.session_state.area_elegida = nombre
            st.session_state.operadora_elegida = "TODAS"
            st.session_state.ultima_operadora = operador
            st.session_state.ultimo_nombre_area = nombre
        else:
            st.session_state.ultima_operadora = None
            st.session_state.ultimo_nombre_area = None
    else:
        st.session_state.punto_buscado = None


# ==============================================================================
# 7. EXPORTACIÓN DE MAPA A IMAGEN (PNG HD) Y REPORTE EJECUTIVO (PDF)
# ==============================================================================
def obtener_filas_exportacion() -> list[dict]:
    """
    Construye la lista normalizada de áreas/coordenadas seleccionadas para el cuadro
    del PDF y el CSV. Si hay áreas pintadas las incluye todas; si además hay un
    punto buscado o área iluminada no pintada, también lo incorpora.
    """
    filas = []
    vistas = set()

    for nombre, data in st.session_state.areas_pintadas.items():
        vistas.add(nombre)
        filas.append(
            {
                "color": data.get("color", "#2B5B84"),
                "area": nombre,
                "operadora": data.get("operadora", "Sin operadora"),
                "gms": data.get("gms", ""),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            }
        )

    if (
        st.session_state.area_elegida != "TODAS"
        and st.session_state.area_elegida not in vistas
        and st.session_state.area_elegida in lookup_areas
    ):
        area_f = st.session_state.area_elegida
        info_f = lookup_areas[area_f]
        vistas.add(area_f)
        filas.append(
            {
                "color": "#1B7A43",
                "area": area_f,
                "operadora": info_f.get("operador", "Sin operadora"),
                "gms": info_f.get("gms", ""),
                "lat": info_f.get("lat"),
                "lon": info_f.get("lon"),
            }
        )

    if st.session_state.ultimas_coordenadas and not filas:
        lat_u, lon_u = st.session_state.ultimas_coordenadas
        filas.append(
            {
                "color": "#006837",
                "area": st.session_state.ultimo_nombre_area or "Coordenada Seleccionada",
                "operadora": st.session_state.ultima_operadora or "Sullair Argentina",
                "gms": decimal_a_gms(lat_u, lon_u),
                "lat": lat_u,
                "lon": lon_u,
            }
        )

    return filas


def generar_imagen_mapa_png(
    gdf: gpd.GeoDataFrame,
    areas_pintadas: dict,
    area_elegida: str,
    operadora_elegida: str,
    puntos_fijos_list: list,
    punto_buscado: list | None,
    es_modo_oscuro: bool = False,
    encuadre: str = "Cuenca completa",
) -> bytes:
    """
    Renderiza el mapa estático en alta resolución (PNG) con todas las áreas pintadas,
    etiquetas de áreas seleccionadas, bases Sullair y leyenda ejecutiva.
    """
    bg_fig = "#0F172A" if es_modo_oscuro else "#F8FAFC"
    bg_ax = "#1E293B" if es_modo_oscuro else "#EEF2F6"
    text_main = "#F8FAFC" if es_modo_oscuro else "#0F172A"
    base_fill = "#334155" if es_modo_oscuro else "#DCE4EC"
    base_edge = "#64748B" if es_modo_oscuro else "#94A3B8"

    fig, ax = plt.subplots(figsize=(12, 8.2), dpi=200)
    fig.patch.set_facecolor(bg_fig)
    ax.set_facecolor(bg_ax)

    # 1. Capa base de todas las áreas hidrocarburíferas
    gdf.plot(
        ax=ax,
        color=base_fill,
        edgecolor=base_edge,
        linewidth=0.55,
        alpha=0.75,
    )

    # 2. Áreas iluminadas por filtro de Operadora o Área
    gdf_foco_list = []
    if operadora_elegida != "TODAS":
        sub_op = gdf[gdf[COL_OPERADORA].astype(str) == operadora_elegida]
        if not sub_op.empty:
            sub_op.plot(
                ax=ax,
                color="#1B7A43",
                edgecolor="#064E3B",
                linewidth=1.3,
                alpha=0.60,
            )
            gdf_foco_list.append(sub_op)

    if area_elegida != "TODAS":
        sub_ar = gdf[gdf[COL_NOMBRE].astype(str) == area_elegida]
        if not sub_ar.empty:
            sub_ar.plot(
                ax=ax,
                color="#1B7A43",
                edgecolor="#064E3B",
                linewidth=1.6,
                alpha=0.68,
            )
            gdf_foco_list.append(sub_ar)

    # 3. Áreas pintadas con sus colores personalizados y etiquetas
    patches_leyenda = []
    for nombre_area, info_p in areas_pintadas.items():
        color_hex = info_p.get("color", "#2B5B84") if isinstance(info_p, dict) else str(info_p)
        sub_p = gdf[gdf[COL_NOMBRE].astype(str) == nombre_area]
        if not sub_p.empty:
            sub_p.plot(
                ax=ax,
                color=color_hex,
                edgecolor="#FFFFFF" if es_modo_oscuro else "#0F172A",
                linewidth=1.5,
                alpha=0.82,
            )
            gdf_foco_list.append(sub_p)
            # Etiqueta en el centroide del polígono pintado
            for _, r_p in sub_p.iterrows():
                lat_c = r_p.get("lat_centro")
                lon_c = r_p.get("lon_centro")
                if pd.notna(lat_c) and pd.notna(lon_c):
                    ax.annotate(
                        str(nombre_area),
                        xy=( float(lon_c), float(lat_c) ),
                        xytext=(0, 2),
                        textcoords="offset points",
                        ha="center",
                        va="center",
                        fontsize=7.5,
                        fontweight="bold",
                        color="#FFFFFF" if es_modo_oscuro else "#0F172A",
                        bbox=dict(
                            boxstyle="round,pad=0.22",
                            fc=color_hex if es_modo_oscuro else "#FFFFFF",
                            ec=color_hex,
                            alpha=0.88,
                            lw=0.9,
                        ),
                        zorder=6,
                    )
            op_label = info_p.get("operadora", "") if isinstance(info_p, dict) else ""
            ley_txt = f"{nombre_area} ({op_label[:22]})" if op_label else str(nombre_area)
            patches_leyenda.append(mpatches.Patch(color=color_hex, label=ley_txt))

    # 4. Bases Fijas Sullair
    for pf in puntos_fijos_list:
        ax.scatter(
            pf["lon"],
            pf["lat"],
            color="#006837",
            edgecolors="#FFFFFF",
            s=75,
            marker="^",
            zorder=7,
        )
        ax.annotate(
            pf["nombre"],
            xy=(pf["lon"], pf["lat"]),
            xytext=(5, 4),
            textcoords="offset points",
            fontsize=7.5,
            fontweight="bold",
            color="#065F46" if not es_modo_oscuro else "#6EE7B7",
            bbox=dict(boxstyle="round,pad=0.18", fc="#ECFDF5" if not es_modo_oscuro else "#064E3B", ec="#006837", alpha=0.85, lw=0.7),
            zorder=8,
        )

    # 5. Punto buscado activo
    if punto_buscado and len(punto_buscado) == 2:
        ax.scatter(
            punto_buscado[1],
            punto_buscado[0],
            color="#DC2626",
            edgecolors="#FFFFFF",
            s=90,
            marker="o",
            zorder=9,
        )

    # 6. Encuadre inteligente (Zoom a selección o Cuenca completa)
    if encuadre == "Ajustar a áreas seleccionadas" and gdf_foco_list:
        gdf_concat = pd.concat(gdf_foco_list, ignore_index=True)
        minx, miny, maxx, maxy = gdf_concat.total_bounds
        dx = max((maxx - minx) * 0.35, 0.18)
        dy = max((maxy - miny) * 0.35, 0.18)
        ax.set_xlim(minx - dx, maxx + dx)
        ax.set_ylim(miny - dy, maxy + dy)
    else:
        minx, miny, maxx, maxy = gdf.total_bounds
        dx = (maxx - minx) * 0.05
        dy = (maxy - miny) * 0.05
        ax.set_xlim(minx - dx, maxx + dx)
        ax.set_ylim(miny - dy, maxy + dy)

    ax.set_title(
        "SULLAIR ARGENTINA — PetroMaps GIS | Áreas Hidrocarburíferas",
        fontsize=12.5,
        fontweight="bold",
        color=text_main,
        pad=12,
    )
    ax.set_xlabel("Longitud (°O)", fontsize=8.5, color=text_main)
    ax.set_ylabel("Latitud (°S)", fontsize=8.5, color=text_main)
    ax.tick_params(colors=text_main, labelsize=8)
    ax.grid(True, linestyle="--", linewidth=0.45, alpha=0.4, color=base_edge)

    if patches_leyenda:
        leg = ax.legend(
            handles=patches_leyenda[:14],
            title="Áreas Pintadas",
            loc="lower right",
            fontsize=7.5,
            title_fontsize=8,
            framealpha=0.92,
        )
        leg.get_frame().set_edgecolor("#CBD5E1")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generar_reporte_mapa_pdf(
    png_bytes: bytes,
    filas_detalle: list[dict],
) -> bytes:
    """
    Genera un reporte PDF profesional (A4) con encabezado Sullair Argentina,
    la imagen renderizada del mapa arriba y el cuadro detallado de coordenadas abajo.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Reporte PetroMaps - Sullair Argentina",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SullairTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=rl_colors.HexColor("#006837"),
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "SullairSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=rl_colors.HexColor("#4B5563"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "SullairSec",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=rl_colors.HexColor("#1F2937"),
        spaceBefore=8,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10.5,
        textColor=rl_colors.HexColor("#1F2937"),
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    story = []
    fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph("SULLAIR ARGENTINA S.A. — PetroMaps GIS", title_style))
    story.append(
        Paragraph(
            f"Reporte Ejecutivo de Áreas Hidrocarburíferas y Coordenadas Seleccionadas &nbsp;|&nbsp; Generado: {fecha_str}",
            subtitle_style,
        )
    )

    # Imagen del mapa (ancho 182mm proporcional)
    img_stream = io.BytesIO(png_bytes)
    rl_img = RLImage(img_stream, width=182 * mm, height=124 * mm)
    story.append(rl_img)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Detalle de Coordenadas y Áreas Seleccionadas ({len(filas_detalle)})", section_style))

    if filas_detalle:
        headers = ["Color", "Área / Concesión", "Empresa Operadora", "Coordenadas (GMS)", "Latitud / Longitud"]
        table_data = [headers]
        row_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#006837")),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("ALIGN", (0, 0), (-1, 0), "LEFT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]

        for idx, item in enumerate(filas_detalle, start=1):
            c_hex = item.get("color", "#2B5B84")
            lat_v = item.get("lat")
            lon_v = item.get("lon")
            dec_str = (
                f"{float(lat_v):.5f}, {float(lon_v):.5f}"
                if (lat_v is not None and lon_v is not None and not pd.isna(lat_v) and not pd.isna(lon_v))
                else "-"
            )
            table_data.append(
                [
                    "",
                    Paragraph(html.escape(str(item.get("area", ""))), cell_bold),
                    Paragraph(html.escape(str(item.get("operadora", ""))), cell_style),
                    Paragraph(html.escape(str(item.get("gms", ""))), cell_style),
                    Paragraph(dec_str, cell_style),
                ]
            )
            try:
                row_styles.append(("BACKGROUND", (0, idx), (0, idx), rl_colors.HexColor(c_hex)))
            except Exception:
                row_styles.append(("BACKGROUND", (0, idx), (0, idx), rl_colors.HexColor("#2B5B84")))
            if idx % 2 == 0:
                row_styles.append(("BACKGROUND", (1, idx), (-1, idx), rl_colors.HexColor("#F8FAFC")))

        tbl = Table(
            table_data,
            colWidths=[13 * mm, 46 * mm, 47 * mm, 44 * mm, 32 * mm],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle(row_styles))
        story.append(tbl)
    else:
        story.append(
            Paragraph(
                "No se pintaron áreas específicas en esta vista. Hacé clic sobre uno o más polígonos del mapa para incluirlos en el cuadro.",
                cell_style,
            )
        )

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# 8. SCAFFOLDING PARA RUTAS LOGÍSTICAS (OPENROUTESERVICE)
# ==============================================================================
def calcular_ruta_logistica(origen, destino, api_key=None, perfil="driving-hgv"):
    if not api_key or not origen or not destino:
        return None
    return None


def agregar_capa_ruta_logistica(mapa_folium, puntos_ruta, nombre="Ruta Logística", color="#FF5722", peso=5):
    if puntos_ruta and len(puntos_ruta) >= 2:
        folium.PolyLine(
            locations=puntos_ruta,
            color=color,
            weight=peso,
            opacity=0.85,
            tooltip=nombre,
            dash_array="6, 8",
        ).add_to(mapa_folium)


# ==============================================================================
# 9. BARRA LATERAL (FILTROS, PINCEL, BASES SULLAIR, EXPORTACIÓN Y ADMIN)
# ==============================================================================
with st.sidebar:
    try:
        st.image("Logo Sullair Verde.png", use_container_width=True)
    except Exception:
        st.warning("Falta el logo de Sullair en la carpeta.")

    # --- BOTÓN DE LIMPIEZA GLOBAL ---
    if st.button("🧹 Limpiar Mapa", type="primary", use_container_width=True):
        st.session_state.area_elegida = "TODAS"
        st.session_state.operadora_elegida = "TODAS"
        st.session_state.punto_buscado = None
        st.session_state.input_coords = ""
        st.session_state.areas_pintadas = {}
        st.session_state.ultimo_dibujo_procesado = None
        st.session_state.ultimas_coordenadas = None
        st.session_state.ultima_operadora = None
        st.session_state.ultimo_nombre_area = None
        st.session_state.map_center = CENTRO_DEFECTO
        st.session_state.map_zoom = 7
        st.rerun()

    st.divider()

    # --- SELECTOR DE TEMA DEL MAPA (SIN API KEY / 100% LIBRE DE MARCAS DE AGUA) ---
    st.header("🌓 Tema Visual del Mapa")
    MAP_THEME_OPTIONS = [
        "Claro (Gris Corporativo)",
        "Oscuro (Noche Ejecutiva)",
        "Clásico (Esri Street Map)",
        "Satélite (Esri World Imagery)",
    ]
    if st.session_state.get("map_theme") not in MAP_THEME_OPTIONS:
        st.session_state.map_theme = "Claro (Gris Corporativo)"

    st.radio(
        "Capa base del mapa:",
        options=MAP_THEME_OPTIONS,
        key="map_theme",
        help="Capas base empresariales Esri ArcGIS libres de API key.",
    )

    st.divider()

    # --- PINCEL DE SELECCIÓN CON PALETA PROFESIONAL ---
    st.header("🎨 Pincel de Selección")
    opciones_paleta = list(PALETA_PROFESIONAL.keys()) + ["Color personalizado..."]
    st.selectbox(
        "Tono profesional:",
        options=opciones_paleta,
        key="preset_color_pincel",
        on_change=on_preset_color_change,
        help="Colores ejecutivos calibrados para cartografía técnica y reportes PDF.",
    )
    color_pincel = st.color_picker(
        "Ajustar color activo:",
        key="color_picker_pincel",
    )
    num_pintadas = len(st.session_state.areas_pintadas)
    if num_pintadas > 0:
        st.caption(f"🖌️ Áreas pintadas activas: **{num_pintadas}**")
        if st.button("🗑️ Despintar todas las áreas", use_container_width=True):
            st.session_state.areas_pintadas = {}
            st.rerun()

    st.divider()

    # --- BASES FIJAS SULLAIR ---
    st.header("🏢 Bases Sullair (Fijas)")
    for p in puntos_fijos:
        col_b1, col_b2 = st.columns([3, 1])
        with col_b1:
            st.write(f"🟢 **{p['nombre']}**")
        with col_b2:
            if st.button("📍 Ir", key=f"btn_ir_{p['id']}"):
                st.session_state.map_center = [p["lat"], p["lon"]]
                st.session_state.map_zoom = 13
                st.session_state.ultimas_coordenadas = (p["lat"], p["lon"])
                st.session_state.ultima_operadora = "Sullair Argentina"
                st.session_state.ultimo_nombre_area = p["nombre"]
                st.rerun()

    st.divider()

    # --- FILTROS DE ÁREAS Y OPERADORAS ---
    st.header("🔎 Filtros del Mapa")
    lista_areas = ["TODAS"] + sorted(gdf_completo[COL_NOMBRE].dropna().astype(str).unique().tolist())
    lista_operadoras = ["TODAS"] + sorted(gdf_completo[COL_OPERADORA].dropna().astype(str).unique().tolist())

    st.selectbox("Iluminar un Área específica:", lista_areas, key="area_elegida", on_change=on_area_change)
    st.selectbox("Iluminar por Empresa operadora:", lista_operadoras, key="operadora_elegida", on_change=on_operadora_change)

    st.divider()

    # --- BÚSQUEDA DE COORDENADAS ---
    st.header("📍 Buscar Coordenadas")
    st.text_input("Pegá un link de Maps o coordenadas (GMS o Decimales):", key="input_coords", on_change=procesar_busqueda)

    st.divider()

    # --- INFORMACIÓN DEL POLÍGONO CLIQUEADO ---
    st.header("📄 Información del Área")
    info_placeholder = st.empty()
    if not estado_previo_mapa or not estado_previo_mapa.get("last_active_drawing"):
        info_placeholder.info("👈 Hacé clic en un polígono del mapa para ver toda su data acá.")
    else:
        props_clicked = estado_previo_mapa["last_active_drawing"].get("properties", {})
        items_str = [(str(k), str(v) if v is not None else "") for k, v in props_clicked.items()]
        df_props = pd.DataFrame(items_str, columns=["Dato", "Valor"])
        with info_placeholder.container():
            st.success(f"**{props_clicked.get(COL_NOMBRE, 'Área seleccionada')}**")
            st.dataframe(df_props, hide_index=True, use_container_width=True)

    st.divider()

    # --- ADMINISTRACIÓN DE CARTOGRAFÍA (SOLO ADMIN) ---
    if st.session_state.usuario == "admin":
        st.sidebar.markdown("### 🗺️ Administración de Cartografía")
        col_upd, col_rbk = st.sidebar.columns(2)
        with col_upd:
            if st.button("🔄 Actualizar", use_container_width=True, help="Descarga la última versión oficial y guarda un backup"):
                actualizar_datos()
        with col_rbk:
            hay_backup = os.path.exists(BACKUP_DIR) and bool(os.listdir(BACKUP_DIR))
            if st.button("⏪ Rollback", use_container_width=True, disabled=not hay_backup, help="Restaura la versión anterior del mapa"):
                restaurar_backup()
        st.divider()

    st.caption("© 2026 - Desarrollado por Fede García Cendra para Sullair Argentina S.A.")
    st.caption("Consultas a: fcendra@sullair.com.ar")

    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.usuario = None
        st.session_state.nombre_usuario = None
        clear_sullapps_sso()
        st.rerun()

# ==============================================================================
# 10. ESTILOS DINÁMICOS Y CONSTRUCCIÓN DEL MAPA FOLIUM
# ==============================================================================
tema_actual = st.session_state.get("map_theme", "Claro (Gris Corporativo)")
es_modo_oscuro = "Oscuro" in tema_actual or "Satélite" in tema_actual


def estilo_iluminado(feature):
    props = feature.get("properties", {})
    nombre_area = str(props.get(COL_NOMBRE, ""))
    empresa = str(props.get(COL_OPERADORA, ""))

    # 1. Polígonos pintados manualmente (tonos profesionales con borde nítido)
    if nombre_area in st.session_state.areas_pintadas:
        info_pintada = st.session_state.areas_pintadas[nombre_area]
        color_guardado = info_pintada["color"] if isinstance(info_pintada, dict) else info_pintada
        return {
            "fillColor": color_guardado,
            "color": "#F8FAFC" if es_modo_oscuro else "#1E293B",
            "weight": 2.2,
            "fillOpacity": 0.68,
        }

    # 2. Polígonos filtrados o vista general sobria
    iluminar = False
    if st.session_state.area_elegida != "TODAS" and nombre_area == st.session_state.area_elegida:
        iluminar = True
    elif st.session_state.operadora_elegida != "TODAS" and empresa == st.session_state.operadora_elegida:
        iluminar = True
    elif st.session_state.area_elegida == "TODAS" and st.session_state.operadora_elegida == "TODAS":
        if es_modo_oscuro:
            return {"fillColor": "#3B6998", "color": "#7DA2C8", "weight": 1.1, "fillOpacity": 0.25}
        return {"fillColor": "#5B82A6", "color": "#334E68", "weight": 1.0, "fillOpacity": 0.24}

    if iluminar:
        if es_modo_oscuro:
            return {"fillColor": "#2E9E5B", "color": "#ECFDF5", "weight": 2.6, "fillOpacity": 0.62}
        return {"fillColor": "#1B7A43", "color": "#064E3B", "weight": 2.6, "fillOpacity": 0.60}
    else:
        if es_modo_oscuro:
            return {"fillColor": "#334155", "color": "#475569", "weight": 0.8, "fillOpacity": 0.14}
        return {"fillColor": "#CBD5E1", "color": "#94A3B8", "weight": 0.8, "fillOpacity": 0.12}


# Capas base Esri ArcGIS Online (100% gratuitas y sin API key en Streamlit Cloud)
ref_tile_url = None
if "Oscuro" in tema_actual:
    tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
    ref_tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
    tile_attr = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
elif "Claro" in tema_actual:
    tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
    ref_tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
    tile_attr = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
elif "Satélite" in tema_actual:
    tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    tile_attr = "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics"
else:
    tile_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
    tile_attr = "Tiles &copy; Esri"

mapa = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    tiles=tile_url,
    attr=tile_attr,
)

if ref_tile_url:
    folium.TileLayer(
        tiles=ref_tile_url,
        attr=tile_attr,
        name="Etiquetas Geográficas",
        overlay=True,
        control=False,
    ).add_to(mapa)

folium.GeoJson(
    gdf_simplificado,
    name="Áreas Concesionadas",
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(
        fields=[COL_NOMBRE, COL_OPERADORA],
        aliases=["🛢️ Área:", "🏢 Operadora:"],
        style=(
            "background-color: #0F172A; color: #F8FAFC; border: 1px solid #38BDF8; border-radius: 6px; padding: 6px 10px; font-family: sans-serif;"
            if es_modo_oscuro
            else "background-color: #FFFFFF; color: #1F2937; border: 1px solid #006837; border-radius: 6px; padding: 6px 10px; font-family: sans-serif;"
        ),
    ),
).add_to(mapa)

for pf in puntos_fijos:
    folium.Marker(
        location=[pf["lat"], pf["lon"]],
        popup=folium.Popup(
            f"<b>🏢 {pf['nombre']}</b><br>📌 {pf.get('categoria', '')}<br>📍 {pf.get('coords_raw', '')}",
            max_width=250,
        ),
        tooltip=f"🏢 {pf['nombre']} ({pf.get('categoria', '')})",
        icon=folium.Icon(color="green", icon="flag", prefix="glyphicon"),
    ).add_to(mapa)

if st.session_state.punto_buscado:
    folium.Marker(
        st.session_state.punto_buscado,
        popup="📍 Punto Buscado",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(mapa)

ruta_activa = None
if ruta_activa:
    agregar_capa_ruta_logistica(mapa, ruta_activa, nombre="Ruta de Abastecimiento")

# ==============================================================================
# 11. RENDERIZADO, DISPLAY GMS UNIFICADO Y MAPA
# ==============================================================================
st.title("🗺️ Visor de Áreas Hidrocarburíferas")

if st.session_state.ultimas_coordenadas:
    lat_act, lon_act = st.session_state.ultimas_coordenadas
    gms_texto = decimal_a_gms(lat_act, lon_act)
    op = st.session_state.ultima_operadora or "Sin operadora"
    area = st.session_state.ultimo_nombre_area or "No especificada"
    tiene_op = bool(st.session_state.ultima_operadora and st.session_state.ultima_operadora not in ["None", "nan", ""])

    bg_color = "#e8f5e9" if tiene_op else "#e1f5fe"
    text_color = "#1b5e20" if tiene_op else "#01579b"
    border_color = "#c8e6c9" if tiene_op else "#b3e5fc"
    btn_color = "#006837" if tiene_op else "#0288d1"

    info_detalle = (
        f"&nbsp;|&nbsp; 🏢 <b>Operadora:</b> <b>{op}</b> &nbsp;|&nbsp; 🛢️ <b>Área:</b> <b>{area}</b>"
        if tiene_op
        else "&nbsp;|&nbsp; ℹ️ <i>Punto fuera de áreas catastradas</i>"
    )

    gms_json = json.dumps(gms_texto)

    banner_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: transparent;
            overflow: hidden;
        }}
        .banner {{
            background-color: {bg_color};
            color: {text_color};
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid {border_color};
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-sizing: border-box;
            height: 44px;
        }}
        .info-text {{
            font-size: 14px;
            line-height: 1.4;
            display: flex;
            align-items: center;
            flex-wrap: nowrap;
            gap: 6px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .coords-code {{
            background: rgba(0,0,0,0.07);
            padding: 2px 7px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 13.5px;
            font-family: monospace;
        }}
        .btn-copy {{
            background-color: {btn_color};
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
            margin-left: 12px;
            outline: none;
            flex-shrink: 0;
        }}
        .btn-copy:hover {{
            opacity: 0.9;
            transform: translateY(-1px);
        }}
        .btn-copy:active {{
            transform: translateY(0);
        }}
    </style>
    </head>
    <body>
    <div class="banner">
        <div class="info-text">
            <span>📍 <b>Coordenadas Activas (GMS):</b></span>
            <span class="coords-code">{gms_texto}</span>
            <span>{info_detalle}</span>
        </div>
        <button id="btnCopy" class="btn-copy" type="button" onclick="copyCoords()">
            📋 Copiar
        </button>
    </div>
    <script>
    window.copyCoords = function() {{
        const text = {gms_json};
        let success = false;
        
        try {{
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'fixed';
            textarea.style.left = '0';
            textarea.style.top = '0';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);
            success = document.execCommand('copy');
            document.body.removeChild(textarea);
        }} catch (e) {{
            success = false;
        }}
        
        if (!success && navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(text).then(showSuccess).catch(function(err) {{
                console.warn('Clipboard API:', err);
            }});
        }} else if (success) {{
            showSuccess();
        }}
    }};

    function showSuccess() {{
        const btn = document.getElementById('btnCopy');
        if (btn) {{
            btn.innerText = '✅ ¡Copiado!';
            btn.style.backgroundColor = '#1b5e20';
            setTimeout(function() {{
                btn.innerText = '📋 Copiar';
                btn.style.backgroundColor = '{btn_color}';
            }}, 2000);
        }}
    }}
    </script>
    </body>
    </html>
    """
    components.html(banner_html, height=48)
else:
    st.info(
        "📍 **Coordenadas Activas:** Seleccioná un área en el mapa, una base Sullair o ingresá coordenadas en el buscador lateral para ver detalles y copiarlas."
    )

# Renderizado de Folium ultra fluido con st_folium
st_folium(
    mapa,
    key="mapa_folium",
    width=None,
    use_container_width=True,
    height=600,
    returned_objects=["last_active_drawing"],
)

# ==============================================================================
# 12. EXPORTACIÓN DEL MAPA (IMAGEN PNG Y PDF CON CUADRO DE COORDENADAS) + TABLA
# ==============================================================================
st.markdown("---")
col_exp_title, col_exp_zoom = st.columns([2.2, 1.8])
with col_exp_title:
    st.subheader(f"📋 Áreas Seleccionadas y Exportación ({len(st.session_state.areas_pintadas)} pintadas)")
with col_exp_zoom:
    encuadre_export = st.radio(
        "Encuadre al exportar imagen/PDF:",
        options=["Cuenca completa", "Ajustar a áreas seleccionadas"],
        horizontal=True,
        key="radio_encuadre_export",
    )

filas_export = obtener_filas_exportacion()
png_mapa_bytes = generar_imagen_mapa_png(
    gdf=gdf_completo,
    areas_pintadas=st.session_state.areas_pintadas,
    area_elegida=st.session_state.area_elegida,
    operadora_elegida=st.session_state.operadora_elegida,
    puntos_fijos_list=puntos_fijos,
    punto_buscado=st.session_state.punto_buscado,
    es_modo_oscuro=es_modo_oscuro,
    encuadre=encuadre_export,
)
pdf_reporte_bytes = generar_reporte_mapa_pdf(
    png_bytes=png_mapa_bytes,
    filas_detalle=filas_export,
)

c_dl1, c_dl2, c_dl3 = st.columns(3)
with c_dl1:
    st.download_button(
        "🖼️ Descargar Mapa como Imagen (PNG)",
        data=png_mapa_bytes,
        file_name="petromaps_areas_sullair.png",
        mime="image/png",
        use_container_width=True,
        type="primary",
    )
with c_dl2:
    st.download_button(
        "📄 Descargar PDF (Mapa + Coordenadas)",
        data=pdf_reporte_bytes,
        file_name="reporte_petromaps_sullair.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )
with c_dl3:
    df_export = pd.DataFrame(
        [
            {
                "Color_Hex": item.get("color", ""),
                "Area": item.get("area", ""),
                "Operadora": item.get("operadora", ""),
                "Coordenadas_GMS": item.get("gms", ""),
                "Latitud": item.get("lat"),
                "Longitud": item.get("lon"),
            }
            for item in filas_export
        ]
    )
    csv_data = df_export.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar Cuadro (CSV)",
        data=csv_data,
        file_name="detalle_areas_seleccionadas.csv",
        mime="text/csv",
        use_container_width=True,
    )

if st.session_state.areas_pintadas:
    filas_html = []
    for nombre, data in st.session_state.areas_pintadas.items():
        color_hex = data.get("color", "#2B5B84")
        operadora = data.get("operadora", "Sin operadora")
        gms = data.get("gms", "")
        lat_val = data.get("lat")
        lon_val = data.get("lon")
        lat_str = f"{float(lat_val):.5f}" if (lat_val is not None and not pd.isna(lat_val)) else "-"
        lon_str = f"{float(lon_val):.5f}" if (lon_val is not None and not pd.isna(lon_val)) else "-"

        color_badge = (
            f'<span style="display:inline-block; width:18px; height:18px; border-radius:50%; '
            f'background-color:{color_hex}; border:1.5px solid #222; vertical-align:middle; '
            f'box-shadow: 0 0 3px rgba(0,0,0,0.3);" title="{color_hex}"></span>'
        )

        filas_html.append(
            {
                "Color": color_badge,
                "Área / Locación": f"<b>{nombre}</b>",
                "Operadora": operadora,
                "Coordenadas (GMS)": f"<code>{gms}</code>",
                "Latitud": lat_str,
                "Longitud": lon_str,
            }
        )

    df_html = pd.DataFrame(filas_html)
    raw_html_table = df_html.to_html(escape=False, index=False)

    styled_table = f"""
    <div style="overflow-x: auto; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; margin-top: 12px; margin-bottom: 20px;">
        <style>
            .tabla-detalle {{
                width: 100%;
                border-collapse: collapse;
                font-family: inherit;
                font-size: 0.95rem;
            }}
            .tabla-detalle th {{
                background-color: rgba(0, 104, 55, 0.10);
                padding: 10px 14px;
                text-align: left;
                border-bottom: 2px solid rgba(0, 104, 55, 0.25);
                font-weight: 600;
            }}
            .tabla-detalle td {{
                padding: 10px 14px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.15);
                vertical-align: middle;
            }}
            .tabla-detalle tr:hover {{
                background-color: rgba(0, 104, 55, 0.04);
            }}
        </style>
        {raw_html_table.replace('<table border="1" class="dataframe">', '<table class="tabla-detalle">')}
    </div>
    """
    st.markdown(styled_table, unsafe_allow_html=True)
