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
from shapely.geometry import Point, shape
import requests
import zipfile
import io

st.set_page_config(page_title="Mapa de Áreas Hidrocarburíferas", page_icon="🛢️", layout="wide")

# ==============================================================================
# 0. SISTEMA DE LOGIN Y CONTROL DE ACCESO
# ==============================================================================
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

if not st.session_state.usuario:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        try:
            st.image("Logo Sullair Verde.png", width=300)
        except Exception:
            st.title("SULLAIR ARGENTINA")
            
        st.subheader("🔒 Acceso al Sistema")
        us = st.text_input("Usuario")
        pw = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar", use_container_width=True):
            if us == "fcendra" and pw == "C4n1ch3r1426":
                st.session_state.usuario = "admin"
                st.rerun()
            elif us == "gensullair" and pw == "2026sullair!":
                st.session_state.usuario = "user"
                st.rerun()
            else:
                st.error("Credenciales incorrectas. Verificá los datos ingresados.")
    st.stop()

# ==============================================================================
# CONSTANTES DE DATOS Y PERSISTENCIA
# ==============================================================================
COL_NOMBRE = 'nombre'
COL_OPERADORA = 'operador'
RUTA_PUNTOS_FIJOS = 'data/puntos_fijos.json'

# Puntos fijos predeterminados (Bases Sullair)
PUNTOS_FIJOS_DEFAULT = [
    {
        "id": "base_anelo",
        "nombre": "Base Sullair Añelo",
        "coords_raw": "38°20'22.0\"S 68°49'17.9\"W",
        "lat": -38.339444,
        "lon": -68.821639,
        "categoria": "Base Operativa",
        "color": "#009639"
    },
    {
        "id": "base_neuquen",
        "nombre": "Base Sullair Neuquén",
        "coords_raw": "38°54'13.6\"S 68°05'09.7\"W",
        "lat": -38.903778,
        "lon": -68.086028,
        "categoria": "Base Central",
        "color": "#009639"
    }
]

