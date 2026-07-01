import subprocess
import threading
from threading import Timer
import logging
import paho.mqtt.client as mqtt
import json
from datetime import datetime, timedelta, timezone
# import picamera
# import cv2
from time import sleep
from config import USERNAME, PASSWORD, BROKER, PORT, KEEP_ALIVE_INTERVAL, BASE_TOPIC, IDENTIFIER, MODEL, VERSION, WATER_LOW_CM, DISTANCE_SENSOR_ENABLED, WATER_REFILL_AMOUNT, FOOD_INTERVAL_DAYS, FOOD_AMOUNT, FOOD_CHECK_INTERVAL_HOURS, GROW_CHECK_INTERVAL_HOURS, GROW_THIN_DAYS_AFTER_FOOD, GROW_ROOT_FIRST_CHECK_DAYS, GROW_ROOT_CHECK_INTERVAL_DAYS, GROW_TRIM_INTERVAL_DAYS, GROW_HARVEST_FIRST_DAYS, GROW_HARVEST_INTERVAL_DAYS, GROW_TANK_REFRESH_INTERVAL_DAYS, GROW_TANK_REFRESH_WARNING_DAYS, UPPER_CAMERA_DEVICE, LOWER_CAMERA_DEVICE, UPPER_IMAGE_PATH, LOWER_IMAGE_PATH, CAMERA_RESOLUTION, IMAGE_INTERVAL_SECONDS

from gpiozero import Button  # Import gpiozero Button
from gpiozero.pins.pigpio import PiGPIOFactory

from app.sensors.light.light import Light
from app.sensors.pump.pump import Pump
from app.sensors.pcb_temp.pcb_temp import get_pcb_temperature
from app.sensors.temperature.temperature import get_temperature_sensor
from app.sensors.humidity.humidity import get_humidity_sensor
from app.sensors.distance.distance import Distance, MeasurementError

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("gardyn.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console (stdout)
    ]
)

logger = logging.getLogger(__name__)

# set to INFO, for to capture mqtt messages at info-level messages.
logger.setLevel(logging.WARNING)

pin_factory = None
pump = None
light = None
distance_sensor = None
button = None
client = None
capture_lock = threading.Lock()
distance_measure_lock = threading.Lock()

# default on brightness
brightness  = 50
speed       = 100
DEFAULT_BRIGHTNESS = 50
DEFAULT_SPEED = 100
sec_per_min = 60
min_per_hr  = 60

# publish twice an hour
publish_frequency = sec_per_min * min_per_hr / 2

# Variables to track the state of the light and pump
light_state = False
pump_state = False
MAX_PUMP_RUNTIME_SECONDS = 7 * 60
pump_watchdog_timer = None
double_press_time = 1  # Time to detect a double press (in seconds)
press_count = 0
double_press_timer = None
food_last_fed = None
food_last_fed_loaded = threading.Event()
grow_state_loaded = threading.Event()
grow_state = {
    "start_date": None,
    "plant_food_started": None,
    "thinned_at": None,
    "roots_checked_at": None,
    "trimmed_at": None,
    "harvested_at": None,
    "tank_refreshed_at": None,
}
GROW_STATE_TOPICS = {
    "grow/start_date": "start_date",
    "grow/plant_food_started": "plant_food_started",
    "grow/thinned_at": "thinned_at",
    "grow/roots_checked_at": "roots_checked_at",
    "grow/trimmed_at": "trimmed_at",
    "grow/harvested_at": "harvested_at",
    "grow/tank_refreshed_at": "tank_refreshed_at",
}

def get_pin_factory():
    global pin_factory
    if pin_factory is None:
        pin_factory = PiGPIOFactory()
    return pin_factory

def get_pump():
    global pump
    if pump is None:
        pump = Pump(pin_factory=get_pin_factory())
    return pump

def get_light():
    global light
    if light is None:
        light = Light(pin_factory=get_pin_factory())
    return light

def get_distance_sensor():
    global distance_sensor
    if not DISTANCE_SENSOR_ENABLED:
        return None
    if distance_sensor is None:
        distance_sensor = Distance(pin_factory=get_pin_factory())
    return distance_sensor

def configure_button_handlers():
    global button
    if button is None:
        button_pin = 13
        button = Button(button_pin, pin_factory=get_pin_factory(), bounce_time=0.2, hold_time=2)
        button.when_pressed = handle_button_press

def initialize_devices():
    get_pump()
    get_light()
    if DISTANCE_SENSOR_ENABLED:
        get_distance_sensor()
    configure_button_handlers()

# Button press callbacks
def publish_light_state(retain=True):
    if client is None:
        return
    client.publish(BASE_TOPIC + "/light/state", "ON" if light_state else "OFF", retain=retain)
    client.publish(BASE_TOPIC + "/light/brightness/state", str(brightness), retain=retain)

def publish_pump_state(retain=True):
    if client is None:
        return
    client.publish(BASE_TOPIC + "/pump/state", "ON" if pump_state else "OFF", retain=retain)
    client.publish(BASE_TOPIC + "/pump/speed/state", str(speed), retain=retain)

def force_pump_off():
    global pump_state
    logger.warning("Pump watchdog forced pump OFF")
    get_pump().off()
    pump_state = False
    publish_pump_state(retain=True)

