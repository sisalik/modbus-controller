from time import time, sleep

from devices import AOut, AIn, DOut, LagDevice, PIDDevice, InputDevice, OutputDevice


"""Any subclass of Routine in this file will be automatically added to the Check Controller as a callable routine."""


class StopException(Exception):
    """Used for stopping the routine from anywhere in the code (instead of a long chain of returns)"""
    pass


class TimeoutException(Exception):
    """Raised when a delay loop times out, waiting for a condition to be met"""
    pass


class NotHealthyException(Exception):
    """Raised when a device is not healthy. For flow control purposes."""
    pass


class Routine(object):
    """A generic routine run on the controller, e.g. a leak check"""

    name = 'Generic'  # Name used for calling the routine externally

    def __init__(self, controller):
        """Call this in every child class, before other initialisation code"""
        self.controller = controller

    def run(self):
        self._running = True
        self._paused = False
        try:
            self._reset()
            self._run()
        except StopException:
            pass
        except Exception as e:
            self.controller.error_message(e)

        # Once self._run returns, the routine has completed or stopped with an exception
        self._reset()
        self.stop()
        self.controller.results_message({}, 'stopped')
        # self.controller.on_plot = None  # TODO: only remove this routine's on_plot method?

        # Remove routine from controller's lists of active routines... not the best way to do this, I know
        try:
            del self.controller.routines[self.name]
        except KeyError:
            pass

    def _run(self):
        """Override this in a child class to give it functionality. Check for self._running every now and then for a stop signal."""
        pass

    def _reset(self):
        """Override this in a child class to give it reset functionality, which is executed before and after a run or a stop."""
        pass

    def on_message(self, args):
        """Override this in a child class to allow it to react to websocket commands while it is running."""
        pass

    @property
    def plot_data(self):
        """Override this in a child class to have it return data that will be plotted in the HMI"""
        return {}

    def safety_check(self):
        """Override this in a child class to check any critical transducers etc."""
        pass

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def pause_loop(self):
        if self._paused:
            self.controller.state_message('paused')
        else:
            return

        while self._paused:
            self.safety_check()
            if not self._running:
                raise StopException
            sleep(0.1)

        self.controller.state_message('resumed')

    def delay(self, seconds):
        start_time = time()
        while time() < start_time + seconds:
            self.safety_check()
            self.pause_loop()  # Pause if requested
            if not self._running:  # Stop the routine if requested
                raise StopException
            sleep(0.1)

    def wait_for(self, condition, timeout=60):
        start_time = time()
        while time() < start_time + timeout:
            if condition():
                return

            self.safety_check()
            self.pause_loop()  # Pause if requested
            if not self._running:  # Stop the routine if requested
                raise StopException
            sleep(0.1)

        raise TimeoutException

    def warning_message(self, msg):
        self.controller.status_message(msg, 'amber')
        self.delay(5)

    def __repr__(self):
        return self.name


