import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import re
from shapely.geometry import Point

st.set_page_config(page_title="Mapa de Áreas Hidrocarburíferas", page_icon="🛢️", layout="wide")
st.title("🗺️ Visor de Áreas Hidrocarburíferas")

# Dejamos fijos los nombres de las columnas de tu archivo
COL_NOMBRE = 'nombre'
COL_OPERADORA = 'operador'

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

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🔎 Filtros del Mapa")
    
    # Extraemos todos los nombres de áreas y empresas que existen en tu archivo
    lista_areas = ["TODAS"] + sorted(gdf[COL_NOMBRE].dropna().astype(str).unique().tolist())
    lista_operadoras = ["TODAS"] + sorted(gdf[COL_OPERADORA].dropna().astype(str).unique().tolist())
    
    # Armamos los selectores con la DATA REAL
    area_elegida = st.selectbox("Iluminar un Área específica:", lista_areas)
    operadora_elegida = st.selectbox("Iluminar por Empresa operadora:", lista_operadoras)
    
    st.divider()
    
    st.header("📍 Buscar Coordenadas")
    busqueda = st.text_input("Pegá un link de Maps o coordenadas (GMS o Decimales):")

# --- MOTOR DE COORDENADAS MEJORADO ---
def extraer_coordenadas(texto):
    if not texto:
        return None, None
    
    match_dms = re.search(r'(\d+)°(\d+)\'([\d\.]+)"([NSns])\s*(\d+)°(\d+)\'([\d\.]+)"([EWOewo])', texto)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m)/60 + float(lat_s)/3600
        if lat_dir.upper() == 'S': lat = -lat
        lon = float(lon_d) + float(lon_m)/60 + float(lon_s)/3600
        if lon_dir.upper() in ['W', 'O']: lon = -lon
        return lat, lon

    match_link = re.search(r'[-@/](-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)', texto)
    if match_link:
        return float(match_link.group(1)), float(match_link.group(2))
    
    match_dec = re.findall(r'-?\d{1,2}\.\d+', texto)
    if len(match_dec) >= 2:
        return float(match_dec[0]), float(match_dec[1])
        
    return None, None

lat_buscada, lon_buscada = extraer_coordenadas(busqueda)

if busqueda:
    if lat_buscada and lon_buscada:
        st.success(f"Coordenadas detectadas: {lat_buscada:.5f}, {lon_buscada:.5f}")
    else:
        st.warning("No pude pescar las coordenadas.")

# --- MAPA Y DIBUJO ---
def estilo_iluminado(feature):
    nombre_area = str(feature['properties'].get(COL_NOMBRE))
    empresa = str(feature['properties'].get(COL_OPERADORA))
    
    iluminar = False
    
    # Lógica para prender las luces
    if area_elegida != "TODAS" and nombre_area == area_elegida:
        iluminar = True
    elif operadora_elegida != "TODAS" and empresa == operadora_elegida:
        iluminar = True
    elif area_elegida == "TODAS" and operadora_elegida == "TODAS":
        # Si no hay nada filtrado, dejamos todo en un azul tranqui
        return {'fillColor': '#3388ff', 'color': 'black', 'weight': 1, 'fillOpacity': 0.4}
        
    # Colores para cuando hay un filtro activo
    if iluminar:
        return {'fillColor': '#00ff00', 'color': 'black', 'weight': 3, 'fillOpacity': 0.7} # Verde flúor para resaltar
    else:
        return {'fillColor': '#cccccc', 'color': 'gray', 'weight': 1, 'fillOpacity': 0.1} # Gris transparente para apagar el resto

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

columnas_info = [col for col in gdf.columns if col != 'geometry']

folium.GeoJson(
    gdf,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[COL_NOMBRE, COL_OPERADORA]),
    popup=folium.GeoJsonPopup(fields=columnas_info) 
).add_to(mapa)

# --- CRUCE GEOGRÁFICO ---
if lat_buscada and lon_buscada:
    punto = Point(lon_buscada, lat_buscada)
    folium.Marker([lat_buscada, lon_buscada], popup="📍 Punto Buscado", icon=folium.Icon(color="red")).add_to(mapa)
    
    area_encontrada = gdf[gdf.geometry.contains(punto)]
    if not area_encontrada.empty:
        nombre_enc = area_encontrada.iloc[0][COL_NOMBRE]
        ope_enc = area_encontrada.iloc[0][COL_OPERADORA]
        st.info(f"🎯 El punto cae en el área **{nombre_enc}** (Operada por: **{ope_enc}**)")
    else:
        st.warning("⚠️ El punto no cae dentro de ninguna área concesionada.")

st_folium(mapa, width=1200, height=650, returned_objects=[])
