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

# Configuración inicial
CACHE_DIR = "cache"
MEDIA_DIR = os.path.join(CACHE_DIR, "media")
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")

os.makedirs(MEDIA_DIR, exist_ok=True)

# Inicializar pygame
pygame.init()

# Obtener el tamaño de la pantalla del dispositivo
screen_info = pygame.display.Info()
screen_width, screen_height = screen_info.current_w, screen_info.current_h

# Configurar pantalla completa
screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)

clock = pygame.time.Clock()

# URLs del servidor
json_url = 'https://api.jaison.mx/raspi/api.php?action=listarImagenes'
base_url = 'http://api.jaison.mx/'

# Variables globales
last_modified = None
media_list = []
current_media_index = 0
last_update_time = time.time()
running = True
media_lock = threading.Lock()

# Zona horaria local
local_timezone = pytz.timezone('America/Mexico_City')

def internet_available():
    """Verifica si hay conexión a internet."""
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False

def download_media():
    """Descarga los medios del servidor y los guarda en caché."""
    global last_modified, media_list

    headers = {'If-Modified-Since': last_modified} if last_modified else {}
    try:
        response = requests.get(json_url, headers=headers, timeout=5)
        if response.status_code == 304:
            print("No hay cambios en los medios.")
            return
        if response.status_code != 200:
            print(f"Error al descargar el JSON: {response.status_code}")
            return

        new_last_modified = response.headers.get('Last-Modified')
        if new_last_modified:
            last_modified = new_last_modified

        data = response.json()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

        new_media_list = []
        for rule in data.get('data', []):
            media_url = f"{base_url}{rule.get('src', '')}"
            if not media_url:
                continue

            filename = os.path.join(MEDIA_DIR, os.path.basename(media_url))
            try:
                if not os.path.exists(filename):
                    media_response = requests.get(media_url, stream=True, timeout=5)
                    if media_response.status_code == 200:
                        with open(filename, 'wb') as f:
                            for chunk in media_response.iter_content(1024):
                                f.write(chunk)

                scaling_type = rule.get("escalado", "fit")  # Obtener el tipo de escalado
                if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    image = pygame.image.load(filename)
                    new_media_list.append(('image', image, scaling_type, rule))
                elif filename.endswith(('.mp4', '.avi', '.mov')):
                    video = cv2.VideoCapture(filename)
                    if not video.isOpened():
                        continue
                    video.set(cv2.CAP_PROP_BUFFERSIZE, 2)
                    fps = video.get(cv2.CAP_PROP_FPS) or 30
                    new_media_list.append(('video', video, fps, scaling_type, rule))

            except Exception as e:
                print(f"Error al descargar {media_url}: {e}")

        with media_lock:
            if new_media_list != media_list:
                media_list = new_media_list
                print("Nuevos medios detectados. Lista actualizada.")

    except requests.RequestException as e:
        print(f"Error en la solicitud al servidor: {e}")

def load_local_media():
    """Carga los medios desde la caché si no hay internet."""
    global media_list
    if not os.path.exists(CONFIG_FILE):
        print("No hay datos almacenados en caché.")
        return

    with open(CONFIG_FILE, 'r') as f:
        data = json.load(f)

    new_media_list = []
    for rule in data.get('data', []):
        filename = os.path.join(MEDIA_DIR, os.path.basename(rule['src']))
        if not os.path.exists(filename):
            continue

        scaling_type = rule.get("escalado", "fit") 
        if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            image = pygame.image.load(filename)
            new_media_list.append(('image', image, scaling_type, rule))
        elif filename.endswith(('.mp4', '.avi', '.mov')):
            video = cv2.VideoCapture(filename)
            if not video.isOpened():
                continue
            video.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            fps = video.get(cv2.CAP_PROP_FPS) or 30
            new_media_list.append(('video', video, fps, scaling_type, rule))

    with media_lock:
        media_list = new_media_list

def update_media():
    """Hilo en segundo plano para actualizar los medios cada 30 segundos si hay internet."""
    global last_update_time
    while running:
        if time.time() - last_update_time >= 30:
            if internet_available():
                download_media()
            else:
                load_local_media()
            last_update_time = time.time()
        time.sleep(10)

