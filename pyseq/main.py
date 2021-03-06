#!/usr/bin/python

import time
import logging
import os
from os.path import join
import sys
import configparser
import threading
import warnings
import argparse

from . import methods
from . import args

##########################################################
## Flowcell Class ########################################
##########################################################
class flowcell():
    """HiSeq 2500 System :: Flowcell

       Attributes:
       position (str): Flowcell is at either position A (left slot )
            or B (right slot).
       recipe_path (path): Path to the recipe.
       recipe (file): File handle for the recipe.
       first_line (int): Line number for the recipe to start from on the
            initial cycle.
       cycle (int): The current cycle.
       total_cycles (int): Total number of the cycles for the experiment.
       history ([[int,],[str,],[str,]]): Timeline of flowcells events, the
            1st column is the timestamp, the 2nd column is the event, and the
            3rd column is an event specific detail.
       imaging (bool): True if the flowcell is being imaged, False if the
            flowcell is not being imaged.
       sections (dict): Dictionary of section names keys and coordinate
            positions of the sections on the flowcell values.
       stage (dict): Dictionary of section names keys and stage positioning
            and imaging details of the sections on the flowcell values.
       thread (int): Thread id of the current event on the flowcell.
       signal_event (str): Event that signals the other flowcell to continue
       wait_thread (threading.Event()): Blocks other flowcell until current
            flowcell reaches signal event.
       waits_for (str): Flowcell A waits for flowcell B and vice versa.
       pump_speed (dict): Dictionary of pump scenario keys and pump speed
            values.
       flush_volume (int): Volume in uL to flush reagent lines.
    """

    def __init__(self, position):
        """Constructor for flowcells

           Parameters:
           position (str): Flowcell is at either position A (left slot) or
                B (right slot).
        """

        self.recipe_path = None
        self.recipe = None
        self.first_line = None
        self.cycle = 0                                                          # Current cycle
        self.total_cycles = 0                                                   # Total number of cycles for experiment
        self.history = [[],[],[]]                                               # summary of events in flowcell history
        self.imaging = False
        self.sections = {}                                                      # coordinates of flowcell of sections to image
        self.stage = {}                                                         # stage positioning info for each section
        self.thread = None                                                      # threading to do parallel actions on flowcells
        self.signal_event = None                                                # defines event that signals the next flowcell to continue
        self.wait_thread = threading.Event()                                    # blocks next flowcell until current flowcell reaches signal event
        self.waits_for = None                                                   # position of the flowcell that signals current flowcell to continue
        self.pump_speed = {}
        self.flush_volume = None

        while position not in ['A', 'B']:
            print(self.name + ' must be at position A or B')
            position = input('Enter position of ' + self.name + ' : ')

        self.position = position


    def addEvent(self, event, command):
        """Record history of events on flow cell.

           Parameters:
           instrument (str): Type of event can be valv, pump, hold, wait, or
                imag.
           command (str): Details specific to each event such as hold time,
                buffer, event to wait for, z planes to image, or pump volume.

           Returns:
           int: A time stamp of the last event.
        """

        self.history[0].append(time.time())                                     # time stamp
        self.history[1].append(event)                                           # event (valv, pump, hold, wait, imag)
        self.history[2].append(command)                                         # details such hold time, buffer, event to wait for

        return self.history[0][-1]                                              # return time stamp of last event


    def restart_recipe(self):
        """Restarts the recipe and returns the number of completed cycles."""

        if self.recipe is not None:
            self.recipe.close()
        self.recipe = open(self.recipe_path)
        self.cycle += 1
        if self.cycle > self.total_cycles:
            end_message = str(self.position + '::Completed ' +
                              str(self.total_cycles) + ' cycles')
            self.thread = threading.Thread(target = logger.log,
                                           args = (21, end_message,))
            thread_id = self.thread.start()
        else:
            restart_message = str('Starting cycle ' + str(self.cycle) +
                                  ' on flowcell ' + self.position)
            self.thread = threading.Thread(target = logger.log,
                                           args = (21, restart_message,))
            thread_id = self.thread.start()

        return self.cycle


    def endHOLD(self):
        """Ends hold for incubations in buffer, returns hold is False."""
        self.hold = False
        logger.log(21, fc.position+'::cycle'+str(fc.cycle)+'::Hold stopped')

        return self.hold




##########################################################
## Setup Flowcells #######################################
##########################################################

