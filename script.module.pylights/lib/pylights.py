# pyLights Python module v0.5

# Copyright 2009-2015 Bryon Bridges

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import serial
import inspect
import socket
import copy
import threading, Queue
from time import sleep, gmtime, asctime, strftime, localtime
from xml.dom.minidom import parse,Document
from sys import argv

'''
pyLights is a Python module for sending Insteon messages via a PLM. It has high
level functions to easily command dimmers, keypads, switches and other devices.
pyLights also acts as an Insteon daemon that updates a device file according to
status messages received after each button press.  This is useful for fast disk
access to up-to-date level information but has many other potential uses.
There is also a built-in UDP server for commanding the PLM remotely.

To reference devices by name rather than address set the 
'device_cfg_filename' parameter to point to an XML configuration file that 
contains names and addresses that match your devices.  An example configuration
file ('devices.xml') is included in the download package.

Example usage:

  import pylights

  # Create a PLM object that controls lights.
  p = pylights.plm(5) # Opens COM5
  # p = pylights.plm('COM5') # Alternate usage
  # p = pylights.plm('/dev/ttyUSB0') # Linux style
  # p = pylights.plm() # Scans for PLM automatically (Windows only)
  # p = pylights.plm(5,verbose=True) # Prints Insteon hex messages to screen.

  # Specify either name or shortName from the XML file and the desired level
  # in percent.
  p.setLevel('Living Room', 50)
  
  # Alternatively, give the address in hex list format.
  p.getLevel([0x12,0x5F,0x5E])
  
  # ...or use dotted hex.
  p.fadeOut('12.5F.5E')
  
  # Close the PLM object to release the serial port.
  p.close()
'''


