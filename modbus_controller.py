import json
import sys
import time
import traceback

from SimpleWebSocketServer import SimpleWebSocketServer, WebSocket

from controller import Controller
from reloader import Reloader


def register_cmd(cmd_name):
    """Decorator that adds a cmd_name attribute to each method that is a websocket command"""
    def decorator(method):
        method.cmd_name = cmd_name
        return method
    return decorator


def timestamp():
    return time.strftime('%d/%m/%y %H:%M:%S')


def get_traceback(ex):
    _, _, ex_traceback = sys.exc_info()
    tb_lines = traceback.format_exception(ex.__class__, ex, ex_traceback)
    tb_text = ''.join(tb_lines)
    return tb_text


class SocketSession(WebSocket):

    DATA_SCALED = 0
    DATA_RAW = 1
    DATA_AVG = 2
    DATA_STDDEV = 3

    def __init__(self, *args, **kwargs):
        super(SocketSession, self).__init__(*args, **kwargs)
        self.check_status = None

        # These three flags control what data is sent to the browser from the controller
        self.stream_enabled = False
        self.stream_raw = False
        self.plot_enabled = False

    @register_cmd('start-check')
    def start_check(self, args):
        check_config = json.loads(' '.join(args))
        self.plot_enabled = True
        controller.call_routine(check_config['name'], check_config)

    @register_cmd('stop-check')
    def stop_check(self, args):
        controller.stop_routine(args[0])

    @register_cmd('pause-check')
    def pause_check(self, args):
        controller.pause_routine(args[0])

    @register_cmd('resume-check')
    def resume_check(self, args):
        controller.resume_routine(args[0])

    @register_cmd('check-msg')
    def check_msg(self, args):
        """Send a message to all running routines. Used for manually continuing a check, for example."""
        for routine in controller.routines.values():
            routine.on_message(args)

    @register_cmd('time')
    def send_time(self, args=None):
        """Return the current UNIX time in milliseconds"""
        self.sendMessage(u'time ' + str(int(time.time() * 1000)))

    @register_cmd('devices')
    def send_devices(self, args=None):
        """Return a list of devices registered with the controller"""
        data = []
        for tag, device in controller.devices.items():
            data.append({'tag': tag,
                         'type': device.type_str})
        data = sorted(data, key=lambda k: k['tag'])
        self.sendMessage(u'devices ' + json.dumps(data, separators=(',', ':')))

    def send_estop_status(self):
        """Sends the status of the E-stop relay"""
        if not controller.estop_status:
            self.sendMessage(u'control estop on')

    @register_cmd('set')
    def set(self, args):
        """Override a device value from the user interface"""
        value = args[0]
        tag = ' '.join(args[1:])
        controller.devices[tag].val = float(value)

    @register_cmd('start-stream')
    def start_stream(self, args=None):
        self.stream_enabled = True

    @register_cmd('stop-stream')
    def stop_stream(self, args=None):
        self.stream_enabled = False

    @register_cmd('stream-select')
    def stream_select(self, args=None):
        self.stream_select = int(args[0])

        if self.stream_select in [self.DATA_AVG, self.DATA_STDDEV]:
            # Enable 5-second logging for each device
            for device in controller.devices.values():
                device.old_log_length = device.log_length
                device.log_length = 5.0
        else:
            # Revert to previous logging settings
            for device in controller.devices.values():
                try:
                    device.log_length = device.old_log_length
                except AttributeError:
                    device.log_length = 0

    @register_cmd('reload')
    def reload(self, args=None):
        reloader.reload()

    def send_data(self, data):
        self.sendMessage(u'data ' + json.dumps(data, separators=(',', ':')))

    def send_plot(self, data):
        self.sendMessage(u'plot ' + json.dumps(data, separators=(',', ':')))

    def send_results(self, data):
        if data['status'] == 'stopped':
            self.plot_enabled = False
        self.sendMessage(u'results ' + json.dumps(data, separators=(',', ':')))

    def update_status(self, msg, colour=None):
        self.sendMessage(u'status ' + json.dumps({'msg': msg, 'col': colour}))

    def handleMessage(self):
        msg = self.data
        args = msg.split(' ')

        print "[{}] << {}: '{}'".format(timestamp(), self.address[1], msg)

        if args[0] in self.ws_cmds:
            try:
                self.ws_cmds[args[0]](self, args[1:])
            except Exception as e:
                self.send_error('Error: ' + str(e))
                raise

        else:  # Unrecognised command
            self.send_error('Unknown command')

    def handleConnected(self):
        self.send_time()
        self.send_devices()
        self.send_estop_status()
        controller.clients.append(self)
        print '[{}]    {} connected (IP: {}) -- {} active'.format(timestamp(), self.address[1], self.address[0], len(controller.clients))

    def handleClose(self):
        controller.clients.remove(self)
        print '[{}]    {} disconnected (IP: {}) -- {} active'.format(timestamp(), self.address[1], self.address[0], len(controller.clients))

    def send_error(self, message):
        self.sendMessage(u'error ' + message)


# Gather the method cmd_name arguments set by decorators and assemble them into a dictionary
print 'Registered commands:'
SocketSession.ws_cmds = {}
for method in SocketSession.__dict__.values():
    if hasattr(method, 'cmd_name'):
        SocketSession.ws_cmds[method.cmd_name] = method
        print '\t{} - {}'.format(method.cmd_name, method)
print

# Main program. Had to use global scope for the Controller object, sorry :(
start_message = 'Websocket server starting'
simulation = False
reloader = Reloader(['modbus_controller.py', 'controller.py', 'routines.py', 'devices.py', 'adapters.py', 'reloader.py'])

# Command line arguments:
if len(sys.argv) > 1:
    if sys.argv[1] == 'simulation':
        start_message = 'Websocket server starting in simulation mode'
        simulation = True

try:
    controller = Controller(simulation=simulation)
    controller.start()

    print start_message
    ws_server = SimpleWebSocketServer('', 11000, SocketSession)

    # Automatically reload the script if any of the below files are modified
    def before_reload():
        ws_server.close()
        controller.stop()

    reloader.before_reload = before_reload
    ws_server.serveforever()
except KeyboardInterrupt:
    controller.stop()
    print 'Server stopped'
except Exception as e:
    print 'Exception:'
    print get_traceback(e)
    print 'Reloading script...\n'
    time.sleep(5)
    reloader.reload()