def cargar_puntos_fijos():
    if os.path.exists(RUTA_PUNTOS_FIJOS):
        try:
            with open(RUTA_PUNTOS_FIJOS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(RUTA_PUNTOS_FIJOS), exist_ok=True)
        with open(RUTA_PUNTOS_FIJOS, 'w', encoding='utf-8') as f:
            json.dump(PUNTOS_FIJOS_DEFAULT, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return PUNTOS_FIJOS_DEFAULT

# ==============================================================================
# 1. FUNCIÓN DE ACTUALIZACIÓN DE DATOS (ADMIN)
# ==============================================================================
def actualizar_datos():
    url_zip = "https://portaldatosabiertos.neuquen.gov.ar/dataset/8447d6e8-3162-4217-91f9-974a6821217e/resource/8750c10c-9ad9-473f-9862-a9b1dabaf7d4/download/areas_hidrocarburiferas.zip" 
    
    try:
        with st.spinner("Descargando e instalando mapa actualizado desde Neuquén..."):
            r = requests.get(url_zip, timeout=30)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            z.extractall("data/")
        st.sidebar.success("¡Datos actualizados correctamente!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Falló la descarga de datos: {e}")

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

    match_url = re.search(r'[@?&/](-?\d{1,2}\.\d+)[,/](-?\d{1,3}\.\d+)', texto)
    if match_url:
        lat, lon = float(match_url.group(1)), float(match_url.group(2))
        return _validar_y_ajustar_lat_lon(lat, lon)

    t = texto.replace('”', '"').replace('’', "'").replace('″', '"').replace('′', "'").replace('´', "'")
    
    regex_dms = r'(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*([NSns])\s*[,;/]?\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*([EWOewo])'
    match_dms = re.search(regex_dms, t)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
        if lat_dir.upper() == 'S':
            lat = -lat
        lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
        if lon_dir.upper() in ['W', 'O']:
            lon = -lon
        return _validar_y_ajustar_lat_lon(lat, lon)

    regex_dms_inv = r'([NSns])\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]?\s*[,;/]?\s*([EWOewo])\s*(\d{1,3})\s*°?\s*(\d{1,2})\s*[\'′]?\s*([\d\.]+)\s*["″]'
    match_inv = re.search(regex_dms_inv, t)
    if match_inv:
        lat_dir, lat_d, lat_m, lat_s, lon_dir, lon_d, lon_m, lon_s = match_inv.groups()
        lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
        if lat_dir.upper() == 'S':
            lat = -lat
        lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
        if lon_dir.upper() in ['W', 'O']:
            lon = -lon
        return _validar_y_ajustar_lat_lon(lat, lon)

    t_dec = re.sub(r'(\d),(\d)', r'\1.\2', t)
    floats = re.findall(r'[-+]?\d{1,3}\.\d+', t_dec)
    if len(floats) >= 2:
        lat, lon = float(floats[0]), float(floats[1])
        return _validar_y_ajustar_lat_lon(lat, lon)
        
    return None, None

# ==============================================================================
# 3. CARGA Y PROCESAMIENTO DE GEODATOS (ULTRA OPTIMIZADO)
# ==============================================================================
@st.cache_data
def cargar_datos():
    ruta_archivo = 'data/areas_hidrocarburiferas.shp'
    gdf = gpd.read_file(ruta_archivo)
    gdf = gdf.to_crs(epsg=4326)
    
    gdf = gdf[gdf.geometry.notnull() & ~gdf.geometry.is_empty].copy()
    try:
        gdf['geometry'] = gdf['geometry'].make_valid()
    except Exception:
        pass
    
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
            
    try:
        centroids_4326 = gdf.to_crs(epsg=3857).geometry.centroid.to_crs(epsg=4326)
        gdf['lat_centro'] = centroids_4326.y
        gdf['lon_centro'] = centroids_4326.x
    except Exception:
        centroids = gdf.geometry.centroid
        gdf['lat_centro'] = centroids.y
        gdf['lon_centro'] = centroids.x
    
    lookup_areas = {}
    for _, row in gdf.iterrows():
        nombre = str(row[COL_NOMBRE])
        operador = str(row[COL_OPERADORA]) if pd.notna(row[COL_OPERADORA]) else "Sin operadora"
        lat = row['lat_centro'] if pd.notna(row['lat_centro']) else None
        lon = row['lon_centro'] if pd.notna(row['lon_centro']) else None
        lookup_areas[nombre] = {
            'operador': operador,
            'lat': float(lat) if lat is not None else None,
            'lon': float(lon) if lon is not None else None,
            'gms': decimal_a_gms(lat, lon) if (lat is not None and lon is not None) else ""
        }
        
    gdf_simplificado = gdf.copy()
    try:
        gdf_simplificado['geometry'] = gdf.geometry.simplify(tolerance=0.0005, preserve_topology=True)
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
if 'area_elegida' not in st.session_state:
    st.session_state.area_elegida = "TODAS"
if 'operadora_elegida' not in st.session_state:
    st.session_state.operadora_elegida = "TODAS"
if 'punto_buscado' not in st.session_state:
    st.session_state.punto_buscado = None
if 'areas_pintadas' not in st.session_state:
    st.session_state.areas_pintadas = {}
if 'ultimo_dibujo_procesado' not in st.session_state:
    st.session_state.ultimo_dibujo_procesado = None
if 'ultimas_coordenadas' not in st.session_state:
    st.session_state.ultimas_coordenadas = None
if 'ultima_operadora' not in st.session_state:
    st.session_state.ultima_operadora = None
if 'ultimo_nombre_area' not in st.session_state:
    st.session_state.ultimo_nombre_area = None
if 'map_center' not in st.session_state:
    st.session_state.map_center = CENTRO_DEFECTO
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 7

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
            operador_clic = meta['operador']
            lat_clic, lon_clic = meta['lat'], meta['lon']
            gms_clic = meta['gms']
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

        color_actual = st.session_state.get("color_picker_pincel", "#FF5733")
        if nombre_clic:
            if nombre_clic in st.session_state.areas_pintadas:
                del st.session_state.areas_pintadas[nombre_clic]
            else:
                st.session_state.areas_pintadas[nombre_clic] = {
                    "color": color_actual,
                    "operadora": operador_clic,
                    "lat": lat_clic,
                    "lon": lon_clic,
                    "gms": gms_clic
                }

# ==============================================================================
# 6. MANEJADORES DE FILTROS Y BÚSQUEDA
# ==============================================================================
def on_area_change():
    st.session_state.operadora_elegida = "TODAS"
    area_sel = st.session_state.area_elegida
    if area_sel != "TODAS" and area_sel in lookup_areas:
        info = lookup_areas[area_sel]
        if info['lat'] is not None and info['lon'] is not None:
            st.session_state.map_center = [info['lat'], info['lon']]
            st.session_state.map_zoom = 10
            st.session_state.ultimas_coordenadas = (info['lat'], info['lon'])
        st.session_state.ultima_operadora = info['operador']
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
# 7. SCAFFOLDING PARA RUTAS LOGÍSTICAS (OPENROUTESERVICE)
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
            dash_array="6, 8"
        ).add_to(mapa_folium)