class plm:
  '''
  Insteon PLM controller object.
  '''
  
  # --- Insteon definitions ---
  
  commands = {
    'dataReq' :       0x03,
    'insteonVer' :    0x0D,
    'idReq' :         0x10,
    'ON' :            0x11,
    'fastOn' :        0x12,
    'OFF' :           0x13,
    'fastOff' :       0x14,
    'brightStep' :    0x15,
    'dimStep' :       0x16,
    'startChange' :   0x17,
    'stopChange' :    0x18,
    'statusRequest' : 0x19,
    'getOpFlags' :    0x1F,
    'setOpFlags' :    0x20,
    'setHiAddr' :     0x28,
    'pokeEE' :        0x29,
    'peekEE' :        0x2B,
    'onAtRate' :      0x2E,
    'offAtRate'     : 0x2F,
    'writeOutput'   : 0x48,
    'readInput'     : 0x49,
    'getSensorVal'  : 0x4A,
    'readCfg'       : 0x4E,
    'ioModuleCtrl'  : 0x4F,
    'setIMCfg'      : 0x6B    
    }
    
  messages = {
    'insteonRecv' :     0x50,
    'insteonExtRecv' :  0x51,
    'x10Recv' :         0x52,
    'plmInfo' :         0x60,
    'insteonSend' :     0x62,
    'sendX10' :         0x63,
    'plmReset' :        0x67,
    'getFirstLink' :    0x69,
    'getNextLink' :     0x6A,
    'getSenderLink' :   0x6C,
    'LED_on' :          0x6D,
    'LED_off' :         0x6E }
    

  devTypes = {'Dimmer' : 1, 'Switch' : 2, 'PLM' : 3, 'Other' : 7}

  devSubtypes = {
    'LampLinc' :        0,
    'SwitchLinc 600W' : 1,
    'SwitchLinc' :      21, 
    'KeypadLinc' :      27 }
  
  # --- X10 codes ---
  
  x10_houseCode = {
    'A' : 0x6,
    'B' : 0xE,
    'C' : 0x2,
    'D' : 0xA,
    'E' : 0x1,
    'F' : 0x9,
    'G' : 0x5,
    'H' : 0xD,
    'I' : 0x7,
    'J' : 0xF,
    'K' : 0x3,
    'L' : 0xB,
    'M' : 0x0,
    'N' : 0x8,
    'O' : 0x4,
    'P' : 0xC }

  x10_unitCode = {
    1 : 0x6,
    2 : 0xE,
    3 : 0x2,
    4 : 0xA,
    5 : 0x1,
    6 : 0x9,
    7 : 0x5,
    8 : 0xD,
    9 : 0x7,
    10 : 0xF,
    11 : 0x3,
    12 : 0xB,
    13 : 0x0,
    14 : 0x8,
    15 : 0x4,
    16 : 0xC }
  
  x10_command = {
    'all lights off' :  0x6,
    'status = off' :    0xE,
    'on' :              0x2,
    'preset dim' :      0xA,
    'all lights on' :   0x1,
    'hail ack' :        0x9,
    'bright' :          0x5,
    'status = on' :     0xD,
    'extended code' :   0x7,
    'status request' :  0xF,
    'off' :             0x3,
    'preset dim' :      0xB,
    'all units off' :   0x0,
    'hail request' :    0x8,
    'dim' :             0x4,
    'extended data' :   0xC }

  x10_key = {'unit code' : 0x00, 'command' : 0x80}

  
  def __init__(self, comPort=None, verbose=False, device_cfg_filename='devices.xml'):

    self.devices = deviceFile(device_cfg_filename)
    
    self.send_q = Queue.Queue()
    self.recv_q = Queue.Queue()
    self.async_q = Queue.Queue()

    self.async_callbacks = []
    self.async_thread = AsyncEventThread(self)
    self.server = ServerThread(self)
    
    self.timer_threads = []
    
    self.verbose = verbose
    self.address = None
    
    # Initialize log file
    self.log_file = 'pylights.log'
    self.log_enabled = False
    if self.log_enabled:   
      with open(self.log_file, 'w') as f:
        print >> f, 'PyLights log created: ' + strftime('%x %X', localtime())
        print >> f, 40*'='

    # Serial port
    try:
      if comPort is None:
        # Use the first available PLM
        ports = self.scan_serial_ports()
        for k in ports:
          print('Trying %s...' % k[1])
          self.s = serial.Serial(k[0],19200,8,'N',1,timeout=1)
          self.serial_rx = SerialRxThread(self)
          response = self.getPlmInfo()
          if response is not None:
            self.address = response[0:3]
            print('PLM found at %s!' % k[1])
            break
          else:
            self.s.close()
        if not self.s.isOpen():
          raise Exception('Could not find a valid serial port')
      else:
        if type(comPort) is int:
          port = comPort - 1
        elif type(comPort) is str:
          port = comPort
        else:
          raise Exception('Serial port must be either a string or an integer.')
        self.s = serial.Serial(port,19200,8,'N',1,timeout=1)
        self.serial_rx = SerialRxThread(self)
        self.address = self.getPlmInfo()[0:3]
    except serial.SerialException:
      raise
    except TypeError:
      # Indexing error (during getPlmInfo)
      self.s.close()
      raise
    except NameError:
      self.s = None
      raise
    except AttributeError:
      # No serial ports found
      self.s = None


  def close(self):
    '''
    Releases the serial port
    '''
    try:
      self.s.close()
      self.server.shutdown()
      # Remove timer instances before exiting
      for tt in self.timer_threads:
        tt.cancel()
        num_tries = 0
        while tt.isAlive() and num_tries < 3:
          num_tries = num_tries + 1
          sleep(0.25)
    except:
      pass

      
  def log(self, msg):
    if self.log_enabled:
      with open(self.log_file, 'a') as f:                
        print >> f, msg + '  <' + strftime('%x %X', localtime()) + '>'
    if self.verbose: print msg
    

  def scan_serial_ports(self):
    '''
    Returns a list of available serial ports (Windows only)
    '''
    available = []
    for i in range(256):
      try:
        s = serial.Serial(i)
        available.append( (i, s.portstr))
        s.close()
      except serial.SerialException:
        pass
    return available

  
  def register_callback(self, func, event=None):
    '''
    Registers a callback function to call upon receiving an asynchronous event.
    Pass an event object to control which events cause the callback to run or
    pass None to let all events trigger the callback. The callback function 
    must accept exactly 1 argument that is the contents of the message buffer.
    '''
    
    func_args = inspect.getargspec(func).args    
    func_args.remove('self')
    if len(func_args) == 1:
      self.async_callbacks.append((func, event))
      return "OK"
    else:
      return "Callback function must take exactly 1 argument"


  def unregister_callback(self, func=None):
    '''
    Unregisters all callbacks with function name 'func'.  Default option 
      unregisters all callbacks.
    '''
    if func is None:
      func_count = len(self.async_callbacks)
      func = '<all>'
      self.async_callbacks = []
    else:
      func_count = 0
      for k in copy.copy(self.async_callbacks):
        if k[0] == func:
          self.async_callbacks.remove(k)
          func_count = func_count + 1
    return 'Removed %d callback function(s) named %s' % (func_count, func)

  
  def listDevices(self, devIndex=None):
    '''
    Returns a list of names for all devices in the device file
    '''
    if devIndex is None:
      dev_list = [self.getNameByIndex(k) for k in range(self.numDevices())]
    else:
      dev_list = self.getNameByIndex(devIndex)
    return dev_list
    
    
  def numDevices(self):
    '''
    Returns the number of devices in the device file
    '''
    return self.devices.numDevices
    
    
  def getPlmInfo(self):
    '''
    Returns the PLM address if found.
    '''
    message = [0x02, self.messages['plmInfo']]
    msg = self.send_msg(message,9,True)
    if msg[-1] == 0x06:  return msg[2:8]
    else: return None

    
  def list_to_hex(self, list_in):
    '''
    Convert a list of integers into nice looking hex.
    Will also accept a list of lists.
    '''
    out = list_in
    if type(list_in) is list:
      list_len = len(list_in)
      if list_len > 0:
        if type(list_in[0]) is int:
          # List is one dimensional.
          list_in = [list_in]
        out = ''
        for list_row in list_in:
          for list_col in list_row:
            out += '%02X ' % list_col
          if self.devices.filename is None:
            name = ''
          else:
            ind = self.getIndexByAddress(list_row[2:5])
            if ind is not None:  
              name = ': (' + self.getNameByIndex(ind) + ')'
            elif list_row[2:5] == self.address:
              name = ': <PLM>'
            else:
              name = ': <none>'
          out = out.strip() + ' ' + name + '\r\n'
        out = out[:-2]
    return out

    
  def prettyPrint(self, list):
    print (self.list_to_hex(list))
  

  def updateLevel(self, device, level):
    '''
    PLM method for updating the XML file given either a device index or address.
    '''
    if self.devices.filename is not None:
      if type(device) is not int:
        address = self.address_to_list(device)
        device = self.getIndexByAddress(address)
      if type(level) is int:
        self.devices.updateLevel(device,level)


  def sendX10(self, house_code, unit_code, cmd):
    '''
    Send an X10 command.
    Example:
      p.sendX10('A',1,'on')      
    
    NB: X10 does not get propagated to the second phase with RF repeaters.
    '''
    try:
      message = ([0x02, self.messages['sendX10'], 
                16*self.x10_houseCode[house_code]+self.x10_unitCode[unit_code], 
                self.x10_key['unit code']])
      if 0x6 == self.send_msg(message)[-1]:
        sleep(0.5)
        message = ([0x02, self.messages['sendX10'], 
                16*self.x10_houseCode[house_code]+self.x10_command[cmd.lower()], 
                self.x10_key['command']])
        if 0x6 == self.send_msg(message)[-1]: return 'OK'
      return 'Error'
    except KeyError:
      return 'Incorrect parameters'


  def sendStdMessage(self,address,cmd1,cmd2=0x00,flags=0x0F):
    '''
    Sends a standard length Insteon message to PLM via the serial port.
    Returns a list that contains the response in base ten notation (not hex).
    '''
    # Set the number of bytes to expect as the response. 0 for group broadcast.
    if (flags & 0xC0):  response_len = 0  
    elif cmd1 == self.commands['idReq']: response_len = 22
    else: response_len = 11
    address = self.address_to_list(address)
    if address is None: return "Invalid address"
    msg = ([0x02,self.messages['insteonSend']]+address+[(flags & 0xEF),cmd1,cmd2])
    return (self.send_msg(msg,response_len))
    

  def sendExtMessage(self,address,cmd1,data,cmd2=0x00,flags=0x1F):
    '''
    Sends an extended Insteon message.
    '''
    if len(data) is not 14: return ('Data length must be 14')
    address = self.address_to_list(address)
    if address is None: return "Invalid address"
    msg = ([0x02,self.messages['insteonSend']]+address+[(flags | 0x10),cmd1,cmd2]+data)
    self.send_msg(msg, 11)
    # Expecting at least one extended return message.
    #self.send_q.put(25)       
    return 'OK'
    
    
  def send_msg(self, message, response_len=0, no_echo=False):
    '''
    This method is responsible for handling all outgoing serial messages.
    Returns the response if requested, otherwise just the N/ACK byte.
    Set 'no_echo' to True if the message response does not echo, e.g.,
    'getplmInfo()'.
    '''
    if not self.s.isOpen():
      return "Serial port is not open"
    # Request echo message
    if no_echo: self.send_q.put(SerialPacket(None, response_len))
    else: 
      self.send_q.put(SerialPacket(None, len(message)+1))
      # Request response message
      if response_len > 0:
        self.send_q.put(SerialPacket(message, None))
    self.s.write(str(bytearray(message)))
    self.log('TX : %s' % self.list_to_hex(message))
    # Get echo response
    try:
      msg_q = self.recv_q.get(True,1)
      self.log('RX : %s' % self.list_to_hex(msg_q.msg))
    except Queue.Empty:
      self.serial_rx.reset('Echo timeout')
      return "Timeout waiting for echo"
    if no_echo: return msg_q.msg
    if msg_q.msg[0:len(message)] != message:
      self.log('Got\t\t{0:s}\nExpected\t{1:s}'\
          .format(self.list_to_hex(msg_q.msg),self.list_to_hex(message)))
      # Wait for serial timeout before returning
      nr = self.serial_rx.num_resets + 1
      tries = 0
      while ((self.serial_rx.num_resets != nr) and (tries < 50)): 
        sleep(0.1)
        tries += 1
      if tries == 50: self.serial_rx.reset('Echo timeout')
      return 'Invalid echo'
    if len(msg_q.msg) != (len(message)+1): 
      self.log('Got\t\t{0:s}\nExpected\t{1:s}'\
          .format(self.list_to_hex(msg_q.msg),self.list_to_hex(message)))
      return 'Invalid message length'
    # Look for ACK/NACK
    if response_len == 0: return msg_q.msg
    if msg_q.msg[-1] != 6:
      if msg_q.msg[-1] == 0x15: 
        # NACK.  Remove response request (if any)
        if not self.send_q.empty():
          self.send_q.get()
        return 'NACK'
      self.serial_rx.reset('Received non-ACK character: %s' % msg_q.msg)
      return 'No ACK received!'
    # Look for response
    try:
      # Block on receive with 8 second timeout
      msg_q = self.recv_q.get(True,8)
      self.log('RX : %s' % self.list_to_hex(msg_q.msg))
    except Queue.Empty:
      self.serial_rx.reset('Response timeout')
      return "Timeout waiting for response"
    except TypeError:
      return "Invalid response"
    except AttributeError:
      raise
    else:
      return (msg_q.msg)

  
  def getOperatingFlags(self, address, cmd2):
    '''
    0x24 switch relays
    0x20 dimmers
    
    0x02 latching
    0x0A momentary A
    0x1A momentary B
    0x9A momentary C    
    '''
    resp = self.sendStdMessage(address, self.commands['getOpFlags'], cmd2)
    if type(resp) is list: resp = resp[-1]
    return resp
      

  def setOperatingFlags(self, address, cmd2):
    '''
    Sets operating flags depending on device.
    '''
    resp = self.sendStdMessage(address, self.commands['setOpFlags'], cmd2)
    if type(resp) is list: resp = resp[-1]
    return resp
	
  
  def getPlmLinkTable(self):
    '''
    This function may not work with an empty table.  Link some devices.
    '''
    links = []
    message = [0x02,self.messages['getFirstLink']]
    link = self.send_msg(message,10)
    if type(link) is list:
      links.append(link[2:])
      done = False
      while not done:
        message = [0x02,self.messages['getNextLink']]
        link = self.send_msg(message,10)
        if type(link) is list:
          links.append(link[2:])
        else:
          done = True
    return links


  def get_button(self, address):
    '''
    Extracts a button number from any supported type of address using colon notation.
    Returns None for error or no button found.
    '''
    button = None
    if type(address) is str:
      addr_split = address.split(':')
      if len(addr_split) == 2:  
        button = int(addr_split[1])
    return button  


  def address_to_list(self, address):
    '''
    Convert any supported type of address to list.
    Returns None upon failure.
    Returns the original address if not the supported type.
    '''    
    if type(address) is str:
      # Remove :'s from button notation
      address = address.split(':')[0]
      if address.find('.') != -1:
        # Address is in dotted hex notation
        try:
          address = [int(str(k),16) for k in address.split('.')]
          if len(address) != 3: address = None
          else:
            # Check for invalid values
            for value in address:
              if not (0 <= value <= 255):
                address = None
                break
        except ValueError:
          address = None
      else:
        # Named address
        address, index = self.devices.findDevAddress(address)   
    return address


  def getDevInfo(self, address):
    '''
    Returns the results of a ID request command
    '''
    if address == self.address:
      info = self.getPlmInfo()
      devSubtype = info[4]
      devType = info[3]
    else:
      info = self.sendStdMessage(address,self.commands['idReq'])
      try:
        if type(info) is list: info = info[-7:]
      except:
        raise
    return info
    
    
  def getVersion(self, address):
    '''
    Returns the INSTEON engine version (i.e., 0=i1, 1=i2)
    '''
    if address == self.address:
      status = 'Not yet implemented'
    else:
      recv = self.sendStdMessage(address,self.commands['insteonVer'])
      if type(recv) is list:
        status = recv[10]
      else: status = recv    
    return status
    
    
  def getDevCat(self, address):
    if address == self.address:
      info = self.getPlmInfo()
      devSubcat = info[4]
      devCat = info[3]
    else:
      recv = self.sendStdMessage(address,self.commands['dataReq'])
      self.send_q.put(SerialPacket([0,0]+self.address_to_list(address), None))
      try:
        d = self.recv_q.get(True, 8) # 8 second timeout
        self.log('RX : %s' % self.list_to_hex(d.msg))
      except Queue.Empty:
        self.send_q.queue.clear()
        return None, None
      devSubcat = d.msg[16]
      devCat = d.msg[15]
    return devCat, devSubcat


  def readEEPROM(self, insteonAddr, addrL, numTries=1):
    '''
    Returns the value stored at the specified low address.
      The high address should be set with 'setMSB()'
    '''
    nt_orig = numTries
    while numTries:
      recv = self.sendStdMessage(insteonAddr,self.commands['peekEE'],addrL,0x0F)
      if type(recv) is list:
        return recv[-1]
      else: 
        numTries -= 1
        sleep(0.5)
    return ('Failed after %d tries' % nt_orig)


  def writeEEPROM(self, insteonAddr, dataByte, numTries=1):
    '''
    Writes a byte to the location having high byte specified by 'setMSB' and 
      low byte as previously used in a 'readEEPROM' command.
    '''
    nt_orig = numTries
    status = "Unknown error"
    while numTries > 0:
      status = self.sendStdMessage(insteonAddr,self.commands['pokeEE'],dataByte)
      if type(status) is list:
        return "OK"
      else:
        numTries -= 1
        sleep(0.5)
    return ('Failed after %(0)d tries. %(1)s' % {'0':nt_orig, '1':status})


  def setMSB(self, insteonAddr, addrH=0x0F):
    '''
    Sets the most significant byte of the EEPROM poke/peek address
    '''
    status = self.sendStdMessage(insteonAddr,self.commands['setHiAddr'],addrH)
    if type(status) is list:
      return "OK"
    else:  
      return status
      
  
  def sendGroupCmd(self, groupNum, cmd):
    '''
    Sends commands to all devices in a particular group
    Make sure the device has a responder link to the PLM.
    '''
    status = self.sendStdMessage([0x00,0x00,groupNum],cmd,0x00,0xCF)
    if type(status) is list:
      return "OK"
    else:  
      return status


  def getLinkTable(self, address, record=None):
    '''
    Sends extended data message to get link DB
    '''
    data = 14*[0] # Send all records
    if record is not None: 
      addr = 0x0FFF - (record*0x08)
      data[2] = (addr & 0xFF00) >> 8
      data[3] = (addr & 0xFF)
      data[4] = 0x01 # Send one record
    self.sendExtMessage(address, 0x2F, data)
    links = []
    done = False
    while not done:
      to_addr = self.address_to_list(address)
      if to_addr is None: return 'Invalid address'
      self.send_q.put(SerialPacket([0,0]+to_addr, None))
      try:
        d = self.recv_q.get(True, 8) # 8 second timeout
        self.log('RX : %s' % self.list_to_hex(d.msg))
      except Queue.Empty:
        self.send_q.queue.clear()
        done = True
      try:
        # Flag byte in last record will be 0x00
        if d.msg[16] == 0x00:
          self.send_q.queue.clear()
          done = True
        else:
          # Add link table data
          links.append(d.msg[16:24])
          if record is not None: done = True
      except UnboundLocalError:
        # Invalid message (d cannot be indexed)
        pass
    return links
      
  
  def writeLinkRecord(self, address, record_data, record_num):
    '''
    Writes a record (list) to the All-Link DB
    '''
    data = 14*[0] # Send all records
    addr = 0x0FFF - (record_num*0x08)
    data[1] = 0x02 # Write All-Link DB
    data[2] = (addr & 0xFF00) >> 8
    data[3] = (addr & 0xFF)
    data[4] = len(record_data) # Number of bytes
    data[5:5+len(record_data)] = record_data
    status = self.sendExtMessage(address, 0x2F, data)
    return status
  
  
  def getLinkTable_old(self, addr, record=None):
    '''
    Searches EEPROM for link table information.
    Specify a record index to retrieve a single record.
    Slow and unreliable.  Use getLinkTable() for i2 devices.
    '''    
    num_tries = 2
    status = self.setMSB(addr,0x0F)
    if status is not "OK":
      return status
    if record is None:
      LSB = 0xF8
    else:
      LSB = 0xF8-(8*record)  # Starting LSB      
    totalList = []
    entriesLeft = True
    while entriesLeft:
      byte = self.readEEPROM(addr,LSB,num_tries)
      if byte == 0: entriesLeft = False
      elif type(byte) is str:
        print ('Received: %s while getting link table. Quitting...' % byte)
        entriesLeft = False
      else:
        List = []
        List.append(byte)
        for k in range(7):
          LSB += 1
          byte = self.readEEPROM(addr,LSB,num_tries)
          if type(byte) is str:
            print ('Received: %s while getting link element. Quitting...' % byte)
            entriesLeft = False
          else:
            List.append(byte)
        print ('%02X : %s' % (LSB-7,self.list_to_hex(List)))
        if record != None: 
          entriesLeft = False
          totalList = List
        else: 
          totalList.append(List)
          LSB -= 0x0F        
    return totalList


