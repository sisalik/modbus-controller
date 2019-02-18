from time import time
import struct
import array
import ctypes
from random import uniform


def mean(data):
    """Return the sample arithmetic mean of data."""
    return sum(data) / float(len(data))


def ss(data):
    """Return sum of square deviations of sequence data."""
    c = mean(data)
    ss = sum((x - c) ** 2 for x in data)
    return ss


class Device(object):
    """Generic Modbus/whatever device. Similar to Rockwell's PlantPAx."""

    # Status byte constants
    STATUS_UNDERRANGE = 0x41  # Analogue input underrange (< 4.0 mA)
    STATUS_OVERRANGE = 0x42  # Analogue input overrange (> 20.0 mA)
    STATUS_OC = 0x42  # Open circuit (thermocouple)

    length = 1  # Length of data structure, in bytes

    def __init__(self, tag, address, scale_from=(0, 0x7FFF), scale_to=(4.0, 20.0), full_scale=None, log_length=0):
        self.tag = tag  # Tag name
        self.address = address  # Usually Modbus offset

        self.scale_from = scale_from
        self.scale_to = scale_to
        self.scale_from_span = scale_from[1] - scale_from[0]
        self.scale_to_span = scale_to[1] - scale_to[0]

        if full_scale is None:
            self.full_scale = scale_to[1]
        else:
            self.full_scale = full_scale

        self.status = 0  # Status byte (high word)
        self.raw = 0  # Raw, unscaled value

        self.log_length = log_length
        self.log = []

    @property
    def val(self):
        """Scaled reading of the device"""
        return self.raw

    @val.setter
    def val(self, value):
        self.raw = value

    @property
    def val_status(self):
        """Value which also takes into account the status of the device"""
        if self.status == Device.STATUS_UNDERRANGE:
            return 'UNDER'
        elif self.status == Device.STATUS_OVERRANGE:
            return 'OVER'
        else:
            return self.val

    @property
    def healthy(self):
        return self.status not in [Device.STATUS_UNDERRANGE, Device.STATUS_OVERRANGE]

    def _update_log(self, data):
        # If logging is required, add data to the log
        if self.log_length:
            self.log.append((time(), data))
            # Delete records older than self.log_length
            while self.log[0][0] < time() - self.log_length:
                self.log.pop(0)

    @property
    def log_average(self):
        """Average of log readings"""
        if len(self.log) < 2:
            return self.val

        return mean([l[1] for l in self.log])

    @property
    def log_stddev(self):
        """Calculates the population standard deviation"""
        n = len(self.log)
        if n < 2:
            return 0

        data = [l[1] for l in self.log]
        pvar = ss(data) / float(n)
        return pvar ** 0.5

    @property
    def log_gradient(self):
        """Calculates the difference between the means of two halves of the logged data"""
        n = len(self.log)
        if n < 2:
            return 0

        midpoint = n / 2

        mean_1 = mean([l[1] for l in self.log[:midpoint]])
        mean_2 = mean([l[1] for l in self.log[midpoint:]])
        return mean_2 - mean_1

    def __repr__(self):
        return self.tag


class AIn(Device):
    length = 1
    type_str = 'a-in'

    @property
    def val(self):
        return self.scale_to[0] + (float(self.raw) - self.scale_from[0]) / self.scale_from_span * self.scale_to_span

    @val.setter
    def val(self, value):
        self.raw = value
        self._update_log(self.val)


class AInStatus(AIn):
    """Analogue input with an adjacent status word, as used in Beckhoff modules"""
    length = 2

    @property
    def val(self):
        return self.scale_to[0] + (float(self.raw) - self.scale_from[0]) / self.scale_from_span * self.scale_to_span

    @val.setter
    def val(self, value):
        self.raw = ctypes.c_short(value).value
        self._update_log(self.val)


class AInTC(AIn):
    """Special case for thermocouples"""
    length = 2

    @property
    def val(self):
        return self.raw / 10.0

    @val.setter
    def val(self, value):
        self.raw = value
        self._update_log(self.val)


class AInRaw(AIn):
    """Used for Netscanner pressure transducers. No scaling, data length 1."""
    length = 1

    @property
    def val(self):
        return self.raw

    @val.setter
    def val(self, value):
        self.raw = value
        self._update_log(self.val)


