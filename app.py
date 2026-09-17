import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
import re
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
# CONSTANTES DE DATOS
# ==============================================================================
COL_NOMBRE = 'nombre'
COL_OPERADORA = 'operador'

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
# 2. TRANSFORMACIONES DE COORDENADAS (GMS / DECIMAL)
# ==============================================================================
def decimal_a_gms(lat, lon):
    """
    Convierte coordenadas en grados decimales (DD) a formato Grados, Minutos y Segundos (GMS).
    Ejemplo: (-38.9516, -68.0591) -> 38°57'05.76"S, 68°03'32.76"O
    """
    if lat is None or lon is None:
        return ""
    
    # Latitud
    lat_dir = "S" if lat < 0 else "N"
    abs_lat = abs(lat)
    lat_deg = int(abs_lat)
    lat_min_float = (abs_lat - lat_deg) * 60
    lat_min = int(lat_min_float)
    lat_sec = (lat_min_float - lat_min) * 60
    lat_gms = f"{lat_deg:02d}°{lat_min:02d}'{lat_sec:05.2f}\"{lat_dir}"
    
    # Longitud
    lon_dir = "O" if lon < 0 else "E"
    abs_lon = abs(lon)
    lon_deg = int(abs_lon)
    lon_min_float = (abs_lon - lon_deg) * 60
    lon_min = int(lon_min_float)
    lon_sec = (lon_min_float - lon_min) * 60
    lon_gms = f"{lon_deg:02d}°{lon_min:02d}'{lon_sec:05.2f}\"{lon_dir}"
    
    return f"{lat_gms}, {lon_gms}"

def extraer_coordenadas(texto):
    if not texto:
        return None, None
    
    # Resolver links acortados de Google Maps
    if "maps.app.goo.gl" in texto or "goo.gl/maps" in texto:
        try:
            r = requests.get(texto, allow_redirects=True, timeout=5)
            texto = r.url
        except Exception:
            pass

    # DMS / GMS (Grados Minutos Segundos)
    match_dms = re.search(r'(\d+)°(\d+)\'([\d\.]+)"([NSns])\s*(\d+)°(\d+)\'([\d\.]+)"([EWOewo])', texto)
    if match_dms:
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = match_dms.groups()
        lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
        if lat_dir.upper() == 'S':
            lat = -lat
        lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
        if lon_dir.upper() in ['W', 'O']:
            lon = -lon
        return lat, lon

    # Decimales en URLs o texto suelto
    match_link = re.search(r'[-@/](-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)', texto)
    if match_link:
        return float(match_link.group(1)), float(match_link.group(2))
    
    match_dec = re.findall(r'-?\d{1,2}\.\d+', texto)
    if len(match_dec) >= 2:
        return float(match_dec[0]), float(match_dec[1])
        
    return None, None

# ==============================================================================
# 3. CARGA Y PROCESAMIENTO DE GEODATOS (ULTRA OPTIMIZADO)
# ==============================================================================
@st.cache_data
def cargar_datos():
    ruta_archivo = 'data/areas_hidrocarburiferas.shp'
    gdf = gpd.read_file(ruta_archivo)
    gdf = gdf.to_crs(epsg=4326)
    
    for col in gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
            
    # Precalcular centroides y diccionario de lookup rápido O(1)
    centroids = gdf.geometry.centroid
    gdf['lat_centro'] = centroids.y
    gdf['lon_centro'] = centroids.x
    
    lookup_areas = {}
    for _, row in gdf.iterrows():
        nombre = str(row[COL_NOMBRE])
        operador = str(row[COL_OPERADORA]) if pd.notna(row[COL_OPERADORA]) else "Sin operadora"
        lat = row['lat_centro']
        lon = row['lon_centro']
        lookup_areas[nombre] = {
            'operador': operador,
            'lat': lat,
            'lon': lon,
            'gms': decimal_a_gms(lat, lon)
        }
        
    # Simplificación geométrica ligera: reduce el tamaño del GeoJSON en un 80% 
    # eliminando el lag y acelerando el renderizado de Folium instantáneamente.
    gdf_simplificado = gdf.copy()
    gdf_simplificado['geometry'] = gdf.geometry.simplify(tolerance=0.0005, preserve_topology=True)
    
    # Calcular centro y límites iniciales de la provincia
    minx, miny, maxx, maxy = gdf.total_bounds
    centro_inicial = [(miny + maxy) / 2.0, (minx + maxx) / 2.0]
    
    return gdf_simplificado, gdf, lookup_areas, centro_inicial

