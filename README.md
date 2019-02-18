# modbus-controller
A Python controller for Modbus devices. Used as a lightweight PC-based replacement for a PLC system.

Features:
- Reads and writes data to supported Modbus/TCP devices over Ethernet
- User-defined routines that manipulate I/O devices in a programmatic manner
- Web-based user interface with a live data feed via a WebSocket connection
- Only supports Python 2 (for now)

Supports the following hardware:
- Beckhoff BK9000 bus couplers and associated I/O modules
- TE Connectivity NetScanner multi-channel pressure transducers
- Alicat pressure controllers

#### Installation

Install the dependencies using pipenv:

`pipenv install`

Alternatively, use pip to install everything under `[packages]` in `Pipfile`.

#### Usage

If you have your Modbus devices configured in `controller.py`, run modbus_controller by executing:

`python modbus_controller.py`

If you want to use random data for demonstration/development purposes, use:

`python modbus_controller.py simulation`


#### Configuration

Edit line 30 onwards in `controller.py` to configure the Modbus adapters and the devices contained within. Examples have been provided.

To integrate the software into an inspection workflow and support user-defined tests, you may wish to generate the `interface.html` file using a template engine/web framework.