class LeakCheck(Routine):
    """Leak check routine"""

    name = 'LEAK'  # Same as in Django model

    def __init__(self, controller, config):
        super(LeakCheck, self).__init__(controller)  # Always call the parent class constructor at the start

        self.config = config  # Test configuration
        self.pressure_delay = 60  # Time to wait for the pressure to stabilise
        self.pressure_error_threshold = 0.02
        self.flow_delay = 120  # Maximum time to wait for the flow rate to stabilise
        self.log_interval_1 = 10  # Log interval for the first part of the check (gradient checks)
        self.log_interval_2 = 20  # Log interval for the second part of the check (recording results)
        self.gradient_threshold = 1.0  # Maximum absolute value of gradient

        # Get devices from parent controller
        devices = controller.devices
        self.all_valves = [devices[tag] for tag in ['Valve 1',
                                                    'Valve 2',
                                                    'Valve 3',
                                                    'Valve 4',
                                                    'Valve 5']]
        self.amb_pressure = devices['Pressure 1']
        self.amb_temperature = devices['Thermocouple']
        self.vent_valve = devices['Valve 5']
        self.flow_valve = devices['Valve 1']
        self.pressure_valve = devices['Valve 3']
        self.pressure_sp = devices['Pressure controller 1.SP']
        self.pressure_pv = devices['Pressure controller 1.PV']
        self.flow_meter = devices['Flow meter 1']

        # Debug mode: overwrite some of the devices with fake ones
        if config['debug']:
            self.pressure_pv = LagDevice('', self.pressure_sp, 2, full_scale=self.pressure_pv.full_scale, noise_amplitude=config['pressureSP'] / 60.0)
            self.flow_meter = LagDevice('', self.pressure_pv, 1.5, 0.95 * float(config['maxLeakage']) / config['pressureSP'], full_scale=self.flow_meter.full_scale, noise_amplitude=config['maxLeakage'] / 60.0)

            self.pressure_delay = 10
            self.flow_delay = 10

    def _reset(self):
        # Set the pressure to zero
        self.pressure_sp.val = 0.0
        sleep(5)

        # Close all valves
        for valve in self.all_valves:
            valve.off()

        # Open the vent valve
        self.vent_valve.on()

        # Disable logging
        self.set_log_intervals(0)

    def _run(self):
        self.controller.status_message('Starting leak check')
        self.pressure_valve.on()
        self.flow_valve.on()
        self.delay(1)
        self.vent_valve.off()

        # Log the pressure and flow rate seconds for calculating statistics
        self.set_log_intervals(self.log_interval_1)

        # Perform health check on devices
        all_healthy = True
        all_healthy &= self.pressure_valve.healthy
        all_healthy &= self.flow_valve.healthy
        all_healthy &= self.pressure_sp.healthy
        all_healthy &= self.pressure_pv.healthy

        if not all_healthy:
            raise Exception('IO fault present. Clear all faults before continuing.')

        self.set_pressure()
        while True:
            self.wait_until_healthy()
            # Wait for the gradient calculation to stabilise and then wait for the flow rate to stabilise - in that order.
            # If either of them returns False, then the flow meter has under- or overranged again. Go back to the start.
            if self.gradient_delay() and self.wait_until_stable():
                break
            else:
                continue

        self.record_results()

    def set_log_intervals(self, value):
        self.pressure_pv.log_length = value
        self.flow_meter.log_length = value
        self.controller.devices['Flow meter 1'].log_length = value  # Configure all of the Flow meter because any one might be used
        self.controller.devices['Flow meter 2'].log_length = value
        self.controller.devices['Flow meter 3'].log_length = value

    def set_pressure(self):
        self.controller.status_message('Setting pressure setpoint')
        self.pressure_sp.val = self.config['pressureSP']
        self.delay(1)
        self.controller.status_message('Waiting for pressure to stabilise')
        print 'Waiting for pressure to stabilise'

        def error_ok():
            error_percentage = abs(self.pressure_pv.val - self.pressure_sp.val) / self.pressure_sp.val
            return error_percentage < self.pressure_error_threshold

        try:
            self.wait_for(error_ok)
        except TimeoutException:
            raise Exception('Unable to achieve pressure setpoint within {} seconds'.format(self.pressure_delay))

    def wait_until_healthy(self):
        self.controller.status_message('Waiting for flow meter to become healthy')
        print 'Waiting for flow meter to become healthy'

        def flow_meter_ok():
            return self.flow_meter.healthy and self.flow_meter.val != 0.0

        try:
            self.wait_for(flow_meter_ok)
        except TimeoutException:
            raise Exception('Flow meter failed to become healthy')

    def gradient_delay(self):
        self.controller.status_message('Calculating flow rate gradient')
        print 'Calculating flow rate gradient'
        # self.delay(self.log_interval_1)

        def flow_meter_ok():
            # Restart the sequence if the flow meter becomes unhealthy again
            if not self.flow_meter.healthy or self.flow_meter.val == 0.0:
                raise NotHealthyException

            return False  # Do not stop the loop until it times out

        try:
            self.wait_for(flow_meter_ok, self.log_interval_1)
        except NotHealthyException:
            return False
        except TimeoutException:
            return True

    def wait_until_stable(self):
        self.controller.status_message('Waiting for flow to stabilise')
        print 'Waiting for flow to stabilise'

        def gradient_ok():
            # Restart the sequence if the flow meter becomes unhealthy again
            if not self.flow_meter.healthy or self.flow_meter.val == 0.0:
                raise NotHealthyException

            gradient = self.flow_meter.log_gradient
            print '\tGradient:', gradient
            return abs(gradient) < self.gradient_threshold

        try:
            self.wait_for(gradient_ok, self.flow_delay)
        except NotHealthyException:
            return False
        except TimeoutException:
            self.warning_message('Warning: unstable flow rate')

        return True

    def record_results(self):
        self.controller.status_message('Recording results')
        self.set_log_intervals(self.log_interval_2)
        self.delay(self.log_interval_2)

        result = {'p': self.pressure_pv.log_average,
                  'm': self.flow_meter.log_average,
                  'pa': self.amb_pressure.val,
                  'ta': self.amb_temperature.val}
        passed = self.flow_meter.val <= self.config['maxLeakage'] and self.flow_meter.healthy  # Measured mass flow below USL
        if passed:
            self.controller.results_message(result, 'passed')
        else:
            self.controller.results_message(result, 'failed')

    @property
    def plot_data(self):
        t = int(time() * 1000)  # Unix timestamp in milliseconds
        m = self.flow_meter.val_status
        p1 = self.controller.devices['Pressure controller 3.PV'].val_status
        p2 = self.pressure_pv.val_status

        # Also use this loop to calculate the software device values
        if self.config['refPressure']:
            self.pressure_cv.calc()
            self.pressure_pid_out.calc()

        if self.config['debug']:
            self.pressure_pv.calc()
            self.flow_meter.calc()

        return {'t': t, 'm': m, 'p1': p1, 'p2': p2}