def arm_pump_watchdog():
    global pump_watchdog_timer
    if pump_watchdog_timer:
        pump_watchdog_timer.cancel()
    pump_watchdog_timer = Timer(MAX_PUMP_RUNTIME_SECONDS, force_pump_off)
    pump_watchdog_timer.daemon = True
    pump_watchdog_timer.start()

def cancel_pump_watchdog():
    global pump_watchdog_timer
    if pump_watchdog_timer:
        pump_watchdog_timer.cancel()
        pump_watchdog_timer = None

def toggle_light():
    global light_state
    light_state = not light_state
    if light_state:
        logger.info("Toggling Light ON")
        get_light().set_duty_cycle(brightness)
    else:
        logger.info("Toggling Light OFF")
        get_light().off()
    publish_light_state(retain=True)

def toggle_pump():
    global pump_state
    pump_state = not pump_state
    if pump_state:
        logger.info("Toggling Pump ON")
        get_pump().set_speed(speed)
        arm_pump_watchdog()
    else:
        logger.info("Toggling Pump OFF")
        get_pump().off()
        cancel_pump_watchdog()
    publish_pump_state(retain=True)

def handle_button_press():
    global press_count, double_press_timer

    press_count += 1

    if press_count == 1:
        # Start a timer to detect if a second press occurs within the double press time window
        double_press_timer = Timer(double_press_time, handle_single_press)
        double_press_timer.start()
    elif press_count == 2:
        # If a second press occurs, cancel the single press action and trigger the double press action
        if double_press_timer:
            double_press_timer.cancel()
        handle_double_press()
        press_count = 0

def handle_single_press():
    global press_count
    toggle_light()  # Single press toggles the light
    press_count = 0

def handle_double_press():
    toggle_pump()  # Double press toggles the pump

# helpers
def flash_lights(times=3, delay=0.3):
    light_device = get_light()
    original_brightness = light_device.get_brightness()  # Save the brightness (0–100 scale)
    was_on = original_brightness > 0  # If >0%, we consider it "on"

    logger.info(f"Flashing lights {times} times. Original brightness: {original_brightness}%")

    for _ in range(times):
        light_device.off()
        sleep(delay)
        light_device.set_brightness(100)  # Flash full brightness for maximum visibility
        sleep(delay)
    # Restore original state
    if was_on:
        light_device.set_brightness(original_brightness)
    else:
        light_device.off()

def safe_distance_measure():
    if not DISTANCE_SENSOR_ENABLED:
        return None
    global distance_sensor
    if not distance_measure_lock.acquire(blocking=False):
        logger.warning("Distance measure already in progress, skipping request")
        return None
    try:
        return get_distance_sensor().measure_once()
    except MeasurementError as e:
        logger.warning(f"Distance measure failed: {e}, trying recovery")
        try:
            if distance_sensor is not None:
                distance_sensor.cleanup()
            distance_sensor = Distance(pin_factory=get_pin_factory())
            return distance_sensor.measure_once()
        except Exception as e2:
            logger.error(f"Distance full recovery failed: {e2}")
            return None
    finally:
        distance_measure_lock.release()

def parse_percentage(payload, label):
    try:
        value = int(payload)
    except (TypeError, ValueError):
        logger.error(f"Invalid {label} value: {payload}")
        return None
    if not 0 <= value <= 100:
        logger.error(f"{label} must be between 0 and 100: {value}")
        return None
    return value

def publish_water_low_mode(client):
    if DISTANCE_SENSOR_ENABLED and WATER_LOW_CM not in (None, 0):
        mode = "Enabled"
    else:
        mode = "Disabled"
    logger.info(f"Publishing water low mode: {mode}")
    client.publish(BASE_TOPIC + "/water/low/mode", mode, retain=True)

def publish_water_low_threshold(client):
    threshold = WATER_LOW_CM if WATER_LOW_CM is not None else 0
    logger.info(f"Publishing water low threshold: {threshold:.2f}cm")
    client.publish(BASE_TOPIC + "/water/low/cm", f"{threshold:.2f}", retain=True)

def publish_water_measurement(client, distance):
    logger.info(f"Publishing Water Level: {distance:.2f}cm")
    client.publish(BASE_TOPIC + "/water/level", f"{distance:.2f}", retain=True)
    if DISTANCE_SENSOR_ENABLED and WATER_LOW_CM not in (None, 0):
        if distance > WATER_LOW_CM:
            client.publish(BASE_TOPIC + "/water/low/state", "ON", retain=True)
            logger.info(f"Updated water low state to ON (distance {distance:.2f}cm > {WATER_LOW_CM:.2f}cm)")
        else:
            client.publish(BASE_TOPIC + "/water/low/state", "OFF", retain=True)
            logger.info(f"Updated water low state to OFF (distance {distance:.2f}cm <= {WATER_LOW_CM:.2f}cm)")