# --- High-level methods ---

  
  def setLevel(self, address, level=100, usePercent=True, update=True):
    '''
    Sets the level of the dimmer at the given address in percent brightness.
    To use direct levels (0-255) set the usePercent parameter to False.
    Setting update to True causes the device status file to be updated.

    NOTE:
    IOLinc devices in "GarageIO" mode do not get updated as we're usually not
      interested in the state of the relay output.  Use update=False in this 
      case.  
    '''
    if usePercent:
      if (0 <= level <= 100):
        level = int(round(2.55*level))
      else: return 'Percent level must be 0-100'
    else:
      if not (0 <= level <= 255):
        return 'Direct level must be 0-255'
    if level == 0: command = self.commands['OFF']
    else: command = self.commands['ON']
    status = self.sendStdMessage(address,command,level)
    if status[-1]==level:
      status = "OK"
      if update == True:  self.updateLevel(address, level)
    return status


  def getLevel(self, address, usePercent=True, fromDisk=False):
    '''
    Returns the current brightness level in percent as read from the 
      Insteon device.
    To get direct levels (0-255), set the usePercent parameter to False.
    Setting fromDisk=True will read the level from the device file without
      sending an Insteon query.
    '''
    if fromDisk:
      status = self.devices.getLevelByIndex(
            self.getIndexByAddress(address))
      if status is None: status = 'Address not found'
      else: status = [status]
    else:
      status = self.sendStdMessage(
        address,self.commands['statusRequest'])
    if type(status) is list:
      self.updateLevel(address, status[-1])
      if usePercent:
        status = int(round(status[-1]*0.39216)) # Multiplying by 100/255
      else: status = int(status[-1])
    return status


  def toggle(self, address):
    '''
    Toggles the device level between fully ON and OFF based on the status 
    in the device file. If the device starts with a dimmed level it will 
    toggle to OFF.
    '''
    status = self.getLevel(address, fromDisk=True)
    if type(status) is int:
      if status == 0:
        status = self.setLevel(address, 100)
      else:
        status = self.setLevel(address, 0)
    return status
    

  def fadeOut(self, address, rate=None):
    '''
    Slowly fades to 0 brightness with optional rate.  Returns immediately.
    '''
    if rate is None:
      status = self.sendStdMessage(address,self.commands['startChange'], 0x00)
    else:
      if 0 <= rate <= 255:
        status = self.sendStdMessage(address,self.commands['offAtRate'], rate)
      else: status = 'Rate must be between 0 and 255'        
    if type(status) is list:
      self.updateLevel(address, 0)
      return "OK"
    else: return status
    
    
  def fadeIn(self, address, rate=None):
    '''
    Slowly fades to 100 percent brightness with optional rate.  Returns 
    immediately.
    '''
    if rate is None:
      status = self.sendStdMessage(address,self.commands['startChange'],0x01)
    else:
      if 0 <= rate <= 255:
        status = self.sendStdMessage(address,self.commands['onAtRate'], rate)
      else: status = 'Rate must be between 0 and 255'
    if type(status) is list:
      self.updateLevel(address, 255)
      return "OK"
    else: return status


  def fadeStop(self, address):
    '''
    Stops a previously started fade operation.
    '''
    status = self.sendStdMessage(address,self.commands['stopChange'])
    if type(status) is list:
      self.updateLevel(index, self.getLevel(address,False))
      return "OK"
    else: return status
    

  def startAutoUpdate(self, time_between=600):
    '''
    Keeps device file up to date by periodically polling levels.
    Default polling interval is 10 minutes.
    '''
    # Find the first valid device
    devInd = -1
    devType = None
    while devType not in ['Dimmer','Switch']:
      if devInd == self.numDevices():
        return "Could not find valid device"
      else: devInd += 1
      devType = self.getTypeByIndex(devInd)
    self.addIntervalEvent(time_between,'update_all',self.getAddressByIndex(devInd),'inf')
    return "OK"

  
  def plmDemo(self, address):
    '''
    This will eventually be cool
    '''
    for k in range(0,101,10):
      if self.setLevel(address, k) == 'OK':
        lvl = self.getLevel(address)
        if k != lvl:
          try:
            print 'Tried setting %d, got %d instead' % (k, lvl)
            print type(lvl)
            print self.getLevel(address)
          except:
            print k
            print lvl
          #sleep(2)
        else:
          print k
      else:
        print ('Failed to set level')
    return 'OK'


  def createLink(self, ctrl_addr, resp_addr,
          ctrl_button=None, resp_button=None):
    '''
    Creates a link between the controller and responder addresses given.
    
    Specify a button number (A=1,B=2...) if either one of the targets is a
    keypad.
    
    THIS FUNCTION SHOULD BE RE-WRITTEN FROM SCRATCH
    '''
    ctrl_addr = self.address_to_list(ctrl_addr)
    resp_addr = self.address_to_list(resp_addr)
    # Get device types
    ctrl_type, ctrl_subtype = self.getDevCat(ctrl_addr)
    resp_type, resp_subtype = self.getDevCat(resp_addr)
    try:
      if ctrl_subtype == self.devSubtypes['KeypadLinc']:
        #print ('Controller is keypad')
        ctrl_is_keypad = True
        if ctrl_button is None:
          raise Exception('Must specify a button number for keypad devices')
      else: 
        #print ('Controller is NOT keypad')
        ctrl_is_keypad = False
      if resp_subtype == self.devSubtypes['KeypadLinc']:
        #print ('Responder is keypad')
        resp_is_keypad = True
        if resp_button is None:
          raise Exception('Must specify a button number for keypad devices')
      else: 
        #print ('Responder is NOT keypad')
        resp_is_keypad = False
    except KeyError:
      print ctrl_subtype
      print resp_subtype
      raise Exception('Found unknown subtype.  Please add it to plm.devSubtypes{}')
    # Search link table of controller
    print ('Getting controller LSB...')
    freeLSB_ctrl = self.getUnusedLinkAddr(ctrl_addr)
    if type(freeLSB_ctrl) is int:
      # Search link table of responder
      print ("Getting responder LSB...")
      freeLSB_resp = self.getUnusedLinkAddr(resp_addr)
      if type(freeLSB_resp) is int:
                  
        
        if ((ctrl_is_keypad == False) and (ctrl_button != None)) or \
            ((resp_is_keypad == False) and (resp_button != None)):
          raise Exception('You have specified a button number for a non-Keypad device.  If this is not an oversight, check your device subtype and add it to the list of acceptable types or notify the author.')
        
        '''
        Apparent facts:
        Keypad as controller:
        [0xE2, group, addr, addr, addr, level, ramp, button]

        Keypad as responder:
        [0xA2, group, addr, addr, addr, level, ramp, button]

        Device as controller:
        [0xE2, group, addr, addr, addr, level, ramp, 0x00]

        Device as responder:
        [0xA2, group, addr, addr, addr, level, ramp, 0x00]
        
        Always match group numbers, controller to responder when linking.
        If controller is keypad, the button number matches the group number.
        
        If dimmer, the button number is always 0x00.
        If the controller is a dimmer, group is 0x1.
        '''
        if ctrl_is_keypad: 
          ctrl_group = ctrl_button
        else:
          ctrl_group = 1
          ctrl_button = 0
        
        if resp_is_keypad:
          if ctrl_is_keypad:
            resp_group = resp_button # Probably wrong
          else:
            resp_group = 1
        else:
          if ctrl_is_keypad:
            resp_group = ctrl_button
          else:
            resp_group = 1
          resp_button = 0
        
        write_list = [0xE2,ctrl_group,resp_addr[0],resp_addr[1],resp_addr[2],0xFF,0x1C,ctrl_button]
        #print (self.link_to_hex(write_list))
        for k in range(8):
          #print ('Writing 0x%X to %s' % (write_list[k], hex(freeLSB_ctrl+k)))
          if type(self.readEEPROM(ctrl_addr,freeLSB_ctrl+k,3)) is not int: 
            return 'Error while reading controller'
          if self.writeEEPROM(ctrl_addr,write_list[k],3) != 'OK': 
            return 'Error while writing controller'
        write_list = [0xA2,resp_group,ctrl_addr[0],ctrl_addr[1],ctrl_addr[2],0xFF,0x1C,resp_button]
        #print (self.link_to_hex(write_list))
        for k in range(8):
          #print ('Writing 0x%X to %s' % (write_list[k], hex(freeLSB_resp+k)))
          if type(self.readEEPROM(resp_addr,freeLSB_resp+k,3)) is not int: 
            return 'Error while reading responder'
          if self.writeEEPROM(resp_addr,write_list[k],3) != 'OK': 
            return 'Error while writing responder'
      else:
        return freeLSB_resp
    else:
      return freeLSB_ctrl
    return 'OK'


  def deleteLinkRecord(self,address,record=-1):
    '''
    Clears an entry from the link pool.  First record is 0.  
    Default argument deletes the last record.
    '''
    t = self.getLinkTable(address)
    if type(t) is list:
      status = 'OK'
      if record != -1:
        if len(t) > 1:
          # Copy last record to deleted position
          status = self.writeLinkRecord(address, t[-1], record)
      # Delete last record
      if status == 'OK':
        status = self.writeLinkRecord(address, 8*[0], len(t)-1)  
    else: status = t
    return status


  def addResponder(self, resp_addr, ctrl_addr, button):
    '''
    Adds a '<respondTo>ctrl_addr:button' tag to the responder element.
    This allows level updates to occur for devices controlled by keypad
    buttons.
    
    Addresses must be given in dotted hex notation, e.g., '12.5F.5E'.
    '''
    if self.devices.filename is None: return 'Not using a device file'
    # New element
    d = self.devices.doc.createElement('respondsToBtn')
    txt = self.devices.doc.createTextNode(ctrl_addr.upper()+':'+str(button))
    d.appendChild(txt)
    # Search for device index.
    devIndex = self.getIndexByAddress(resp_addr)
    # Add new element (with formatting text)
    c = self.devices.dev[devIndex].childNodes
    c_txt = c.item(c.length-3)
    if c_txt.nodeType == 3:
      c.insert(c.length-1,d)
      c.insert(c.length-2,c_txt)
    else:
      print (c_txt.toxml())
      return 'Wrong node type.  Should be text'
    self.devices.updateXML()
    return 'OK'


