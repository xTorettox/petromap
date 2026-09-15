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

COL_NOMBRE = 'nombre'
COL_OPERADORA = 'operador'

# --- 1. FUNCIÓN DE ACTUALIZACIÓN AUTOMÁTICA ---
def actualizar_datos():
    # FEDE: Pegá acá el link que copiás haciendo clic derecho en el botón verde de "DESCARGAR"
    url_zip = "https://portaldatosabiertos.neuquen.gov.ar/dataset/d726d6de-bf79-4302-bc5e-1f2b975fc9a3/resource/8750c10c-9ad9-473f-9862-a9b1dabaf7d4/download/areas_hidrocarburiferas.zip" 
    
    if url_zip == "LINK_DIRECTO_DEL_ZIP_ACA":
        st.sidebar.error("Che, te olvidaste de poner el link de descarga en el código.")
        return

    try:
        with st.spinner("Descargando e instalando mapa actualizado..."):
            r = requests.get(url_zip)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            z.extractall("data/")
        st.sidebar.success("¡Datos actualizados al toque!")
        st.cache_data.clear() # Limpiamos caché para obligar a leer los archivos nuevos
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

# --- 3. ESTADOS PARA FILTROS EXCLUYENTES ---
if 'area_elegida' not in st.session_state:
    st.session_state.area_elegida = "TODAS"
if 'operadora_elegida' not in st.session_state:
    st.session_state.operadora_elegida = "TODAS"

def reset_operadora():
    st.session_state.operadora_elegida = "TODAS"

def reset_area():
    st.session_state.area_elegida = "TODAS"

# --- 4. BARRA LATERAL ---
with st.sidebar:
    # Branding Sullair
    try:
        st.image("Logo Sullair Verde.png", use_container_width=True)
    except:
        st.warning("Falta el 'Logo Sullair Verde.png' en la carpeta.")
        
    st.header("🔎 Filtros del Mapa")
    
    lista_areas = ["TODAS"] + sorted(gdf[COL_NOMBRE].dropna().astype(str).unique().tolist())
    lista_operadoras = ["TODAS"] + sorted(gdf[COL_OPERADORA].dropna().astype(str).unique().tolist())
    
    st.selectbox("Iluminar un Área específica:", lista_areas, key='area_elegida', on_change=reset_operadora)
    st.selectbox("Iluminar por Empresa operadora:", lista_operadoras, key='operadora_elegida', on_change=reset_area)
    
    st.divider()
    
    st.header("📍 Buscar Coordenadas")
    busqueda = st.text_input("Pegá un link de Maps o coordenadas:")
    
    st.divider()
    
    # Acá guardamos un espacio vacío para mostrar la data cuando hagas clic
    st.header("📄 Información del Área")
    info_placeholder = st.empty()
    info_placeholder.info("👈 Hacé clic en un polígono del mapa para ver toda su data acá.")
    
    st.divider()
    
    if st.button("🔄 Actualizar Datos desde Neuquén", use_container_width=True):
        actualizar_datos()

    # Pie de página / Firma
    st.divider()
    st.caption("© 2026 - Desarrollado por Fede García Cendra para Sullair Argentina S.A.")
    st.caption("Consultas a: fcendra@sullair.com.ar")

# --- 5. MOTOR DE COORDENADAS ---
def extraer_coordenadas(texto):
    if not texto: return None, None
    match_dms = re.search(r'(\d+)°(\d+)\'([\d\.]+)"([NSns])\s*(\d+)°(\d+)\'([\d\.]+)"([EWOewo])', texto)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
        if lat_dir.upper() == 'S': lat = -lat
        lon = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
        if lon_dir.upper() in ['W', 'O']: lon = -lon
        return lat, lon

    match_link = re.search(r'[-@/](-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)', texto)
    if match_link: return float(match_link.group(1)), float(match_link.group(2))
    
    match_dec = re.findall(r'-?\d{1,2}\.\d+', texto)
    if len(match_dec) >= 2: return float(match_dec[0]), float(match_dec[1])
    return None, None

lat_buscada, lon_buscada = extraer_coordenadas(busqueda)

# --- 6. MAPA Y ESTILOS ---
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

if lat_buscada and lon_buscada:
    centro = [lat_buscada, lon_buscada]
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

# Ya NO le pasamos el popup a GeoJson para que no moleste en el mapa
folium.GeoJson(
    gdf,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[COL_NOMBRE, COL_OPERADORA])
).add_to(mapa)

if lat_buscada and lon_buscada:
    punto = Point(lon_buscada, lat_buscada)
    folium.Marker([lat_buscada, lon_buscada], popup="📍 Punto Buscado", icon=folium.Icon(color="red")).add_to(mapa)
    area_encontrada = gdf[gdf.geometry.contains(punto)]
    if not area_encontrada.empty:
        st.info(f"🎯 El punto cae en el área **{area_encontrada.iloc[0][COL_NOMBRE]}**")
    else:
        st.warning("⚠️ El punto no cae dentro de ninguna área concesionada.")

# --- 7. RENDER Y CAPTURA DE CLIC ---
# Capturamos toda la interacción del usuario con el mapa
datos_mapa = st_folium(mapa, width=1200, height=650)

# Si el usuario hizo clic en un área, llenamos el contenedor vacío de la barra lateral
if datos_mapa and datos_mapa.get("last_active_drawing"):
    propiedades = datos_mapa["last_active_drawing"]["properties"]
    
    # Armamos un dataframe chiquito para que se vea lindo
    df_info = pd.DataFrame(list(propiedades.items()), columns=["Dato", "Valor"])
    
    # Metemos la info en el hueco que dejamos preparado en la barra lateral
    with info_placeholder.container():
        st.success(f"**{propiedades.get(COL_NOMBRE, 'Área seleccionada')}**")
        st.dataframe(df_info, hide_index=True, use_container_width=True)