try:
    gdf_simplificado, gdf_completo, lookup_areas, CENTRO_DEFECTO = cargar_datos()
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
# 5. INTERCEPCIÓN DE CLICS EN EL MAPA (PROCESAMIENTO EN 1 SOLO PASO)
# ==============================================================================
# Al leer el estado del widget antes de construir el mapa, actualizamos el color 
# y el estado inmediatamente SIN requerir un st.rerun() adicional ni causar lag.
estado_previo_mapa = st.session_state.get("mapa_folium")
if estado_previo_mapa and estado_previo_mapa.get("last_active_drawing"):
    dibujo_activo = estado_previo_mapa["last_active_drawing"]
    props = dibujo_activo.get("properties", {})
    nombre_clic = str(props.get(COL_NOMBRE, ""))
    
    # Identificador único del evento para no reprocesar en reruns ajenos
    firma_clic = f"{nombre_clic}_{dibujo_activo.get('id', '')}"
    
    if firma_clic != st.session_state.ultimo_dibujo_procesado:
        st.session_state.ultimo_dibujo_procesado = firma_clic
        
        # Obtener metadatos y coordenadas del área cliqueada
        meta = lookup_areas.get(nombre_clic)
        if meta:
            operador_clic = meta['operador']
            lat_clic, lon_clic = meta['lat'], meta['lon']
            gms_clic = meta['gms']
        else:
            try:
                geom = shape(dibujo_activo.get("geometry", {}))
                c = geom.centroid
                lat_clic, lon_clic = c.y, c.x
                gms_clic = decimal_a_gms(lat_clic, lon_clic)
            except Exception:
                lat_clic, lon_clic, gms_clic = None, None, ""
            operador_clic = str(props.get(COL_OPERADORA, "Sin operadora"))
            
        # Actualizar display superior
        if lat_clic is not None and lon_clic is not None:
            st.session_state.ultimas_coordenadas = (lat_clic, lon_clic)
            st.session_state.ultima_operadora = operador_clic
            st.session_state.ultimo_nombre_area = nombre_clic

        # Toggle de selección de colores (Pintar / Despintar)
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
    """
    Función modular preparada para conectarse con la API de OpenRouteService (ORS).
    """
    if not api_key or not origen or not destino:
        return None
    return None

def agregar_capa_ruta_logistica(mapa_folium, puntos_ruta, nombre="Ruta Logística", color="#FF5722", peso=5):
    """
    Inyecta una capa folium.PolyLine en el mapa si existen coordenadas de ruta calculadas.
    """
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
# 8. BARRA LATERAL (FILTROS, PINCEL Y ACCIONES)
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

    st.header("🎨 Pincel de Selección")
    color_pincel = st.color_picker("Color para pintar polígonos:", value="#FF5733", key="color_picker_pincel")
    num_pintadas = len(st.session_state.areas_pintadas)
    if num_pintadas > 0:
        st.caption(f"🖌️ Áreas pintadas activas: **{num_pintadas}**")
        if st.button("🗑️ Despintar todas las áreas", use_container_width=True):
            st.session_state.areas_pintadas = {}
            st.rerun()
    
    st.divider()

    st.header("🔎 Filtros del Mapa")
    lista_areas = ["TODAS"] + sorted(gdf_completo[COL_NOMBRE].dropna().astype(str).unique().tolist())
    lista_operadoras = ["TODAS"] + sorted(gdf_completo[COL_OPERADORA].dropna().astype(str).unique().tolist())
    
    st.selectbox("Iluminar un Área específica:", lista_areas, key='area_elegida', on_change=on_area_change)
    st.selectbox("Iluminar por Empresa operadora:", lista_operadoras, key='operadora_elegida', on_change=on_operadora_change)
    
    st.divider()
    
    st.header("📍 Buscar Coordenadas")
    st.text_input("Pegá un link de Maps o coordenadas (GMS o Decimales):", key="input_coords", on_change=procesar_busqueda)
    
    st.divider()
    
    st.header("📄 Información del Área Cliqueada")
    info_placeholder = st.empty()
    if not estado_previo_mapa or not estado_previo_mapa.get("last_active_drawing"):
        info_placeholder.info("👈 Hacé clic en un polígono del mapa para ver toda su data acá.")
    else:
        props_clicked = estado_previo_mapa["last_active_drawing"].get("properties", {})
        df_props = pd.DataFrame(list(props_clicked.items()), columns=["Dato", "Valor"])
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
    
    # 1. Prioridad: Áreas pintadas con selección múltiple
    if nombre_area in st.session_state.areas_pintadas:
        info_pintada = st.session_state.areas_pintadas[nombre_area]
        color_guardado = info_pintada["color"] if isinstance(info_pintada, dict) else info_pintada
        return {
            'fillColor': color_guardado,
            'color': '#111111',
            'weight': 2.5,
            'fillOpacity': 0.8
        }
    
    # 2. Filtros interactivos por selectbox
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

