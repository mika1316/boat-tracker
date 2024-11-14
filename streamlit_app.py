import streamlit as st
import streamlit.components.v1 as components
import folium
from datetime import datetime, timezone
import time
from collections import deque
import random
from math import radians, sin, cos, sqrt, atan2
import requests

# Configuración de la página
st.set_page_config(
    page_title="Rastreador de Veleros",
    page_icon="⛵",
    layout="wide"
)

class GarminShareTracker:
    def __init__(self, history_length=100):
        self.boats = {}
        self.map = None
        self.history_length = history_length
        self.colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred']
        self.noronha_coords = (-3.8547, -32.4248)
        self.radius_nm = 10
        self.proximity_circle = None
        self.last_update_time = {}
        
    def nautical_miles_to_meters(self, nm):
        return nm * 1852
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371000
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance_m = R * c
        return distance_m / 1852

    def extract_share_id(self, garmin_url):
        return garmin_url.split('/')[-1]
    
    def add_boat(self, name, garmin_share_url):
        color = random.choice(self.colors)
        self.colors.remove(color)
        share_id = self.extract_share_id(garmin_share_url)
        self.boats[name] = {
            'share_id': share_id,
            'marker': None,
            'path': None,
            'color': color,
            'history': deque(maxlen=self.history_length),
            'last_update': None
        }
        self.last_update_time[name] = 0

    def get_position(self, share_id, boat_name):
        try:
            current_time = time.time()
            if current_time - self.last_update_time.get(boat_name, 0) < 60:
                return None
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json'
            }
            
            time.sleep(2)
            
            position_url = f"https://share.garmin.com/Feed/Share/{share_id}"
            response = requests.get(position_url, headers=headers)
            
            if response.status_code == 429:
                st.warning(f"Límite de peticiones alcanzado para {boat_name}. Esperando...")
                time.sleep(60)
                response = requests.get(position_url, headers=headers)
            
            if response.status_code != 200:
                raise Exception(f"Error accessing Garmin Share: {response.status_code}")
            
            data = response.json()
            self.last_update_time[boat_name] = current_time
            
            location = data.get('locations', [{}])[0]
            return {
                'lat': location.get('latitude'),
                'lon': location.get('longitude'),
                'timestamp': location.get('timestamp'),
                'speed': location.get('speed', {}).get('value', 0),
                'course': location.get('course', 0),
                'elevation': location.get('elevation', {}).get('value', 0)
            }
        except Exception as e:
            st.error(f"Error getting position from Garmin Share for {boat_name}: {e}")
            return None

    def create_popup_content(self, boat_name, position):
        try:
            timestamp = datetime.fromtimestamp(position['timestamp']/1000, timezone.utc)
            local_time = timestamp.astimezone()
        except:
            local_time = datetime.now()
            
        return f"""
            <div style="font-family: Arial, sans-serif; min-width: 200px;">
                <h3 style="margin: 0 0 10px 0;">{boat_name}</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td><b>Última actualización:</b></td>
                        <td>{local_time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                    <tr><td><b>Velocidad:</b></td>
                        <td>{position['speed']:.1f} nudos</td></tr>
                    <tr><td><b>Rumbo:</b></td>
                        <td>{position['course']}°</td></tr>
                    <tr><td><b>Posición:</b></td>
                        <td>{position['lat']:.4f}°, {position['lon']:.4f}°</td></tr>
                    <tr><td><b>Elevación:</b></td>
                        <td>{position['elevation']:.1f} m</td></tr>
                </table>
            </div>
        """

    def find_closest_boat_to_noronha(self):
        closest_boat = None
        min_distance = float('inf')
        closest_position = None
        
        for boat_name, boat_info in self.boats.items():
            if boat_info['last_update']:
                position = boat_info['last_update']
                distance = self.calculate_distance(
                    self.noronha_coords[0], self.noronha_coords[1],
                    position['lat'], position['lon']
                )
                
                if distance < min_distance:
                    min_distance = distance
                    closest_boat = boat_name
                    closest_position = position
        
        return closest_boat, closest_position, min_distance

    def update_proximity_circle(self):
        if self.proximity_circle and self.map:
            self.map.remove_layer(self.proximity_circle)
            
        closest_boat, position, distance = self.find_closest_boat_to_noronha()
        
        if closest_boat and position:
            self.proximity_circle = folium.Circle(
                location=[position['lat'], position['lon']],
                radius=self.nautical_miles_to_meters(self.radius_nm),
                color="red",
                fill=True,
                fillColor="red",
                fillOpacity=0.2,
                popup=f"Radio de {self.radius_nm}nm alrededor de {closest_boat}\n"
                      f"Distancia a Fernando de Noronha: {distance:.1f}nm"
            )
            self.proximity_circle.add_to(self.map)
            
            folium.Marker(
                location=self.noronha_coords,
                popup="Fernando de Noronha",
                icon=folium.Icon(color='green', icon='info-sign')
            ).add_to(self.map)

    def update_boat_position(self, boat_name, boat_info):
        position = self.get_position(boat_info['share_id'], boat_name)
        
        if position:
            boat_info['history'].append([position['lat'], position['lon']])
            boat_info['last_update'] = position

            if boat_info['marker'] is not None:
                self.map.remove_layer(boat_info['marker'])
            if boat_info['path'] is not None:
                self.map.remove_layer(boat_info['path'])

            popup_content = self.create_popup_content(boat_name, position)
            marker = folium.Marker(
                location=[position['lat'], position['lon']],
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.Icon(color=boat_info['color'], icon='ship', prefix='fa')
            )
            marker.add_to(self.map)
            boat_info['marker'] = marker

            if len(boat_info['history']) > 1:
                path = folium.PolyLine(
                    locations=list(boat_info['history']),
                    weight=3,
                    color=boat_info['color'],
                    opacity=0.8
                )
                path.add_to(self.map)
                boat_info['path'] = path

    def initialize_map(self, center_lat=-5.0, center_lon=-35.0, zoom=6):
        self.map = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles='OpenStreetMap',
            attr='Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
        )

    def update_positions(self):
        if self.map is None:
            self.initialize_map()
            
        for boat_name, boat_info in self.boats.items():
            self.update_boat_position(boat_name, boat_info)
        
        self.update_proximity_circle()
        
        return self.map

