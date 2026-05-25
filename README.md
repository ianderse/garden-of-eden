<img src="docs/_banner.svg" width="800px">

# Garden of Eden

Truly own that which is yours!

If you are interested in collaborating please review the [CONTRIBUTORS](CONTRIBUTORS.md) for commit styling guides.

## Video Tutorial for Gardyn of Eden and Homeassistant

Thanks to "Yong" for very well edited video tutorial.

[Video Tutorial](https://www.youtube.com/watch?v=gH5yu8JwS8Y)

## Project Status & Milestones

Work in progress. We should be picking up some steam here to give the DYI community the features you deserve.

[Milestones](https://github.com/iot-root/garden-of-eden/milestones)

![image](https://github.com/user-attachments/assets/403248f5-b7d4-4cb1-921a-0458f515f387)


## Table of Contents

- [Garden of Eden](#garden-of-eden)
  - [Project Status \& Milestones](#project-status--milestones)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
  - [Usage](#usage)
    - [MQTT with HomeAssistant](#mqtt-with-homeassistant)
      - [Home Assistant Dashboard](#home-assistant-dashboard)
      - [Manual MQTT Tests](#manual-mqtt-tests)
    - [Testing](#testing)
    - [Controlling Individual Sensors](#controlling-individual-sensors)
    - [REST API](#rest-api)
      - [Endpoints](#endpoints)
      - [Postman](#postman)
    - [Cron Job](#cron-job)
  - [Hardware Overview](#hardware-overview)
    - [Air Temp \& Humidity Sensor](#air-temp--humidity-sensor)
    - [Pump Power Monitor](#pump-power-monitor)
    - [PCB Temp Sensor](#pcb-temp-sensor)
    - [Lights](#lights)
      - [Method](#method)
      - [Pins](#pins)
    - [Pump](#pump)
      - [Method](#method-1)
      - [Pins](#pins-1)
    - [Camera](#camera)
      - [Method](#method-2)
      - [Devices](#devices)
    - [Water Level Sensor](#water-level-sensor)
      - [Pins](#pins-2)
      - [Method](#method-3)
      - [References](#references)
    - [Momentary Button](#momentary-button)
    - [Electrical Diagrams](#electrical-diagrams)
      - [Sensors](#sensors)
      - [Power and Header](#power-and-header)
    - [Recommendations](#recommendations)
      - [Upgrading the Pi Zero 2](#upgrading-the-pi-zero-2)
  - [Design Decisions](#design-decisions)
    - [Python Version 3.6 \>=](#python-version-36-)
    - [Delays in Reading Temp/Humidity data](#delays-in-reading-temphumidity-data)
    - [GPIO](#gpio)
  - [Folder Structure](#folder-structure)

## Getting Started

### Prerequisites

Start with a clean install of Linux. Use the [RaspberryPi Imager](https://www.raspberrypi.com/software/). Ensure ssh and wifi is setup. Once the image is written, pop the SDcard into the pi and ssh into it.

```bash
# clone repo
git clone git@github.com:iot-root/garden-of-eden.git
cd garden-of-eden 
```

Update the `.env` with mqtt broker info

```
cp .env-dist .env
nano .env
```

Install dependencies, and run services pigpiod, mqtt.service

```
./bin/setup.sh
```

Ensure the pigpiod daemon is running

```
sudo systemctl status pigpiod
sudo systemctl status mqtt.service
```

## Usage

## Quick Toggle Guide

> Ensure your press is quick and within the time frame for the action to register correctly. The press time window can be modified directly in the `mqtt.py` file.

- **One Press** (within 1 second): 
  - **Action**: Toggles the **Lights** on or off. 
  - **Description**: A single, swift press will illuminate or darken your space with ease.

- **Two Presses** (within 1 second): 
  - **Action**: Toggles the **Pump** on or off.
  - **Description**: Need to water the garden or fill up the pool? Double tap for action!


### MQTT with HomeAssistant

This fork is designed to run the Gardyn control service on the Raspberry Pi inside the Gardyn, while Home Assistant and Mosquitto can run on a separate box such as a Beelink.

Recommended layout:

- Gardyn Pi: runs `pigpiod` and `mqtt.service`
- Beelink/Home Assistant: runs the MQTT broker
- Home Assistant: uses MQTT discovery to create the Gardyn entities

On the Gardyn Pi, set `.env` to point at the Home Assistant broker:

```bash
MQTT_BROKER=<home-assistant-or-beelink-ip>
MQTT_PORT=1883
MQTT_USERNAME=gardyn
MQTT_PASSWORD=somepassword
MQTT_BASETOPIC=gardyn
MQTT_IDENTIFIER=gardyn_03
```

On Home Assistant, install or enable the Mosquitto broker add-on, create the `gardyn` MQTT user, then add the MQTT integration under **Settings -> Devices & services -> MQTT**. After `mqtt.service` connects, the device should appear through MQTT discovery.

Restart and watch the Pi service:

```bash
sudo systemctl restart mqtt.service
sudo journalctl -u mqtt.service -f
```

To confirm the Pi is publishing to the broker, run this from any machine with `mosquitto-clients` installed:

```bash
mosquitto_sub -h <home-assistant-or-beelink-ip> -u gardyn -P "somepassword" -t "gardyn/#" -v
```

#### Home Assistant Dashboard

Add a manual Lovelace card and adjust entity IDs to match the entities discovered under **Settings -> Devices & services -> MQTT -> Gardyn**. Home Assistant may suffix entity IDs if names already exist.

```yaml
type: sections
title: Gardyn
sections:
  - type: grid
    cards:
      - type: heading
        heading: Controls
      - type: tile
        entity: light.gardyn_03_light
        name: Light
        features:
          - type: light-brightness
      - type: tile
        entity: light.gardyn_03_pump
        name: Pump
        features:
          - type: light-brightness
      - type: entities
        title: Environment
        entities:
          - entity: sensor.gardyn_03_temperature
            name: Air temperature
          - entity: sensor.gardyn_03_humidity
            name: Humidity
          - entity: sensor.gardyn_03_pcb_temp
            name: PCB temperature

  - type: grid
    cards:
      - type: heading
        heading: Water
      - type: entities
        entities:
          - entity: binary_sensor.gardyn_03_water_low
            name: Water low
          - entity: sensor.gardyn_03_water_level
            name: Water level
          - entity: number.gardyn_03_water_low_cm
            name: Low-water threshold
          - entity: sensor.gardyn_03_water_low_mode
            name: Low-water guard
          - entity: sensor.gardyn_03_water_refill_amount
            name: Refill amount

  - type: grid
    cards:
      - type: heading
        heading: Food
      - type: entities
        entities:
          - entity: binary_sensor.gardyn_03_food_needed
            name: Food needed
          - entity: sensor.gardyn_03_last_fed
            name: Last fed
          - entity: sensor.gardyn_03_food_amount
            name: Food amount
          - entity: button.gardyn_03_log_feeding
            name: Log feeding

  - type: grid
    cards:
      - type: heading
        heading: Grow Cycle
      - type: entities
        entities:
          - entity: sensor.gardyn_03_grow_day
            name: Grow day
          - entity: sensor.gardyn_03_grow_next_task
            name: Next task
          - entity: binary_sensor.gardyn_03_grow_thin_needed
            name: Thin sprouts
          - entity: binary_sensor.gardyn_03_grow_roots_check_needed
            name: Check roots
          - entity: binary_sensor.gardyn_03_grow_trim_needed
            name: Trim plants
          - entity: binary_sensor.gardyn_03_grow_harvest_needed
            name: Harvest
          - entity: binary_sensor.gardyn_03_grow_tank_refresh_needed
            name: Refresh tank
          - entity: sensor.gardyn_03_grow_tank_refresh_status
            name: Tank refresh status
      - type: entities
        title: Log grow tasks
        entities:
          - entity: button.gardyn_03_grow_start_cycle
          - entity: button.gardyn_03_grow_log_plant_food
          - entity: button.gardyn_03_grow_log_thinning
          - entity: button.gardyn_03_grow_log_root_check
          - entity: button.gardyn_03_grow_log_trim
          - entity: button.gardyn_03_grow_log_harvest
          - entity: button.gardyn_03_grow_log_tank_refresh

  - type: grid
    cards:
      - type: heading
        heading: Cameras
      - type: picture-entity
        entity: image.gardyn_03_upper_camera
        name: Upper camera
        show_state: false
      - type: picture-entity
        entity: image.gardyn_03_lower_camera
        name: Lower camera
        show_state: false
```

If the entity IDs differ, open the Gardyn MQTT device in Home Assistant and copy the entity IDs from there. The entity names are stable, but Home Assistant can generate different IDs depending on prior discovery history.

#### Manual MQTT Tests

Light:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/light/command" -m "ON" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/light/brightness/set" -m "70" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/light/command" -m "OFF" -u gardyn -P "somepassword"
```

Pump:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/pump/command" -m "ON" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/pump/speed/set" -m "100" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/pump/command" -m "OFF" -u gardyn -P "somepassword"
```

Water:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/water/level/get" -m "" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/water/low/cm/set" -m "11" -u gardyn -P "somepassword"
mosquitto_sub -h <broker-ip> -t "gardyn/water/#" -v -u gardyn -P "somepassword"
```

Food:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/food/last_fed/set" -m "now" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/food/last_fed/set" -m "2026-05-01T12:00:00-06:00" -u gardyn -P "somepassword"
mosquitto_sub -h <broker-ip> -t "gardyn/food/#" -v -u gardyn -P "somepassword"
```

Grow cycle:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/grow/start_date/set" -m "now" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/grow/plant_food_started/set" -m "now" -u gardyn -P "somepassword"
mosquitto_pub -h <broker-ip> -t "gardyn/grow/roots_checked_at/set" -m "now" -u gardyn -P "somepassword"
mosquitto_sub -h <broker-ip> -t "gardyn/grow/#" -v -u gardyn -P "somepassword"
```

Camera:

```bash
mosquitto_pub -h <broker-ip> -t "gardyn/image/capture" -m "now" -u gardyn -P "somepassword"
mosquitto_sub -h <broker-ip> -t "gardyn/image/#" -v -u gardyn -P "somepassword"
```

### Testing

Activate python venv `source venv/bin/activate`

Start the Flask REST API `python run.py`

Test options:

```bash
# REST endpoints
./bin/api-test.sh

# unit test
python -m unittest -v

# individual tests
python tests/test_distance.py
```

### Controlling Individual Sensors

Activate python venv `source venv/bin/activate`

Examples:

```bash
python app/sensors/distance/distance.py
python app/sensors/humidity/humidity.py
python app/sensors/light/light.py [--on] [--off] [--brightness INT%]
python app/sensors/pcb_temp/pcb_temp.py
python app/sensors/pump/pump.py [--on] [--off] [--speed INT%] [--factory-host STR%] [--factory-port INT%]
python app/sensors/temperature/temperature.py
```

### REST API

Activate python venv `source venv/bin/activate`

Then Run `python run.py`, this will print the ip to send requests.

> **Note:** if run.py errors with: AttributeError: module 'dotenv' has no attribute 'find_dotenv'

```
pip uninstall python-dotenv
python run.py
```

#### Endpoints

```
[GET] http://<pi-ip>:5000/distance

[GET] http://<pi-ip>:5000/humidity

[POST] http://<pi-ip>:5000/light/on
[POST] http://<pi-ip>:5000/light/off
[POST] http://<pi-ip>:5000/light/brightness body:{"value": 50 }
[GET] http://<pi-ip>:5000/light/brightness

[GET] http://<pi-ip>:5000/temperature

[GET] http://<pi-ip>:5000/pcb-temp

[POST] http://<pi-ip>:5000/pump/on
[POST] http://<pi-ip>:5000/pump/off
[POST] http://<pi-ip>:5000/pump/speed body:{"value": 50 }
[GET] http://<pi-ip>:5000/pump/speed
[GET] http://<pi-ip>:5000/pump/stats
```

#### Postman

Export this [Postman collection](https://www.postman.com/orange-shadow-8689/workspace/garden-of-eden/collection/8244324-e9d8f79e-d3f2-423e-b0d1-a4ca5b1b08ca?action=share&creator=8244324&active-environment=8244324-861384b4-b4e3-48a3-8da1-181705bd2d8c), add to your private workspace, add the `pi-ip` env variable and you should be good to go.

### Cron Job

Run `crontab -e`, select your preferred editor and then add the following job. Edit as needed.

> Note: update your paths for the following...

```text
# †urn on lights at 6am, 9am, 5pm, and turn off at 8pm
0 6 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/light/light.py --on --brightness 50
0 9 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/light/light.py --on --brightness 70
0 17 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/light/light.py --on --brightness 50
0 20 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/light/light.py --off

# Pump run at 8am for 5 minutes
0 8 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --on --speed 100
5 8 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --off

# Pump run at 4pm 5 minutes
0 16 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --on --speed 100
5 16 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --off

# Pump run at 9pm for 5 minutes
0 21 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --on --speed 100
5 21 * * * /home/gardyn/projects/garden-of-eden/venv/bin/python /home/gardyn/projects/garden-of-eden/app/sensors/pump/pump.py --off

# Collect sensor data every 30 mins
*/30 * * * * /home/gardyn/projects/garden-of-eden/bin/get-sensor-data.sh
```

## Hardware Overview

Depending on the system you have, here is a breakdown of the hardware.

Notes:

- GPIO num is different than pin number. See (<https://pinout.xyz/>)

### Air Temp & Humidity Sensor

- temp/humidity sensor AM2320 at address of `0x38`

### Pump Power Monitor

- motor power usage sensor INA219 at address of `0x40`

### PCB Temp Sensor

- pcb temp sensor PCT2075 at address `pf 0x48`

When you run `sudo i2cdetect -y 1`, you should see something like:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- 38 -- -- -- -- -- -- --
40: 40 -- -- -- -- -- -- -- 48 -- -- -- -- -- -- --
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
70: -- -- -- -- -- -- -- --
```

### Lights

LED full spectrum lights.

#### Method

- Lights are driven by PWM duty and a frequency of 8 kHz.

#### Pins

- [GPIO-18 | PIN-12](https://pinout.xyz/pinout/pin12_gpio18/)

### Pump

#### Method

- The pump is driven by PWM with max duty of 30% and frequency of 50 Hz
- There is a current sensor to measure pump draw and a overtemp sensor to determine if board monitor PCB temp.

#### Pins

- [GPIO-24 | PIN-18](https://pinout.xyz/pinout/pin18_gpio24/)

Notes:

- Pump duty cycle is limited, likely full on is too much current draw for the system.

### Camera

Two USB cameras.

#### Method

- image capture with fswebcam

#### Devices

- /dev/video0
- /dev/video1

### Water Level Sensor

Uses the ultrasonic distance sensor DYP-A01-V2.0.

#### Pins

- [GPIO-19 | PIN-35](https://pinout.xyz/pinout/pin35_gpio19/): water level in (trigger)
- [GPIO-26 | PIN-37](https://pinout.xyz/pinout/pin37_gpio26/): water level out (echo)

#### Method

- Uses time between the echo and response to deterine the distances.

#### References

- <https://www.google.com/search?q=DYP-A01-V2.0>
- <https://www.dypcn.com/uploads/A02-Datasheet.pdf>

### Momentary Button

`<section incomplete>`

### Electrical Diagrams

Incase you need to troubleshoot any problems with your system.

#### Sensors

<img src="docs/pcb1.png" width="800px">

#### Power and Header

<img src="docs/pcb2.png" width="800px">

### Recommendations

#### Upgrading the Pi Zero 2

For better performance, the Pi Zero can be replaced with a Pi Zero 2. This will enable the use of VS Code Remote Server to edit files and debug the python code remotely. The VS Code remote server uses OpenSSH and the minimum architecture is ARMv7.

> Buy one **without** a header, you will need to solder one on in the opposite direction.

## Design Decisions

### Python Version 3.6 >=

Minimum python version of 3.6 to support `printf()`

### Delays in Reading Temp/Humidity data

Reading sensor values  with inherently long delays and responding to the REST API. To minimize the delay in subsequent readings the value is cached and given if another read occurs within two seconds.

### GPIO

Using `gpiozero` to leverage `pigpio` daemon which is hardware driven and more efficient.This ensures better accuracy of the distance sensor and is less cpu intensive when using PWMs.

## Folder Structure

```text
<gardyn-of-eden>
├── run.py
├── app
│   ├── __init__.py
│   └── sensors
│       ├── config.py
│       ├── distance
│       │   ├── distance.py
│       │   ├── __init__.py
│       │   └── routes.py
│       ├── __init__.py
│       ├── light
│       │   ├── __init__.py
│       │   ├── light.py
│       │   └── routes.py
│       └── pump
│           ├── __init__.py
│           ├── pump.py
│           └── routes.py
└── tests
    ├── __init__.py
    ├── test_distance.py
    ├── test_light.py
    └── test_pump.py
```