# --- Wrapper functions ---

  def getIndexByAddress(self, address): 
    return self.devices.getIndexByAddress(self.address_to_list(address))
  def getNameByIndex(self, index): return self.devices.getNameByIndex(index)
  def getShortNameByIndex(self, index): 
    return self.devices.getShortNameByIndex(index)
  def getAddressByIndex(self, index): 
    return self.devices.getAddressByIndex(index)
  def getTypeByIndex(self, index): return self.devices.getTypeByIndex(index)
  def getLevelByIndex(self, index): return self.devices.getLevelByIndex(index)
  def getGroupByIndex(self, index): return self.devices.getGroupByIndex(index)
  def getAddrList(self, addrStr): return self.devices.getAddrList(addrStr)

  
# --- Event functions ---
    
  def addIntervalEvent(self, interval, action, address, num_events=1):
    '''
    Add a timed event.  Interval events occur between time intervals as many
    times as specified by 'num_events'.
    
    Parameters:
      interval: time between events in seconds
      action: can be 
        'toggle' - toggles on and off
        'update' - polls the device and updates device file
        'update_all' - same as 'update' except device is automatically cycled
        integer number - specifies a brightness level to set
      address: the address of the device
      num_events: 
        integer number - number of events to schedule.
        'inf' - event does not expire        
    '''
    if action not in ['toggle','update','update_all']: 
      if action not in range(0,256):
        return "Invalid action"
    if interval <= 0: return "Invalid interval"
    # Create a new event
    event = LightingEvent('interval', interval)
    event.events_remaining = num_events
    if type(action) is int:
      event.action = 'on'
      event.level = action
    else: event.action = action
    event.to_address = address
    # Create new timer for this event (decide which function to call here...)
    timer = threading.Timer(interval, self.timer_handler, [event])
    self.timer_threads.append(timer)
    timer.start()
    return "OK"


  def addTriggeredEvent(self, trig_address, trig_cmd, action, delay, action_address=None):
    '''
    Add an event trigger for delayed action.
    Specify a button by appending ':<btn>' to dotted-hex address.  E.g., '12.5F.5E:2'.
    If 'action_address' is None the action is applied to the trigger address.
    
    Example:
      def callback_fcn(event):
        print ('Action detected')
      
      p = pylights.plm()
      p.addTriggeredEvent('living room', p.commands['fastOff'], 'callback', 0, callback_fcn)
    '''
    if type(action) is int and action not in range(0,256): return "Invalid level"
      # ((0 <= action) and (action <= 255)): return "Invalid level"
    if action not in ['toggle','on','off','callback']: return "Invalid action"
    # Validate address
    addr_split = trig_address.split(':')
    if len(addr_split) == 2:  btn_num = int(addr_split[1])
    else:  btn_num = None
    trig_address = self.address_to_list(addr_split[0])
    if trig_address is None: return "Invalid address"
    # Create a new event
    event = LightingEvent('trigger', delay)
    if action == 'on':
      event.level = 255
    elif action == 'off':
      event.level = 0 
    event.action = action
    event.from_address = trig_address
    event.from_cmd = trig_cmd
    event.from_button = btn_num
    if action_address is None:
      event.to_address = trig_address
    else: event.to_address = action_address
    return self.register_callback(self.timer_handler, event)

  
  def addDailyEvent(self, action_time, action_address, action):
    '''
    action_time should be formatted as 'HH:MM:SS'.
    Set action_time to 'sunrise' or 'sunset' to automatically calculate the appropriate time.
    '''
    # Daily events are just interval events that are automatically calculated.
    if type(action) is int:
      if action not in range(0,256): return "Invalid level"
    elif action not in ['toggle']: return "Invalid action"
    if action_time == 'sunrise':
      print ('Calculate sunrise...')
      seconds = 4
    elif action_time == 'sunset':
      print ('Calculate sunset...')
      seconds = 4
    else:
      act_time = action_time.split(':')
      seconds = 3600*int(act_time[0]) + 60*int(act_time[1]) + int(act_time[2])
      now = localtime()
      now_sec = 3600*int(now.tm_hour) + 60*int(now.tm_min) + int(now.tm_sec)
      interval = seconds - now_sec
      if interval < 0: interval += 3600*24
      #print ('Wait for %d seconds' % interval)
    # Create a new event
    event = LightingEvent('daily', interval)
    event.events_remaining = 'Inf'
    if type(action) is int:
      event.action = 'on'
      event.level = action
    else:
      event.action = action
    event.to_address = action_address
    # Create new timer for this event
    timer = threading.Timer(interval, self.timer_handler, [event])
    self.timer_threads.append(timer)
    timer.start()
    return "OK"
    
    
  def timer_handler(self, event):
    '''
    Responsible for handling event timer operations.
    '''
    if event.type in ['interval','daily']:
      # This is run after an interval event expires.
      if type(event.events_remaining) is int: event.events_remaining -= 1
      if event.events_remaining != 0:
        # Reschedule the event
        if event.type == 'daily': event.interval = 3600*24
        timer = threading.Timer(event.interval, self.timer_handler, [event])
        self.timer_threads.append(timer)
        timer.start()
      self.action_handler(event)
    elif event.type == 'trigger':
      # This is run after a trigger event occurs.
      timer = threading.Timer(event.interval, self.action_handler, [event])
      self.timer_threads.append(timer)
      timer.start()
            
  
  def action_handler(self, event):
    '''
    Handles the actions for timed events.
    '''
    if event.action == 'toggle':
      self.toggle(event.to_address)
    elif event.action == 'on':
      self.setLevel(event.to_address, event.level, usePercent=False)
    elif event.action == 'off':
      self.setLevel(event.to_address, 0)
    elif event.action == 'callback':
      # Call the user specified function given by 'to_address' field. 
      event.to_address(event)
    elif event.action == 'update':
      self.getLevel(event.to_address)
    elif event.action == 'update_all':
      self.getLevel(event.to_address)
      # Find device position in dev list
      devInd = self.getIndexByAddress(event.to_address)
      # Increment index until we find a valid device type
      devType = None
      while devType not in ['Dimmer','Switch']:
        if devInd == self.numDevices()-1:
          devInd = 0
        else: devInd += 1
        devType = self.getTypeByIndex(devInd)
      # Set next address to update
      event.to_address = self.getAddressByIndex(devInd)
      
    