def setup_flowcells(first_line):
    """Read configuration file and create flowcells.

       Parameters:
       first_line (int): Line number for the recipe to start from on the
            initial cycle.

       Returns:
       dict: Dictionary of flowcell position keys with flowcell object values.
    """

    experiment = config['experiment']
    method = experiment['method']
    method = config[method]

    flowcells = {}
    for sect_name in config['sections']:
        position = config['sections'][sect_name]
        AorB, coord  = position.split(':')
        # Create flowcell if it doesn't exist
        if AorB not in flowcells.keys():
            flowcells[AorB] = flowcell(AorB)
            flowcells[AorB].recipe_path = experiment['recipe path']
            flowcells[AorB].flush_volume = int(method.get('flush volume',
                fallback=2000))
            flowcells[AorB].pump_speed['flush'] = int(method.get('flush speed',
                fallback=700))
            flowcells[AorB].pump_speed['reagent'] = int(method.get(
                'reagent speed', fallback=40))
            flowcells[AorB].first_line = first_line
            flowcells[AorB].total_cycles = int(config.get('experiment',
                'cycles'))

        # Add section to flowcell
        if sect_name in flowcells[AorB].sections:
            print(sect_name + ' already on flowcell ' + AorB)
            print('check config file for section name duplications')
            sys.exit()
        else:
            coord = coord.split(',')
            flowcells[AorB].sections[sect_name] = []                            # List to store coordinates of section on flowcell
            flowcells[AorB].stage[sect_name] = {}                               # Dictionary to store stage position of section on flowcell
            for i in range(4):
                try:
                    flowcells[AorB].sections[sect_name].append(float(coord[i]))
                except:
                    print(sect_name +
                        ' does not have a position, check config file')
                    sys.exit()

        # if runnning mulitiple flowcells...
        # Define first flowcell
        # Define prior flowcell signals to next flowcell
        if len(flowcells) > 1:
            flowcell_list = [*flowcells]
            for fc in flowcells.keys():
                flowcells[fc].waits_for = flowcell_list[
                    flowcell_list.index(fc)-1]
            if experiment['first flowcell'] not in flowcells:
                print('First flowcell does not exist')
                sys.exit()

    return flowcells



##########################################################
## Parse lines from recipe ###############################
##########################################################
def parse_line(line):
    """Parse line and return event (str) and command (str)"""

    comment_character = '#'
    delimiter = '\t'
    no_comment = line.split(comment_character)[0]                               # remove comment
    sections = no_comment.split(delimiter)
    event = sections[0]                                                         # first section is event
    event = event[0:4]                                                          # event identified by first 4 characters
    command = sections[1]                                                       # second section is command
    command = command.replace(' ','')                                           # remove space

    return event, command


##########################################################
## Setup Logging #########################################
##########################################################
def setup_logger():
    """Create a logger and return the handle."""

    # Get experiment info from config file
    experiment = config['experiment']
    experiment_name = experiment['experiment name']
    # Make directory to save data
    save_path = join(experiment['save path'],experiment_name)
    if not os.path.exists(save_path):
        os.mkdir(save_path)
    # Make directory to save logs
    log_path = join(save_path, experiment['log path'])
    if not os.path.exists(log_path):
        os.mkdir(log_path)

    # Create a custom logger
    logger = logging.getLogger(__name__)
    logger.setLevel(10)

    # Create console handler
    c_handler = logging.StreamHandler()
    c_handler.setLevel(21)
    # Create file handler
    f_log_name = join(log_path,experiment_name + '.log')
    f_handler = logging.FileHandler(f_log_name)
    f_handler.setLevel(logging.INFO)

    # Create formatters and add it to handlers
    c_format = logging.Formatter('%(asctime)s - %(message)s')
    f_format = logging.Formatter('%(asctime)s - %(message)s')
    c_handler.setFormatter(c_format)
    f_handler.setFormatter(f_format)

    # Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    # Save copy of config with log
    config_path = join(log_path,'config.cfg')
    with open(config_path, 'w') as configfile:
        config.write(configfile)

    return logger

