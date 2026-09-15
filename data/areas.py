import geopandas as gpd
import folium
from folium import plugins
import pandas as pd
import random

ruta_archivo = r'C:\Users\fcendra\Downloads\areas_hidrocarburiferas\areas_hidrocarburiferas.shp'
ruta_html = r'C:\Users\fcendra\Downloads\areas_hidrocarburiferas\mapa_areas.html'

gdf = gpd.read_file(ruta_archivo)
gdf = gdf.to_crs(epsg=4326)

minx, miny, maxx, maxy = gdf.total_bounds
centro_lon = (minx + maxx) / 2.0
centro_lat = (miny + maxy) / 2.0

for col in gdf.columns:
    if pd.api.types.is_datetime64_any_dtype(gdf[col]):
        gdf[col] = gdf[col].astype(str)

# --- ¡ATENCIÓN FEDE! CAMBIÁ ESTO ---
# Mirá el mapa que abriste antes y poné acá el nombre exacto de tus columnas (respetá mayúsculas)
COL_OPERADORA = 'OPERADOR'  # Reemplazá 'OPERADOR' por la columna que tiene la empresa
COL_NOMBRE_AREA = 'NOMBRE'  # Reemplazá 'NOMBRE' por la columna que tiene el nombre del área
# -----------------------------------

# Generamos colores aleatorios para cada empresa
operadoras = gdf[COL_OPERADORA].dropna().unique()
colores = {op: f"#{random.randint(0, 0xFFFFFF):06x}" for op in operadoras}

def estilo(feature):
    empresa = feature['properties'].get(COL_OPERADORA)
    return {
        'fillColor': colores.get(empresa, '#808080'), # Gris por si un área no tiene operadora
        'color': 'black',
        'weight': 1,
        'fillOpacity': 0.6
    }

mapa = folium.Map(
    location=[centro_lat, centro_lon], 
    zoom_start=7, 
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attr='Esri'
)

columnas_info = gdf.columns.tolist()
if 'geometry' in columnas_info:
    columnas_info.remove('geometry')

# Capa de áreas con el estilo de colores
capa_areas = folium.GeoJson(
    gdf,
    name='Áreas Hidrocarburíferas',
    style_function=estilo,
    popup=folium.GeoJsonPopup(fields=columnas_info)
).add_to(mapa)

# Buscador para escribir el nombre y que te lleve al área
buscador = plugins.Search(
    layer=capa_areas,
    geom_type='Polygon',
    placeholder='Buscar nombre del área...',
    collapsed=False,
    search_label=COL_NOMBRE_AREA # Le decimos que busque en esta columna
)
mapa.add_child(buscador)

mapa.save(ruta_html)
print("¡Listo! Abrí el HTML, mirá los colores y probá el buscador.")