class deviceFile:
  '''
  Handles XML device file access.  This is normally instantiated by a PLM 
  object.
  '''
  def __init__(self, filename):
    try:
      if filename is not None:
        try:
          file = open(filename)
        except IOError:
          raise Exception('Cannot find device (XML) file: %s.' % filename)
        else:
          self.doc = parse(file)
          file.close()
          self.filename = filename
          self.dev = self.doc.getElementsByTagName('Device')
          self.numDevices = self.dev.length
      else:
        self.filename = None
        self.numDevices = 0
    except:
      raise
      #self.filename = None
      
  
  def findDevAddress(self, devName):
    '''
    Returns the device address and index given the device name, short name,
    or address string if found in the device file. Otherwise, returns None.
    '''
    addrList = None
    devIndex = None
    if self.filename is not None:
      for devIndex in range(self.numDevices):
        dimDev = self.dev.item(devIndex)
        # Get device name
        nameEl = dimDev.getElementsByTagName('name')
        nameData = nameEl.item(0)
        nameStr = nameData.firstChild.data.upper()
        # Get device short name
        shortNameEl = dimDev.getElementsByTagName('shortName')
        shortNameData = shortNameEl.item(0)
        try:
          shortName = shortNameData.firstChild.data.upper()
        except AttributeError:
          # shortName probably doesn't (and needn't) exist
          shortName = 'dummy'
        if ((shortName == devName.upper()) or (nameStr == devName.upper())):
          # Get device address
          addrEl = dimDev.getElementsByTagName('address')
          addrData = addrEl.item(0)
          addrStr = addrData.firstChild.data
          addrList = self.getAddrList(addrStr)
          break
      if addrList is None: devIndex = None
    return addrList, devIndex


  def findResponders(self, address, button):
    '''
    Scans the device file for responders to an address/button combination.
    Returns the address(es) if found, empty list otherwise.
    '''
    if type(address) is not list: return 'Address type must be list'
    respList = []
    if self.filename is not None:
      for devIndex in range(self.numDevices):
        dimDev = self.dev.item(devIndex)
        # Get device name
        respEl = dimDev.getElementsByTagName('respondsToBtn')
        try:
          for items in respEl:
            respStr = items.firstChild.data.upper()
            addr_btn = respStr.split(':')
            addr = [int(k,16) for k in addr_btn[0].split('.')]
            btn = int(addr_btn[1])
            if addr == address:
              if btn == button:
                respList.append(self.getAddressByIndex(devIndex))
        except AttributeError:
          pass
    # Devices always respond to their own button 1
    if button == 1: respList.append(address)
    return respList


  def getAddressByIndex(self, index):
    '''
    Returns the device address given an index into the device list.
    '''
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      addrEl = dimDev.getElementsByTagName('address')
      addrData = addrEl.item(0)
      addrStr = addrData.firstChild.data
      addrList = self.getAddrList(addrStr)
      return addrList
    else:
      return None


  def getIndexByAddress(self, address):
    '''
    Returns an index into the device list given an address.
    '''
    if type(address) is list:
      if self.filename is not None:
        for devIndex, device in enumerate(self.doc.getElementsByTagName('address')):
          addrStr = device.firstChild.data
          addrList = self.getAddrList(addrStr)
          if addrList == address:
            return devIndex
      return None
    else:
      return "Address type must be list"


  def getNameByIndex(self, index):
    '''
    Returns the name of the device with the specified index.
    '''
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      nameEl = dimDev.getElementsByTagName('name')
      nameData = nameEl.item(0)
      nameStr = nameData.firstChild.data
      return str(nameStr)
    else: return None


  def getShortNameByIndex(self, index):
    '''
    Returns the short name of the device with the specified index.
    '''
    nameStr = None
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      nameEl = dimDev.getElementsByTagName('shortName')
      nameData = nameEl.item(0)
      try:
        nameStr = nameData.firstChild.data
      except AttributeError: pass
    return nameStr


  def getLevelByIndex(self, index):
    '''
    Returns the level status of the device with the specified index.
    '''
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      nameEl = dimDev.getElementsByTagName('level')
      levelData = nameEl.item(0)
      try:
        levelStr = int(levelData.firstChild.data)
      except ValueError:
        levelStr = None
      return levelStr
    else:
      return None


  def getTypeByIndex(self, index):
    '''
    Returns the device type (<devType> tag) of the device with the specified
      index.
    '''
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      nameEl = dimDev.getElementsByTagName('devType')
      typeData = nameEl.item(0)
      return str(typeData.firstChild.data)
    else:
      return None      


  def getGroupByIndex(self, index):
    '''
    Returns the group number (<group> tag) of the device with the specified
      index.  Returns None if there is no group number.
    '''
    if 0 <= index < self.numDevices:
      dimDev = self.dev.item(index)
      nameEl = dimDev.getElementsByTagName('group')
      typeData = nameEl.item(0)
      if typeData is not None:
        return str(typeData.firstChild.data)
      else: 
        return None
    else:
      return None


  def getAddrList(self, addrStr):
    '''
    Converts a device file address to a list.  Handles non-Insteon addresses.
    '''
    try:
      addrList = [int(addrStr[0:2],16),int(addrStr[3:5],16),int(addrStr[6:8],16)]
    except ValueError:
      addrList = [addrStr]
    return addrList


  def updateLevel(self, index, level):
    '''
    Updates the level in the device file using either index or address.
    Levels are always given as direct levels and not percent.    
    '''
    if (type(index) is int): # and (type(level) is int):
      dimDev = self.dev.item(index)
      levelEl = dimDev.getElementsByTagName('level')
      levelData = levelEl.item(0)
      levelData.firstChild.data = level
      self.updateXML()
      
    
  def updateXML(self):
    file = open(self.filename,'w')
    self.doc.writexml(file)
    file.close()
    