class AInFloat(AIn):
    """32-bit IEEE-754 floating point number, spanning two registers."""
    length = 2

    @property
    def val(self):
        arr = array.array('H', self.raw_array)
        arr.byteswap()
        val_raw = struct.unpack('>f', arr)[0]
        return self.scale_to[0] + (val_raw - self.scale_from[0]) / self.scale_from_span * self.scale_to_span

    @val.setter
    def val(self, value):
        self.raw_array = value
        self._update_log(self.val)

    @property
    def raw(self):
        """A method to return a numeric value for the raw data array"""
        return self.val

    @raw.setter
    def raw(self, value):
        pass


class AOut(Device):
    length = 1
    type_str = 'a-out'

    @property
    def val(self):
        return self.scale_to[0] + (float(self.raw) - self.scale_from[0]) / self.scale_from_span * self.scale_to_span

    @val.setter
    def val(self, value):
        self.raw = int(self.scale_from[0] + (float(value) - self.scale_to[0]) / self.scale_to_span * self.scale_from_span)
        # print '{} set to {}'.format(self.tag, self.raw)


class AOutStatus(AOut):
    """Analogue output with an adjacent status word, as used in Beckhoff modules"""
    length = 2


class AOutFloat(AOut):
    """32-bit IEEE-754 floating point number, spanning two registers."""
    length = 2

    def __init__(self, *args, **kwargs):
        super(AOutFloat, self).__init__(*args, **kwargs)
        self.val = 0

    @property
    def val(self):
        arr = array.array('H', self.raw_array)
        arr.byteswap()
        val_raw = struct.unpack('>f', arr)[0]
        return self.scale_to[0] + (val_raw - self.scale_from[0]) / self.scale_from_span * self.scale_to_span

    @val.setter
    def val(self, value):
        val_scaled = self.scale_from[0] + (float(value) - self.scale_to[0]) / self.scale_to_span * self.scale_from_span
        arr = array.array('H', struct.pack('>f', val_scaled))
        arr.byteswap()
        self.raw_array = arr

    @property
    def raw(self):
        """A method to return a numeric value for the raw data array"""
        return self.val

    @raw.setter
    def raw(self, value):
        pass


class DIn(Device):
    length = 1
    type_str = 'd-in'

    @property
    def val(self):
        return self.raw

    @val.setter
    def val(self, value):
        self.raw = value
        self._update_log(self.val)


class DOut(Device):
    length = 1
    type_str = 'd-out'

    @property
    def val(self):
        return self.raw

    @val.setter
    def val(self, value):
        self.raw = int(value)

    def on(self):
        """Turn on a digital input"""
        self.val = 1

    def off(self):
        """Turn off a digital input"""
        self.val = 0


# Software/simulated devices

class InputDevice(Device):
    """Acts as a buffer for user-entered data"""

    type_str = 'a-out'

    def __init__(self, tag):
        self.tag = tag
        self.status = 0
        self.raw = 0
        self.val = 0

        self.log_length = 0
        self.log = []

    def calc(self):
        self.raw = self.val


class OutputDevice(Device):
    """Pipes data from one device into another"""

    type_str = ''  # No need to show this in the device menu

    def __init__(self, tag, input_device, output_device):
        self.tag = tag
        self.input_device = input_device
        self.output_device = output_device
        self.status = 0
        self.raw = 0
        self.val = 0

        self.log_length = 0
        self.log = []

    def calc(self):
        if not self.input_device or not self.output_device:
            return

        self.val = self.input_device.val
        self.output_device.val = self.val
        self.raw = self.val


class GainDevice(Device):
    """Takes a signal from its input device and outputs an amplified signal"""

    type_str = 'a-in'

    def __init__(self, tag, input_device, gain=1, noise_amplitude=0, full_scale=1, log_length=0):
        self.tag = tag
        self.input_device = input_device
        self.gain = gain
        self.noise_amplitude = noise_amplitude
        self.full_scale = full_scale

        self.output_buffer = 0
        self.output = 0
        self.status = 0
        self.raw = 0
        self.val = 0

        self.log_length = log_length
        self.log = []

    def calc(self):
        self.raw = self.gain * self.input_device.val
        self.val = self.raw + uniform(-self.noise_amplitude, self.noise_amplitude)


