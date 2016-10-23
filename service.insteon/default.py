import xbmc
import xbmcaddon
import xbmcgui
import os
import json
import re
import datetime
import time
import pylights

addon                  = xbmcaddon.Addon()
dialog                 = xbmcgui.Dialog()
addon_id               = addon.getAddonInfo('id')
addon_folder           = xbmc.translatePath("special://profile/addon_data/"+addon_id)
log_file               = os.path.join(addon_folder, "insteon.log")
port                   = addon.getSetting('port')
devices                = os.path.join(addon_folder, "devices.xml")
   
def translation(id):
    """Get the translated string from the languages directory based on the id"""
    
    return addon.getLocalizedString(id).encode('utf-8')

def log(message):
    logger = open(log_file, 'a')
    logger.write(message + "\n")
    logger.close()

def parameters_string_to_dict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict
    
def adjustDimmer(address, dim_adjust):
    val = p.getLevel(address)
    m = re.match('\d+', str(val))
    if m:
        log("Dimmer: " + address + " reports value: " + str(val))
        set_val = int(val) + dim_adjust
        if set_val < 0:
            set_val = 0
        elif set_val > 100:
            set_val = 100
        time.sleep(1)
        if (int(val) != set_val):
            p.setLevel(address, set_val)
            time.sleep(1)
            log("Adjusting Dimmer: " + address + " to value " + str(set_val))
        else:
            log("No need to adjust Dimmer: " + address + " already at " + str(set_val))
          
class XBMCPlayer( xbmc.Player ):

    def __init__( self, *args ):
        pass

        
    def onPlayBackStarted(self):
        if self.isPlayingVideo():
            log("Kodi playback started")

            # Pots
            p.setLevel('42.22.B8', 0)
            
            time.sleep(1)
            
            #Tray
            p.setLevel('42.20.F8', 30)        
            
            xbmcgui.Window(10000).setProperty("insteon-video-playing", "true" )
            
            
    def onPlayBackEnded( self ):
        if xbmcgui.Window(10000).getProperty("insteon-video-playing") == "true":
            xbmcgui.Window(10000).setProperty("insteon-video-playing", "false" )
            log("Kodi playback ended")
            # Pots
            p.setLevel('42.22.B8', 0)
            
            time.sleep(1)
            
            #Tray
            p.setLevel('42.20.F8', 100)
      
      
    def onPlayBackPaused( self ):
        if self.isPlayingVideo():
            log("Kodi playback paused")
            # Pots
            p.setLevel('42.22.B8', 20)
            
            time.sleep(1)
            
            #Tray
            p.setLevel('42.20.F8', 100)

    def onPlayBackResumed( self ):
        if self.isPlayingVideo():
            log("Kodi playback resumed")
            # Pots
            p.setLevel('42.22.B8', 0)
            
            time.sleep(1)
            
            #Tray
            p.setLevel('42.20.F8', 30)
            
    def onPlayBackStopped( self ):
        if xbmcgui.Window(10000).getProperty("insteon-video-playing") == "true":
            xbmcgui.Window(10000).setProperty("insteon-video-playing", "false" )
            log("Kodi playback stopped")
            # Pots
            p.setLevel('42.22.B8', 0)
            
            time.sleep(1)
            
            #Tray
            p.setLevel('42.20.F8', 100)
    
# Start of script


xbmcgui.Window(10000).setProperty("insteon-video-playing", "false")
xbmcgui.Window(10000).setProperty("insteon-allon", "false")
xbmcgui.Window(10000).setProperty("insteon-alldim", "false")
xbmcgui.Window(10000).setProperty("insteon-allbrighter", "false")
xbmcgui.Window(10000).setProperty("insteon-alldimmmer", "false")
                     
player = XBMCPlayer()
monitor = xbmc.Monitor()

log("Kodi Starting, insteon service attaching to Serial Port: " + port)
p = pylights.plm(port, device_cfg_filename=None)

while not monitor.abortRequested():
    # Insert code here to handle keybinds
    if xbmcgui.Window(10000).getProperty("insteon-alldimmer") == "true":
        xbmcgui.Window(10000).setProperty("insteon-alldimmer", "false")
        adjustDimmer('42.20.F8', -33)
        adjustDimmer('42.22.B8', -33)

        
    if xbmcgui.Window(10000).getProperty("insteon-allbrighter") == "true":
        xbmcgui.Window(10000).setProperty("insteon-allbrighter", "false")
        adjustDimmer('42.20.F8', 33)
        adjustDimmer('42.22.B8', 33)

        
    if xbmcgui.Window(10000).getProperty("insteon-allon") == "true":
        xbmcgui.Window(10000).setProperty("insteon-allon", "false")
        
        # Pots
        p.setLevel('42.22.B8', 100)
        
        time.sleep(1)
        
        #Tray
        p.setLevel('42.20.F8', 100)

        log("Request All On")
    if xbmcgui.Window(10000).getProperty("insteon-alldim") == "true":
        xbmcgui.Window(10000).setProperty("insteon-alldim", "false")

        # Pots
        p.setLevel('42.22.B8', 0)  
        
        time.sleep(1)
        
        #Tray
        p.setLevel('42.20.F8', 30)     

        log("Request All Dim")


    if monitor.waitForAbort(.04):
        break

log("Kodi Exiting")
p.close()