# kodi_theatre_automation

This repository contains Kodi addons used for automation in a home theater.

service.aspect-ratio-changer

This addon connects via the RS-232 (serial port) to a Panasonic AE4000U projector and select a lens memory preset based on the Aspect ratio of the content.  The addon will (optionally) query IMDB to find the aspect ratio for the movie.  This is desireable because if the black bars are encoded within the video file the aspect ratio reported by Kodi will be incorrect.  Alternatively the user can override the AR of the title by selecting it via the menu.

There are three commands that can be tied to keypresses:
 - aspectratiochanger-set235 (Sets the projector AR to 2.35:1)
 - aspectratiochanger-set185 (Sets the prject AR to 1.85:1)
 - aspectratiocyhanger-showmenu (If the video playback is happening, bring up a menu to set an override of that title to the selected aspect ratio)
 
In order to access these commands, insert them into your keymaps file and bind to the desired key.  For example:

<f4>SetProperty(aspectratiochanger-set235, true, 10000)</f4>
<f5>SetProperty(aspectratiochanger-set185, true, 10000)</f5>
<f6>SetProperty(aspectratiochanger-showmenu, true, 10000)</f6>

service-insteon

This addon connects via the RS-232 (serial port) to an Insteon PowerLinc Modem (PLM).  Specifically I have tested with the 2413S.  The addon will set the light level of the Insteon dimmer upon video start/stop/pause/resume functions.  

Additionally keypresses can be bound to initiate specific lighting levels:

<f11>SetProperty(insteon-allon, true, 10000)</f11>
<f12>SetProperty(insteon-alldim, true, 10000)</f12>

Note:  This addon does not work with any of the Insteon HUBs - those are externally programmed via a REST api, and a kodi plugin exists elsewhere to work with that.

