============
Magic Mirror
============

Setup
-----

HP x360 laptop which had a hinge to allow tablet mode like operation was very convenient for Magic Mirror setup. This allowed the display to be setup without opening up the laptop. Also additional cost of screen and or screen plus adapter was avoided. To avoid issues with using the built-in camera, sound, mic the native windows 10 with an upgrade to Pro (to allow for RDP) was used.

Goals
-----

* Setup the hardware for Magic Mirror

    * Acrylic mirror https://www.amazon.com/dp/B07CWG8DRK/ref=cm_sw_r_tw_dp_x_ohjuFbN4G54XM (12" x 18")
    * Strips of wood for the frame plus a thicker one for supporting a laptop at the bottom
    * Paint the wood strips black
    * Attach the acrylic sheet to the wood strips (Use a frame, gluing shows through the mirror)
    * Mount the laptop
    * Black craft tape to cover areas where there are gaps

* Windows 10 setup
    * Upgraded home to Pro version to enable Remote Desktop / RDP
    * Used physical keyboard plus mouse to fix the display mode to portrait only
    * Used a DOS script to run ``tscon.exe 2 /dest:console`` to let the display be on the screen once RDP session is done

* Next Steps
    * Script to turn display on/off
    * Determine server platform to run various commands based on sensor input
    * Use PIR or built-in camera to trigger display on/off
    * Train face recognition models
    * Display message based on who is in front
    * Integrate voice to the display
    * Integrate work calendar to the display
    * Add Minority Report interface

