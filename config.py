import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MQTT configurations
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
KEEP_ALIVE_INTERVAL = int(os.getenv("MQTT_KEEPALIVE_INTERVAL", "60"))

# Topic configurations
VERSION = os.getenv("MQTT_VERSION", "1.0.0")
IDENTIFIER = os.getenv("MQTT_IDENTIFIER", "gardyn-xx")
MODEL= os.getenv("MQTT_DEVICE_MODEL", "gardyn 3.0")
BASE_TOPIC = os.getenv("MQTT_BASETOPIC", "gardyn")

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

SENSOR_TYPE = os.getenv('SENSOR_TYPE')

WATER_LOW_CM = float(os.getenv("WATER_LOW_CM", 0)) or None

GROW_CHECK_INTERVAL_HOURS = int(os.getenv("GROW_CHECK_INTERVAL_HOURS", "6"))
GROW_THIN_DAYS_AFTER_FOOD = int(os.getenv("GROW_THIN_DAYS_AFTER_FOOD", "7"))
GROW_ROOT_FIRST_CHECK_DAYS = int(os.getenv("GROW_ROOT_FIRST_CHECK_DAYS", "21"))
GROW_ROOT_CHECK_INTERVAL_DAYS = int(os.getenv("GROW_ROOT_CHECK_INTERVAL_DAYS", "14"))
GROW_TRIM_INTERVAL_DAYS = int(os.getenv("GROW_TRIM_INTERVAL_DAYS", "14"))
GROW_HARVEST_FIRST_DAYS = int(os.getenv("GROW_HARVEST_FIRST_DAYS", "28"))
GROW_HARVEST_INTERVAL_DAYS = int(os.getenv("GROW_HARVEST_INTERVAL_DAYS", "7"))
GROW_TANK_REFRESH_INTERVAL_DAYS = int(os.getenv("GROW_TANK_REFRESH_INTERVAL_DAYS", "28"))
GROW_TANK_REFRESH_WARNING_DAYS = int(os.getenv("GROW_TANK_REFRESH_WARNING_DAYS", "7"))

UPPER_CAMERA_DEVICE = os.getenv("UPPER_CAMERA_DEVICE", "/dev/video0")
LOWER_CAMERA_DEVICE = os.getenv("LOWER_CAMERA_DEVICE", "/dev/video2")
UPPER_IMAGE_PATH = os.getenv("UPPER_IMAGE_PATH", "/tmp/upper_camera.jpg")
LOWER_IMAGE_PATH = os.getenv("LOWER_IMAGE_PATH", "/tmp/lower_camera.jpg")
CAMERA_RESOLUTION = os.getenv("CAMERA_RESOLUTION", "640x480")
IMAGE_INTERVAL_SECONDS = int(os.getenv("IMAGE_INTERVAL_SECONDS", "3600"))
