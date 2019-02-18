from time import sleep
import socket
from collections import OrderedDict
from random import uniform, choice

import win_inet_pton  # noqa -- ignore the unused import error
from pyModbusTCP.client import ModbusClient

from devices import DIn, DOut, AIn, AOut


class ConnectionError(Exception):
    """Connection error"""
    pass


class Adapter(object):
    """A generic remote IO rack."""
    def __init__(self, ip_address=None):
        self.ip_address = ip_address

        self.devices = {}  # Dictionary of all devices (key: tag name, value: Device object)
        self.d_ins = {}  # Dictionary of digital input devices (key: address, value: Device object)
        self.d_in_range = [0xFFFF, 0]  # Offset range for digital inputs (min - max)
        self.d_outs = {}
        self.d_out_range = [0xFFFF, 0]
        self.a_ins = {}
        self.a_in_range = [0xFFFF, 0]
        self.a_outs = {}
        self.a_out_range = [0xFFFF, 0]

    def add_device(self, device):
        if isinstance(device, DIn):
            self.d_ins[device.address] = device
        elif isinstance(device, DOut):
            self.d_outs[device.address] = device
        elif isinstance(device, AIn):
            self.a_ins[device.address] = device
        elif isinstance(device, AOut):
            self.a_outs[device.address] = device

        self.devices[device.tag] = device

    def update_io_image(self):
        def adjust_range(io_range, device):
            if device.address < io_range[0]:
                io_range[0] = device.address
            if device.address > io_range[1]:
                io_range[1] = device.address + device.length - 1

        # Convert dictionaries to ordered dictionaries, sorted by device address
        self.d_ins = OrderedDict(sorted(self.d_ins.items()))
        self.d_outs = OrderedDict(sorted(self.d_outs.items()))
        self.a_ins = OrderedDict(sorted(self.a_ins.items()))
        self.a_outs = OrderedDict(sorted(self.a_outs.items()))

        for d in self.d_ins.values():
            adjust_range(self.d_in_range, d)
        for d in self.d_outs.values():
            adjust_range(self.d_out_range, d)
        for d in self.a_ins.values():
            adjust_range(self.a_in_range, d)
        for d in self.a_outs.values():
            adjust_range(self.a_out_range, d)

    def start(self):
        """Start connection/data collection. Override in child class."""
        pass

    def stop(self):
        """Stop connection/data collection. Override in child class."""
        pass

    def read_all(self):
        """Read all devices/addresses associated with the rack. Override in child class."""
        pass

    def write_all(self):
        """Write to all devices/addresses associated with the rack. Override in child class."""
        pass

    def __repr__(self):
        text = ''
        if self.d_ins:
            text += '\tDigital inputs:\t\t' + str(len(self.d_ins)) + '\t' + str(self.d_in_range) + '\n'
        if self.d_outs:
            text += '\tDigital outputs:\t' + str(len(self.d_outs)) + '\t' + str(self.d_out_range) + '\n'
        if self.a_ins:
            text += '\tAnalogue inputs:\t' + str(len(self.a_ins)) + '\t' + str(self.a_in_range) + '\n'
        if self.a_outs:
            text += '\tAnalogue outputs:\t' + str(len(self.a_outs)) + '\t' + str(self.a_out_range) + '\n'

        return text


class SimulationAdapter(Adapter):
    """A virtual rack that generates random data for all its inputs."""
    def __init__(self):
        super(SimulationAdapter, self).__init__()

    def read_all(self):
        if self.d_ins:
            for d in self.d_ins.values():
                d.status = 0  # Healthy
                d.val = choice([0, 1])
        if self.a_ins:
            for d in self.a_ins.values():
                d.status = 0  # Healthy
                d.val = uniform(0, d.full_scale)

        sleep(0.01)  # Don't kill the browser by sending too much data


class SoftwareAdapter(Adapter):
    """A virtual rack that is used for software devices."""
    def __init__(self):
        super(SoftwareAdapter, self).__init__()

    def read_all(self):
        for d in self.devices.values():
            d.calc()
        sleep(0.01)  # Don't kill the browser by sending too much data

    def write_all(self):
        pass


