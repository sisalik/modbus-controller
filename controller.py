import json
import thread
import urllib2

import routines
from devices import DIn, DOut
from devices import AIn, AInStatus, AInFloat
from devices import AOut, AOutStatus, AOutFloat
from devices import InputDevice, LagDevice, RampDevice, PIDDevice, OutputDevice
from adapters import Beckhoff, Netscanner, Alicat, SimulationAdapter, SoftwareAdapter
from adapters import ConnectionError


class Controller(object):
    """Modbus device controller. Executes routines and reads/writes IO devices."""
    def __init__(self, simulation=False, new_thread=True):
        self.simulation = simulation  # Simulation mode - randomly generated data
        self.new_thread = new_thread  # Whether to start a new thread for the main loop

        self.routine_classes = {}  # Classes of available routines (key: name, value: class)
        self.routines = {}  # Running routines (key: name, value: Routine object)
        self.devices = {}  # Dictionary of all devices (key: tag name, value: Device object)
        self.adapters = []  # List of IO adapters to be scanned in the main loop
        self.clients = []  # List of Websocket clients

        # E-stop relay status indication flags
        self.estop_status = True  # True = not triggered
        self.estop_prev_status = self.estop_status  # Used for detecting state changes

        ############ EDIT THE LINES BELOW TO CONFIGURE THE IO TREE ############
        beckhoff = Beckhoff('192.168.100.20')
        beckhoff.add_device(DOut('Valve 1', 0))
        beckhoff.add_device(DOut('Valve 2', 1))
        beckhoff.add_device(DOut('Valve 3', 2))
        beckhoff.add_device(DOut('Valve 4', 3))
        beckhoff.add_device(DOut('Valve 5', 4))
        beckhoff.add_device(DIn('E-stop', 0))  # E-stop status

        beckhoff.add_device(AInStatus('Pressure 1', 0, scale_to=(0.0, 1.2)))
        beckhoff.add_device(AInStatus('Pressure 2', 2, scale_from=(4609, 23960), scale_to=(972.0, 5040.0)))
        beckhoff.add_device(AInStatus('Flow meter 1', 4, scale_to=(0.0, 100.0), full_scale=100.0))
        beckhoff.add_device(AInStatus('Flow meter 2', 6, scale_to=(0.0, 1000.0), full_scale=1000.0))
        beckhoff.add_device(AInStatus('Flow meter 3', 8, scale_to=(0.0, 10000.0), full_scale=10000.0))
        beckhoff.add_device(AInStatus('Flow controller 1.PV', 10, scale_from=(0, 24686), scale_to=(0, 27.1800), full_scale=35.9745))
        beckhoff.add_device(AInStatus('Flow controller 2.PV', 12, scale_from=(0, 30207), scale_to=(0, 2.6666), full_scale=2.8004))
        beckhoff.add_device(AInStatus('Flow controller 3.PV', 14, scale_from=(0, 32703), scale_to=(0, 1.0991), full_scale=1.0771))

        beckhoff.add_device(AOutStatus('Flow controller 1.SP', 2080, scale_from=(0, 24576), scale_to=(0, 27.1800)))
        beckhoff.add_device(AOutStatus('Flow controller 2.SP', 2082, scale_from=(0, 30000), scale_to=(0, 2.6666)))
        beckhoff.add_device(AOutStatus('Flow controller 3.SP', 2084, scale_from=(0, 32600), scale_to=(0, 1.0991)))

        beckhoff.add_device(AInStatus('Thermocouple', 40, scale_from=(0, 10), scale_to=(0, 1)))
        self._add_adapter(beckhoff)

        netscanner = Netscanner('192.168.100.30')
        netscanner.add_device(AIn('Pressure 1', 0, scale_from=(-1.25, 1000.5), scale_to=(0.0, 1001.0), full_scale=1034.21))
        netscanner.add_device(AIn('Pressure 2', 0, scale_from=(-1.25, 1000.5), scale_to=(0.0, 1001.0), full_scale=1034.21))
        netscanner.add_device(AIn('Pressure 3', 0, scale_from=(-1.25, 1000.5), scale_to=(0.0, 1001.0), full_scale=1034.21))
        netscanner.add_device(AIn('Pressure 4', 0, scale_from=(-1.25, 1000.5), scale_to=(0.0, 1001.0), full_scale=1034.21))
        netscanner.add_device(AIn('Pressure 5', 0, scale_from=(-1.25, 1000.5), scale_to=(0.0, 1001.0), full_scale=1034.21))
        self._add_adapter(netscanner)

        alicat1 = Alicat('192.168.100.40')
        alicat1.add_device(AInFloat('Pressure controller 1.PV', 1202, scale_from=(0, 4.98), scale_to=(0, 4.98), full_scale=4.98))
        alicat1.add_device(AOutFloat('Pressure controller 1.SP', 1009, scale_from=(0, 4.98), scale_to=(0, 4.98), full_scale=4.98))
        self._add_adapter(alicat1)

        alicat2 = Alicat('192.168.100.41')
        alicat2.add_device(AInFloat('Pressure controller 2.PV', 1202, scale_from=(0, 69.0), scale_to=(0, 69.0), full_scale=69.0))
        alicat2.add_device(AOutFloat('Pressure controller 2.SP', 1009, scale_from=(0, 69.0), scale_to=(0, 69.0), full_scale=69.0))
        self._add_adapter(alicat2)

        alicat3 = Alicat('192.168.100.42')
        alicat3.add_device(AInFloat('Pressure controller 3.PV', 1202, scale_from=(0, 345.0), scale_to=(0, 345.0), full_scale=345.0))
        alicat3.add_device(AOutFloat('Pressure controller 3.SP', 1009, scale_from=(0, 345.0), scale_to=(0, 345.0), full_scale=345.0))
        self._add_adapter(alicat3)

        # Add 'software devices', e.g. PID controllers, user input fields, plant models etc.
        software = SoftwareAdapter()
        # software.add_device(InputDevice('Pressure-PID.SP'))
        # software.add_device(PIDDevice('Pressure-PID.CV', None, software.devices['Pressure-PID.SP'], 1, 2, 0, min_cv=0.0, max_cv=10.0))
        # software.add_device(OutputDevice('Pressure-PID.Out', software.devices['Pressure-PID.CV'], None))

        # Additional devices used for development
        if self.simulation:
            self.devices['E-stop'] = DIn(None, None)  # Dummy device; keeps the E-stop input from flickering randomly
            self.devices['E-stop'].val = 1
            # software.add_device(InputDevice('-Test PID SP'))
            # software.add_device(LagDevice('-Test PID PV', None, 5.0))
            # software.add_device(PIDDevice('-Test PID CV', None, None, 1, 1, 0, min_cv=0.0, max_cv=100.0))
            # software.add_device(RampDevice('-Test Ramp', None, 1.0))

            # # Route the data connections between the software devices
            # software.devices['-Test PID PV'].input_device = software.devices['-Test PID CV']
            # software.devices['-Test PID CV'].sp_device = software.devices['-Test PID SP']
            # software.devices['-Test PID CV'].pv_device = software.devices['-Test PID PV']
            # software.devices['-Test Ramp'].input_device = software.devices['-Test PID SP']

        self._add_adapter(software)

        ############ END IO TREE ############

        # Get calibration parameters from the database
        self._get_cal_parameters()

        # Configure routines
        self._add_routines()

    def _add_adapter(self, adapter):
        # If the controller is in simulation mode, replace the adapter with one that generates random readings for its inputs
        if self.simulation and not isinstance(adapter, SoftwareAdapter):
            sim_adapter = SimulationAdapter()
            for device in adapter.devices.values():
                # Create a new, simplified device
                if isinstance(device, DIn):
                    sim_device = DIn(device.tag, device.address, device.scale_from, device.scale_to, device.full_scale, device.log_length)
                elif isinstance(device, DOut):
                    sim_device = DOut(device.tag, device.address, device.scale_from, device.scale_to, device.full_scale, device.log_length)
                elif isinstance(device, AIn):
                    sim_device = AIn(device.tag, device.address, device.scale_from, device.scale_to, device.full_scale, device.log_length)
                elif isinstance(device, AOut):
                    sim_device = AOut(device.tag, device.address, device.scale_from, device.scale_to, device.full_scale, device.log_length)
                else:  # E.g. a software device
                    sim_device = device

                sim_adapter.add_device(sim_device)

            adapter = sim_adapter

        adapter.update_io_image()
        self.devices.update(adapter.devices)
        self.adapters.append(adapter)
        if self.simulation and not isinstance(adapter, SoftwareAdapter):
            print 'Simulated IO adapter:'
        else:
            print 'Adapter {} at {}:'.format(type(adapter), adapter.ip_address)
        print adapter

    def _get_cal_parameters(self):
        param_url = 'http://localhost:10000/cal_parameters/'
        param_file = 'calibration_parameters.json'

        print 'Reading calibration parameters from the server...'
        try:
            response = urllib2.urlopen(param_url).read()
        except Exception as e:
            print 'Unable to read parameters from server: {}. Using file values.'. format(e)
            with open(param_file) as f:
                response = f.read()

        params = json.loads(response)
        for p in params:
            try:
                device = self.devices[p['tag']]
            except KeyError:
                print "\tDevice '{}' not found".format(p['tag'])
                continue

            device.scale_from = (p['raw_min'], p['raw_max'])
            device.scale_to = (p['scaled_min'], p['scaled_max'])
            device.full_scale = p['full_scale']

        print 'Parameters successfully applied to {} devices'.format(len(params))
        print

    def _add_routines(self):
        # Iterate over all objects in the routines module and register any subclasses of Routine
        print 'Registered routines:'
        for obj in routines.__dict__.values():
            if isinstance(obj, type) and issubclass(obj, routines.Routine):
                self.routine_classes[obj.name] = obj
                print '\t' + obj.name + ' - ' + str(obj)
        print

    def call_routine(self, name, parameters=None):
        RoutineClass = self.routine_classes[name]
        try:
            routine = RoutineClass(self, parameters)
        except Exception as e:
            print 'Error initialising routine {}: {}'.format(name, e)
            self.error_message(e)
            return

        print 'Starting routine', name
        thread.start_new_thread(routine.run, ())
        self.routines[name] = routine

    def stop_routine(self, name):
        self.routines[name].stop()

    def pause_routine(self, name):
        self.routines[name].pause()

    def resume_routine(self, name):
        self.routines[name].resume()

    def status_message(self, msg, colour=None):
        for client in self.clients:
            client.update_status(msg, colour)

    def control_message(self, msg):
        for client in self.clients:
            client.sendMessage(u'control ' + unicode(msg))

    def state_message(self, msg):
        for client in self.clients:
            client.sendMessage(u'state ' + unicode(msg))

    def results_message(self, data, status):
        data['status'] = status
        for client in self.clients:
            client.send_results(data)

    def error_message(self, msg):
        self.results_message({'errorMessage': str(msg)}, 'error')

    def start(self):
        self._running = True
        print 'Connecting to remote devices...'
        for adapter in self.adapters:
            adapter.start()

        print 'Starting main loop'
        if self.new_thread:
            thread.start_new_thread(self._main_loop, ())
        else:
            self._main_loop()

    def stop(self):
        self._running = False
        for adapter in self.adapters:
            adapter.stop()

    def _main_loop(self):
        reset = False  # Restart loop after stopping
        while self._running:
            # Read all inputs
            try:
                for adapter in self.adapters:
                    adapter.read_all()
            except ConnectionError:
                print 'Connection error in main loop. Restarting...'
                reset = True
                break

            # Send E-stop relay status, if it has changed
            self.estop_status = self.devices['E-stop'].val
            if not self.estop_status and self.estop_prev_status:  # Turned on
                self.control_message('estop on')
            elif self.estop_status and not self.estop_prev_status:  # Turned off
                self.control_message('estop off')
            self.estop_prev_status = self.estop_status

            # Send the requested data to each websocket client
            for client in self.clients:
                # Readings from all devices
                if client.stream_enabled:
                    if client.stream_select == client.DATA_RAW:
                        data = {device.tag: device.raw for device in self.devices.values()}
                    elif client.stream_select == client.DATA_AVG:
                        data = {device.tag: device.log_average for device in self.devices.values()}
                    elif client.stream_select == client.DATA_STDDEV:
                        data = {device.tag: device.log_stddev for device in self.devices.values()}
                    else:
                        data = {device.tag: device.val_status for device in self.devices.values()}

                    client.send_data(data)

                # Data to be plotted from each routine
                if client.plot_enabled:
                    for routine in self.routines.values():
                        client.send_plot(routine.plot_data)

            # Write all outputs
            for adapter in self.adapters:
                adapter.write_all()

        if reset:
            self.start()


def main():
    def print_function(text):
        print text

    controller = Controller(simulation=True, new_thread=False)
    controller.on_data = print_function  # Won't work anymore :(
    controller.start()


if __name__ == '__main__':
    main()
