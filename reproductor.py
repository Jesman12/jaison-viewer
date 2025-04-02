import pygame
import sys
import os
import requests
import json
from datetime import datetime
import time
import pytz
import threading
import cv2
import numpy as np

# =============================================
# CONFIGURACIÓN INICIAL Y CONSTANTES
# =============================================

# Directorios
CACHE_DIR = "cache"
MEDIA_DIR = os.path.join(CACHE_DIR, "media")
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

# Constantes
UPDATE_INTERVAL = 30  
CONNECTION_TIMEOUT = 5   
DEFAULT_DURATION = 5  
FPS = 30  # 

# URLs del servidor
JSON_URL = 'https://api.jaison.mx/raspi/api.php?action=listarImagenes'
BASE_URL = 'http://api.jaison.mx/'

# Zona horaria
LOCAL_TIMEZONE = pytz.timezone('America/Mexico_City')

# =============================================
# CLASE PRINCIPAL MEDIA PLAYER
# =============================================

class MediaPlayer:
    def __init__(self):
        """Inicializa el reproductor multimedia."""
        self.init_pygame()
        self.last_modified = None
        self.media_list = []
        self.current_media_index = 0
        self.last_update_time = time.time()
        self.running = True
        self.media_lock = threading.Lock()
        self.start_time = pygame.time.get_ticks()
    
    # =============================================
    # MÉTODOS DE INICIALIZACIÓN
    # =============================================
    
    # def init_pygame(self):
    #     """Inicializa pygame y configura la pantalla."""
    #     pygame.init()
    #     self.screen_width, self.screen_height = 800, 600
    #     self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
    #     self.clock = pygame.time.Clock()
    def init_pygame(self):
        """Inicializa pygame y configura la pantalla en modo fullscreen."""
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.screen_width, self.screen_height = self.screen.get_size()
        self.clock = pygame.time.Clock()
    
    # =============================================
    # MÉTODOS DE CONEXIÓN Y DESCARGA
    # =============================================
    
    def internet_available(self):
        """Verifica si hay conexión a internet."""
        try:
            requests.get("https://www.google.com", timeout=CONNECTION_TIMEOUT)
            return True
        except requests.ConnectionError:
            return False
    
    def download_file(self, url, filename):
        """Descarga un archivo y lo guarda en la ubicación especificada."""
        try:
            response = requests.get(url, stream=True, timeout=CONNECTION_TIMEOUT)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"Error al descargar {url}: {e}")
        return False
    
    # =============================================
    # MÉTODOS DE GESTIÓN DE MEDIOS
    # =============================================
    
    def download_media(self):
        """Descarga los medios del servidor y los guarda en caché."""
        headers = {'If-Modified-Since': self.last_modified} if self.last_modified else {}
        
        try:
            print("Intentando descargar JSON desde:", JSON_URL)
            response = requests.get(JSON_URL, headers=headers, timeout=CONNECTION_TIMEOUT)
            
            if response.status_code == 304:
                print("JSON no modificado desde la última descarga")
                return
                
            if response.status_code != 200:
                print(f"Error al descargar el JSON: {response.status_code}")
                return

            print("JSON descargado exitosamente")
            self.last_modified = response.headers.get('Last-Modified', self.last_modified)
            
            try:
                data = response.json()
                print("JSON parseado correctamente")
                print(f"Número de reglas: {len(data.get('data', []))}")
            except json.JSONDecodeError:
                print("Error al parsear JSON")
                return

            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f)
                print("Configuración guardada en caché")

            new_media_list = []
            for i, rule in enumerate(data.get('data', [])):
                print(f"\nProcesando regla {i}:")
                print(f"Contenido de regla: {rule}")
                
                if 'src' not in rule:
                    print("Regla sin campo 'src', omitiendo")
                    continue
                    
                media_url = f"{BASE_URL}{rule.get('src', '')}"
                print(f"URL de medio: {media_url}")

                if not media_url:
                    print("URL de medio vacía, omitiendo")
                    continue

                filename = os.path.join(MEDIA_DIR, os.path.basename(media_url))
                print(f"Ruta local: {filename}")

                if not os.path.exists(filename):
                    print("Archivo no existe localmente, intentando descargar...")
                    if not self.download_file(media_url, filename):
                        print("Descarga fallida, omitiendo")
                        continue
                    print("Descarga exitosa")
                else:
                    print("Archivo ya existe en caché")

                scaling_type = rule.get("escalado", "fit")
                print(f"Tipo de escalado: {scaling_type}")

                media_item = self.create_media_item(filename, scaling_type, rule)
                if media_item:
                    new_media_list.append(media_item)
                    print("Medio agregado a la lista")
                else:
                    print("No se pudo crear item de medio")

            with self.media_lock:
                print(f"\nTotal de nuevos medios: {len(new_media_list)}")
                if new_media_list != self.media_list:
                    self.media_list = new_media_list
                    self.current_media_index = 0  # Resetear índice al actualizar lista
                    self.start_time = pygame.time.get_ticks()  # Resetear timer
                    print("Lista de medios actualizada")

        except requests.RequestException as e:
            print(f"Error en la solicitud al servidor: {e}")
    
    def load_local_media(self):
        """Carga los medios desde la caché si no hay internet."""
        if not os.path.exists(CONFIG_FILE):
            return

        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)

        new_media_list = []
        for rule in data.get('data', []):
            filename = os.path.join(MEDIA_DIR, os.path.basename(rule['src']))
            if os.path.exists(filename):
                media_item = self.create_media_item(filename, rule.get("escalado", "fit"), rule)
                if media_item:
                    new_media_list.append(media_item)

        with self.media_lock:
            self.media_list = new_media_list
    
    def create_media_item(self, filename, scaling_type, rule):
        """Crea un elemento de medio según su tipo."""
        try:
            if not os.path.exists(filename):
                print(f"Archivo no encontrado: {filename}")
                return None
                
            lower_filename = filename.lower()
            
            if lower_filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                try:
                    image = pygame.image.load(filename)
                    print(f"Imagen cargada: {filename}")
                    return ('image', image, scaling_type, rule)  # 4 elementos
                except pygame.error as e:
                    print(f"Error al cargar imagen {filename}: {e}")
                    return None
                    
            elif lower_filename.endswith(('.mp4', '.avi', '.mov')):
                try:
                    cap = cv2.VideoCapture(filename)
                    if not cap.isOpened():
                        print(f"No se pudo abrir el video: {filename}")
                        return None
                    print(f"Video cargado: {filename}")
                    return ('video', cap, scaling_type, rule)  # 4 elementos
                except Exception as e:
                    print(f"Error al cargar video {filename}: {e}")
                    return None
                    
        except Exception as e:
            print(f"Error al cargar {filename}: {e}")
            return None
    
    # =============================================
    # MÉTODOS DE ACTUALIZACIÓN EN SEGUNDO PLANO
    # =============================================
    
    def update_media(self):
        """Actualiza los medios periódicamente."""
        while self.running:
            if time.time() - self.last_update_time >= UPDATE_INTERVAL:
                if self.internet_available():
                    self.download_media()
                    print("con internet")
                else:
                    self.load_local_media()
                self.last_update_time = time.time()
            time.sleep(10)
    
    def update_coordinates(self):
        """Actualiza las coordenadas (x, y) periódicamente."""
        while self.running:
            try:
                response = requests.get(JSON_URL, timeout=CONNECTION_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    
                    with self.media_lock:
                        for media in self.media_list:
                            for rule in data.get('data', []):
                                if rule.get('src') in media[-1].get('src', ''):
                                    media[-1]["x"] = rule.get("x", "0")
                                    media[-1]["y"] = rule.get("y", "0")
                time.sleep(10)
            except Exception as e:
                print(f"Error al actualizar coordenadas: {e}")
    
    # =============================================
    # MÉTODOS DE VISUALIZACIÓN
    # =============================================
    
    def scale_media(self, media, scaling_type, json_x=0, json_y=0):
        """Escala el medio según el tipo de escalado y aplica desplazamientos."""
        media_width, media_height = media.get_size()
        target_width, target_height = self.screen_width, self.screen_height
        
        if scaling_type == "original":
            # Tamaño original + permite movimiento
            pos_x = (target_width // 2 - media_width // 2) + int(json_x)
            pos_y = (target_height // 2 - media_height // 2) + int(json_y)
            return media, (pos_x, pos_y)
        
        elif scaling_type == "fit":
            # Ajuste manteniendo relación de aspecto + solo movimiento en Y
            aspect_ratio = media_width / media_height
            if target_width / target_height > aspect_ratio:
                new_height = target_height
                new_width = int(new_height * aspect_ratio)
            else:
                new_width = target_width
                new_height = int(new_width / aspect_ratio)
            scaled = pygame.transform.scale(media, (new_width, new_height))
            pos_x = (target_width - new_width) // 2
            pos_y = ((target_height - new_height) // 2) + int(json_y)
            return scaled, (pos_x, pos_y)
        
        elif scaling_type == "outfit":
            # Ajuste cubriendo pantalla + solo movimiento en X
            aspect_ratio = media_width / media_height
            if target_width / target_height > aspect_ratio:
                new_width = target_width
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = target_height
                new_width = int(new_height * aspect_ratio)
            scaled = pygame.transform.scale(media, (new_width, new_height))
            pos_x = ((target_width - new_width) // 2) + int(json_x)
            pos_y = (target_height - new_height) // 2
            return scaled, (pos_x, pos_y)
        
        elif scaling_type == "escalado":
            # Escalado forzado (sin movimiento)
            return pygame.transform.scale(media, (target_width, target_height)), (0, 0)
        
        else:
            # Por defecto: "fit"
            return self.scale_media(media, "fit", json_x, json_y)
    
    def process_video_frame(self, video_capture):
        """Procesa un frame de video y lo convierte para pygame."""
        ret, frame = video_capture.read()
        if not ret:
            return None
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        frame = cv2.flip(frame, 1)
        return pygame.surfarray.make_surface(frame)
    
    # =============================================
    # MÉTODOS DE CONTROL DE TIEMPO
    # =============================================
    
    def is_within_time_range(self, rule):
        """Verifica si la fecha/hora actual está dentro del rango permitido."""
        try:
            if not all(key in rule for key in ['fecha_inicio', 'fecha_fin', 'hora_inicio', 'hora_fin']):
                return False
                
            now = datetime.now(LOCAL_TIMEZONE)
            fecha_inicio = datetime.strptime(rule['fecha_inicio'], '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(rule['fecha_fin'], '%Y-%m-%d').date()
            
            # Verificar primero el rango de fechas
            if not (fecha_inicio <= now.date() <= fecha_fin):
                return False
                
            hora_inicio = datetime.strptime(rule['hora_inicio'], '%H:%M:%S').time()
            hora_fin = datetime.strptime(rule['hora_fin'], '%H:%M:%S').time()
            
            return hora_inicio <= now.time() <= hora_fin
        except Exception as e:
            print(f"Error en is_within_time_range: {e}")
            return False
    
    def has_valid_media(self):
        """Verifica si hay medios válidos según la fecha/hora."""
        with self.media_lock:
            print(f"Total de medios cargados: {len(self.media_list)}")
            for i, media in enumerate(self.media_list):
                rule = media[-1]
                within_time = self.is_within_time_range(rule)
                print(f"Medio {i}: {media[0]} - Válido: {within_time}")
                if within_time:
                    return True
            return False
    
    def should_switch_media(self, rule):
        """Determina si debe cambiar al siguiente medio basado en la duración."""
        duration = int(rule.get("duracion", DEFAULT_DURATION))
        return (pygame.time.get_ticks() - self.start_time) / 1000 >= duration
    
    # =============================================
    # BUCLE PRINCIPAL
    # =============================================
    
    def run(self):
        """Bucle principal de ejecución."""
        # Iniciar hilos de actualización
        threading.Thread(target=self.update_media, daemon=True).start()
        threading.Thread(target=self.update_coordinates, daemon=True).start()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    self.running = False

            self.screen.fill((0, 0, 0))  # Fondo negro

            with self.media_lock:
                media_count = len(self.media_list)
                if media_count > 0:
                    # Variable para controlar si debemos avanzar al siguiente medio
                    should_advance = False
                    
                    # Obtener el medio actual
                    media = self.media_list[self.current_media_index]
                    media_type, *media_data, rule = media

                    # Verificar si está en rango de tiempo
                    if not self.is_within_time_range(rule):
                        print(f"Medio {self.current_media_index} fuera de rango temporal, avanzando...")
                        should_advance = True
                    else:
                        # Si está en rango, procesar el medio
                        json_x = rule.get("x", "0")
                        json_y = rule.get("y", "0")

                        if media_type == 'image':
                            try:
                                scaled, pos = self.scale_media(media_data[0], media_data[1], json_x, json_y)
                                self.screen.blit(scaled, pos)
                                
                                if self.should_switch_media(rule):
                                    should_advance = True
                                    
                            except Exception as e:
                                print(f"Error al mostrar imagen: {e}")
                                should_advance = True

                        elif media_type == 'video':
                            try:
                                if len(media_data) >= 2:
                                    video_capture = media_data[0]
                                    video_scaling = media_data[1]
                                    
                                    frame = self.process_video_frame(video_capture)
                                    if frame:
                                        scaled, pos = self.scale_media(frame, video_scaling, json_x, json_y)
                                        self.screen.blit(scaled, pos)
                                    else:
                                        print("Fin de video alcanzado")
                                        should_advance = True
                                else:
                                    print(f"Error: media_data incompleto para video")
                                    should_advance = True
                                    
                            except Exception as e:
                                print(f"Error al mostrar video: {e}")
                                should_advance = True

                    # Avanzar al siguiente medio si es necesario
                    if should_advance:
                        self.current_media_index = (self.current_media_index + 1) % media_count
                        self.start_time = pygame.time.get_ticks()
                        print(f"Cambiando a medio {self.current_media_index}")
                
            pygame.display.flip()
            self.clock.tick(FPS)

# =============================================
# EJECUCIÓN PRINCIPAL
# =============================================

if __name__ == "__main__":
    player = MediaPlayer()
    player.run()