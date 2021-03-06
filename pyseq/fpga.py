#!/usr/bin/python
"""Illumina HiSeq 2500 System :: FPGA
The FPGA arms triggers for the TDI cameras.
The FPGA also controls the z stage, the objective stage, and the optics.

Commands from www.hackteria.org/wiki/HiSeq2000_-_Next_Level_Hacking

Examples:
    #Create FPGA object
    >>>import pyseq
    >>>fpga = pyseq.fpga.FPGA('COM12','COM15')
    #Initialize FPGA
    >>>fpga.initialize()
    # Read write encoder position (to sync with y stage).
    >>>fpga.read_position()
    >>>0
    >>>fpga.write_position(0)
    # Arm y stage triggers for TDI imgaging.
    >>>fpga.TDIYPOS(3000000)
    >>>fpga.TDIYPOS3(4096,3000000)

Kunal Pandit 9/19
"""


import serial
import io
import time


# FPGA object

class FPGA():
    """HiSeq 2500 System :: FPGA"""

    def __init__(self, com_port_command, com_port_response, baudrate = 115200, logger = None):
        """The constructor for the FPGA.

           Parameters:
           com_port_command (str): The communication port to send FPGA commands.
           com_port_response (str): The communication port to receive FPGA
                responses.
           baudrate (int, optional): The communication speed in symbols per
                second.
           logger (log, optional): The log file to write communication with the
                FPGA.

           Returns:
           fpga object: A fpga object to control the FPGA.
        """

        # Open Serial Port
        s_command = serial.Serial(com_port_command, baudrate, timeout = 1)
        s_response = serial.Serial(com_port_response, baudrate, timeout = 1)

        # Text wrapper around serial port
        self.serial_port = io.TextIOWrapper(io.BufferedRWPair(s_response,s_command),
                                            encoding = 'ascii',
                                            errors = 'ignore')
        self.suffix = '\n'
        self.y_offset = 7000000
        self.logger = logger


    def initialize(self):
        """Initialize the FPGA."""

        response = self.command('RESET')                                # Initialize FPGA
        self.command('EX1HM')                                           # Home excitation filter
        self.command('EX2HM')                                           # Home excitation filter
        self.command('EM2I')                                            # Move emission filter into light path
        self.command('SWLSRSHUT 0')                                     # Shutter lasers


    def command(self, text):
        """Send commands to the FPGA and return the response.

           Parameters:
           text (str): A command to send to the FPGA.

           Returns:
           str: The response from the FPGA.
        """

        text = text + self.suffix
        self.serial_port.write(text)                                    # Write to serial port
        self.serial_port.flush()                                        # Flush serial port
        response = self.serial_port.readline()
        if self.logger is not None:
            self.logger.info('FPGA::txmt::'+text)
            self.logger.info('FPGA::rcvd::'+response)

        return  response


    def read_position(self):
        """Read the y position of the encoder for TDI imaging.

           Returns:
           int: The y position of the encoder.
        """
        tdi_pos = self.command('TDIYERD')
        tdi_pos = tdi_pos.split(' ')[1]
        tdi_pos = int(tdi_pos[0:-1]) - self.y_offset
        return tdi_pos


    def write_position(self, position):
        """Write the position of the y stage to the encoder.

           Parameters:
           position (int) = The position of the y stage.

           TODO:
           * Confirm the position is written correctly.
        """
        position = position + self.y_offset
        while abs(self.read_position() + self.y_offset - position) > 5:
            self.command('TDIYEWR ' + str(position))
            time.sleep(1)


    def TDIYPOS(self, y_pos):
        """Set the y position for TDI imaging.

           Parameters:
           y_pos (int): The initial y position of the image.
        """
        self.command('TDIYPOS ' + str(y_pos+self.y_offset-80000))


    def TDIYARM3(self, n_triggers, y_pos):
        """Arm the y stage triggers for TDI imaging.

           Parameters:
           y_pos (int) = The initial y position of the image.
        """
        self.command('TDIYARM3 ' + str(n_triggers) + ' ' +
                  str(y_pos + self.y_offset-10000) + ' 1')
