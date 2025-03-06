import pygame
import sys
import requests
import json
from io import BytesIO
import cv2  # Importar OpenCV
import numpy as np
from datetime import datetime  # Para manejar la fecha y hora actual
import time
import pytz

# Función para convertir la hora del servidor a la zona horaria local 
def convert_to_local_time(server_time_str):
    # Convertir la cadena a un objeto datetime (asumiendo que está en UTC)
    server_time = datetime.strptime(server_time_str, '%Y-%m-%d %H:%M:%S')
    server_time = pytz.utc.localize(server_time)  # Asignar la zona horaria UTC

    # Convertir a la zona horaria local
    local_timezone = pytz.timezone('America/Mexico_City')  # Cambia esto a tu zona horaria
    local_time = server_time.astimezone(local_timezone)

    return local_time

# Inicializar pygame
pygame.init()

# URL para obtener el JSON
json_url = 'https://api.jaison.mx/raspi/api.php?action=listarImagenes'

# URL base del servidor para las imágenes y videos (ajusta esto según tu configuración)
base_url = 'http://api.jaison.mx/'

# Variable para almacenar la última marca de tiempo de modificación
last_modified = None

# Función para descargar y cargar los medios desde el servidor
def load_media_from_server():
    global last_modified

    # Encabezados para enviar la última marca de tiempo al servidor
    headers = {}
    if last_modified:
        headers['If-Modified-Since'] = last_modified

    # Descargar el JSON desde el servidor
    response = requests.get(json_url, headers=headers)

    # Si no hay cambios (código 304), no hacer nada
    if response.status_code == 304:
        print("No hay cambios en el servidor.")
        return None

    # Si hay un error, mostrar el mensaje y salir
    if response.status_code != 200:
        print(f"Error al descargar el JSON: {response.status_code}")
        return None

    # Cargar el JSON
    data = response.json()

    # Actualizar la última marca de tiempo
    last_modified = data.get('last_modified')

    # Descargar las imágenes y videos desde el servidor
    media_list = []
    for rule in data['data']:
        media_url = f"{base_url}{rule['src']}"
        response = requests.get(media_url)
        if response.status_code == 200:
            if rule['src'].endswith(('.jpg', '.jpeg', '.png', '.webp')):  # Si es una imagen
                image_data = BytesIO(response.content)
                image = pygame.image.load(image_data)
                media_list.append(('image', image, rule))  # Guardar la regla completa
            elif rule['src'].endswith(('.mp4', '.avi', '.mov')):  # Si es un video
                video_path = f"{rule['src'].split('/')[-1]}"  # Guardar el video en /tmp
                with open(video_path, 'wb') as f:
                    f.write(response.content)
                video = cv2.VideoCapture(video_path)  # Cargar el video con OpenCV
                fps = video.get(cv2.CAP_PROP_FPS)  # Obtener el FPS del video
                duration = int(video.get(cv2.CAP_PROP_FRAME_COUNT)) / fps  # Duración del video en segundos
                media_list.append(('video', video, fps, duration, rule))  # Guardar la regla completa
        else:
            print(f"Error al descargar el archivo: {media_url}")
    return media_list

# Cargar los medios iniciales desde el servidor
media_list = load_media_from_server()
if not media_list:
    print("No se pudieron cargar los medios iniciales.")
    pygame.quit()
    sys.exit()

# Configurar la pantalla con un tamaño inicial
screen_width, screen_height = 800, 600  # Tamaño inicial de la ventana
screen = pygame.display.set_mode((screen_width, screen_height), pygame.RESIZABLE)

# Inicializar variables para el control del tiempo y el índice actual
current_media_index = 0
clock = pygame.time.Clock()  # Reloj para controlar el FPS
start_time = pygame.time.get_ticks()  # Tiempo inicial
last_update_time = time.time()  # Última vez que se verificaron cambios en el servidor

# Función para verificar si la fecha y hora actual están dentro del rango permitido
def is_within_time_range(rule):
    try:
        # Obtener la fecha y hora actual
        current_datetime = datetime.now()

        # Convertir las fechas y horas del JSON a objetos datetime
        fecha_inicio = datetime.strptime(rule['fecha_inicio'], '%Y-%m-%d')
        fecha_fin = datetime.strptime(rule['fecha_fin'], '%Y-%m-%d')
        hora_inicio = datetime.strptime(rule['hora_inicio'], '%H:%M:%S').time()
        hora_fin = datetime.strptime(rule['hora_fin'], '%H:%M:%S').time()

        # Verificar si la fecha actual está dentro del rango
        if fecha_inicio <= current_datetime <= fecha_fin:
            # Verificar si la hora actual está dentro del rango
            current_time = current_datetime.time()
            return hora_inicio <= current_time <= hora_fin
        return False
    except Exception as e:
        print(f"Error al procesar el rango de fechas/horas: {e}")
        return False  # Si hay un error, no mostrar el archivo