class SerialPacket():
  '''
  A standard serial message structure.
  '''
  def __init__(self,msg,recv_len=0):
    self.msg = msg
    self.recv_len = recv_len

    
class SerialRxThread(threading.Thread):
  '''
  Receives all serial messages from the PLM.  This is done in a thread so it
  can do blocking reads.
  '''
  
  # Expected length when serial packet has None type length 
  response_len = {
    0x50 : 11,
    0x51 : 25,
    0x52 : 4,
    0x54 : 3,
    0x53 : 10,
    0x57 : 10,
    0x60 : 9,
    0x62 : 9,
    0x63 : 5,
    0x69 : 3,
    0x6A : 3}
  
  
  def __init__(self, plm):
    threading.Thread.__init__(self)
    self.setDaemon(True)
    self.plm = plm
    self.done = False
    self.num_resets = 0
    self.start()
    
  
  def shutdown(self):
    if self.done: return
    self.done = True
    #self.join()

    
  def reset(self,caller=None):
    '''
    Resets the serial loop to its initial state.
    '''
    if caller is not None: rst_msg = 'Reset requested by: ' + caller + '\n'
    else: rst_msg = 'Resetting...\n'

    try:
      ow = self.plm.s.outWaiting()
    except AttributeError:
      # outWaiting is not supported in Linux.
      ow = 0
      pass
   
    log_msg = 'Partial data received: {0:s}\n' \
      'Expected length: {1:d}\n' \
      'Actual length: {2:d}\n' \
      'Items in send queue: {3:d}\n' \
      'Items in recv queue: {4:d}\n' \
      'Characters in receive buffer: {5:d}\n' \
      'Characters in send buffer: {6:d}\n' \
      'Items in async queue: {7:d}\n' \
      'Total number of resets: {8:d}' \
      .format(self.plm.list_to_hex(self.data), \
              self.expected_len, \
              len(self.data), \
              self.plm.send_q.qsize(), \
              self.plm.recv_q.qsize(), \
              self.plm.s.inWaiting(), \
              ow, \
              self.plm.async_q.qsize(), \
              self.num_resets+1)
    self.plm.log(rst_msg + log_msg)
    
    self.data = []
    self.first_timeout = True
    self.expected_len = 11
    self.plm.send_q.queue.clear()
    self.plm.recv_q.queue.clear()
    self.plm.async_q.queue.clear()
    self.plm.s.flushInput()
    self.plm.s.flushOutput()
    self.num_resets += 1

  
  def run (self):
    '''
    Main serial thread.
    '''
    self.data = []
    self.first_timeout = True
    self.expected_len = 11

    
    extra_bytes_flag = False
    extra_bytes = []
    
    while not self.done:
      # Check serial receive buffer for new data
      try:
        recv_byte = self.plm.s.read(1)
        if recv_byte:
          #print(ord(recv_byte))
          self.first_timeout = False
          self.data.append(ord(recv_byte))
          if len(self.data) == 6 and self.data[1] == 0x62:
            # Check message flags for extended message bit
            if (self.data[5] & 0x10):
              self.expected_len = 23
            else:
              self.expected_len = 9 
          elif len(self.data) == 2:
            # Determine response length based on second byte in response
            if 1: #not self.data[1] in [0x57, 0x69, 0x6a]:
              try:
                self.expected_len = self.response_len[self.data[1]]
              except KeyError:
                print ("Unknown response.  Fix response_len dictionary")
                print self.data
          elif len(self.data) == 1:
            if self.data[0] == 0x02:
              if extra_bytes_flag: 
                extra_bytes_flag = False
                self.plm.log('Extra byte(s): %s' % self.plm.list_to_hex(extra_bytes))
                extra_bytes = []
              if not self.plm.send_q.empty():
                sp = self.plm.send_q.get()
                if type(sp) is list:
                  print ('SP is: ')
                  print (sp)
                if sp.recv_len is not None:
                  self.expected_len = sp.recv_len
            else:
              # First byte was not 0x02
              extra_bytes_flag = True
              extra_bytes.append(ord(recv_byte))
              self.data = []
          if len(self.data) >= self.expected_len:
            # Done receiving. Determine if message is expected or asynchronous.
            try:
              if self.data[1] == 0x50 or self.data[1] == 0x51:
                '''
                 Response message type. Compare with expected address to avoid
                   responding with a message that is actually asynchronous.
                   This also compares message flags because sometimes devices
                   respond to standard messages with an extended message and 
                   vice-versa
                 '''
                if sp.msg[2:5] == self.data[2:5]:
                  self.plm.recv_q.put(SerialPacket(self.data))
                else:  
                  self.plm.async_q.put(SerialPacket(self.data))
              else:
                # Not asychronous or response type.
                self.plm.recv_q.put(SerialPacket(self.data))
              del(sp)
            except (AttributeError, UnboundLocalError, TypeError):
              self.plm.async_q.put(SerialPacket(self.data))
            # Clear buffered data
            self.data = []
        elif len(self.data) != 0:
          '''
          Did not receive the full message before timeout.
          Allow two timeout periods to elapse to handle the case 
          where a command is issued near the end of the timeout 
          period causing it to be too short.  Actual timeout 
          period is variable from s.timeout (min) to 
          2*s.timeout (max)
          '''
          if self.first_timeout: 
            self.first_timeout = False
          else:
            # Remove queue object due to serial timeout
            self.reset('Serial_RX timeout')
      except (serial.SerialException, ValueError):
        self.done = True
      except:
        self.done = True
        raise



