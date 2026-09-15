import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import re
from shapely.geometry import Point

# Configuración de página
st.set_page_config(page_title="Mapa de Áreas Hidrocarburíferas", page_icon="🛢️", layout="wide")
st.title("🗺️ Visor de Áreas Hidrocarburíferas")

# 1. Cargamos los datos (Ruta relativa para que ande en GitHub/Servidor)
@st.cache_data
def cargar_datos():
    # ¡Asegurate de que los archivos estén en la carpeta 'data'!
    ruta_archivo = 'data/areas_hidrocarburiferas.shp'
    gdf = gpd.read_file(ruta_archivo)
    gdf = gdf.to_crs(epsg=4326) # Pasamos a lat/lon web
    
    # Limpiamos fechas para evitar errores de serialización
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
    return gdf

try:
    gdf = cargar_datos()
except Exception as e:
    st.error(f"Error al cargar el mapa. ¿Pusiste los archivos en la carpeta 'data'? Detalle: {e}")
    st.stop()

# 2. Barra Lateral (Sidebar) para los controles
with st.sidebar:
    st.header("⚙️ Configuración")
    st.info("Seleccioná las columnas correspondientes a tus datos:")
    columnas = gdf.columns.tolist()
    
    col_nombre = st.selectbox("Columna de Nombre del Área", columnas, index=0)
    col_operadora = st.selectbox("Columna de Operadora", columnas, index=1 if len(columnas) > 1 else 0)
    
    st.divider()
    
    st.header("🔎 Filtrar Mapa")
    lista_operadoras = ["TODAS"] + sorted(gdf[col_operadora].dropna().astype(str).unique().tolist())
    operadora_elegida = st.selectbox("Iluminar áreas de la empresa:", lista_operadoras)
    
    st.divider()
    
    st.header("📍 Buscar Coordenadas")
    busqueda = st.text_input("Pegá un link de Maps o coordenadas (Ej: -38.95, -68.05):")

# 3. Procesamos la búsqueda de coordenadas
lat_buscada, lon_buscada = None, None
if busqueda:
    coordenadas = re.findall(r'-?\d{1,2}\.\d+', busqueda)
    if len(coordenadas) >= 2:
        lat_buscada = float(coordenadas[0])
        lon_buscada = float(coordenadas[1])
        st.success(f"Coordenadas detectadas: {lat_buscada}, {lon_buscada}")
    else:
        st.warning("No pude extraer las coordenadas de ese texto.")

# 4. Definimos el estilo dinámico para iluminar operadoras
def estilo_iluminado(feature):
    empresa = feature['properties'].get(col_operadora)
    if operadora_elegida == "TODAS" or str(empresa) == operadora_elegida:
        return {'fillColor': '#0055ff', 'color': 'black', 'weight': 2, 'fillOpacity': 0.6}
    else:
        return {'fillColor': '#cccccc', 'color': 'gray', 'weight': 1, 'fillOpacity': 0.15}

# 5. Armamos el mapa
if lat_buscada and lon_buscada:
    centro = [lat_buscada, lon_buscada]
    zoom = 10
else:
    minx, miny, maxx, maxy = gdf.total_bounds
    centro = [(miny + maxy) / 2.0, (minx + maxx) / 2.0]
    zoom = 6

mapa = folium.Map(
    location=centro, 
    zoom_start=zoom,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attr='Esri'
)

# Dibujamos los polígonos
folium.GeoJson(
    gdf,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[col_nombre, col_operadora])
).add_to(mapa)

# 6. Cruce geográfico del punto buscado
if lat_buscada and lon_buscada:
    punto = Point(lon_buscada, lat_buscada)
    folium.Marker(
        [lat_buscada, lon_buscada], 
        popup="📍 Punto Buscado", 
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa)
    
    area_encontrada = gdf[gdf.geometry.contains(punto)]
    if not area_encontrada.empty:
        nombre_enc = area_encontrada.iloc[0][col_nombre]
        ope_enc = area_encontrada.iloc[0][col_operadora]
        st.info(f"🎯 El punto cae en el área **{nombre_enc}** (Operada por: **{ope_enc}**)")
    else:
        st.warning("⚠️ El punto no cae dentro de ninguna área concesionada.")

# 7. Renderizamos el mapa
st_folium(mapa, width=1200, height=650, returned_objects=[])