# Construcción de mapa con centro y zoom estables
mapa = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attr='Esri'
)

# Capa GeoJSON ultra liviana (simplificada)
folium.GeoJson(
    gdf_simplificado,
    name='Áreas',
    style_function=estilo_iluminado,
    tooltip=folium.GeoJsonTooltip(fields=[COL_NOMBRE, COL_OPERADORA])
).add_to(mapa)

# Marcador del punto buscado
if st.session_state.punto_buscado:
    folium.Marker(
        st.session_state.punto_buscado,
        popup="📍 Punto Buscado",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa)

# Inyección de Capa de Rutas Logísticas (Scaffolding preparado)
ruta_activa = None  # calcular_ruta_logistica(...)
if ruta_activa:
    agregar_capa_ruta_logistica(mapa, ruta_activa, nombre="Ruta de Abastecimiento")

# ==============================================================================
# 10. RENDERIZADO Y PANELES INFORMATIVOS
# ==============================================================================
st.title("🗺️ Visor de Áreas Hidrocarburíferas")

# --- PANEL DE COORDENADAS ACTIVAS Y OPERADORA (GMS) ---
if st.session_state.ultimas_coordenadas:
    lat_act, lon_act = st.session_state.ultimas_coordenadas
    gms_texto = decimal_a_gms(lat_act, lon_act)
    
    if st.session_state.ultima_operadora and st.session_state.ultima_operadora not in ["None", "nan", ""]:
        st.success(
            f"📍 **Coordenadas Activas (GMS):** `{gms_texto}` &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"🏢 **Operadora:** **{st.session_state.ultima_operadora}** &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"🛢️ **Área:** **{st.session_state.ultimo_nombre_area or 'No especificada'}**"
        )
    else:
        st.info(
            f"📍 **Coordenadas Activas (GMS):** `{gms_texto}` &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"ℹ️ *Punto fuera de áreas catastradas o sin operadora asignada.*"
        )
else:
    st.info("📍 **Coordenadas Activas:** Seleccioná un área en el mapa o ingresá coordenadas en el buscador lateral para ver detalles en formato GMS y su operadora.")

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
# 11. TABLA RESUMEN DE ÁREAS SELECCIONADAS (REQUERIMIENTO 3)
# ==============================================================================
if st.session_state.areas_pintadas:
    st.markdown("---")
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.subheader(f"📋 Inventario de Áreas Seleccionadas ({len(st.session_state.areas_pintadas)})")
    with col_t2:
        # Botón para exportar datos seleccionados a CSV
        df_export = pd.DataFrame([
            {
                "Color_Hex": data["color"],
                "Area": nombre,
                "Operadora": data["operadora"],
                "Coordenadas_GMS": data["gms"],
                "Latitud": data["lat"],
                "Longitud": data["lon"]
            }
            for nombre, data in st.session_state.areas_pintadas.items()
        ])
        csv_data = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Descargar CSV",
            data=csv_data,
            file_name="areas_seleccionadas_sullair.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Construir tabla visual
    filas_tabla = []
    for nombre, data in st.session_state.areas_pintadas.items():
        filas_tabla.append({
            "🎨 Color": data["color"],
            "🛢️ Área / Locación": nombre,
            "🏢 Operadora": data["operadora"],
            "📍 Coordenadas (GMS)": data["gms"],
            "🌐 Latitud": f"{data['lat']:.5f}" if data['lat'] is not None else "-",
            "🌐 Longitud": f"{data['lon']:.5f}" if data['lon'] is not None else "-"
        })
    
    df_tabla = pd.DataFrame(filas_tabla)
    
    st.dataframe(
        df_tabla,
        column_config={
            "🎨 Color": st.column_config.TextColumn("Color", width="small"),
            "🛢️ Área / Locación": st.column_config.TextColumn("Área / Locación", width="medium"),
            "🏢 Operadora": st.column_config.TextColumn("Operadora", width="medium"),
            "📍 Coordenadas (GMS)": st.column_config.TextColumn("Coordenadas (GMS)", width="large"),
            "🌐 Latitud": st.column_config.TextColumn("Latitud", width="small"),
            "🌐 Longitud": st.column_config.TextColumn("Longitud", width="small"),
        },
        hide_index=True,
        use_container_width=True
    )