class AsyncEventThread(threading.Thread):
  '''
  Handles asynchronous messages from Insteon devices.
  '''
  def __init__(self, plm):
    threading.Thread.__init__(self)
    self.setDaemon(True)
    self.plm = plm
    self.last_cmd = None
    self.last_addr = None
    self.start()
    
  
  def run (self):
    while True:
      msg_q = self.plm.async_q.get()
      self.parse_async_event(msg_q.msg)
      # Execute callback functions
      for cb in self.plm.async_callbacks:
        cb_func = cb[0]
        event = cb[1]
        if event is None:
          '''
          Callback is executed for any async event and receives the contents
            of the message buffer.
          '''
          cb_func(msg_q.msg)
        else:
          data = msg_q.msg
          if data[1] == self.plm.messages['x10Recv']:
            from_addr = [data[2] for k in range(3)] # X10 address repeated 3 times
            to_addr = None
            btn = None
            flags = None
            cmd1 = None
            cmd2 = None
            print('X10 message from: {0:s}'.format(from_addr))
          else:
            try:
              from_addr = data[2:5]
              to_addr = data[5:8]
              btn = data[7]
              flags = data[8]
              cmd1 = data[9]
              cmd2 = data[10]
            except IndexError:
              print ('Invalid data in msg')
              print data
          # Determine if callback function should be called
          addr = self.plm.address_to_list(event.from_address)
          if addr == from_addr or addr is None:
            if event.from_cmd == cmd1 or event.from_cmd is None:
              if event.from_button == btn or event.from_button is None:
                flags_upper = flags & 0xF0
                if flags_upper == 0xC0:
                  # Call the callback function with event info.
                  cb_func(event)
            
            
  def parse_async_event(self, data):
    '''
    Updates the device file following asynchronous events.
    '''
    try:
      from_addr = data[2:5]
      to_addr = data[5:8]
      btn = data[7]
      flags = data[8]
      cmd1 = data[9]
      cmd2 = data[10]
    except IndexError: return

    self.plm.log('RX_ASYNC : %s' % self.plm.list_to_hex(data))
    
    # Check for group cleanup messages
    BROADCAST = 0x80
    GROUP_CLEANUP = 0x40
    GROUP_BROADCAST = 0xC0
    EXTENDED_MSG = 0x10
    DIRECT = 0x00
  
    flags_upper = flags & 0xF0
    if flags_upper == GROUP_BROADCAST:
      if cmd1 == self.plm.commands['ON'] or cmd1 == self.plm.commands['OFF'] or \
          cmd1 == self.plm.commands['stopChange']:
        for dev in self.plm.devices.findResponders(from_addr, btn):
          # Get the device type.  If GarageIO then do not poll for status.          
          devType = self.plm.getTypeByIndex(self.plm.getIndexByAddress(dev))
          if devType == 'GarageIO': 
            if cmd1 == self.plm.commands['ON']:
              self.plm.updateLevel(dev,255)
            if cmd1 == self.plm.commands['OFF']:
              self.plm.updateLevel(dev,0)
          else:
            sleep(4.0) # FIXME Should queue an update here instead of sleeping.
            if len(dev):
              self.plm.updateLevel(dev,self.plm.getLevel(dev,False))
            else:
              print('Invalid responder for from_addr = {0} and btn = {1}'.format(from_addr,btn))
      '''
      elif flags_upper == GROUP_CLEANUP:
        if cmd1 == self.plm.commands['ON'] or cmd1 == self.plm.commands['OFF'] or \
            cmd1 == self.plm.commands['stopChange']:
          for dev in self.plm.devices.findResponders(from_addr, cmd2): #cmd2 is button
            #self.plm.updateLevel(dev,255)
            self.plm.updateLevel(dev,self.plm.getLevel(dev,False))
      '''  

    return
    