def update_water_low_state(client):
    if not DISTANCE_SENSOR_ENABLED:
        client.publish(BASE_TOPIC + "/water/low/state", "OFF", retain=True)
        logger.info("Distance sensor disabled, setting water low state to OFF")
        return

    if WATER_LOW_CM not in (None, 0):
        distance = safe_distance_measure()
        if distance is not None:
            publish_water_measurement(client, distance)
        else:
            logger.warning("Could not update water low state because distance reading failed")
    else:
        # If checking is disabled, maybe set it to OFF by default
        client.publish(BASE_TOPIC + "/water/low/state", "OFF", retain=True)
        logger.info("Water low checking disabled, setting water low state to OFF")

def parse_food_timestamp(payload):
    if not payload:
        return None
    try:
        timestamp = payload
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None

def parse_grow_timestamp(payload):
    if not payload:
        return None
    try:
        timestamp = payload
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None

def grow_day(now):
    start_date = grow_state["start_date"]
    if start_date is None:
        return 0
    return max(1, (now.date() - start_date.date()).days + 1)

def is_due_since(timestamp, days, now):
    return timestamp is not None and now - timestamp >= timedelta(days=days)

def grow_task_states(now=None):
    now = now or datetime.now(timezone.utc)
    start_date = grow_state["start_date"]
    plant_food_started = grow_state["plant_food_started"]
    tank_refresh_anchor = grow_state["tank_refreshed_at"] or start_date

    thin_needed = False
    if plant_food_started is not None:
        thin_logged_after_food = (
            grow_state["thinned_at"] is not None
            and grow_state["thinned_at"] >= plant_food_started
        )
        thin_needed = not thin_logged_after_food and is_due_since(
            plant_food_started,
            GROW_THIN_DAYS_AFTER_FOOD,
            now
        )

    roots_anchor = grow_state["roots_checked_at"]
    if roots_anchor is None:
        roots_needed = is_due_since(start_date, GROW_ROOT_FIRST_CHECK_DAYS, now)
    else:
        roots_needed = is_due_since(roots_anchor, GROW_ROOT_CHECK_INTERVAL_DAYS, now)

    trim_anchor = grow_state["trimmed_at"] or start_date
    trim_needed = is_due_since(trim_anchor, GROW_TRIM_INTERVAL_DAYS, now)

    harvest_anchor = grow_state["harvested_at"]
    if harvest_anchor is None:
        harvest_needed = is_due_since(start_date, GROW_HARVEST_FIRST_DAYS, now)
    else:
        harvest_needed = is_due_since(harvest_anchor, GROW_HARVEST_INTERVAL_DAYS, now)

    tank_refresh_needed = False
    tank_refresh_status = "OK"
    if tank_refresh_anchor is not None:
        tank_refresh_due_at = tank_refresh_anchor + timedelta(days=GROW_TANK_REFRESH_INTERVAL_DAYS)
        if now >= tank_refresh_due_at:
            tank_refresh_needed = True
            tank_refresh_status = "DUE"
        elif tank_refresh_due_at - now <= timedelta(days=GROW_TANK_REFRESH_WARNING_DAYS):
            tank_refresh_status = "SOON"

    next_task = "None"
    if start_date is None:
        next_task = "Start grow cycle"
    elif tank_refresh_needed:
        next_task = "Refresh tank"
    elif thin_needed:
        next_task = "Thin sprouts"
    elif roots_needed:
        next_task = "Check roots"
    elif trim_needed:
        next_task = "Trim plants"
    elif harvest_needed:
        next_task = "Harvest"
    elif tank_refresh_status == "SOON":
        next_task = "Refresh tank soon"

    return {
        "day": grow_day(now),
        "thin_needed": thin_needed,
        "roots_check_needed": roots_needed,
        "trim_needed": trim_needed,
        "harvest_needed": harvest_needed,
        "tank_refresh_needed": tank_refresh_needed,
        "tank_refresh_status": tank_refresh_status,
        "next_task": next_task,
    }

def publish_grow_tasks(client):
    states = grow_task_states()
    client.publish(BASE_TOPIC + "/grow/day", str(states["day"]), retain=True)
    client.publish(BASE_TOPIC + "/grow/thin_needed", "ON" if states["thin_needed"] else "OFF", retain=True)
    client.publish(BASE_TOPIC + "/grow/roots_check_needed", "ON" if states["roots_check_needed"] else "OFF", retain=True)
    client.publish(BASE_TOPIC + "/grow/trim_needed", "ON" if states["trim_needed"] else "OFF", retain=True)
    client.publish(BASE_TOPIC + "/grow/harvest_needed", "ON" if states["harvest_needed"] else "OFF", retain=True)
    client.publish(BASE_TOPIC + "/grow/tank_refresh_needed", "ON" if states["tank_refresh_needed"] else "OFF", retain=True)
    client.publish(BASE_TOPIC + "/grow/tank_refresh_status", states["tank_refresh_status"], retain=True)
    client.publish(BASE_TOPIC + "/grow/next_task", states["next_task"], retain=True)
    logger.info(f"Published grow task states: {states}")

def clear_grow_task_logs(client):
    for state_topic, state_key in GROW_STATE_TOPICS.items():
        if state_key == "start_date":
            continue
        grow_state[state_key] = None
        client.publish(BASE_TOPIC + "/" + state_topic, payload=None, retain=True)

def food_needed_state():
    if food_last_fed is None:
        return "ON"
    elapsed_days = (datetime.now(timezone.utc) - food_last_fed).total_seconds() / (24 * 60 * 60)
    return "ON" if elapsed_days >= FOOD_INTERVAL_DAYS else "OFF"