class Beckhoff(Adapter):
    """Beckhoff Modbus/TCP bus coupler (e.g. BK9000)"""
    def __init__(self, ip_address):
        super(Beckhoff, self).__init__(ip_address)
        self.mb_client = ModbusClient(host=ip_address, timeout=5)

    def start(self):
        while True:
            self.mb_client.open()
            if self.mb_client.is_open():
                break

            print 'Unable to connect to Beckhoff rack at {}; retrying...'.format(self.ip_address)
            sleep(1)

    def stop(self):
        self.mb_client.close()

    def read_all(self):
        # print 'Read inputs'
        if self.d_ins:
            data = self.mb_client.read_discrete_inputs(self.d_in_range[0], self.d_in_range[1] - self.d_in_range[0] + 1)
            if not data:
                raise ConnectionError('No data received for DIns')

            i0 = self.d_in_range[0]  # Starting index for looking up values from the data list
            for d in self.d_ins.values():
                d.val = data[d.address - i0]

        if self.a_ins:
            # print '\tRead input registers', self.a_in_range[0], self.a_in_range[1] - self.a_in_range[0] + 1
            data = self.mb_client.read_input_registers(self.a_in_range[0], self.a_in_range[1] - self.a_in_range[0] + 1)
            if not data:
                raise ConnectionError('No data received from AIns')

            i0 = self.a_in_range[0]  # Starting index for looking up values from the data list
            for d in self.a_ins.values():
                d.status = data[d.address - i0]
                d.val = data[d.address - i0 + 1]

    def write_all(self):
        # print 'Write outputs'
        if self.d_outs:
            data = []
            for i in xrange(self.d_out_range[0], self.d_out_range[1] + 1):
                try:
                    data.append(self.d_outs[i].raw)
                except KeyError:
                    data.append(0)  # Default value

            self.mb_client.write_multiple_coils(self.d_out_range[0], data)

        if self.a_outs:
            data = []
            for d in self.a_outs.values():
                data.append(0)
                data.append(d.raw)  # Only write to low words

            self.mb_client.write_multiple_registers(self.a_out_range[0], data)


class Netscanner(Adapter):
    """Netscanner pressure brick"""
    def __init__(self, ip_address):
        super(Netscanner, self).__init__(ip_address)

    def start(self):
        # Generate a list of transducers, sorted by address/offset (descending)
        self.transducers = sorted(self.a_ins.values(), key=lambda d: d.address, reverse=True)

        # Generate the ASCII command
        channel_mask = 0
        for device in self.transducers:
            channel_mask |= 1 << device.address
        self.read_cmd = 'r{:04x}0'.format(channel_mask)

        # Set up and connect to the Netscanner
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)

        while True:
            try:
                self.sock.connect((self.ip_address, 9000))
            except socket.error:
                print 'Unable to connect to Netscanner at {}; retrying...'.format(self.ip_address)
                sleep(1)
            else:
                break

    def stop(self):
        self.sock.close()

    def read_all(self):
        self.sock.send(self.read_cmd)
        try:
            data = self.sock.recv(1024)
        except socket.timeout:
            print 'Unable to read data from Netscanner at {}; retrying...'.format(self.ip_address)
            return
        except socket.error:
            raise ConnectionError('Unable to read data from Netscanner at {}'.format(self.ip_address))

        # Extract transducer readings
        for i, device in enumerate(self.transducers):
            start = i * 12  # Start index
            reading = float(data[start:start + 12]) * 68.947573  # Convert psi to mbar
            device.val = reading


class Alicat(Adapter):
    """Alicat device (e.g. pressure controller) with a Modbus/TCP interface"""
    def __init__(self, ip_address):
        super(Alicat, self).__init__(ip_address)
        self.mb_client = ModbusClient(host=ip_address, timeout=5)

    def start(self):
        while True:
            self.mb_client.open()
            if self.mb_client.is_open():
                break

            print 'Unable to connect to Alicat device at {}; retrying...'.format(self.ip_address)
            sleep(1)

    def stop(self):
        self.mb_client.close()

    def read_all(self):
        if self.a_ins:
            data = self.mb_client.read_input_registers(self.a_in_range[0], self.a_in_range[1] - self.a_in_range[0] + 1)
            if not data:
                raise ConnectionError

            i0 = self.a_in_range[0]  # Starting index for looking up values from the data list
            for d in self.a_ins.values():
                if d.length == 2:
                    d.val = data[d.address - i0:d.address - i0 + 2]
                elif d.length == 1:
                    d.val = data[d.address - i0]

    def write_all(self):
        # print 'Write outputs'
        if self.a_outs:
            data = []
            for d in self.a_outs.values():
                if d.length == 2:
                    data += d.raw_array
                elif d.length == 1:
                    data.append(d.raw_array)

            self.mb_client.write_multiple_registers(self.a_out_range[0], data)