##########################################################
## Setup HiSeq ###########################################
##########################################################
def initialize_hs():
    """Initialize the HiSeq and return the handle"""

    import pyseq

    hs = pyseq.HiSeq(logger)
    hs.initializeCams(logger)
    hs.initializeInstruments()

    experiment = config['experiment']
    method = config[experiment['method']]

    hs.l1.set_power(int(method.get('laser power', fallback = 100)))
    hs.l2.set_power(int(method.get('laser power', fallback = 100)))

    # Assign output directory
    save_path = experiment['save path']
    experiment_name = experiment['experiment name']
    save_path = join(experiment['save path'], experiment['experiment name'])
    if not os.path.exists(save_path):
        os.mkdir(save_path)
    # Assign image directory
    image_path = join(save_path, experiment['image path'])
    if not os.path.exists(image_path):
        os.mkdir(image_path)
    hs.image_path = image_path
    # Assign log directory
    log_path = join(save_path, experiment['log path'])
    if not os.path.exists(log_path):
        os.mkdir(log_path)
    hs.log_path = log_path
    
    return hs


##########################################################
## Check Instructions ####################################
##########################################################
def check_instructions():
    """Check the instructions for errors.

       Returns:
       first_line (int): Line number for the recipe to start from on the
            initial cycle.
    """

    method = config.get('experiment', 'method')
    method = config[method]

    first_port = method.get('first port', fallback = None)                      # Get first reagent to use in recipe
    try:
        first_port = int(first_port)
        first_line = first_port
        first_port = None
    except:
        first_line = 0

    variable_ports = method.get('variable reagents', fallback  = None)


    valid_wait = []
    ports = []
    for port in config['valve24'].items():
        ports.append(port[1])
    if variable_ports is not None:
        variable_ports = variable_ports.split(',')
        for port in variable_ports:
            ports.append(port.replace(' ',''))
    valid_wait = ports
    valid_wait.append('IMAG')
    valid_wait.append('STOP')

    f = open(config['experiment']['recipe path'])
    line_num = 1
    error = 0


    def message(text, error):
        try:
            logger(21,text)
        except:
            print(text)
        error += 1
        return error

    for line in f:
            instrument, command = parse_line(line)

            if instrument == 'PORT':
                # Make sure ports in instruction files exist in port dictionary in config file
                if command not in ports:
                    error = message(command + ' port on line ' + str(line_num) +
                        ' does not exist.\n', error)

                #Find line to start at for first cycle
                if first_line == 0 and first_port is not None:
                    if command.find(first_port) != -1:
                        first_line = line_num

            # Make sure pump volume is a number
            elif instrument == 'PUMP':
                if command.isdigit() == False:
                    error = message('Invalid volume on line ' + str(line_num) +
                        '\n', error)

            # Make sure wait command is valid
            elif instrument == 'WAIT':
                if command not in valid_wait:
                    error = message('Invalid wait command on line ' +
                        str(line_num) + '\n', error)

            # Make sure z planes is a number
            elif instrument == 'IMAG':
                 if command.isdigit() == False:
                    error = message('Invalid number of z planes on line ' +
                        str(line_num) + '\n', error)

            # Make sure hold time (minutes) is a number
            elif instrument == 'HOLD':
                if command.isdigit() == False:
                    error = message('Invalid time on line ' + str(line_num) +
                        '\n', error)

            # Warn user that HiSeq will completely stop with this command
            elif instrument == 'STOP':
                warnings.warn(
                    'HiSeq will complete stop until user input at line' +
                     str(line_num) + '\n')

            # Make sure the instrument name is valid
            else:
                error = message('Bad instrument name on line ' + str(line_num) +
                    '\n', error)

            line_num += 1

    if error > 0:
            print(str(error) + " errors in instruction file")
            f.close() #close instruction file
            sys.exit()
    else:
            print("Good instruction file")
            f.close() #close instruction file
            return first_line

