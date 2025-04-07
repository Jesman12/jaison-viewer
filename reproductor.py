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
import socket

# Configuración inicial
CACHE_DIR = "cache"
MEDIA_DIR = os.path.join(CACHE_DIR, "media")
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

UPDATE_INTERVAL = 30
CONNECTION_TIMEOUT = 5
DEFAULT_DURATION = 5
FPS = 30
JSON_URL = 'https://api.jaison.mx/raspi/api.php?action=listarImagenes'
BASE_URL = 'http://api.jaison.mx/'
LOCAL_TIMEZONE = pytz.timezone('America/Mexico_City')

class MediaPlayer:
    def __init__(self):
        self.init_pygame()
        self.last_modified = None
        self.media_list = []
        self.current_media_index = 0
        self.last_update_time = time.time()
        self.running = True
        self.media_lock = threading.Lock()
        self.start_time = pygame.time.get_ticks()
        self.interrupt_rule_id = None
        self.interrupt_lock = threading.Lock()
        self.socket_port = 8080
        
    def init_pygame(self):
         """Inicializa pygame y configura la pantalla en modo fullscreen."""
         pygame.init()
         self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
         self.screen_width, self.screen_height = self.screen.get_size()
         self.clock = pygame.time.Clock()
    
    def handle_socket_connections(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.socket_port))
            s.listen()
            
            while self.running:
                conn, addr = s.accept()
                with conn:
                    data = conn.recv(1024).decode('utf-8').strip()
                    if data.startswith("socket_") and "_" in data:
                        _, rule_id = data.split("_", 1)
                        if rule_id.isdigit():
                            with self.interrupt_lock:
                                self.interrupt_rule_id = int(rule_id)
                            conn.sendall(b"ok")
                        else:
                            conn.sendall(b"error: id invalido")
                    else:
                        conn.sendall(b"error: formato incorrecto")

    def internet_available(self):
        try:
            requests.get("https://www.google.com", timeout=CONNECTION_TIMEOUT)
            return True
        except requests.ConnectionError:
            return False
    
    def download_file(self, url, filename):
        try:
            response = requests.get(url, stream=True, timeout=CONNECTION_TIMEOUT)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
        except Exception:
            return False
    
    def download_media(self):
        headers = {'If-Modified-Since': self.last_modified} if self.last_modified else {}
        
        try:
            response = requests.get(JSON_URL, headers=headers, timeout=CONNECTION_TIMEOUT)
            
            if response.status_code == 304:
                return
                
            if response.status_code != 200:
                return

            self.last_modified = response.headers.get('Last-Modified', self.last_modified)
            data = response.json()

            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f)

            new_media_list = []
            for rule in data.get('data', []):
                if 'src' not in rule:
                    continue
                    
                media_url = f"{BASE_URL}{rule.get('src', '')}"
                if not media_url:
                    continue

                filename = os.path.join(MEDIA_DIR, os.path.basename(media_url))
                if not os.path.exists(filename):
                    if not self.download_file(media_url, filename):
                        continue

                scaling_type = rule.get("escalado", "fit")
                media_item = self.create_media_item(filename, scaling_type, rule)
                if media_item:
                    # Verificar si ya existe un medio con la misma fuente para actualizarlo
                    existing_index = next((i for i, m in enumerate(self.media_list) 
                                        if len(m) > 3 and m[3].get('src') == rule.get('src')), None)
                    if existing_index is not None:
                        self.media_list[existing_index] = media_item
                    else:
                        new_media_list.append(media_item)

            with self.media_lock:
                # Agregar solo los nuevos medios que no existían antes
                existing_srcs = [m[3].get('src') for m in self.media_list if len(m) > 3]
                for media in new_media_list:
                    if len(media) > 3 and media[3].get('src') not in existing_srcs:
                        self.media_list.append(media)

        except requests.RequestException:
            pass
    
    def load_local_media(self):
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
        try:
            if not os.path.exists(filename):
                return None
                
            lower_filename = filename.lower()
            
            if lower_filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                image = pygame.image.load(filename)
                return ('image', image, scaling_type, rule)
                
            elif lower_filename.endswith(('.mp4', '.avi', '.mov')):
                cap = cv2.VideoCapture(filename)
                if not cap.isOpened():
                    return None
                return ('video', cap, scaling_type, rule)
                
        except Exception:
            return None
    
    def update_media(self):
        while self.running:
            if time.time() - self.last_update_time >= UPDATE_INTERVAL:
                if self.internet_available():
                    self.download_media()
                else:
                    self.load_local_media()
                self.last_update_time = time.time()
            time.sleep(10)
    
    def update_coordinates(self):
        while self.running:
            try:
                response = requests.get(JSON_URL, timeout=CONNECTION_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    
                    with self.media_lock:
                        for i, media in enumerate(self.media_list):
                            for rule in data.get('data', []):
                                if rule.get('src') in media[-1].get('src', ''):
                                    # Actualiza coordenadas
                                    media[-1]["x"] = rule.get("x", "0")
                                    media[-1]["y"] = rule.get("y", "0")
                                    # Actualiza el tipo de escalado si ha cambiado
                                    if len(media) > 2:  # Asegurarnos que tenemos el campo de escalado
                                        new_scaling = rule.get("escalado", "fit")
                                        if media[2] != new_scaling:
                                            # Actualizamos el tipo de escalado en el elemento multimedia
                                            self.media_list[i] = (media[0], media[1], new_scaling, media[3])
                time.sleep(10)
            except Exception:
                pass
        
    def scale_media(self, media, scaling_type, json_x=0, json_y=0):
        media_width, media_height = media.get_size()
        target_width, target_height = self.screen_width, self.screen_height
        
        if scaling_type == "original":
            pos_x = (target_width // 2 - media_width // 2) + int(json_x)
            pos_y = (target_height // 2 - media_height // 2) + int(json_y)
            return media, (pos_x, pos_y)
        
        elif scaling_type == "fit":
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
            return pygame.transform.scale(media, (target_width, target_height)), (0, 0)
        
        else:
            return self.scale_media(media, "fit", json_x, json_y)
    
    def process_video_frame(self, video_capture):
        ret, frame = video_capture.read()
        if not ret:
            return None
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        frame = cv2.flip(frame, 1)
        return pygame.surfarray.make_surface(frame)
    
    def is_within_time_range(self, rule):
        try:
            if not all(key in rule for key in ['fecha_inicio', 'fecha_fin', 'hora_inicio', 'hora_fin']):
                return False
                
            now = datetime.now(LOCAL_TIMEZONE)
            fecha_inicio = datetime.strptime(rule['fecha_inicio'], '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(rule['fecha_fin'], '%Y-%m-%d').date()
            
            if not (fecha_inicio <= now.date() <= fecha_fin):
                return False
                
            hora_inicio = datetime.strptime(rule['hora_inicio'], '%H:%M:%S').time()
            hora_fin = datetime.strptime(rule['hora_fin'], '%H:%M:%S').time()
            
            return hora_inicio <= now.time() <= hora_fin
        except Exception:
            return False
    
    def has_valid_media(self):
        with self.media_lock:
            for media in self.media_list:
                rule = media[-1]
                if self.is_within_time_range(rule):
                    return True
            return False
    
    def should_switch_media(self, rule):
        duration = int(rule.get("duracion", DEFAULT_DURATION))
        return (pygame.time.get_ticks() - self.start_time) / 1000 >= duration
    
    def run(self):
        threading.Thread(target=self.update_media, daemon=True).start()
        threading.Thread(target=self.update_coordinates, daemon=True).start()
        threading.Thread(target=self.handle_socket_connections, daemon=True).start()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    self.running = False

            self.screen.fill((0, 0, 0))

            with self.media_lock:
                media_count = len(self.media_list)
                if media_count > 0:
                    with self.interrupt_lock:
                        if self.interrupt_rule_id is not None:
                            for idx, media in enumerate(self.media_list):
                                if len(media) > 3 and media[3].get('rule_id') == str(self.interrupt_rule_id):
                                    self.current_media_index = idx
                                    self.start_time = pygame.time.get_ticks()
                                    self.interrupt_rule_id = None
                                    break
                            else:
                                self.interrupt_rule_id = None
                    
                    should_advance = False
                    media = self.media_list[self.current_media_index]
                    media_type, *media_data, rule = media
                    
                    if not self.is_within_time_range(rule):
                        should_advance = True
                    else:
                        json_x = rule.get("x", "0")
                        json_y = rule.get("y", "0")
                        scaling_type = media_data[1]  # El tipo de escalado está en la posición 1 de media_data
                        
                        if media_type == 'image':
                            try:
                                scaled, pos = self.scale_media(media_data[0], scaling_type, json_x, json_y)
                                self.screen.blit(scaled, pos)
                                
                                if self.should_switch_media(rule):
                                    should_advance = True
                            except Exception:
                                should_advance = True
                                
                        elif media_type == 'video':
                            try:
                                if len(media_data) >= 2:
                                    video_capture = media_data[0]
                                    frame = self.process_video_frame(video_capture)
                                    if frame:
                                        scaled, pos = self.scale_media(frame, scaling_type, json_x, json_y)
                                        self.screen.blit(scaled, pos)
                                    else:
                                        video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                        should_advance = True
                                else:
                                    should_advance = True
                            except Exception:
                                should_advance = True
                                
                    if should_advance:
                        self.current_media_index = (self.current_media_index + 1) % media_count
                        self.start_time = pygame.time.get_ticks()
            
            pygame.display.flip()
            self.clock.tick(FPS)

if __name__ == "__main__":
    player = MediaPlayer()
    player.run()