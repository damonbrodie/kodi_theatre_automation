import xbmc
import xbmcaddon
import xbmcgui
import os
import json
import urllib2
import html5lib
import re
import serial
import datetime

addon                  = xbmcaddon.Addon()
dialog                 = xbmcgui.Dialog()
addon_id               = addon.getAddonInfo('id')
addon_folder           = xbmc.translatePath("special://profile/addon_data/"+addon_id)
movie_cache_folder     = os.path.join(addon_folder, "cache", "movies")
tv_cache_folder        = os.path.join(addon_folder, "cache", "tv")
movie_override_folder  = os.path.join(addon_folder, "ar_overrides", "movies")
tv_override_folder     = os.path.join(addon_folder, "ar_overrides", "tv")
restoreonpause         = addon.getSetting('restoreonpause')
useimdb                = addon.getSetting('useimdb')
log_file               = os.path.join(addon_folder, "aspectratiochanger.log")
base_url               = 'http://www.imdb.com/title/tt'
port                    = addon.getSetting('port')


# Set default values
baudrate = 9600
parity=serial.PARITY_NONE
stopbits=serial.STOPBITS_ONE
bytesize=serial.EIGHTBITS

pj_delay = 10

pj_codes = [ 
	chr(02)+"VXX:LMLI0=+00000"+chr(03),
	chr(02)+"VXX:LMLI0=+00001"+chr(03),
	chr(02)+"VXX:LMLI0=+00002"+chr(03),
	chr(02)+"VXX:LMLI0=+00003"+chr(03),
	chr(02)+"VXX:LMLI0=+00004"+chr(03),
	chr(02)+"VXX:LMLI0=+00005"+chr(03)
]
baudrate = 9600
parity=serial.PARITY_NONE
stopbits=serial.STOPBITS_ONE
bytesize=serial.EIGHTBITS
    
ser = serial.Serial(
    baudrate=baudrate,
    parity=parity,
    stopbits=stopbits,
    bytesize=bytesize,
	port=port
)

def changeProjectorSetting(ar):
    xbmcgui.Window(10000).setProperty("aspectratiochanger-next-setting", ar )

def getProjectorSetting(new_ar):
    float_new_ar = float(new_ar)
    if float_new_ar >= 0 and float_new_ar <= 1.6:
        val = int(addon.getSetting('pj_ar_4_3'))
        return val
    elif float_new_ar > 1.6 and float_new_ar <= 1.8:
        val = int(addon.getSetting('pj_ar_16_9'))
        return val
    elif float_new_ar > 1.8 and float_new_ar < 2.0:
        val = int(addon.getSetting('pj_ar_1.85_1'))
        return val
    elif float_new_ar > 2.0 and float_new_ar < 2.37:
        val = int(addon.getSetting('pj_ar_235_1'))
        return val
    elif float_new_ar > 2.37:
        val = int(addon.getSetting('pj_ar_240_1'))
        return val

    
def translation(id):
    """Get the translated string from the languages directory based on the id"""
    
    return addon.getLocalizedString(id).encode('utf-8')

def parameters_string_to_dict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict
    
def getMovieAspectRatio(imdb_id):
    # Check to see if there is a user generated override stored for this movie
    override_file = os.path.join(movie_override_folder, str(imdb_id)+".txt")
    if os.path.isfile(override_file):
        fh = open(override_file, 'r')
        ar = fh.read().rstrip()
        fh.close()
        logger = open(log_file, 'a')
        logger.write("User override AR found: " + str(imdb_id) + " aspect ratio: " + ar + "\n")
        logger.close()        
        return ar    
    
    if useimdb:
        cache_file = os.path.join(movie_cache_folder, str(imdb_id)+".txt")
        if not os.path.isfile(cache_file):
            url = base_url + str(imdb_id).zfill(7) + "/"
            got_page = False
            logger = open(log_file, 'a')
            logger.write("IMDB lookup at: " + url + "\n")
            logger.close() 
            req = urllib2.Request(url)
            response = None
            counter = 0
            # Try a few times to get the page from IMDB then give up
            while counter < 2 and not got_page:               
                try:
                    response = urllib2.urlopen(req, timeout=3)
                    got_page = True
                except:
                    counter += 1
            if got_page:
                the_doc = response.read()
                etree_document = html5lib.parse(the_doc, namespaceHTMLElements=False)
                divs  = etree_document.findall('.//div/[h4="Aspect Ratio:"]')
                if len(divs) > 0:
                    list =  divs[0].itertext()
                    for item in list:
                        m = re.search('\s+(\d*\.?\d*)\s+:',item)
                        if m:
                            ar = m.group(1)
                            fh = open(cache_file, 'w')
                            fh.write(ar)
                            fh.close()
                            logger = open(log_file, 'a')
                            logger.write("IMDB new lookup for title: " + str(imdb_id) + " aspect ratio: " + ar + "\n")
                            logger.close()
                            return ar
            else:
                logger = open(log_file, 'a')
                logger.write("Error with IMDB lookup: " + str(imdb_id) + "\n")
                logger.close()
                return None
        else:
            fh = open(cache_file, 'r')
            ar = fh.read()
            fh.close()
            logger = open(log_file, 'a')
            logger.write("IMDB cached lookup for title: " + str(imdb_id) + " aspect ratio: " + ar + "\n")
            logger.close()
            return ar
            return ar
    logger = open(log_file, 'a')
    logger.write("No Override found, IMDB disabled: " + url + "\n")
    logger.close()   
    return None