##########################################################
## Check Ports ###########################################
##########################################################
def check_ports():
    """Check for port errors and return a port dictionary"""

    method = config.get('experiment', 'method')
    method = config[method]
    total_cycles = int(config.get('experiment', 'cycles'))

    # Get cycle and port information from configuration file
    valve = config['valve24']                                                   # Get dictionary of port number of valve : name of reagent
    cycle_variables = method.get('variable reagents', fallback = None )         # Get list of port names in recipe that change every cycle
    cycle_reagents = config['cycles'].items()                                   # Get variable reagents that change with each cycle

    error = 0
    port_dict = {}

    # Make sure there are no duplicated names in the valve
    if len(valve.values()) != len(set(valve.values())):
        print('Port names are not unique in configuration file.' +
              ' Rename or remove duplications.')
        error += 1

    if len(valve) > 0:
        # Create port dictionary
        for port in valve.keys():
            port_dict[valve[port]] = int(port)

        # Add cycle variable port dictionary
        if cycle_variables is not None:
            cycle_variables = cycle_variables.split(',')
            for variable in cycle_variables:
                variable = variable.replace(' ','')
                if variable in port_dict:
                    print('Variable ' + variable + ' can not be a reagent!')
                    error = error+1
                else:
                    port_dict[variable] = {}

            # Fill cycle variable port dictionary with cycle: reagent name
            for cycle in cycle_reagents:
                reagent = cycle[1]
                variable, cyc_number = cycle[0].split(' ')
                if reagent in valve.values():
                    if variable in port_dict:
                        port_dict[variable][int(cyc_number)] = reagent
                    else:
                        print(variable +
                              ' not listed as variable reagent in config')
                        error += 1
                else:
                    print('Cycle reagent: ' + reagent +
                          ' does not exist on valve')
                    error += 1

            # Check number of reagents in variable reagents matches number of total cycles
            for variable in cycle_variables:
                variable = variable.replace(' ','')
                if len(port_dict[variable]) != total_cycles:
                    print('Number of ' + variable +
                          ' reagents does not match experiment cycles')
                    error += 1

        else:
            response = True
            while response:
                response = input(
                    'Are all ports the same for every cycle? Y/N: ')
                if response == 'Y':
                    response = False
                elif response == 'N':
                    sys.exit()

    else:
        warnings.warn('No ports are specified')

    if error > 0:
        print(str(error) + ' errors in configuration file')
        sys.exit()
    else:
        print('Ports checked without errors')
        return port_dict


##########################################################
## Flush Lines ###########################################
##########################################################
def do_flush():
    """Flush lines with all reagents in config if prompted."""

    ## Flush lines
    flush_YorN = input("Prime lines? Y/N = ")
    hs.z.move([0,0,0])
    hs.move_stage_out()
    if flush_YorN == 'Y':
        print("Lock temporary flowcell(s) on to stage")
        print("Place all valve input lines in PBS/water")
        input("Press enter to continue...")
        #Flush all lines
        for fc in flowcells.keys():
            volume = flowcells[fc].flush_volume
            speed = flowcells[fc].pump_speed['flush']
            for port in hs.v24[fc].port_dict.keys():
                if isinstance(port_dict[port], int):
                    print('Priming ' + str(port))
                    hs.v24[fc].move(port)
                    hs.p[fc].pump(volume, speed)

        print("Replace temporary flowcell with experiment flowcell and lock on to stage")
        print("Place all valve input lines in correct reagent")
        input("Press enter to continue...")
    else:
        print("Lock experiment flowcells on to stage")
        input("Press enter to continue...")

    for fc in flowcells.values():
        fc.restart_recipe()

#######
def do_nothing():
    """Do nothing."""
    pass