class ServerThread(threading.Thread):
  '''
  Waits for a client to issue commands via a UDP socket

  Client example:
  
    import socket
    HOST_IP = '127.0.0.1'
    PORT = 52006
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto("setLevel('room', 50)", (HOST_IP, PORT))
  '''
  
  def __init__(self, plm, PORT=52006):
    threading.Thread.__init__(self)
    self.setDaemon(True)
    self.done = False
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.sock.settimeout(0.5)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
      self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
      self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, 1)
    except AttributeError:
      pass # Some systems don't support SO_REUSEPORT
    try:    
      self.sock.bind(('', PORT))
    except socket.error:
      # Address already in use error
      raise
    else:
      self.plm = plm
      self.start()

  def shutdown(self):
    if self.done: return
    self.done = True
    self.join()

  def run (self):
    safe_list = ['self','self.plm']
    safe_dict = dict([ (k, locals().get(k, None)) for k in safe_list ])
    safe_dict['True'] = True;
    safe_dict['False'] = False;
    while not self.done:
      try:
        data, addr = self.sock.recvfrom(1024)
      except socket.timeout:
        pass
      else:
        try:
          '''
          Execute the received string as if it were a 
          command, then send back the response as a string.
          Commands are limited to those in the safe list.
          '''
          cmd_resp = eval('self.plm.' + data, {"__builtins__":None}, safe_dict)
          self.sock.sendto(str(cmd_resp)+'\n',(addr))
        except (AttributeError, NameError, SyntaxError):
          msg = 'Invalid network client command: %s' % data
          self.sock.sendto(msg+'\n',(addr))


class LightingEvent:
  def __init__(self, type, interval):
    self.type = type # time_interval | daily | triggered
    self.interval = interval
    self.creation_time = asctime(gmtime())
    self.events_remaining = None # Inf
    self.action = None # toggle | level | callback
    self.from_address = None # Insteon address with cause
    self.from_button = None # Button number
    self.from_cmd = None # Command number
    self.to_address = None # Insteon address to effect
    self.to_button = None # Button number
    self.level = None # light level
    self.rate = None # change rate
    self.flags = None # sunrise_lookup | sunset_lookup <= Schedules next event based on sunrise/set.
    self.callback = None # Callback function name
    
  