def scale_media(media, scaling_type, target_width, target_height, json_x=0, json_y=0):
    """
    Escala el medio y aplica desplazamientos según el tipo de escalado.
    - json_x, json_y: Coordenadas del JSON (solo se aplican según scaling_type).
    """
    if scaling_type == "original":
        # Tamaño original + permite movimiento en X e Y
        scaled_media = media
        pos_x = (target_width // 2 - media.get_width() // 2) + int(json_x)
        pos_y = (target_height // 2 - media.get_height() // 2) + int(json_y)
        return scaled_media, (pos_x, pos_y)
    
    elif scaling_type == "fit":
        # Ajuste manteniendo relación de aspecto + solo movimiento en Y
        aspect_ratio = media.get_width() / media.get_height()
        if target_width / target_height > aspect_ratio:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)
        scaled_media = pygame.transform.scale(media, (new_width, new_height))
        pos_x = (target_width - new_width) // 2  # X fijo (centrado)
        pos_y = ((target_height - new_height) // 2) + int(json_y)  # Y móvil
        return scaled_media, (pos_x, pos_y)
    
    elif scaling_type == "outfit":
        # Ajuste cubriendo pantalla + solo movimiento en X
        aspect_ratio = media.get_width() / media.get_height()
        if target_width / target_height > aspect_ratio:
            new_width = target_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = target_height
            new_width = int(new_height * aspect_ratio)
        scaled_media = pygame.transform.scale(media, (new_width, new_height))
        pos_x = ((target_width - new_width) // 2) + int(json_x)  # X móvil
        pos_y = (target_height - new_height) // 2  # Y fijo (centrado)
        return scaled_media, (pos_x, pos_y)
    
    elif scaling_type == "escalado":
        # Escalado forzado (sin movimiento)
        scaled_media = pygame.transform.scale(media, (target_width, target_height))
        return scaled_media, (0, 0)  # Posición fija
    
    else:
        # Por defecto: "fit"
        return scale_media(media, "fit", target_width, target_height, json_x, json_y)
    
def draw_media():
    """Dibuja el medio actual en la pantalla."""
    with media_lock:
        if not media_list:
            return

        media_type, media, scaling_type, rule = media_list[current_media_index]

    if media_type == 'image':
        scaled_media, pos = scale_media(media, scaling_type, screen_width, screen_height)
        screen.blit(scaled_media, pos)
    elif media_type == 'video':
        ret, frame = media.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = pygame.surfarray.make_surface(frame)
            scaled_frame, pos = scale_media(frame, scaling_type, screen_width, screen_height)
            screen.blit(scaled_frame, pos)
        else:
            media.set(cv2.CAP_PROP_POS_FRAMES, 0)

def is_within_time_range(rule):
    """Verifica si la fecha/hora actual está dentro del rango permitido."""
    try:
        current_datetime = datetime.now()
        fecha_inicio = datetime.strptime(rule['fecha_inicio'], '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(rule['fecha_fin'], '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(rule['hora_inicio'], '%H:%M:%S').time()
        hora_fin = datetime.strptime(rule['hora_fin'], '%H:%M:%S').time()

        if fecha_inicio <= current_datetime.date() <= fecha_fin:
            if hora_inicio <= current_datetime.time() <= hora_fin:
                return True
        return False
    except Exception as e:
        print(f"Error en is_within_time_range: {e}")
        return False

def has_valid_media():
    """Verifica si hay medios válidos según la fecha/hora."""
    with media_lock:
        for media in media_list:
            media_type = media[0]  
            rule = media[-1]       
            if is_within_time_range(rule):
                return True
        return False

threading.Thread(target=update_media, daemon=True).start()

if internet_available():
    download_media()
else:
    load_local_media()

start_time = pygame.time.get_ticks()

while running:
    # Procesar eventos (solo para salir)
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False

    screen.fill((0, 0, 0))

    if has_valid_media():
        media = media_list[current_media_index]
        media_type = media[0]
        rule = media[-1]  # Datos del JSON

        if is_within_time_range(rule):
            # Obtener coordenadas del JSON (como strings)
            json_x = rule.get("x", "0")  # Default: "0"
            json_y = rule.get("y", "0")  # Default: "0"

            if media_type == 'image':
                scaled_media, pos = scale_media(
                    media[1], 
                    media[2],  # scaling_type
                    screen_width, 
                    screen_height,
                    json_x,
                    json_y
                )
                screen.blit(scaled_media, pos)

                # Cambio después de la duración
                if (pygame.time.get_ticks() - start_time) / 1000 >= int(rule.get("duracion", 5)):
                    current_media_index = (current_media_index + 1) % len(media_list)
                    start_time = pygame.time.get_ticks()

            elif media_type == 'video':
                ret, frame = media[1].read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    frame = cv2.flip(frame, 1)
                    frame_surface = pygame.surfarray.make_surface(frame)
                    
                    scaled_frame, pos = scale_media(
                        frame_surface,
                        media[3],  # scaling_type
                        screen_width,
                        screen_height,
                        json_x,
                        json_y
                    )
                    screen.blit(scaled_frame, pos)
                else:
                    media[1].set(cv2.CAP_PROP_POS_FRAMES, 0)
                    current_media_index = (current_media_index + 1) % len(media_list)
                    start_time = pygame.time.get_ticks()

    pygame.display.flip()
    clock.tick(30)
pygame.quit()
sys.exit()