##########################################################
## iterate over lines, send to pump, and print response ##
##########################################################
def do_recipe(fc):
    """Do the next event in the recipe.

       Parameters:
       fc (flowcell): The current flowcell.
    """

    AorB = fc.position
    fc.thread = None

    # Skip to first line of recipe on initial cycle
    if fc.cycle == 1 and fc.first_line is not None:
        for i in range(fc.first_line-1):
            line = fc.recipe.readline()
        fc.first_line = None


    # get instrument and command
    line = fc.recipe.readline()
    if line:
        instrument, command = parse_line(line)

        # Move reagent valve
        if instrument == 'PORT':
            #Move to cycle specific reagent if it is variable a reagent
            if (command in hs.v24[AorB].variable_ports and
            fc.cycle <= fc.total_cycles):
                command = hs.v24[AorB].port_dict[command][fc.cycle]

            log_message = 'Move to ' + command
            fc.thread = threading.Thread(target = hs.v24[AorB].move,
                args = (command,))

        # Pump reagent into flowcell
        elif instrument == 'PUMP':
            volume = int(command)
            speed = fc.pump_speed['reagent']
            log_message = 'Pumping ' + str(volume) + ' uL'
            fc.thread = threading.Thread(target = hs.p[AorB].pump,
                args = (volume, speed,))

        # Incubate flowcell in reagent for set time
        elif instrument == 'HOLD':
            holdTime = float(command)*60
            log_message = 'Flowcell holding for ' + str(command) + ' min.'
            fc.thread = threading.Timer(holdTime, fc.endHOLD)

        # Wait for other flowcell to finish event before continuing with current flowcell
        elif instrument == 'WAIT':
            if fc.waits_for is not None:
                log_message = 'Flowcell waiting for ' + command
                fc.thread = threading.Thread(target = WAIT,
                    args = (AorB, command,))
            else:
                log_message = 'Skipping waiting for ' + command
                fc.thread = threading.Thread(target = do_nothing)

        # Image the flowcell
        elif instrument == 'IMAG':
            log_message = 'Imaging flowcell'
            fc.thread = threading.Thread(target = IMAG,
                args = (fc,int(command),))

        # Block all further processes until user input
        elif instrument == 'STOP':
            logger.log(21,'Paused')
            input("press enter to continue...")
            logger.log(21,'Continuing...')


        #Signal to other flowcell that current flowcell reached signal event
        if fc.signal_event == instrument or fc.signal_event == command:
            fc.wait_thread.set()
            fc.signal_event = None

        # Start new action on current flowcell
        if fc.thread is not None and fc.cycle <= fc.total_cycles:
            fc.addEvent(instrument, command)
            logger.log(21, AorB+'::cycle'+str(fc.cycle)+'::'+log_message)
            thread_id = fc.thread.start()
        elif fc.thread is not None and fc.cycle > fc.total_cycles:
            fc.thread = threading.Thread(target = WAIT, args = (AorB, None,))

    # End of recipe
    elif fc.cycle <= fc.total_cycles:
        fc.restart_recipe()
    elif fc.cycle > fc.total_cycles:
        fc.thread =  threading.Thread(target = time.sleep, args = (10,))
        fc.thread.start()

##########################################################
## Image flowcell ########################################
##########################################################
def IMAG(fc, n_Zplanes):
    """Image the flowcell at a number of z planes.

       For each section on the flowcell, the stage is first positioned
       to the center of the section find the optimal focus. Then if no
       optical settings are listed, the optimal filter sets are found.
       Next, the stage is repositioned to scan the entire section and
       image the specified number of z planes.

       Parameters:
       fc: The flowcell to image.
       n_Zplanes: The number of z planes to image.

       Returns:
       int: Time in seconds to scan the entire section.
    """

    AorB = fc.position
    cycle = str(fc.cycle)
    fc.imaging = True
    start = time.time()


    for section in fc.sections:
        x_center = fc.stage[section]['x center']
        y_center = fc.stage[section]['y center']
        x_pos = fc.stage[section]['x initial']
        y_pos = fc.stage[section]['y initial']
        n_scans = fc.stage[section]['n scans']
        n_frames = fc.stage[section]['n frames']

        # Find/Move to focal z stage position
        if fc.stage[section]['z pos'] is None:
            logger.log(21, AorB+'::Finding rough focus of ' + str(section))

            hs.y.move(y_center)
            hs.x.move(x_center)
            hs.optics.move_ex(1, 0.6)
            hs.optics.move_ex(2, 0.9)
            hs.optics.move_em_in(True)
            Z,C = hs.rough_focus()
            fc.stage[section]['z pos'] = hs.z.position[:]
        else:
            hs.z.move(fc.stage[section]['z pos'])

        # Find/Move to focal obj stage position,
        # Edited to find focus every cycle change -1 to None if only want initial cycle
        if fc.stage[section]['obj pos'] is not -1:
            logger.log(21, AorB+'::Finding fine focus of ' + str(section))

            hs.y.move(y_center)
            hs.x.move(x_center)
            hs.optics.move_ex(1, 0.6)
            hs.optics.move_ex(2, 0.9)
            hs.optics.move_em_in(True)
            Z,C = hs.fine_focus()
            fc.stage[section]['obj pos'] = hs.obj.position
        else:
            hs.obj.move(fc.stage[section]['obj pos'])

        # Optimize filter
        logger.log(21, AorB+'::Finding optimal filter')
        hs.y.move(y_pos)
        hs.x.move(x_center)
        opt_filter = hs.optimize_filter(32)                                     #Find optimal filter set on 32 frames on image
        hs.optics.move_ex(1, opt_filter[0])
        hs.optics.move_ex(2, opt_filter[1])
        hs.optics.move_em_in(True)
        fc.ex_filter1 = opt_filter[0]
        fc.ex_filter2 = opt_filter[1]



        if n_Zplanes > 1:
            obj_start = int(hs.obj.position - hs.nyquist_obj*n_Zplanes/2)
            obj_step = hs.nyquist_obj
            obj_stop = int(hs.obj.position + hs.nyquist_obj*n_Zplanes/2)
        else:
            obj_start = hs.obj.position
            obj_step = 1000
            obj_stop = hs.obj.position + 10

        image_name = AorB
        image_name = image_name + '_' + str(section)
        image_name = image_name + '_' + 'c' + cycle

        # Scan section on flowcell
        logger.log(21, AorB + '::cycle'+cycle+'::Imaging ' + str(section))
        scan_time = hs.scan(x_pos, y_pos,
                            obj_start, obj_stop, obj_step,
                            n_scans, n_frames, image_name)
        scan_time = str(int(scan_time/60))
        logger.log(21, AorB+'::cycle'+cycle+'::Took ' + scan_time +
                       ' minutes ' + 'imaging ' + str(section))

    fc.imaging = False
    stop = time.time()
    hs.z.move([0,0,0])

    return stop-start