class RampDevice(Device):
    """Takes a signal from its input device and outputs a rate-limited signal"""

    type_str = 'a-in'

    def __init__(self, tag, input_device, ramp_rate, full_scale=1, log_length=0):
        self.tag = tag
        self.input_device = input_device
        self.ramp_rate = ramp_rate
        self.full_scale = full_scale

        self.output = 0
        self.status = 0
        self.raw = 0
        self.val = 0
        self.prev_t = time()

        self.log_length = log_length
        self.log = []

    def calc(self):
        # Calculate the time step
        t = time()
        time_step = t - self.prev_t
        self.prev_t = t

        # Calculate the output signal
        if self.output < self.input_device.val:
            self.output += self.ramp_rate * time_step
            if self.output > self.input_device.val:
                self.output = self.input_device.val
        elif self.output > self.input_device.val:
            self.output -= self.ramp_rate * time_step
            if self.output < self.input_device.val:
                self.output = self.input_device.val

        self.raw = self.output
        self.val = self.output
        self._update_log(self.output)


class LagDevice(Device):
    """Takes a signal from its input device and outputs a filtered signal"""

    type_str = 'a-in'

    def __init__(self, tag, input_device, time_constant, gain=1, noise_amplitude=0, full_scale=1, log_length=0):
        self.tag = tag
        self.input_device = input_device
        self.time_constant = time_constant
        self.gain = gain
        self.noise_amplitude = noise_amplitude
        self.full_scale = full_scale

        self.output_buffer = 0
        self.output = 0
        self.raw = 0
        self.val = 0
        self.prev_t = time()

        self.status = 0
        self.log_length = log_length
        self.log = []

    def calc(self):
        # Calculate the time step
        t = time()
        time_step = t - self.prev_t
        self.prev_t = t

        # Calculate the output signal
        error = self.input_device.val - self.output_buffer
        self.output_buffer += error * time_step / self.time_constant
        self.output = self.gain * self.output_buffer
        self.raw = self.output

        # Add noise if necessary
        if self.noise_amplitude:
            self.output += uniform(-self.noise_amplitude, self.noise_amplitude)

        self.val = self.output
        self._update_log(self.output)


class PIDDevice(Device):
    """Outputs a control signal to bring an process (PV) device closer to a setpoint (SP) device"""

    type_str = 'a-in'

    def __init__(self, tag, pv_device, sp_device, p, t_i, t_d, min_cv=None, max_cv=None):
        self.tag = tag
        self.pv_device = pv_device
        self.sp_device = sp_device
        self.p = p  # Proportional gain
        self.t_i = t_i  # Integral time (s)
        self.t_d = t_d  # Derivative time (s)
        self.min_cv = min_cv
        self.max_cv = max_cv

        self.prev_t = time()  # Time of the previous iteration
        self.cv_1 = 0  # Output signal (CV) from the previous iteration
        self.e_1 = 0  # Error (SP - PV) from the previous iteration
        self.e_2 = 0  # Error (SP - PV) from the iteration before that

        self.status = 0
        self.raw = 0
        self.val = 0
        self.log_length = 0
        self.log = []

    def calc(self):
        if not self.pv_device or not self.sp_device:
            return

        # Calculate the error and time step
        e = self.sp_device.val - self.pv_device.val
        t = time()
        time_step = t - self.prev_t
        if time_step == 0.0:
            return self.cv_1

        self.prev_t = t

        # Calculate the output signal (based on http://folk.ntnu.no/skoge/prosessregulering/lectures/SiS7PID%20controller.pdf)
        cv = self.cv_1 + self.p * ((e - self.e_1) +
                                   time_step / self.t_i * e +
                                   self.t_d / time_step * (e - 2 * self.e_1 + self.e_2))

        # CV clamping
        if self.min_cv is not None and cv < self.min_cv:
            cv = self.min_cv
        elif self.max_cv is not None and cv > self.max_cv:
            cv = self.max_cv

        # Update previous iteration values
        self.e_2 = self.e_1
        self.e_1 = e
        self.cv_1 = cv
        self.raw = cv
        self.val = cv