# ==============================================================================
# 8. BARRA LATERAL (FILTROS, PINCEL, BASES SULLAIR Y ACCIONES)
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

    # --- PINCEL DE COLOR ---
    st.header("🎨 Pincel de Selección")
    color_pincel = st.color_picker("Color para pintar polígonos:", value="#FF5733", key="color_picker_pincel")
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
    
    st.selectbox("Iluminar un Área específica:", lista_areas, key='area_elegida', on_change=on_area_change)
    st.selectbox("Iluminar por Empresa operadora:", lista_operadoras, key='operadora_elegida', on_change=on_operadora_change)
    
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
        # Convertir todos los valores a string para compatibilidad 100% con PyArrow
        items_str = [(str(k), str(v) if v is not None else "") for k, v in props_clicked.items()]
        df_props = pd.DataFrame(items_str, columns=["Dato", "Valor"])
        with info_placeholder.container():
            st.success(f"**{props_clicked.get(COL_NOMBRE, 'Área seleccionada')}**")
            st.dataframe(df_props, hide_index=True, use_container_width=True)
    
    st.divider()
    
    if st.session_state.usuario == "admin":
        if st.button("🔄 Actualizar Datos desde Neuquén", use_container_width=True):
            actualizar_datos()
        st.divider()

    st.caption("© 2026 - Desarrollado por Fede García Cendra para Sullair Argentina S.A.")
    st.caption("Consultas a: fcendra@sullair.com.ar")
    
    if st.button("Cerrar Sesión"):
        st.session_state.usuario = None
        st.rerun()

# ==============================================================================
# 9. ESTILOS DINÁMICOS Y CONSTRUCCIÓN DEL MAPA FOLIUM
# ==============================================================================
def estilo_iluminado(feature):
    props = feature.get('properties', {})
    nombre_area = str(props.get(COL_NOMBRE, ''))
    empresa = str(props.get(COL_OPERADORA, ''))
    
    if nombre_area in st.session_state.areas_pintadas:
        info_pintada = st.session_state.areas_pintadas[nombre_area]
        color_guardado = info_pintada["color"] if isinstance(info_pintada, dict) else info_pintada
        return {
            'fillColor': color_guardado,
            'color': '#111111',
            'weight': 2.5,
            'fillOpacity': 0.8
        }
    
    iluminar = False
    if st.session_state.area_elegida != "TODAS" and nombre_area == st.session_state.area_elegida:
        iluminar = True
    elif st.session_state.operadora_elegida != "TODAS" and empresa == st.session_state.operadora_elegida:
        iluminar = True
    elif st.session_state.area_elegida == "TODAS" and st.session_state.operadora_elegida == "TODAS":
        return {'fillColor': '#3388ff', 'color': 'black', 'weight': 1, 'fillOpacity': 0.35}
        
    if iluminar:
        return {'fillColor': '#00ff00', 'color': 'black', 'weight': 3, 'fillOpacity': 0.7}
    else:
        return {'fillColor': '#cccccc', 'color': 'gray', 'weight': 1, 'fillOpacity': 0.1}

