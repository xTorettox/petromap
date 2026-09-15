import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import re
from shapely.geometry import Point
import requests
import zipfile
import io

st.set_page_config(page_title="Mapa de Áreas Hidrocarburíferas", page_icon="🛢️", layout="wide")

# --- 0. SISTEMA DE LOGIN ---
if 'usuario' not in st.session_state:
    st.session_state.usuario = None

if not st.session_state.usuario:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Tratamos de cargar el logo si está, si no, texto nomás
        try:
            st.image("Logo Sullair Verde.png", width=300)
        except:
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
                st.error("Credenciales incorrectas. Rajá de acá, salame.")
    st.stop() # Esto frena la app acá hasta que te loguees bien

# --- CONSTANTES ---
COL_NOMBRE = 'nombre'
COL_OPERADORA = 'operador'

# --- 1. FUNCIÓN DE ACTUALIZACIÓN ---
def actualizar_datos():
    # URL directa de descarga del portal de Neuquén
    url_zip = "https://portaldatosabiertos.neuquen.gov.ar/dataset/8447d6e8-3162-4217-91f9-974a6821217e/resource/8750c10c-9ad9-473f-9862-a9b1dabaf7d4/download/areas_hidrocarburiferas.zip" 
    
    try:
        with st.spinner("Descargando e instalando mapa actualizado..."):
            r = requests.get(url_zip)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            z.extractall("data/")
        st.sidebar.success("¡Datos actualizados al toque!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Falló la descarga: {e}")

# --- 2. CARGA DE DATOS ---
@st.cache_data
def cargar_datos():
    ruta_archivo = 'data/areas_hidrocarburiferas.shp'
    gdf = gpd.read_file(ruta_archivo)
    gdf = gdf.to_crs(epsg=4326)
    
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
    return gdf

try:
    gdf = cargar_datos()
except Exception as e:
    st.error(f"Error al cargar el mapa. Detalle: {e}")
    st.stop()

# --- 3. MANEJO DE ESTADOS Y EXTRACCIÓN ---
if 'area_elegida' not in st.session_state: st.session_state.area_elegida = "TODAS"
if 'operadora_elegida' not in st.session_state: st.session_state.operadora_elegida = "TODAS"
if 'punto_buscado' not in st.session_state: st.session_state.punto_buscado = None

def reset_operadora(): st.session_state.operadora_elegida = "TODAS"
def reset_area(): st.session_state.area_elegida = "TODAS"

def extraer_coordenadas(texto):
    if not texto: return None, None
    
    # Resolvemos los links acortados de Maps
    if "maps.app.goo.gl" in texto or "goo.gl/maps" in texto:
        try:
            r = requests.get(texto, allow_redirects=True, timeout=5)
            texto = r.url
        except:
            pass

    # DMS (Grados Minutos Segundos)
    match_dms = re.search(r'(\d+)°(\d+)\'([\d\.]+)"([NSns])\s*(\d+)°(\d+)\'([\d\.]+)"([EWOewo])', texto)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
        if lat_dir.upper() == 'S': lat = -lat
        lon = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
        if lon_dir.upper() in ['W', 'O']: lon = -lon
        return lat, lon

    # Decimales en links o pegados sueltos
    match_link = re.search(r'[-@/](-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)', texto)
    if match_link: return float(match_link.group(1)), float(match_link.group(2))
    
    match_dec = re.findall(r'-?\d{1,2}\.\d+', texto)
    if len(match_dec) >= 2: return float(match_dec[0]), float(match_dec[1])
    return None, None

def procesar_busqueda():
    texto = st.session_state.input_coords
    lat, lon = extraer_coordenadas(texto)
    
    if lat and lon:
        st.session_state.punto_buscado = [lat, lon]
        punto = Point(lon, lat)
        area_encontrada = gdf[gdf.geometry.contains(punto)]
        
        # Si cae en un área, aplicamos el filtro automáticamente y borramos el resto
        if not area_encontrada.empty:
            st.session_state.area_elegida = str(area_encontrada.iloc[0][COL_NOMBRE])
            st.session_state.operadora_elegida = "TODAS"
    else:
        st.session_state.punto_buscado = None

