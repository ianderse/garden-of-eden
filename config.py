import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def _get_int(name, default, minimum=None, maximum=None):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

def _get_float(name, default, minimum=None, maximum=None):
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

# MQTT configurations
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = _get_int("MQTT_PORT", 1883, minimum=1, maximum=65535)
KEEP_ALIVE_INTERVAL = _get_int("MQTT_KEEPALIVE_INTERVAL", 60, minimum=1)

# Topic configurations
VERSION = os.getenv("MQTT_VERSION", "1.0.0")
IDENTIFIER = os.getenv("MQTT_IDENTIFIER", "gardyn-xx")
MODEL= os.getenv("MQTT_DEVICE_MODEL", "gardyn 3.0")
BASE_TOPIC = os.getenv("MQTT_BASETOPIC", "gardyn")

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

SENSOR_TYPE = os.getenv('SENSOR_TYPE')

WATER_LOW_CM = _get_float("WATER_LOW_CM", 0, minimum=0) or None
DISTANCE_SENSOR_ENABLED = os.getenv("DISTANCE_SENSOR_ENABLED", "true").strip().lower() in ("true", "1", "yes", "on")
WATER_REFILL_AMOUNT = os.getenv("WATER_REFILL_AMOUNT", "2L")

FOOD_INTERVAL_DAYS = _get_int("FOOD_INTERVAL_DAYS", 14, minimum=1)
FOOD_AMOUNT = os.getenv("FOOD_AMOUNT", "5ml per liter")
FOOD_CHECK_INTERVAL_HOURS = _get_int("FOOD_CHECK_INTERVAL_HOURS", 6, minimum=1)

GROW_CHECK_INTERVAL_HOURS = _get_int("GROW_CHECK_INTERVAL_HOURS", 6, minimum=1)
GROW_THIN_DAYS_AFTER_FOOD = _get_int("GROW_THIN_DAYS_AFTER_FOOD", 7, minimum=1)
GROW_ROOT_FIRST_CHECK_DAYS = _get_int("GROW_ROOT_FIRST_CHECK_DAYS", 21, minimum=1)
GROW_ROOT_CHECK_INTERVAL_DAYS = _get_int("GROW_ROOT_CHECK_INTERVAL_DAYS", 14, minimum=1)
GROW_TRIM_INTERVAL_DAYS = _get_int("GROW_TRIM_INTERVAL_DAYS", 14, minimum=1)
GROW_HARVEST_FIRST_DAYS = _get_int("GROW_HARVEST_FIRST_DAYS", 28, minimum=1)
GROW_HARVEST_INTERVAL_DAYS = _get_int("GROW_HARVEST_INTERVAL_DAYS", 7, minimum=1)
GROW_TANK_REFRESH_INTERVAL_DAYS = _get_int("GROW_TANK_REFRESH_INTERVAL_DAYS", 28, minimum=1)
GROW_TANK_REFRESH_WARNING_DAYS = _get_int("GROW_TANK_REFRESH_WARNING_DAYS", 7, minimum=0)

UPPER_CAMERA_DEVICE = os.getenv("UPPER_CAMERA_DEVICE", "/dev/video0")
LOWER_CAMERA_DEVICE = os.getenv("LOWER_CAMERA_DEVICE", "/dev/video2")
UPPER_IMAGE_PATH = os.getenv("UPPER_IMAGE_PATH", "/tmp/upper_camera.jpg")
LOWER_IMAGE_PATH = os.getenv("LOWER_IMAGE_PATH", "/tmp/lower_camera.jpg")
CAMERA_RESOLUTION = os.getenv("CAMERA_RESOLUTION", "640x480")
IMAGE_INTERVAL_SECONDS = _get_int("IMAGE_INTERVAL_SECONDS", 3600, minimum=1)
