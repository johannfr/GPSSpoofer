#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import threading
import time
import Queue
import requests # Apache requests
import json
from math import *
import random

ROUTE_URL = "http://www.yournavigation.org/api/1.0/gosmore.php?format=geojson&flat=%f&flon=%f&tlat=%f&tlon=%f&v=%s&fast=1&layer=mapnik"


R = 6371.0
DRIVING = 0
WALKING = 1


class Spoofer(threading.Thread):

    def __init__(self, initialLat, initialLon):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.currentLat = initialLat
        self.currentLon = initialLon

        self.current_travel_mode = DRIVING
        self.travelling = False
        self.currentRoute = []
        self.currentRouteSegmented = []
        self.currentRouteLock = threading.Lock()
        self.currentLeg = []
        self.currentLegLock = threading.Lock()

        self.current_location_listeners = []

    def add_current_location_listener(self, listener):
        self.current_location_listeners.append(listener)

    def getDistance(self, fromLat, fromLon, toLat, toLon):
        radFromLat = radians(fromLat)
        radToLat = radians(toLat)
        deltaLat = radians(toLat-fromLat)
        deltaLon = radians(toLon-fromLon)

        a = sin(deltaLat/2) * sin(deltaLat/2) + cos(radFromLat) * \
        cos(radToLat) * sin(deltaLon/2) * sin(deltaLon/2)
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        d = R * c
        return abs(d)


    def waypoint(self, radFromLat, radFromLon, theta, d):
        radToLat = asin(sin(radFromLat) * cos(d/R) + cos(radFromLat) * \
            sin(d/R) * cos(theta))
        radToLon = radFromLon + atan2(sin(theta) * sin(d/R) * cos(radFromLat),
            cos(d/R) - sin(radFromLat) * sin(radToLat))
        radToLon = (radToLon + 3.0 * pi) % (2.0 * pi) - pi
        return (degrees(radToLat), degrees(radToLon))

    def getIntermediatePoints(self, fromLat, fromLon, toLat, toLon, stepsize):
        intermediatePoints = []
        try:
            radFromLat, radFromLon = (radians(fromLat), radians(fromLon))
            radToLat, radToLon = (radians(toLat), radians(toLon))

            d = R * acos( sin(radFromLat) * sin(radToLat) + cos(radFromLat) * \
                cos(radToLat) * cos(radToLon - radFromLon) )
            theta = atan2( sin(radToLon - radFromLon) * cos(radToLat),
                cos(radFromLat) * sin(radToLat) - sin(radFromLat) * cos(radToLat) *\
                cos(radToLon - radFromLon) )

            i = 0.0
            while i < abs(d):
                intermediatePoints.append(self.waypoint(radFromLat, radFromLon, theta, i))
                i = i + stepsize
        except ValueError:
            print "ValueError", fromLat, fromLon, toLat, toLon, stepsize

        return intermediatePoints


    def getRoute(self, fromLat, fromLon, toLat, toLon, v="motorcar"):
        result = requests.get(ROUTE_URL%(fromLat, fromLon, toLat, toLon, v))
        if result.status_code == 200:
            method = "DRIVING"
            if v != "motorcar":
                method = "WALKING"
            jsonResult = json.loads(result.text)
            return [(t[1], t[0], method) for t in jsonResult["coordinates"]]
        return []

    def goto(self, toLat, toLon):
        # print "Goto: %0.9f, %0.9f"%(toLat, toLon)
        walking_preamble = []
        walking_postamble = []
        newRoute = self.getRoute(
            self.currentLat,
            self.currentLon,
            toLat,
            toLon)

        if len(newRoute) < 1:
            for l in self.current_location_listeners:
                try:
                    error_message = """
                    <div id="content" style="width: 220px; height: 70px;">
                    <div id="siteNotice">
                    </div>
                    <div id="bodyContent">
                    <p><b>Villa:</b> Engin leið fannst.</p>
                    <p>Prófaðu að setja endapunkt nær vegi.</p>
                    </div>
                    </div>
                    """
                    l.send_error_message(error_message)
                except AttributeError:
                    self.current_location_listeners.remove(l)
            return

        if self.getDistance(
            self.currentLat,
            self.currentLon,
            newRoute[0][0],
            newRoute[0][1]
        ) * 1000.0 > 0.5:
            #walking_preamble = self.getRoute(
            #    self.currentLat,
            #    self.currentLon,
            #    newRoute[0][0],
            #    newRoute[0][1],
            #    "foot"
            #)
            if len(walking_preamble) < 1:
                walking_preamble = [
                    (self.currentLat, self.currentLon, "WALKING"),
                    (newRoute[0][0], newRoute[0][1], "WALKING")
                ]

        if self.getDistance(
            toLat,
            toLon,
            newRoute[-1][0],
            newRoute[-1][1]
        ) * 1000.0 > 3.0:
            #walking_postamble = self.getRoute(
            #    newRoute[-1][0],
            #    newRoute[-1][1],
            #    toLat,
            #    toLon,
            #    "foot"
            #)
            if len(walking_postamble) < 1:
                walking_postamble = [
                    (newRoute[-1][0],  newRoute[-1][1], "WALKING"),
                    (toLat, toLon, "WALKING")
                ]

        self.currentRouteSegmented = [walking_preamble, newRoute, walking_postamble]
        self.travelling = False
        self.currentRouteLock.acquire()
        self.currentRoute = []
        self.currentRoute.extend(walking_preamble)
        if len(walking_preamble) > 2:
            for i in range(15):
                self.currentRoute.extend([walking_preamble[-1]])
        self.currentRoute.extend(newRoute)
        if len(newRoute) > 2:
            for i in range(15):
                self.currentRoute.extend([newRoute[-1]])
        self.currentRoute.extend(walking_postamble)
        self.currentRouteLock.release()
        self.currentLegLock.acquire()
        self.currentLeg = []
        self.currentLegLock.release()
        for l in self.current_location_listeners:
            try:
                l.send_current_route(self.currentRouteSegmented)
            except AttributeError:
                self.current_location_listeners.remove(l)
        self.travelling = True

    def run(self):
        while True:
            if len(self.currentRoute) + len(self.currentLeg) > 0:
                if len(self.currentLeg) == 0:
                    self.currentRouteLock.acquire()
                    try:
                        nextRoutePoint = self.currentRoute[0]
                        self.currentRoute = self.currentRoute[1:]
                    except IndexError:
                        print "Info: Empty route list"
                    self.currentRouteLock.release()
                    self.currentLegLock.acquire()
                    # FIXME: Check if walking or driving
                    if nextRoutePoint[2] == "DRIVING":
                        speed = (((60 + random.randrange(-20, 20)) * 1000.0) / 3600.0) / 1000.0
                    else:
                        speed = 1.388/1000.0
                    self.currentLeg = self.getIntermediatePoints(
                        self.currentLat,
                        self.currentLon,
                        nextRoutePoint[0],
                        nextRoutePoint[1],
                        speed)
                    self.currentLegLock.release()

                if len(self.currentLeg) < 1:
                    continue
                self.currentLegLock.acquire()
                nextLegPoint = self.currentLeg[0]
                self.currentLeg = self.currentLeg[1:]
                self.currentLegLock.release()
                self.currentLat, self.currentLon = nextLegPoint
            for l in self.current_location_listeners:
                try:
                    l.send_current_location(self.currentLat, self.currentLon)
                    if not hasattr(l, "initial_route_sent"):
                        l.send_current_route(self.currentRouteSegmented)
                        l.initial_route_sent = True
                except AttributeError:
                    self.current_location_listeners.remove(l)
            # print "Lat,Lon: %0.9f, %0.9f"%(self.currentLat, self.currentLon)
            time.sleep(1)


if __name__ == "__main__":
    # Heima 64.138865, -21.961221
    # Siminn 64.135782, -21.877460
    spoofer = Spoofer(64.135782, -21.877460)
    spoofer.start()
    # print spoofer.getRoute(64.138865, -21.961221)
    #print spoofer.getDistance(52.215676, 5.963946, 52.2573, 6.1799)
    # print spoofer.getIntermediatePoints(-33, -71.6, 31.4, 121.8, 2000)
    spoofer.goto(64.138865, -21.961221)
    time.sleep(10)
    spoofer.goto(64.135782, -21.877460)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            # TODO Clean up
            sys.stdout.write("Exiting!\n")
            sys.stdout.flush()
            break
