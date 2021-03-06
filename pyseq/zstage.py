#!/usr/bin/python
"""Illumina HiSeq 2500 System :: Z-STAGE
Uses commands found on  https://www.hackteria.org/wiki/HiSeq2000_-_Next_Level_Hacking#Control_Software

The zstage can be moved up and down by 3 independent tilt motors. Each tilt
motor can from step positions 0 to 25000. Initially, all of the tilt motors
in the zstage are homed to step position 0. Lower step positions are down,
and higher step positions are up. Each tilt motor step is about 1.5 microns.
These motors are not precise and not have great repeatability. They are not
expected to go to the exact step position. Furthermore, they are not
expected to accurately go to the same position over and over again. 

Examples:
    #Create zstage
    >>>import pyseq
    >>>xstage = pyseq.zstage.Zstage('COM10')
    #Initialize zstage
    >>>zstage.initialize()
    #Move all tilt motors on zstage to absolute step position 21000
    >>>zstage.move([21000, 21000, 21000])
    >>>[21000, 21000, 21000]

Kunal Pandit 9/19
"""


import time


class Zstage():
    """Illumina HiSeq 2500 System :: Z-STAGE

       Attributes:
       spum (float): Number of zstage steps per micron.
       position ([int, int, int]): A list with absolute positions of each tilt
            motor in steps.
    """


    def __init__(self, fpga, logger = None):
        """The constructor for the zstage.

           Parameters:
           fpga (fpga object): The Illumina HiSeq 2500 System :: FPGA.
           logger (log, optional): The log file to write communication with the
                zstage to.

           Returns:
           zstage object: A zstage object to control the zstage.
        """

        self.serial_port = fpga
        self.min_z = 0
        self.max_z = 25000
        self.spum = 0.656           #steps per um
        self.suffix = '\n'
        self.position = [0, 0, 0]
        self.motors = ['1','2','3']
        self.logger = logger


    def initialize(self):
        """Initialize the zstage."""

        #Home Motors
        for i in range(3):
            response = self.command('T' + self.motors[i] + 'HM')

        #Wait till they stop
        response = self.check_position()

        # Clear motor count registers
        for i in range(3):
            response = self.command('T' + self.motors[i] + 'CR')

        # Update position
        for i in range(3):
            self.position[i] = int(self.command('T' + self.motors[i]
                + 'RD')[5:])                                                    # Set position


    def command(self, text):
        """Send a serial command to the zstage and return the response.

           Parameters:
           text (str): A command to send to the zstage.

           Returns:
           str: The response from the zstage.
        """

        text = text + self.suffix
        self.serial_port.write(text)                                            # Write to serial port
        self.serial_port.flush()                                                # Flush serial port
        response = self.serial_port.readline()
        if self.logger is not None:
            self.logger.info('Zstage::txmt::'+text)
            self.logger.info('Zstage::rcvd::'+response)

        return  response


    def move(self, position):
        """Move all tilt motors to specified absolute step positions.

           Parameters:
           position ([int, int, int]): List of absolute positions for each tilt
                motor.

           Returns:
           [int, int, int]: List with absolute positions of each tilt motor
                after the move.
        """
        for i in range(3):
            if position[i] <= self.max_z and position[i] >= self.min_z:
                self.command('T' + self.motors[i] + 'MOVETO ' +
                    str(position[i]))                                           # Move Absolute
            else:
                print("ZSTAGE can only move between " + str(self.min_z) +
                    ' and ' + str(self.max_z))

        return self.check_position()                                            # Check position


    # Check if Zstage motors are stopped and return their position
    def check_position(self):
        """Return a list with absolute positions of each tilt motor
                [int, int ,int]."""

        # Get Current position
        old_position = [0,0,0]
        for i in range(3):
            successful = True
            while successful:
                try:
                    old_position[i] = int(self.command('T' + self.motors[i] +
                        'RD')[5:])
                    successful = False
                except:
                    time.sleep(2)


        all_stopped = 0
        while all_stopped != 3:
            all_stopped = 0
            for i in range(3):
                successful = True
                while successful:
                    try:
                        new_position = int(self.command('T' + self.motors[i] +
                            'RD')[5:])                                          # Get current position
                        stopped = new_position == old_position[i]               # Compare old position to new position
                        all_stopped = all_stopped + stopped                     # all_stopped will = 3 if all 3 motors are in position
                        old_position[i] = new_position                          # Save new position
                        successful = False
                    except:
                        time.sleep(2)

        for i in range(3):
            self.position[i] = old_position[i]                                  # Set position

        return self.position                                                    # Return position