def publish_food_needed_state(client):
    state = food_needed_state()
    client.publish(BASE_TOPIC + "/food/needed", state, retain=True)
    logger.info(f"Published food needed state: {state}")

def publish_static_display_values(client):
    client.publish(BASE_TOPIC + "/water/refill_amount", WATER_REFILL_AMOUNT, retain=True)
    client.publish(BASE_TOPIC + "/food/amount", FOOD_AMOUNT, retain=True)

# https://www.home-assistant.io/integrations/mqtt/#discovery-messages
#  Note: homeassistant/<component>/[<node_id>/]<object_id>/config.
#  User device_class for auto suggestion on HA card picks
def send_discovery_messages(client):
    device_info = {
        "identifiers": [IDENTIFIER],
        "name": BASE_TOPIC,
        "manufacturer": "gardyn-of-eden",
        "model": MODEL,
        "sw_version": VERSION,
    }

    # Config for Light
    TEMP_CONFIG_TOPIC = "homeassistant/light/gardyn/"+IDENTIFIER+"_light/config"
    temp_config_payload = {
        "name": "Light",
        "unique_id": IDENTIFIER + "_light",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/light/state",
        "command_topic": BASE_TOPIC + "/light/command",
        "brightness_state_topic": BASE_TOPIC + "/light/brightness/state",
        "brightness_command_topic": BASE_TOPIC + "/light/brightness/set",
        "brightness_scale": 100,
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    #Config for Pump (as a light with speed control, for example)
    # todo: maybe use fan instead....
    TEMP_CONFIG_TOPIC = "homeassistant/light/gardyn/"+IDENTIFIER+"_pump/config"
    temp_config_payload = {
        "name": "Pump",
        "unique_id": IDENTIFIER + "_pump",
        "platform": "mqtt",
	"device_class": "fan",
        "state_topic": BASE_TOPIC + "/pump/state",
        "command_topic": BASE_TOPIC + "/pump/command",

        "brightness_state_topic": BASE_TOPIC + "/pump/speed/state",
        "brightness_command_topic": BASE_TOPIC + "/pump/speed/set",
        "brightness_scale": 100,

        # if using fan....
	# "percentage_state_topic": BASE_TOPIC + "/pump/speed/state",
	# "percentage_command_topic": BASE_TOPIC + "/pump/speed/set",
	# "speed_range_min": 1,
	# "speed_range_max": 100,
        "icon": "mdi:water-pump",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    #Config for Temperature from PCB
    TEMP_CONFIG_TOPIC = "homeassistant/sensor/gardyn/"+IDENTIFIER+"_pcb_temp/config"
    temp_config_payload = {
        "name": "PCB Temperature",
        "unique_id": IDENTIFIER + "_pcb_temp",
        "state_topic": BASE_TOPIC + "/pcb/temperature",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    #Config for Temperature Sensor
    TEMP_CONFIG_TOPIC = "homeassistant/sensor/gardyn/"+IDENTIFIER+"_temperature/config"
    temp_config_payload = {
        "name": "Temperature",
        "unique_id": IDENTIFIER + "_temperature",
        "state_topic": BASE_TOPIC + "/temperature",
        "command_topic": BASE_TOPIC + "/temperature/get",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    #Config for Humidity Sensor
    TEMP_CONFIG_TOPIC = "homeassistant/sensor/gardyn/"+IDENTIFIER+"_humidity/config"
    temp_config_payload = {
        "name": "Humidity",
        "unique_id": IDENTIFIER + "_humidity",
        "state_topic": BASE_TOPIC + "/humidity",
        "command_topic": BASE_TOPIC + "/humidity/get",
        "unit_of_measurement": "%",
        "device_class": "humidity",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)


    #Config for Water Level Sensor
    TEMP_CONFIG_TOPIC = "homeassistant/sensor/gardyn/"+IDENTIFIER+"_water_level/config"

    temp_config_payload = {
        "name": "Water Level",
        "unique_id": IDENTIFIER + "_water_level",
        "state_topic": BASE_TOPIC + "/water/level",
        "command_topic": BASE_TOPIC + "/water/level/get",
        "unit_of_measurement": "cm",
        "device_class": "distance",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Water Low Binary Sensor
    TEMP_CONFIG_TOPIC = f"homeassistant/binary_sensor/gardyn/{IDENTIFIER}_water_low/config"
    temp_config_payload = {
        "name": "Water Low",
        "unique_id": IDENTIFIER + "_water_low",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/water/low/state",
        "device_class": "problem",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Water Refill Amount
    TEMP_CONFIG_TOPIC = f"homeassistant/sensor/gardyn/{IDENTIFIER}_water_refill_amount/config"
    temp_config_payload = {
        "name": "Water Refill Amount",
        "unique_id": IDENTIFIER + "_water_refill_amount",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/water/refill_amount",
        "icon": "mdi:cup-water",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Food Needed Binary Sensor
    TEMP_CONFIG_TOPIC = f"homeassistant/binary_sensor/gardyn/{IDENTIFIER}_food_needed/config"
    temp_config_payload = {
        "name": "Food Needed",
        "unique_id": IDENTIFIER + "_food_needed",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/food/needed",
        "device_class": "problem",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Last Fed Sensor
    TEMP_CONFIG_TOPIC = f"homeassistant/sensor/gardyn/{IDENTIFIER}_last_fed/config"
    temp_config_payload = {
        "name": "Last Fed",
        "unique_id": IDENTIFIER + "_last_fed",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/food/last_fed",
        "device_class": "timestamp",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Log Feeding Button
    TEMP_CONFIG_TOPIC = f"homeassistant/button/gardyn/{IDENTIFIER}_log_feeding/config"
    temp_config_payload = {
        "name": "Log Feeding",
        "unique_id": IDENTIFIER + "_log_feeding",
        "platform": "mqtt",
        "command_topic": BASE_TOPIC + "/food/last_fed/set",
        "payload_press": "now",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Food Amount Sensor
    TEMP_CONFIG_TOPIC = f"homeassistant/sensor/gardyn/{IDENTIFIER}_food_amount/config"
    temp_config_payload = {
        "name": "Food Amount",
        "unique_id": IDENTIFIER + "_food_amount",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/food/amount",
        "icon": "mdi:food-apple",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    def publish_sensor_config(object_id, name, state_topic, device_class=None, unit=None, icon=None):
        temp_config_topic = f"homeassistant/sensor/gardyn/{IDENTIFIER}_{object_id}/config"
        temp_config_payload = {
            "name": name,
            "unique_id": IDENTIFIER + "_" + object_id,
            "platform": "mqtt",
            "state_topic": BASE_TOPIC + state_topic,
            "device": device_info
        }
        if device_class:
            temp_config_payload["device_class"] = device_class
        if unit:
            temp_config_payload["unit_of_measurement"] = unit
        if icon:
            temp_config_payload["icon"] = icon
        client.publish(temp_config_topic, json.dumps(temp_config_payload), retain=True)

    def publish_binary_sensor_config(object_id, name, state_topic):
        temp_config_topic = f"homeassistant/binary_sensor/gardyn/{IDENTIFIER}_{object_id}/config"
        temp_config_payload = {
            "name": name,
            "unique_id": IDENTIFIER + "_" + object_id,
            "platform": "mqtt",
            "state_topic": BASE_TOPIC + state_topic,
            "device_class": "problem",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": device_info
        }
        client.publish(temp_config_topic, json.dumps(temp_config_payload), retain=True)

    def publish_button_config(object_id, name, command_topic):
        temp_config_topic = f"homeassistant/button/gardyn/{IDENTIFIER}_{object_id}/config"
        temp_config_payload = {
            "name": name,
            "unique_id": IDENTIFIER + "_" + object_id,
            "platform": "mqtt",
            "command_topic": BASE_TOPIC + command_topic,
            "payload_press": "now",
            "device": device_info
        }
        client.publish(temp_config_topic, json.dumps(temp_config_payload), retain=True)

    publish_sensor_config("grow_day", "Grow Day", "/grow/day", unit="d", icon="mdi:sprout")
    publish_sensor_config("grow_next_task", "Next Grow Task", "/grow/next_task", icon="mdi:clipboard-list-outline")
    publish_sensor_config("grow_tank_refresh_status", "Tank Refresh Status", "/grow/tank_refresh_status", icon="mdi:water-sync")

    publish_sensor_config("grow_start_date", "Grow Cycle Start", "/grow/start_date", device_class="timestamp")
    publish_sensor_config("grow_plant_food_started", "Plant Food Started", "/grow/plant_food_started", device_class="timestamp")
    publish_sensor_config("grow_thinned_at", "Last Thinned", "/grow/thinned_at", device_class="timestamp")
    publish_sensor_config("grow_roots_checked_at", "Last Root Check", "/grow/roots_checked_at", device_class="timestamp")
    publish_sensor_config("grow_trimmed_at", "Last Trim", "/grow/trimmed_at", device_class="timestamp")
    publish_sensor_config("grow_harvested_at", "Last Harvest", "/grow/harvested_at", device_class="timestamp")
    publish_sensor_config("grow_tank_refreshed_at", "Last Tank Refresh", "/grow/tank_refreshed_at", device_class="timestamp")

    publish_binary_sensor_config("grow_thin_needed", "Thin Needed", "/grow/thin_needed")
    publish_binary_sensor_config("grow_roots_check_needed", "Roots Check Needed", "/grow/roots_check_needed")
    publish_binary_sensor_config("grow_trim_needed", "Trim Needed", "/grow/trim_needed")
    publish_binary_sensor_config("grow_harvest_needed", "Harvest Needed", "/grow/harvest_needed")
    publish_binary_sensor_config("grow_tank_refresh_needed", "Tank Refresh Needed", "/grow/tank_refresh_needed")

    publish_button_config("grow_start_cycle", "Start Grow Cycle", "/grow/start_date/set")
    publish_button_config("grow_log_plant_food", "Log Plant Food Started", "/grow/plant_food_started/set")
    publish_button_config("grow_log_thinning", "Log Thinning", "/grow/thinned_at/set")
    publish_button_config("grow_log_root_check", "Log Root Check", "/grow/roots_checked_at/set")
    publish_button_config("grow_log_trim", "Log Trim", "/grow/trimmed_at/set")
    publish_button_config("grow_log_harvest", "Log Harvest", "/grow/harvested_at/set")
    publish_button_config("grow_log_tank_refresh", "Log Tank Refresh", "/grow/tank_refreshed_at/set")

    # Config for Water Low Threshold (current value)
        # Config for Water Low CM Set Number
    TEMP_CONFIG_TOPIC = f"homeassistant/number/gardyn/{IDENTIFIER}_water_low_cm/config"
    temp_config_payload = {
        "name": "Set Water Low Threshold",
        "unique_id": IDENTIFIER + "_water_low_cm",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/water/low/cm",
        "command_topic": BASE_TOPIC + "/water/low/cm/set",
        "min": 0,
        "max": 15,
        "step": 0.5,
        "unit_of_measurement": "cm",
        "device_class": "distance",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Config for Water Low Mode (Enabled/Disabled)
    TEMP_CONFIG_TOPIC = f"homeassistant/sensor/gardyn/{IDENTIFIER}_water_low_mode/config"
    temp_config_payload = {
        "name": "Water Low Mode",
        "unique_id": IDENTIFIER + "_water_low_mode",
        "platform": "mqtt",
        "state_topic": BASE_TOPIC + "/water/low/mode",
        "icon": "mdi:toggle-switch",  # Optional: or use mdi:alert for dramatic effect
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Discovery configuration for Camera A (image entity)
    TEMP_CONFIG_TOPIC = "homeassistant/image/gardyn/" + IDENTIFIER + "_upper_camera/config"
    temp_config_payload = {
        "name": "Upper Camera",
        "unique_id": IDENTIFIER + "_upper_camera",
        "image_topic": BASE_TOPIC + "/image/upper_camera",
        "content_type": "image/jpeg",
        "object_id": IDENTIFIER + "_upper_camera",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

    # Discovery configuration for Camera B (image entity)
    TEMP_CONFIG_TOPIC = "homeassistant/image/gardyn/" + IDENTIFIER + "_lower_camera/config"
    temp_config_payload = {
        "name": "Lower Camera",
        "unique_id": IDENTIFIER + "_lower_camera",
        "image_topic": BASE_TOPIC + "/image/lower_camera",
        "content_type": "image/jpeg",
        "object_id": IDENTIFIER + "_lower_camera",
        "device": device_info
    }
    client.publish(TEMP_CONFIG_TOPIC, json.dumps(temp_config_payload), retain=True)

def republish_runtime_state(client):
    publish_light_state(retain=True)
    publish_pump_state(retain=True)
    publish_water_low_mode(client)
    publish_water_low_threshold(client)
    publish_static_display_values(client)

def on_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"Connected with result code {rc}")
    client.subscribe(BASE_TOPIC + "/#")
    client.subscribe("homeassistant/status")
    # client.subscribe(BASE_TOPIC + "/light/brightness/set")
    send_discovery_messages(client)
    republish_runtime_state(client)

def on_message(client, userdata, msg):
    global brightness, speed, WATER_LOW_CM, food_last_fed, light_state, pump_state

    # Handle binary payloads (like image topics) — skip decoding
    if msg.topic.endswith("/image/upper_camera") or msg.topic.endswith("/image/lower_camera"):
        logger.debug(f"Received binary image on topic {msg.topic}, skipping decode.")
        return

    try:
        payload = msg.payload.decode("utf-8").strip()
        logger.debug(f"Decoded payload on {msg.topic}: '{payload}'")
    except UnicodeDecodeError:
        logger.error(f"Failed to decode message on topic {msg.topic}. Likely binary.")
        return

    topic_suffix = msg.topic.replace(BASE_TOPIC + "/", "")

    try:
        if msg.topic == "homeassistant/status" and payload.lower() == "online":
            send_discovery_messages(client)
            republish_runtime_state(client)
            return

        # === Pump Logic ===
        if topic_suffix == "pump/command":
            if payload.upper() == "ON":
                if DISTANCE_SENSOR_ENABLED and WATER_LOW_CM not in (None, 0):
                    distance = safe_distance_measure()
                    if distance is not None and distance > WATER_LOW_CM:
                        logger.warning(f"Water too low ({distance:.2f}cm > {WATER_LOW_CM:.2f}cm), aborting pump")
                        flash_lights()
                        client.publish(BASE_TOPIC + "/water/low/state", "ON", retain=True)
                        return
                    else:
                        client.publish(BASE_TOPIC + "/water/low/state", "OFF", retain=True)
                if speed <= 0:
                    speed = DEFAULT_SPEED
                get_pump().set_speed(speed)
                pump_state = True
                publish_pump_state(retain=True)
                arm_pump_watchdog()
            elif payload.upper() == "OFF":
                get_pump().off()
                pump_state = False
                publish_pump_state(retain=True)
                cancel_pump_watchdog()

        elif topic_suffix == "pump/speed/set":
            parsed_speed = parse_percentage(payload, "pump speed")
            if parsed_speed is None:
                return
            speed = parsed_speed
            if speed == 0:
                get_pump().off()
                pump_state = False
                cancel_pump_watchdog()
            else:
                get_pump().set_speed(speed)
                pump_state = True
                arm_pump_watchdog()
            publish_pump_state(retain=True)

        # === Light Logic ===
        elif topic_suffix == "light/command":
            if payload.upper() == "ON":
                if brightness <= 0:
                    brightness = DEFAULT_BRIGHTNESS
                get_light().set_duty_cycle(brightness)
                light_state = True
                publish_light_state(retain=True)
            elif payload.upper() == "OFF":
                get_light().off()
                light_state = False
                publish_light_state(retain=True)

        elif topic_suffix == "light/brightness/set":
            parsed_brightness = parse_percentage(payload, "light brightness")
            if parsed_brightness is None:
                return
            brightness = parsed_brightness
            if brightness == 0:
                get_light().off()
                light_state = False
            else:
                get_light().set_duty_cycle(brightness)
                light_state = True
            publish_light_state(retain=True)

        # === Water Level ===
        elif topic_suffix == "water/level/get":
            if DISTANCE_SENSOR_ENABLED:
                distance = safe_distance_measure()
                if distance is not None:
                    publish_water_measurement(client, distance)

        elif topic_suffix == "water/low/cm/set":
            try:
                WATER_LOW_CM = float(payload)
                publish_water_low_threshold(client)
                publish_water_low_mode(client)
                update_water_low_state(client)
            except ValueError:
                logger.error(f"Invalid water low cm value: {payload}")

        # === Food Notifications ===
        elif topic_suffix == "food/last_fed":
            parsed = parse_food_timestamp(payload)
            if parsed is None:
                logger.error(f"Invalid retained food last fed timestamp: {payload}")
                return
            food_last_fed = parsed
            food_last_fed_loaded.set()
            publish_food_needed_state(client)

        elif topic_suffix == "food/last_fed/set":
            if payload.lower() == "now":
                food_last_fed = datetime.now(timezone.utc)
            else:
                parsed = parse_food_timestamp(payload)
                if parsed is None:
                    logger.error(f"Invalid food last fed command payload: {payload}")
                    return
                food_last_fed = parsed
            food_last_fed_loaded.set()
            client.publish(BASE_TOPIC + "/food/last_fed", food_last_fed.isoformat(), retain=True)
            publish_food_needed_state(client)

        # === Grow Cycle Tasks ===
        elif topic_suffix in GROW_STATE_TOPICS:
            state_key = GROW_STATE_TOPICS[topic_suffix]
            if payload == "":
                grow_state[state_key] = None
                grow_state_loaded.set()
                publish_grow_tasks(client)
                return
            parsed = parse_grow_timestamp(payload)
            if parsed is None:
                logger.error(f"Invalid retained grow timestamp on {msg.topic}: {payload}")
                return
            grow_state[state_key] = parsed
            grow_state_loaded.set()
            publish_grow_tasks(client)

        elif topic_suffix.endswith("/set") and topic_suffix[:-4] in GROW_STATE_TOPICS:
            state_topic = topic_suffix[:-4]
            state_key = GROW_STATE_TOPICS[state_topic]
            if payload.lower() in ("", "clear", "none"):
                grow_state[state_key] = None
                grow_state_loaded.set()
                client.publish(BASE_TOPIC + "/" + state_topic, payload=None, retain=True)
                publish_grow_tasks(client)
                return
            elif payload.lower() == "now":
                logged_at = datetime.now(timezone.utc)
            else:
                parsed = parse_grow_timestamp(payload)
                if parsed is None:
                    logger.error(f"Invalid grow command payload on {msg.topic}: {payload}")
                    return
                logged_at = parsed
            grow_state[state_key] = logged_at
            grow_state_loaded.set()
            client.publish(BASE_TOPIC + "/" + state_topic, logged_at.isoformat(), retain=True)
            if state_key == "start_date":
                clear_grow_task_logs(client)
            publish_grow_tasks(client)

        # === Sensor Data on Request ===
        elif topic_suffix == "pcb/temperature/get":
            pcb_temp = get_pcb_temperature()
            client.publish(BASE_TOPIC + "/pcb/temperature", f"{pcb_temp:.2f}")

        elif topic_suffix == "temperature/get":
            temperature_sensor = get_temperature_sensor()
            if temperature_sensor is None:
                raise RuntimeError("Temperature sensor is not initialized")
            temperature = temperature_sensor.read()
            client.publish(BASE_TOPIC + "/temperature", f"{temperature:.2f}")

        elif topic_suffix == "humidity/get":
            humidity_sensor = get_humidity_sensor()
            if humidity_sensor is None:
                raise RuntimeError("Humidity sensor is not initialized")
            humidity = humidity_sensor.read()
            client.publish(BASE_TOPIC + "/humidity", f"{humidity:.2f}")

        elif topic_suffix == "image/capture":
            threading.Thread(target=capture_images, args=(client,), daemon=True).start()

    except Exception as e:
        logger.exception(f"Error handling message on topic {msg.topic}: {e}")

def publish_pcb_temperature(client):
    while True:
        try:
            pcb_temp = get_pcb_temperature()
            logger.info(f"Publishing PCB Temperature: {pcb_temp:.2f}°C")
            client.publish(BASE_TOPIC + "/pcb/temperature", f"{pcb_temp:.2f}")
        except Exception as e:
            logger.error(f"Failed to read or publish PCB temperature: {e}")
        sleep(30*60)  # Publish frequency, every x seconds

def publish_temperature(client):
    while True:
        try:
            temperature_sensor = get_temperature_sensor()
            if temperature_sensor is None:
                raise RuntimeError("Temperature sensor is not initialized")
            temperature = temperature_sensor.read()
            logger.info(f"Publishing Temperature: {temperature:.2f}°C")
            client.publish(BASE_TOPIC + "/temperature", f"{temperature:.2f}")
        except Exception as e:
            logger.error(f"Failed to read or publish ambient temperature: {e}")
        sleep(30*60)  # Publish frequency, every x seconds

def publish_humidity(client):
    while True:
        try:
            humidity_sensor = get_humidity_sensor()
            if humidity_sensor is None:
                raise RuntimeError("Humidity sensor is not initialized")
            humidity = humidity_sensor.read()
            logger.info(f"Publishing Humidity: {humidity:.2f}%")
            client.publish(BASE_TOPIC + "/humidity", f"{humidity:.2f}")
        except Exception as e:
            logger.error(f"Failed to read or publish ambient humidity: {e}")
        sleep(30*60)  # Publish frequency, every x seconds

def publish_water_level(client):
    if not DISTANCE_SENSOR_ENABLED:
        return
    while True:
        distance = safe_distance_measure()
        if distance is not None:
            publish_water_measurement(client, distance)
        sleep(30 * 60)

def capture_images(client):
    if not capture_lock.acquire(blocking=False):
        logger.warning("Camera capture already in progress, skipping request")
        return
    try:
        subprocess.check_call([
            'fswebcam', '-d', UPPER_CAMERA_DEVICE, '-r', CAMERA_RESOLUTION,
            '-S', '2', '-F', '2', '--no-banner', UPPER_IMAGE_PATH
        ])
        logger.info(f"Captured image from upper camera ({UPPER_CAMERA_DEVICE})")

        subprocess.check_call([
            'fswebcam', '-d', LOWER_CAMERA_DEVICE, '-r', CAMERA_RESOLUTION,
            '-S', '2', '-F', '2', '--no-banner', LOWER_IMAGE_PATH
        ])
        logger.info(f"Captured image from lower camera ({LOWER_CAMERA_DEVICE})")

        with open(UPPER_IMAGE_PATH, 'rb') as f:
            upper_cam_jpeg_data = f.read()
            client.publish(BASE_TOPIC + "/image/upper_camera", payload=upper_cam_jpeg_data, qos=0, retain=False)
            logger.info("Published image to /image/upper_camera")

        with open(LOWER_IMAGE_PATH, 'rb') as f:
            lower_cam_jpeg_data = f.read()
            client.publish(BASE_TOPIC + "/image/lower_camera", payload=lower_cam_jpeg_data, qos=0, retain=False)
            logger.info("Published image to /image/lower_camera")
    finally:
        capture_lock.release()

def publish_food_needed(client):
    food_last_fed_loaded.wait(timeout=5)
    while True:
        publish_food_needed_state(client)
        sleep(FOOD_CHECK_INTERVAL_HOURS * 60 * 60)

def publish_grow_cycle(client):
    grow_state_loaded.wait(timeout=5)
    while True:
        publish_grow_tasks(client)
        sleep(GROW_CHECK_INTERVAL_HOURS * 60 * 60)

def publish_images(client):
    while True:
        try:
            capture_images(client)

        except subprocess.CalledProcessError as e:
            logger.error(f"Camera capture failed: {e}")
        except Exception as e:
            logger.exception("Unexpected error during image capture/publish")

        sleep(IMAGE_INTERVAL_SECONDS)


if __name__ == "__main__":
    logger.info(f"Connecting to {BROKER} on port {PORT} with keep alive {KEEP_ALIVE_INTERVAL}")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{IDENTIFIER}_mqtt")
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(USERNAME, PASSWORD)
    client.connect(BROKER, PORT, KEEP_ALIVE_INTERVAL)
    initialize_devices()

    pcb_temp_thread = threading.Thread(target=publish_pcb_temperature, args=(client,))
    pcb_temp_thread.daemon = True
    pcb_temp_thread.start()

    temperature_thread = threading.Thread(target=publish_temperature, args=(client,))
    temperature_thread.daemon = True
    temperature_thread.start()

    humidity_thread = threading.Thread(target=publish_humidity, args=(client,))
    humidity_thread.daemon = True
    humidity_thread.start()

    water_level_thread = threading.Thread(target=publish_water_level, args=(client,))
    water_level_thread.daemon = True
    water_level_thread.start()

    food_needed_thread = threading.Thread(target=publish_food_needed, args=(client,))
    food_needed_thread.daemon = True
    food_needed_thread.start()

    grow_cycle_thread = threading.Thread(target=publish_grow_cycle, args=(client,))
    grow_cycle_thread.daemon = True
    grow_cycle_thread.start()

    publish_images_thread = threading.Thread(target=publish_images, args=(client,))
    publish_images_thread.daemon = True
    publish_images_thread.start()

    client.loop_forever()