# holds current flowcell until an event in the signal flowcell, returns time held
def WAIT(AorB, event):
    """Hold the current flowcell until the specfied event in the other flowell.

       Parameters:
       AorB (str): Flowcell position, A or B, to be held.
       event: Event in the other flowcell that releases the held flowcell.

       Returns:
       int: Time in seconds the current flowcell was held.
    """
    signaling_fc = flowcells[AorB].waits_for
    cycle = str(flowcells[AorB].cycle)
    start = time.time()
    flowcells[signaling_fc].signal_event = event                                # Set the signal event in the signal flowcell
    flowcells[signaling_fc].wait_thread.wait()                                  # Block until signal event in signal flowcell
    logger.log(21, AorB+ '::cycle'+cycle+'::Flowcell ready to continue')
    flowcells[signaling_fc].wait_thread.clear()                                 # Reset wait event
    stop = time.time()

    return stop-start

##########################################################
## Shut down system ######################################
##########################################################
def do_shutdown():
    """Shutdown the HiSeq and flush all reagent lines if prompted."""

    logger.log(21,'Shutting down...')
    for fc in flowcells.values():
        fc.wait_thread.set()

    hs.z.move([0, 0, 0])
    hs.move_stage_out()
    ##Flush all lines##
    flush_YorN = input("Flush lines? Y/N = ")
    if flush_YorN == 'Y':
        print("Lock temporary flowcell on  stage")
        print("Place all valve input lines in PBS/water")
        input("Press enter to continue...")

        for fc in flowcells.keys():
            volume = flowcells[fc].flush_volume
            speed = flowcells[fc].pump_speed['flush']
            for port in hs.v24[fc].port_dict.keys():
                if isinstance(port_dict[port], int):
                    hs.v24[fc].move(port)
                    hs.p[fc].pump(volume, speed)
            ##Return pump to top and NO port##
            hs.p[fc].command('OA0R')
            hs.p[fc].command('IR')
    else:
        print('Retrieve experiment flowcells')
        input('Press any key to finish shutting down')

    for fc in flowcells.values():
        AorB = fc.position
        fc_log_path = join(hs.log_path, 'Flowcell'+AorB+'.log')
        with open(fc_log_path, 'w') as fc_file:
            for i in range(len(fc.history[0])):
                fc_file.write(str(fc.history[0][i])+' '+
                              str(fc.history[1][i])+' '+
                              str(fc.history[2][i])+'\n')

    # Turn off y stage motor
    hs.y.command('OFF')



##########################################################
## Free Flowcells ########################################
##########################################################
def free_fc():
    """Release the first flowcell if flowcells are waiting on each other."""

    # Get which flowcell is to be first
    experiment = config['experiment']
    first_fc = experiment.get('first flowcell', fallback = 'A')

    if len(flowcells) == 1:
        fc = flowcells[[*flowcells][0]]
        fc.wait_thread.set()
        fc.signal_event = None
    else:
        fc = flowcells[first_fc]
        flowcells[fc.waits_for].wait_thread.set()
        flowcells[fc.waits_for].signal_event = None

    logger.log(21, 'Flowcells are waiting on each other,' +
                   ' starting flowcell ' + fc.position)

    return fc.position