# Función para escalar una imagen o frame de video manteniendo la relación de aspecto
def scale_to_fit(image, target_width, target_height):
    original_width, original_height = image.get_size()
    aspect_ratio = original_width / original_height
    target_aspect_ratio = target_width / target_height

    # Calcular el nuevo tamaño manteniendo la relación de aspecto
    if aspect_ratio > target_aspect_ratio:
        # Escalar según el ancho
        new_width = target_width
        new_height = int(new_width / aspect_ratio)
    else:
        # Escalar según el alto
        new_height = target_height
        new_width = int(new_height * aspect_ratio)

    # Escalar la imagen
    scaled_image = pygame.transform.scale(image, (new_width, new_height))

    # Crear una superficie negra del tamaño de la pantalla
    black_surface = pygame.Surface((target_width, target_height))
    black_surface.fill((0, 0, 0))  # Rellenar con color negro

    # Centrar la imagen escalada en la superficie negra
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    black_surface.blit(scaled_image, (x_offset, y_offset))

    return black_surface

# Función para verificar si hay archivos válidos en la lista de medios
def has_valid_media(media_list):
    for media in media_list:
        media_type, _, *extra = media
        rule = extra[-1]  # El último elemento de extra es la regla completa
        if is_within_time_range(rule):
            return True
    return False

# Inicializar fps con un valor predeterminado
fps = 60  # FPS predeterminado para imágenes o cuando no se pueda determinar el FPS de un video

# Bucle principal
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.VIDEORESIZE:  # Manejar el redimensionamiento de la ventana
            screen_width, screen_height = event.size
            screen = pygame.display.set_mode((screen_width, screen_height), pygame.RESIZABLE)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    # Verificar cambios en el servidor cada 30 segundos
    if time.time() - last_update_time >= 30:  # Verificar cada 30 segundos
        new_media_list = load_media_from_server()
        if new_media_list:
            media_list = new_media_list  # Actualizar la lista de medios
            current_media_index = 0  # Reiniciar el índice actual
            start_time = pygame.time.get_ticks()  # Reiniciar el temporizador
        last_update_time = time.time()  # Actualizar el tiempo de la última verificación

    # Verificar si hay archivos válidos para mostrar
    if has_valid_media(media_list):
        # Obtener el archivo actual (imagen o video)
        media_type, media, *extra = media_list[current_media_index]
        rule = extra[-1]  # El último elemento de extra es la regla completa

        # Verificar si la fecha y hora actual están dentro del rango permitido
        if is_within_time_range(rule):
            # Mostrar la imagen o el video
            if media_type == 'image':
                # Escalar la imagen manteniendo la relación de aspecto
                scaled_image = scale_to_fit(media, screen_width, screen_height)
                screen.blit(scaled_image, (0, 0))
                # Cambiar a la siguiente imagen después de 5 segundos
                if pygame.time.get_ticks() - start_time >= 5000:  # 5 segundos
                    current_media_index = (current_media_index + 1) % len(media_list)
                    start_time = pygame.time.get_ticks()  # Reiniciar el temporizador
            elif media_type == 'video':
                fps, duration = extra[0], extra[1]  # Obtener el FPS y la duración del video
                ret, frame = media.read()  # Leer el siguiente frame del video
                if ret:  # Si se leyó correctamente el frame
                    # Convertir el frame de OpenCV a una superficie de Pygame
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convertir de BGR a RGB
                    frame = np.rot90(frame)  # Rotar el frame (opcional, dependiendo de la orientación)
                    frame_surface = pygame.surfarray.make_surface(frame)

                    # Escalar el frame manteniendo la relación de aspecto
                    scaled_frame = scale_to_fit(frame_surface, screen_width, screen_height)
                    screen.blit(scaled_frame, (0, 0))
                else:  # Si el video terminó, cambiar al siguiente archivo
                    current_media_index = (current_media_index + 1) % len(media_list)
                    media.set(cv2.CAP_PROP_POS_FRAMES, 0)  
                    start_time = pygame.time.get_ticks() 
        else:
            # Si no está dentro del rango de fechas/horas, pasar al siguiente archivo
            current_media_index = (current_media_index + 1) % len(media_list)
            start_time = pygame.time.get_ticks()  
    else:
        # Si no hay archivos válidos, limpiar la pantalla
        screen.fill((0, 0, 0)) 

    # Actualizar la pantalla
    pygame.display.flip()

    # Controlar la velocidad de reproducción del video
    if has_valid_media(media_list) and media_type == 'video':
        clock.tick(fps)  
    else:
        clock.tick(30)  

# Liberar los recursos de los videos
for media in media_list:
    if media[0] == 'video':
        media[1].release()

# Salir de pygame
pygame.quit()
sys.exit()