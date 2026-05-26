import time

import pigpio

class MeasurementError(Exception):
    """
    Raised when there's an error in distance measurement.
    """
    def __init__(self, message):
        super().__init__(message)

class Distance:
    """
    Class to handle ultrasonic distance measurements using pigpio timing.

    Attributes:
        trigger_pin (int): GPIO pin used to trigger a measurement.
        echo_pin (int): GPIO pin used to receive the echo pulse.
    """

    def __init__(self, pin_factory=None, trigger_pin=19, echo_pin=26, timeout=0.08):
        """
        Initializes the ultrasonic distance sensor pins.

        Args:
            pin_factory: Accepted for compatibility with callers that share a gpiozero factory.
            trigger_pin (int): GPIO pin used to trigger a measurement.
            echo_pin (int): GPIO pin used to receive the echo pulse.
            timeout (float): Seconds to wait for an echo pulse.

        Raises:
            MeasurementError: If pigpio is unavailable or pins cannot be configured.
        """
        self.pin_factory = pin_factory
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.timeout = timeout
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise MeasurementError("Failed to connect to pigpiod daemon. Ensure it's running.")
        try:
            self.pi.set_mode(self.trigger_pin, pigpio.OUTPUT)
            self.pi.write(self.trigger_pin, 0)
            self.pi.set_mode(self.echo_pin, pigpio.INPUT)
            self.pi.set_pull_up_down(self.echo_pin, pigpio.PUD_DOWN)
        except Exception as e:
            self.pi.stop()
            raise MeasurementError(f"Failed to initialize Distance sensor pins: {e}")

    def measure_once(self):
        """
        Measures the distance once.

        Returns:
            float: The measured distance in centimeters.

        Raises:
            MeasurementError: If the measurement fails.
        """
        pulse = {"rise": None, "fall": None}

        def echo_callback(gpio, level, tick):
            if level == 1:
                pulse["rise"] = tick
            elif level == 0 and pulse["rise"] is not None and pulse["fall"] is None:
                pulse["fall"] = tick

        callback = self.pi.callback(self.echo_pin, pigpio.EITHER_EDGE, echo_callback)
        try:
            self.pi.gpio_trigger(self.trigger_pin, 10, 1)
            deadline = time.monotonic() + self.timeout
            while pulse["fall"] is None and time.monotonic() < deadline:
                time.sleep(0.001)

            if pulse["rise"] is None or pulse["fall"] is None:
                raise MeasurementError(
                    f"No echo received on GPIO{self.echo_pin} after triggering GPIO{self.trigger_pin}"
                )

            pulse_us = pigpio.tickDiff(pulse["rise"], pulse["fall"])
            if pulse_us <= 0:
                raise MeasurementError(f"Invalid echo pulse width: {pulse_us}us")

            distance = pulse_us * 0.0343 / 2
            return round(distance, 2)
        except Exception as e:
            if isinstance(e, MeasurementError):
                raise
            raise MeasurementError(f"Measurement failed: {e}")
        finally:
            callback.cancel()

    def measure(self):
        """
        Measures the distance multiple times and returns the average of the median values.

        Returns:
            float: The average of the median distance measurements in cm.

        Raises:
            MeasurementError: If no successful measurements are obtained.
        """
        measurements = []
        for _ in range(10):
            try:
                measurement = self.measure_once()
                measurements.append(measurement)
            except MeasurementError:
                pass  # Handle individual measurement errors gracefully
        if not measurements:
            raise MeasurementError("No successful measurements")
        median_value = self.median(measurements)
        return round(sum(median_value) / len(median_value), 2)

    def median(self, data):
        """
        Returns the median value from a list of numbers.

        Args:
            data (list): A list of distance measurements.

        Returns:
            list[float]: A list containing the median value.

        Raises:
            MeasurementError: If the data is invalid.
        """
        if not isinstance(data, list) or not data:
            raise MeasurementError("Invalid data for median calculation")
        sorted_data = sorted(data)
        data_length = len(data)
        if data_length % 2 > 0:
            return [sorted_data[data_length // 2]]
        else:
            mid = data_length // 2
            return [(sorted_data[mid - 1] + sorted_data[mid]) / 2]

    def cleanup(self):
        """
        Properly closes the sensor and pin factory connections.
        """
        try:
            if hasattr(self, 'pi') and self.pi and self.pi.connected:
                self.pi.write(self.trigger_pin, 0)
                self.pi.stop()
        except Exception as e:
            print(f"Warning during cleanup: {e}")

    def __enter__(self):
        """
        Context manager entry.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit, ensuring resources are closed.
        """
        self.cleanup()
        return False

if __name__ == "__main__":
    """
    If the module is executed as a standalone script, it will return the distance in a telegraf friendly format.
    """
    distance_instance = None
    try:
        distance_instance = Distance()
        distance = distance_instance.measure()
        print(f"distance, value={distance:.2f}")
    except MeasurementError as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("Script interrupted.")
    finally:
        if distance_instance:
            distance_instance.cleanup()
