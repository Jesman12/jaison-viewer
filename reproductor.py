import pygame
import sys
import requests
import os
import json
from io import BytesIO
import cv2
import numpy as np
from datetime import datetime
import time
import pytz
import threading

# Crear carpeta de caché si no existe
CACHE_DIR = "cache"
MEDIA_DIR = os.path.join(CACHE_DIR, "media")
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")

os.makedirs(MEDIA_DIR, exist_ok=True)

# Inicializar pygame
pygame.init()
info = pygame.display.Info()
screen_width, screen_height = info.current_w, info.current_h
screen = pygame.display.set_mode((screen_width, screen_height), pygame.NOFRAME | pygame.FULLSCREEN)
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

# Zona horaria local
local_timezone = pytz.timezone('America/Mexico_City')

def internet_available():
    """ Verifica si hay conexión a internet haciendo una petición a Google. """
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False

def convert_to_local_time(server_time_str):
    try:
        server_time = datetime.strptime(server_time_str, '%Y-%m-%d %H:%M:%S')
        server_time = pytz.utc.localize(server_time)
        return server_time.astimezone(local_timezone)
    except Exception:
        return None

def download_media():
    """ Descarga los medios del servidor y los guarda en caché. """
    global last_modified, media_list
    headers = {'If-Modified-Since': last_modified} if last_modified else {}

    try:
        response = requests.get(json_url, headers=headers, timeout=5)
        if response.status_code == 304:
            return  # No hay cambios

        if response.status_code != 200:
            print(f"Error al descargar el JSON: {response.status_code}")
            return

        data = response.json()
        last_modified = data.get('last_modified', last_modified)

        # Guardar configuración en JSON local
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

        new_media_list = []
        for rule in data.get('data', []):
            media_url = f"{base_url}{rule.get('src', '')}"
            if not media_url:
                continue

            filename = os.path.join(MEDIA_DIR, os.path.basename(media_url))
            try:
                if not os.path.exists(filename):  # Evitar descargar si ya existe
                    media_response = requests.get(media_url, stream=True, timeout=5)
                    if media_response.status_code == 200:
                        with open(filename, 'wb') as f:
                            for chunk in media_response.iter_content(1024):
                                f.write(chunk)

                if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    image = pygame.image.load(filename)
                    new_media_list.append(('image', image, rule))
                elif filename.endswith(('.mp4', '.avi', '.mov')):
                    video = cv2.VideoCapture(filename)
                    if not video.isOpened():
                        continue
                    video.set(cv2.CAP_PROP_BUFFERSIZE, 2)
                    fps = video.get(cv2.CAP_PROP_FPS) or 30
                    new_media_list.append(('video', video, fps, rule))

            except Exception as e:
                print(f"Error al descargar {media_url}: {e}")

        media_list = new_media_list
    except requests.RequestException as e:
        print(f"Error en la solicitud al servidor: {e}")

def load_local_media():
    """ Carga los medios desde la caché si no hay internet. """
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

        if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            image = pygame.image.load(filename)
            new_media_list.append(('image', image, rule))
        elif filename.endswith(('.mp4', '.avi', '.mov')):
            video = cv2.VideoCapture(filename)
            if not video.isOpened():
                continue
            video.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            fps = video.get(cv2.CAP_PROP_FPS) or 30
            new_media_list.append(('video', video, fps, rule))

    media_list = new_media_list

def update_media():
    """ Hilo en segundo plano para actualizar los medios cada 30 segundos si hay internet. """
    global last_update_time
    while running:
        if time.time() - last_update_time >= 30:
            if internet_available():
                download_media()
            else:
                load_local_media()
            last_update_time = time.time()
        time.sleep(10)

# Iniciar el hilo de actualización de medios
threading.Thread(target=update_media, daemon=True).start()

def is_within_time_range(rule):
    """ Verifica si la fecha/hora actual está dentro del rango permitido. """
    try:
        current_datetime = datetime.now()
        fecha_inicio = datetime.strptime(rule['fecha_inicio'], '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(rule['fecha_fin'], '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(rule['hora_inicio'], '%H:%M:%S').time()
        hora_fin = datetime.strptime(rule['hora_fin'], '%H:%M:%S').time()
        return fecha_inicio <= current_datetime.date() <= fecha_fin and hora_inicio <= current_datetime.time() <= hora_fin
    except Exception:
        return False

def scale_to_fit(image, target_width, target_height):
    """ Escala imágenes manteniendo la relación de aspecto. """
    return pygame.transform.smoothscale(image, (target_width, target_height))

def has_valid_media():
    """ Verifica si hay medios válidos según la fecha/hora. """
    return any(is_within_time_range(rule) for _, _, *extra in media_list for rule in [extra[-1]])

# Cargar los medios según la disponibilidad de internet
if internet_available():
    download_media()
else:
    load_local_media()

start_time = pygame.time.get_ticks()

# Bucle principal
while running:
    # Procesar eventos
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False

    # Verificar si hay medios disponibles
    if has_valid_media():
        media_type, media, *extra = media_list[current_media_index]
        rule = extra[-1]

        if is_within_time_range(rule):
            if media_type == 'image':
                # Mostrar imagen
                scaled_image = scale_to_fit(media, screen_width, screen_height)
                screen.blit(scaled_image, (0, 0))

                # Cambiar después de 5 segundos
                if (pygame.time.get_ticks() - start_time) / 1000 >= 5:
                    current_media_index = (current_media_index + 1) % len(media_list)
                    start_time = pygame.time.get_ticks()
            elif media_type == 'video':
                # Mostrar video
                ret, frame = media.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = np.rot90(frame)
                    frame_surface = pygame.surfarray.make_surface(frame)
                    scaled_frame = scale_to_fit(frame_surface, screen_width, screen_height)
                    screen.blit(scaled_frame, (0, 0))
                else:
                    # Reiniciar video cuando termine
                    media.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    current_media_index = (current_media_index + 1) % len(media_list)
                    start_time = pygame.time.get_ticks()

    # Actualizar la pantalla y controlar la tasa de actualización
    pygame.display.flip()
    clock.tick(30)  # Limitar a 30 FPS para un rendimiento estable

pygame.quit()
sys.exit()