# Título de la aplicación
st.title('🚢 Rastreador de Veleros')

# Configuración de la sesión
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()
    st.session_state.tracker = GarminShareTracker()
    
    # Añadir los veleros
    st.session_state.tracker.add_boat("Contessa", "https://share.garmin.com/contessa")
    st.session_state.tracker.add_boat("Azuluc", "https://share.garmin.com/AZULUC")
    st.session_state.tracker.add_boat("Finisterre", "https://share.garmin.com/FINISTERRE")
    st.session_state.tracker.add_boat("Yorugua", "https://share.garmin.com/YoruguaSY")
    
    # Inicializar mapa
    st.session_state.tracker.initialize_map()

# Crear columnas para organizar la interfaz
col1, col2 = st.columns([4, 1])

with col1:
    # Mostrar el mapa
    map_obj = st.session_state.tracker.update_positions()
    st.components.v1.html(map_obj._repr_html_(), height=600)

with col2:
    # Información y controles
    st.write("### Información")
    st.write(f"Última actualización: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Botón de actualización manual
    if st.button('Actualizar Posiciones'):
        st.session_state.last_update = datetime.now()
        map_obj = st.session_state.tracker.update_positions()
        st.experimental_rerun()

    # Mostrar leyenda de barcos
    st.write("### Barcos")
    for name, info in st.session_state.tracker.boats.items():
        st.markdown(f"* <span style='color: {info['color']}'>{name}</span>", unsafe_allow_html=True)

# Actualización automática cada 5 minutos
if (datetime.now() - st.session_state.last_update).seconds > 300:
    st.session_state.last_update = datetime.now()
    st.experimental_rerun()
