import unittest
from unittest.mock import patch, Mock
import sys
import os
# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.sensors.distance.distance import Distance, MeasurementError

class TestDistance(unittest.TestCase):

    @patch('app.sensors.distance.distance.pigpio.pi')
    def setUp(self, MockPi):
        self.mock_pi = MockPi.return_value
        self.mock_pi.connected = True
        self.mock_callback = Mock()
        self.mock_pi.callback.return_value = self.mock_callback

        def trigger_echo(trigger_pin, pulse_len, level):
            echo_callback = self.mock_pi.callback.call_args.args[2]
            echo_callback(26, 1, 1000)
            echo_callback(26, 0, 3915)

        self.mock_pi.gpio_trigger.side_effect = trigger_echo
        self.distance = Distance()

    def assertAlmostEqual(self, a, b, places=5):
        # An epsilon check for floating-point comparisons
        self.assertTrue(abs(a-b) < 10**(-places))

    def test_measure_once(self):
        measured_distance = self.distance.measure_once()
        self.assertEqual(measured_distance, 49.99)

    def test_uses_documented_gpio_pins(self):
        self.mock_pi.set_mode.assert_any_call(19, 1)
        self.mock_pi.set_mode.assert_any_call(26, 0)
        self.mock_pi.set_pull_up_down.assert_called_with(26, 1)

    def test_median_odd_length(self):
        data = [1, 2, 3, 4, 5]
        median_value = self.distance.median(data)
        self.assertEqual(median_value, [3])

    def test_median_even_length(self):
        data = [1, 2, 3, 4, 5, 6]
        median_value = self.distance.median(data)
        self.assertEqual(median_value, [3.5])

    def test_median_with_empty_data(self):
        with self.assertRaises(MeasurementError):
            self.distance.median([])

    def test_median_with_non_list(self):
        with self.assertRaises(MeasurementError):
            self.distance.median("string")

    @patch('app.sensors.distance.distance.Distance.measure_once', autospec=True) 
    def test_measure(self, mock_measure_once):
        mock_measure_once.side_effect = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        measured_distance = self.distance.measure()
        self.assertAlmostEqual(measured_distance, 55.00)

    @patch('app.sensors.distance.distance.pigpio.pi')
    def test_cleanup_does_not_close_injected_pin_factory(self, MockPi):
        MockPi.return_value.connected = True
        pin_factory = Mock()
        distance = Distance(pin_factory=pin_factory)
        distance.cleanup()
        pin_factory.close.assert_not_called()

    @patch('app.sensors.distance.distance.pigpio.pi')
    def test_cleanup_stops_pigpio_connection(self, MockPi):
        MockPi.return_value.connected = True
        distance = Distance()
        distance.cleanup()
        MockPi.return_value.stop.assert_called_once()

    @patch('app.sensors.distance.distance.pigpio.pi')
    def test_measure_once_raises_when_echo_missing(self, MockPi):
        MockPi.return_value.connected = True
        MockPi.return_value.callback.return_value = Mock()
        distance = Distance(timeout=0)
        with self.assertRaises(MeasurementError):
            distance.measure_once()

if __name__ == "__main__":
    unittest.main()