# --- 4. BARRA LATERAL ---
with st.sidebar:
    try:
        st.image("Logo Sullair Verde.png", use_container_width=True)
    except:
        st.warning("Falta el logo de Sullair en la carpeta.")
        
    st.header("🔎 Filtros del Mapa")
    
    lista_areas = ["TODAS"] + sorted(gdf[COL_NOMBRE].dropna().astype(str).unique().tolist())
    lista_operadoras = ["TODAS"] + sorted(gdf[COL_OPERADORA].dropna().astype(str).unique().tolist())
    
    st.selectbox("Iluminar un Área específica:", lista_areas, key='area_elegida', on_change=reset_operadora)
    st.selectbox("Iluminar por Empresa operadora:", lista_operadoras, key='operadora_elegida', on_change=reset_area)
    
    st.divider()
    
    st.header("📍 Buscar Coordenadas")
    st.text_input("Pegá un link de Maps o coordenadas (GMS o Decimales):", key="input_coords", on_change=procesar_busqueda)
    
    st.divider()
    
    st.header("📄 Información del Área")
    info_placeholder = st.empty()
    info_placeholder.info("👈 Hacé clic en un polígono del mapa para ver toda su data acá.")
    
    st.divider()
    
    # Menú exclusivo para el Administrador
    if st.session_state.usuario == "admin":
        if st.button("🔄 Actualizar Datos desde Neuquén", use_container_width=True):
            actualizar_datos()
        st.divider()

    st.caption("© 2026 - Desarrollado por Fede García Cendra para Sullair Argentina S.A.")
    st.caption("Consultas a: fcendra@sullair.com.ar")
    
    if st.button("Cerrar Sesión"):
        st.session_state.usuario = None
        st.rerun()

# --- 5. MAPA Y ESTILOS ---
def estilo_iluminado(feature):
    nombre_area = str(feature['properties'].get(COL_NOMBRE))
    empresa = str(feature['properties'].get(COL_OPERADORA))
    
    iluminar = False
    if st.session_state.area_elegida != "TODAS" and nombre_area == st.session_state.area_elegida:
        iluminar = True
    elif st.session_state.operadora_elegida != "TODAS" and empresa == st.session_state.operadora_elegida:
        iluminar = True
    elif st.session_state.area_elegida == "TODAS" and st.session_state.operadora_elegida == "TODAS":
        return {'fillColor': '#3388ff', 'color': 'black', 'weight': 1, 'fillOpacity': 0.4}
        
    if iluminar:
        return {'fillColor': '#00ff00', 'color': 'black', 'weight': 3, 'fillOpacity': 0.7}
    else:
        return {'fillColor': '#cccccc', 'color': 'gray', 'weight': 1, 'fillOpacity': 0.1}

if st.session_state.punto_buscado:
    centro = st.session_state.punto_buscado
    zoom = 12
else:
    minx, miny, maxx, maxy = gdf.total_bounds
    centro = [(miny + maxy) / 2.0, (minx + maxx) / 2.0]
    zoom = 6

mapa = folium.Map(
    location=centro, zoom_start=zoom,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attr='Esri'
)

folium.GeoJson(
    gdf,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[COL_NOMBRE, COL_OPERADORA])
).add_to(mapa)

# Dibujamos el punto si hubo búsqueda
if st.session_state.punto_buscado:
    folium.Marker(st.session_state.punto_buscado, popup="📍 Punto Buscado", icon=folium.Icon(color="red")).add_to(mapa)

st.title("🗺️ Visor de Áreas Hidrocarburíferas")

# ¡LA MAGIA DE LA VELOCIDAD ESTÁ ACÁ! Solo devolvemos la info del polígono cliqueado, no el mapa entero.
datos_mapa = st_folium(mapa, width=1200, height=650, returned_objects=["last_active_drawing"])

if datos_mapa and datos_mapa.get("last_active_drawing"):
    propiedades = datos_mapa["last_active_drawing"]["properties"]
    df_info = pd.DataFrame(list(propiedades.items()), columns=["Dato", "Valor"])
    
    with info_placeholder.container():
        st.success(f"**{propiedades.get(COL_NOMBRE, 'Área seleccionada')}**")
        st.dataframe(df_info, hide_index=True, use_container_width=True)
