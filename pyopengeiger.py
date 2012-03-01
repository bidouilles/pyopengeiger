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
import subprocess
import os

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

#
# RRDTool
#
create = """%s create %s --step '60' 'DS:cpm:GAUGE:120:0:10000' 'DS:microsievert:GAUGE:120:0:100' 'RRA:LAST:0.5:1:288' 'RRA:AVERAGE:0.5:1:2880' 'RRA:AVERAGE:0.5:10:4464' 'RRA:MIN:0.5:10:4464' 'RRA:MAX:0.5:10:4464'"""

update = "%s update opengeiger.rrd N:%d:%.3f"

graph = """%s graph %s --start -1h --end now --width=620 --height=200 --lower-limit 0 --vertical-label "CPM" DEF:average1=%s:cpm:AVERAGE 'DEF:average1wk=%s:cpm:AVERAGE:start=-1w' DEF:average2=%s:microsievert:AVERAGE LINE2:average1#00FF00:'CPM Avg'"""

graphPrints = """'GPRINT:average1:LAST:Last CPM\: %2.0lf' 'GPRINT:average2:LAST:Last uSv/h\: %2.3lf\j'"""

graphTrend = """'VDEF:D2=average1,LSLSLOPE' 'VDEF:H2=average1,LSLINT' 'CDEF:avg1=average1,POP,D2,COUNT,*,H2,+' 'LINE2:avg1#FFBB00:Trend since 1h:dashes=10'"""

graphTrend1wk = """'VDEF:D3=average1wk,LSLSLOPE' 'VDEF:H3=average1wk,LSLINT' 'CDEF:avg1wk=average1wk,POP,D3,COUNT,*,H3,+' 'LINE2:avg1wk#0077FF'"""

def UpdateRRDTool(rrdtool, rrddb, rrdpng, field1, field2):
   cmd = update % (rrdtool, field1, field2)
   subprocess.call(cmd, shell=True)

   cmd = graph % (rrdtool, rrdpng, rrddb, rrddb, rrddb)
   cmd += " "+graphPrints
   cmd += " "+graphTrend
   subprocess.call(cmd, shell=True)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    dev = usb.core.find(idVendor = ID_VENDOR, idProduct = ID_PRODUCT)
    # Check if opengeiger device is available
    if dev is None:
       raise ValueError('Device not found')

    # Load config settings
    config = ConfigParser.ConfigParser()
    config.read(".pyopengeiger")

    # Make sure rrd database is ready (if needed)
    if "rrdtool" in config.sections():
      rrdtool = config.get('rrdtool', 'rrdTool')
      rrddb = config.get('rrdtool', 'rrdDb')
      rrdpng = config.get('rrdtool', 'rrdPng')
      if not os.path.exists(rrddb):
        cmd = create % (rrdtool, rrddb)
        subprocess.call(cmd, shell=True)
       
    # Start measurements
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

         if "rrdtool" in config.sections():
           UpdateRRDTool(rrdtool, rrddb, rrdpng, CPM, usvh)

         time.sleep(60)
       except:
         print "Failed to update servers, retry in 1 second ..."
         time.sleep(1)
         pass

