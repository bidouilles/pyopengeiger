#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright (C) 2011  Lionel Bergeret
#
# ----------------------------------------------------------------
# The contents of this file are distributed under the CC0 license.
# See http://creativecommons.org/publicdomain/zero/1.0/
# ----------------------------------------------------------------

import usb.util
import usb.legacy

import httplib, urllib, urllib2
import time, datetime
import ConfigParser

# opengeiger usb device information
ID_VENDOR = 0x20a0
ID_PRODUCT = 0x4176

# opengeiger requests definition
GM01A_RequestGetCPMperUsvh    = 0x00
GM01A_RequestGetCPM           = 0x01
GM01A_RequestGetTotalCount    = 0x02
GM01A_RequestGetIntervalCount = 0x03

# geiger tube convertion factor
usvh_per_cpm = 150.0 # Cs-137 1uSv/h (25cps/mR/h)

# ThingSpeak stream update
def UpdateThingspeak(apikey, field1, field2):
   params = urllib.urlencode({'field1': field1, 'field2': field2,'key': apikey})
   headers = {"Content-type": "application/x-www-form-urlencoded","Accept": "text/plain"}
   conn = httplib.HTTPConnection("api.thingspeak.com:80")
   conn.request("POST", "/update", params, headers)
   response = conn.getresponse()
   print ">", response.status, response.reason
   data = response.read()
   conn.close()

# Pachube stream update
def UpdatePachube(feedid, apikey, field1, field2):
   # Pachube API V2 and CSV data format
   opener = urllib2.build_opener(urllib2.HTTPHandler)
   request = urllib2.Request('http://api.pachube.com/v2/feeds/'+feedid+'/datastreams/0.csv?_method=put', "%d" % (field1))
   request.add_header('Host','api.pachube.com')
   request.add_header('X-PachubeApiKey', apikey)
   url = opener.open(request)
   request = urllib2.Request('http://api.pachube.com/v2/feeds/'+feedid+'/datastreams/1.csv?_method=put', "%0.3f" % (field2))
   request.add_header('Host','api.pachube.com')
   request.add_header('X-PachubeApiKey', apikey)
   url = opener.open(request)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    dev = usb.core.find(idVendor = ID_VENDOR, idProduct = ID_PRODUCT)
    # was it found?
    if dev is None:
       raise ValueError('Device not found')

    # Load config settings
    config = ConfigParser.ConfigParser()
    config.read(".pyopengeiger")

    while (True):
       # Collect the raw data
       result = dev.ctrl_transfer((usb.legacy.ENDPOINT_IN | usb.legacy.RECIP_DEVICE | usb.legacy.TYPE_VENDOR),
              GM01A_RequestGetCPM, 0, 0, 1, timeout = 5000)
       if len(result) != 1:
          continue

       # Extract CPM and compute usv/h
       CPM = result.tolist()[0]
       usvh = float(CPM/usvh_per_cpm)

       # Update streams
       print "%s - %d CPM %0.3f µSv/h" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), CPM, usvh)
       try:
         if "thingspeak" in config.sections():
           thingspeakAPIKey = config.get('thingspeak', 'apiKey')
           UpdateThingspeak(thingspeakAPIKey, CPM, usvh)

         if "pachube" in config.sections():
           pachubeFeedID = config.get('pachube', 'feedID')
           pachubeAPIKey = config.get('pachube', 'apiKey')
           UpdatePachube(pachubeFeedID, pachubeAPIKey, CPM, usvh)

         time.sleep(60)
       except:
         print "Failed to update servers, retry in 1 second ..."
         time.sleep(1)
         pass