def saveMovieAspectRatio(imdb_id, ar):
    override_file = os.path.join(movie_override_folder, str(imdb_id)+".txt")
    fh = open(override_file, 'w')
    fh.write(str(ar))
    fh.close()
    logger = open(log_file, 'a')
    logger.write("Saving user preference for movie title: " + str(imdb_id) + " aspect ratio: " + ar + "\n")
    logger.close()

    
def saveTVAspectRatio(tvshow_id, ar):
    override_file = os.path.join(tv_override_folder, str(tvshow_id)+".txt")
    fh = open(override_file, 'w')
    fh.write(str(ar))
    fh.close()
    logger = open(log_file, 'a')
    logger.write("Saving user preference for tv title: " + str(tvshow_id) + " aspect ratio: " + ar + "\n")
    logger.close()

    
def getTVAspectRatio(tvshow_id):
    # Check to see if there is a user generated override stored for this TV show
    override_file = os.path.join(tv_override_folder, str(tvshow_id)+".txt")
    if os.path.isfile(override_file):
        fh = open(override_file, 'r')
        ar = fh.read()
        fh.close()
        return ar    
    
    return None
    
def getVideoID():
    filename = player.getPlayingFile()
    response = json.loads(xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Files.GetFileDetails","params":{"file":"%s","media":"video","properties":["imdbnumber","tvshowid"]},"id":1}' %filename.replace("\\", "\\\\")))
    if response.has_key('result') and response['result'].has_key('filedetails'):
        if response['result']['filedetails'].has_key('imdbnumber'):
            imdb_id_str = response.get('result').get('filedetails').get('imdbnumber').replace("tt","")
            if imdb_id_str is not None and imdb_id_str != "":
                imdb_id = int(imdb_id_str)
                return("movie", imdb_id)
        if response['result']['filedetails'].has_key('tvshowid'):
            tvshow_id = response.get('result').get('filedetails').get('tvshowid')
            if tvshow_id is not None and tvshow_id > 0 :
                return("tvshow", tvshow_id)
    return(None, None)
    

    
  
class XBMCPlayer( xbmc.Player ):

    def __init__( self, *args ):
        pass

        
    def onPlayBackStarted(self):
        if self.isPlayingVideo():
            logger = open(log_file, 'a')
            logger.write("Kodi playback started\n")
            logger.close()
            ar = None
            xbmcgui.Window(10000).setProperty("aspectratiochanger-video-playing", "true" )
            [video_type, id] = getVideoID()
            if video_type == 'movie' and id is not None and id > 0:
                ar = getMovieAspectRatio(id)
            elif video_type == 'tvshow' and id is not None and id > 0:
                ar = getTVAspectRatio(id)       
        
            # Fallback to the AR of the video file
            if ar is None or ar == 0:
                ar = xbmc.getInfoLabel('VideoPlayer.VideoAspect')
                logger = open(log_file, 'a')
                logger.write("Getting AR from Kodi: " + ar + "\n")
                logger.close()
                
            xbmcgui.Window(10000).setProperty("aspectratiochanger-current-ar", ar)
            changeProjectorSetting(ar)
            
            
    def onPlayBackEnded( self ):
        if xbmcgui.Window(10000).getProperty("aspectratiochanger-video-playing") == "true":
            xbmcgui.Window(10000).setProperty("aspectratiochanger-video-playing", "false" )
            logger = open(log_file, 'a')
            logger.write("Kodi playback ended\n")
            logger.close()
            changeProjectorSetting("1.85")
      
      
    def onPlayBackPaused( self ):
        if self.isPlayingVideo() and restoreonpause:
            logger = open(log_file, 'a')
            logger.write("Kodi playback paused\n")
            logger.close()
            changeProjectorSetting("1.85")


    def onPlayBackResumed( self ):
        if self.isPlayingVideo():
            curr_setting = xbmcgui.Window(10000).getProperty("aspectratiochanger-current-ar")
            if restoreonpause:
                logger = open(log_file, 'a')
                logger.write("Kodi playback resumed - the video AR is " + curr_setting + "\n")
                logger.close()
                changeProjectorSetting(curr_setting)
            
            
    def onPlayBackStopped( self ):
        if xbmcgui.Window(10000).getProperty("aspectratiochanger-video-playing") == "true":
            xbmcgui.Window(10000).setProperty("aspectratiochanger-video-playing", "false" )
            logger = open(log_file, 'a')
            logger.write("Kodi playback stopped - restoring to default AR\n")
            logger.close()
            changeProjectorSetting("1.85")

      
        
# Start of script
if not os.path.isdir(movie_cache_folder):
    os.makedirs(movie_cache_folder)
if not os.path.isdir(movie_override_folder):
    os.makedirs(movie_override_folder)
if not os.path.isdir(tv_cache_folder):
    os.makedirs(tv_cache_folder)
if not os.path.isdir(tv_override_folder):
    os.makedirs(tv_override_folder)

    
xbmcgui.Window(10000).setProperty("aspectratiochanger-showmenu", "false")
xbmcgui.Window(10000).setProperty("aspectratiochanger-video-playing", "false")
xbmcgui.Window(10000).setProperty("aspectratiochanger-current-ar", "1.85")
xbmcgui.Window(10000).setProperty("aspectratiochanger-set185", "false")
xbmcgui.Window(10000).setProperty("aspectratiochanger-set235", "false")
                     
player = XBMCPlayer()
monitor = xbmc.Monitor()

pj_action_time = datetime.datetime.now() - datetime.timedelta(seconds=pj_delay)
code = -1
last_code = -1

ar = None

while not monitor.abortRequested():
    # This code is called when a property is set via a key press in the custom keymaps code: 
    if xbmcgui.Window(10000).getProperty("aspectratiochanger-set235") == "true":
        xbmcgui.Window(10000).setProperty("aspectratiochanger-set235", "false")
        ar = "2.35"
    if xbmcgui.Window(10000).getProperty("aspectratiochanger-set185") == "true":
        xbmcgui.Window(10000).setProperty("aspectratiochanger-set185", "false")
        ar = "1.85"
    
    isplayingvideo = player.isPlayingVideo()
    # Show the context menu only if currently playing video and if the trigger (from a configured keypress) sets the correct property.
    if xbmcgui.Window(10000).getProperty("aspectratiochanger-showmenu") == "true":
        xbmcgui.Window(10000).setProperty("aspectratiochanger-showmenu", "false")
        if isplayingvideo:
            entries = []
            entries.append(translation(30204))
            entries.append(translation(30205))
            ret = dialog.select(translation(30200), entries)

            [video_type, id] = getVideoID()
            if video_type == "movie" and id is not None and id > 0:
                if ret == 0:
                    saveMovieAspectRatio(id, "1.85")
                    ar = "1.85"
                if ret == 1:
                    saveMovieAspectRatio(id, "2.35")
                    ar = "2.35"
            if video_type == "tvshow" and id is not None and id > 0:
                if ret == 0:
                    saveTVAspectRatio(id, "1.85")
                    ar = "1.85"
                elif ret == 1:
                    saveTVAspectRatio(id, "2.35")
                    ar = "2.35"
    # Invoked when player callbacks are called
    if xbmcgui.Window(10000).getProperty("aspectratiochanger-next-setting") != "":
        ar = xbmcgui.Window(10000).getProperty("aspectratiochanger-next-setting")
        xbmcgui.Window(10000).setProperty("aspectratiochanger-next-setting", "")
    if ar is not None and datetime.datetime.now() > pj_action_time:
        code = getProjectorSetting(float(ar))
        if last_code != code:
            ser.write(pj_codes[code])
            pj_action_time = datetime.datetime.now() + datetime.timedelta(seconds=pj_delay)
            last_code = code
            ar = None
    if monitor.waitForAbort(.04):
        break