mapa = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attr='Esri'
)

folium.GeoJson(
    gdf_simplificado,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[COL_NOMBRE, COL_OPERADORA])
).add_to(mapa)

for pf in puntos_fijos:
    folium.Marker(
        location=[pf["lat"], pf["lon"]],
        popup=folium.Popup(f"<b>🏢 {pf['nombre']}</b><br>📌 {pf.get('categoria', '')}<br>📍 {pf.get('coords_raw', '')}", max_width=250),
        tooltip=f"🏢 {pf['nombre']} ({pf.get('categoria', '')})",
        icon=folium.Icon(color="green", icon="flag", prefix="glyphicon")
    ).add_to(mapa)

if st.session_state.punto_buscado:
    folium.Marker(
        st.session_state.punto_buscado,
        popup="📍 Punto Buscado",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa)

ruta_activa = None
if ruta_activa:
    agregar_capa_ruta_logistica(mapa, ruta_activa, nombre="Ruta de Abastecimiento")

# ==============================================================================
# 10. RENDERIZADO, DISPLAY GMS UNIFICADO Y MAPA
# ==============================================================================
st.title("🗺️ Visor de Áreas Hidrocarburíferas")

# --- PANEL DE COORDENADAS ACTIVAS UNIFICADO (1 SOLO CUADRO CON BOTÓN COPIAR INTEGRADO) ---
if st.session_state.ultimas_coordenadas:
    lat_act, lon_act = st.session_state.ultimas_coordenadas
    gms_texto = decimal_a_gms(lat_act, lon_act)
    op = st.session_state.ultima_operadora or "Sin operadora"
    area = st.session_state.ultimo_nombre_area or "No especificada"
    tiene_op = bool(st.session_state.ultima_operadora and st.session_state.ultima_operadora not in ["None", "nan", ""])
    
    bg_color = "#e8f5e9" if tiene_op else "#e1f5fe"
    text_color = "#1b5e20" if tiene_op else "#01579b"
    border_color = "#c8e6c9" if tiene_op else "#b3e5fc"
    btn_color = "#009639" if tiene_op else "#0288d1"
    
    info_detalle = f"&nbsp;|&nbsp; 🏢 <b>Operadora:</b> <b>{op}</b> &nbsp;|&nbsp; 🛢️ <b>Área:</b> <b>{area}</b>" if tiene_op else "&nbsp;|&nbsp; ℹ️ <i>Punto fuera de áreas catastradas</i>"
    
    banner_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: {bg_color}; color: {text_color}; padding: 9px 16px; border-radius: 8px; border: 1px solid {border_color}; display: flex; align-items: center; justify-content: space-between; margin-bottom: 0px; box-sizing: border-box;">
        <div style="font-size: 14px; line-height: 1.4; display: flex; align-items: center; flex-wrap: wrap; gap: 6px;">
            <span>📍 <b>Coordenadas Activas (GMS):</b></span>
            <code style="background: rgba(0,0,0,0.06); padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 13.5px;">{gms_texto}</code>
            <span>{info_detalle}</span>
        </div>
        <button id="btnCopy" onclick="copyCoords()" style="background-color: {btn_color}; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap; transition: 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin-left: 12px; outline: none;">
            📋 Copiar
        </button>
    </div>
    <script>
    function copyCoords() {{
        const text = "{gms_texto}";
        let success = false;
        
        // Método 1: Textarea con foco explícito (compatible 100% con iframes)
        try {{
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.left = "0";
            textarea.style.top = "0";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);
            success = document.execCommand("copy");
            document.body.removeChild(textarea);
        }} catch (e) {{
            success = false;
        }}
        
        // Método 2: Clipboard API moderna (si está disponible y permitida)
        if (!success && navigator.clipboard) {{
            navigator.clipboard.writeText(text).then(showSuccess).catch(() => {{}});
        }} else if (success) {{
            showSuccess();
        }}
    }}
    function showSuccess() {{
        const btn = document.getElementById('btnCopy');
        btn.innerText = '✅ ¡Copiado!';
        btn.style.backgroundColor = '#1b5e20';
        setTimeout(() => {{
            btn.innerText = '📋 Copiar';
            btn.style.backgroundColor = '{btn_color}';
        }}, 2000);
    }}
    </script>
    """
    components.html(banner_html, height=52)
else:
    st.info("📍 **Coordenadas Activas:** Seleccioná un área en el mapa, una base Sullair o ingresá coordenadas en el buscador lateral para ver detalles y copiarlas.")

# Renderizado de Folium ultra fluido con st_folium
st_folium(
    mapa,
    key="mapa_folium",
    width=None,
    use_container_width=True,
    height=600,
    returned_objects=["last_active_drawing"]
)

# ==============================================================================
# 11. DETALLE DE ÁREAS SELECCIONADAS (CON REDONDEL DE COLOR VISUAL)
# ==============================================================================
if st.session_state.areas_pintadas:
    st.markdown("---")
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.subheader(f"📋 Detalle de Áreas Seleccionadas ({len(st.session_state.areas_pintadas)})")
    with col_t2:
        df_export = pd.DataFrame([
            {
                "Color_Hex": data.get("color", ""),
                "Area": nombre,
                "Operadora": data.get("operadora", ""),
                "Coordenadas_GMS": data.get("gms", ""),
                "Latitud": data.get("lat"),
                "Longitud": data.get("lon")
            }
            for nombre, data in st.session_state.areas_pintadas.items()
        ])
        csv_data = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Descargar CSV",
            data=csv_data,
            file_name="detalle_areas_seleccionadas.csv",
            mime="text/csv",
            use_container_width=True
        )

    filas_html = []
    for nombre, data in st.session_state.areas_pintadas.items():
        color_hex = data.get("color", "#FF5733")
        operadora = data.get("operadora", "Sin operadora")
        gms = data.get("gms", "")
        lat_val = data.get("lat")
        lon_val = data.get("lon")
        lat_str = f"{float(lat_val):.5f}" if (lat_val is not None and not pd.isna(lat_val)) else "-"
        lon_str = f"{float(lon_val):.5f}" if (lon_val is not None and not pd.isna(lon_val)) else "-"
        
        color_badge = f'<span style="display:inline-block; width:18px; height:18px; border-radius:50%; background-color:{color_hex}; border:1.5px solid #222; vertical-align:middle; box-shadow: 0 0 3px rgba(0,0,0,0.3);" title="{color_hex}"></span>'
        
        filas_html.append({
            "Color": color_badge,
            "Área / Locación": f"<b>{nombre}</b>",
            "Operadora": operadora,
            "Coordenadas (GMS)": f"<code>{gms}</code>",
            "Latitud": lat_str,
            "Longitud": lon_str
        })
    
    df_html = pd.DataFrame(filas_html)
    raw_html_table = df_html.to_html(escape=False, index=False)
    
    styled_table = f"""
    <div style="overflow-x: auto; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; margin-top: 8px; margin-bottom: 20px;">
        <style>
            .tabla-detalle {{
                width: 100%;
                border-collapse: collapse;
                font-family: inherit;
                font-size: 0.95rem;
            }}
            .tabla-detalle th {{
                background-color: rgba(128, 128, 128, 0.12);
                padding: 10px 14px;
                text-align: left;
                border-bottom: 2px solid rgba(128, 128, 128, 0.25);
                font-weight: 600;
            }}
            .tabla-detalle td {{
                padding: 10px 14px;
                border-bottom: 1px solid rgba(128, 128, 128, 0.15);
                vertical-align: middle;
            }}
            .tabla-detalle tr:hover {{
                background-color: rgba(128, 128, 128, 0.06);
            }}
        </style>
        {raw_html_table.replace('<table border="1" class="dataframe">', '<table class="tabla-detalle">')}
    </div>
    """
    st.markdown(styled_table, unsafe_allow_html=True)