##########################################################
## Initialize Flowcells ##################################
##########################################################
def integrate_fc_and_hs(port_dict):
    """Integrate flowcell info with hiseq configuration info."""

    method = config.get('experiment', 'method')                                 # Read method specific info
    method = config[method]
    variable_ports = method.get('variable reagents', fallback = None)
    z_pos = method.get('z start', fallback = None)
    obj_pos = method.get('objective start', fallback = None)

    n_barrels = int(method.get('barrels per lane', 8))                          # Get method specific pump barrels per lane, fallback to 8

    for fc in flowcells.values():
        AorB = fc.position
        hs.v24[AorB].port_dict = port_dict                                      # Assign ports on HiSeq
        if variable_ports is not None:
            variable_ports = variable_ports.split(',')
            for variable in variable_ports:                                     # Assign variable ports
                variable = variable.replace(' ','')
                hs.v24[AorB].variable_ports.append(variable)
        hs.p[AorB].n_barrels = n_barrels                                        # Assign barrels per lane to pump
        for section in fc.sections:                                             # Convert coordinate sections on flowcell to stage info
            stage = hs.position(fc.position, fc.sections[section])
            fc.stage[section]['x center'] = stage[0]
            fc.stage[section]['y center'] = stage[1]
            fc.stage[section]['x initial'] = stage[2]
            fc.stage[section]['y initial'] = stage[3]
            fc.stage[section]['n scans'] = stage[4]
            fc.stage[section]['n frames'] = stage[5]
            fc.stage[section]['z pos'] = z_pos
            fc.stage[section]['obj pos'] = obj_pos


##########################################################
## Get Config ############################################
##########################################################
def get_config(args):
    """Return the experiment config appended with the method config.

       Parameters:
       args (dict): Dictionary with the config path, the experiment name and
            the output path to store images and logs.

       Returns:
       config: The experiment config appended with the method config.
    """
    # Create config parser
    config = configparser.ConfigParser()

    # Defaults that can be overided
    config.read_dict({'experiment' : {'log path': 'logs',
                                      'image path': 'images'}
                      })
    # Open config file
    if os.path.isfile(args['config']):
         config.read(args['config'])
    else:
        print('Configuration file does not exist')
        sys.exit()
    # Set output path
    config['experiment']['save path'] = args['output']
    # Set experiment name
    config['experiment']['experiment name'] = args['name']

    # Get method specific configuration
    method = config['experiment']['method']
    if method in methods.get_methods():
        config_path, recipe_path = methods.return_method(method)
        config.read(config_path)
    elif os.path.isfile(method):
            config.read(method)
    else:
        print('Error reading method configuration')
        sys.exit()

    # Get recipe
    recipe_name = config[method]['recipe']
    if recipe_path is not None:
        pass
    elif os.path.isfile(recipe_name):
        recipe_path = recipe_name
    else:
        print('Error reading recipe')
        sys.exit()

    config['experiment']['recipe path'] = recipe_path

    return config

###################################
## Run System #####################
###################################
args_ = args.get_arguments()

if __name__ == 'pyseq.main':                                                    # Get config path, experiment name, & output path
    config = get_config(args_)                                                  # Get config file
    logger = setup_logger()                                                     # Create logfiles
    port_dict = check_ports()                                                   # Check ports in configuration file
    first_line = check_instructions()                                           # Checks instruction file is correct and makes sense
    flowcells = setup_flowcells(first_line)                                     # Create flowcells
    hs = initialize_hs()                                                        # Initialize HiSeq, takes a few minutes
    integrate_fc_and_hs(port_dict)                                              # Integrate flowcell info with hs

    do_flush()                                                                  # Flush out lines

    cycles_complete = False

    while not cycles_complete:
        stuck = 0
        complete = 0

        for fc in flowcells.values():
            if not fc.thread.is_alive():                                        # flowcell not busy, do next step in recipe
                do_recipe(fc)

            if fc.signal_event:                                                 # check if flowcells are waiting on each other
                stuck += 1

            if fc.cycle > fc.total_cycles:                                      # check if all cycles are complete on flowcell
                complete += 1

        if stuck == len(flowcells):                                             # Start the first flowcell if they are waiting on each other
            free_fc()

        if complete == len(flowcells):                                          # Exit while loop
            cycles_complete = True

    do_shutdown()                                                               # Shutdown HiSeq
