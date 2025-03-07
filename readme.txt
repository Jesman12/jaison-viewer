Instalación del Visualizador Multimedia en Raspberry Pi Zero
--Requisitos previos
Antes de instalar el programa, asegúrate de que tu Raspberry Pi Zero cuenta con:

*Raspbian instalado y actualizado
*Conexión a internet
*Python 3 instalado

--Instalación de dependencias

Actualiza el sistema:

sudo apt update
sudo apt upgrade

//Instala las bibliotecas necesarias:

sudo apt install python3-pip python3-dev libatlas-base-dev ffmpeg libsm6 libxext6

//Instala las librerías de Python:

pip3 install pygame requests opencv-python numpy pytz

--Configuración del programa

Descarga el archivo main.py en una carpeta de tu elección, por ejemplo:

mkdir ~/visualizador
cd ~/visualizador
nano main.py

//Pega el contenido del código.

Modifica las siguientes variables según tu configuración:

json_url: URL del JSON que contiene las rutas de las imágenes y videos

base_url: URL base del servidor para acceder a las imágenes y videos

local_timezone: Ajusta la zona horaria según tu ubicación (ejemplo: America/Mexico_City)

//Ejecución del programa

Para ejecutar el visualizador:
python3 main.py
