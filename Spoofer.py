#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import threading
import time
import Queue
import requests # Apache requests
import json
from math import *

ROUTE_URL = "http://www.yournavigation.org/api/1.0/gosmore.php?format=geojson&flat=%f&flon=%f&tlat=%f&tlon=%f&v=motorcar&fast=1&layer=mapnik"


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
        return d


    def waypoint(self, radFromLat, radFromLon, theta, d):
        radToLat = asin(sin(radFromLat) * cos(d/R) + cos(radFromLat) * \
            sin(d/R) * cos(theta))
        radToLon = radFromLon + atan2(sin(theta) * sin(d/R) * cos(radFromLat),
            cos(d/R) - sin(radFromLat) * sin(radToLat))
        radToLon = (radToLon + 3.0 * pi) % (2.0 * pi) - pi
        return (degrees(radToLat), degrees(radToLon))

    def getIntermediatePoints(self, fromLat, fromLon, toLat, toLon, stepsize):
        intermediatePoints = []
        radFromLat, radFromLon = (radians(fromLat), radians(fromLon))  # Valparaíso
        radToLat, radToLon = (radians(toLat), radians(toLon))  # Shanghai

        d = R * acos( sin(radFromLat) * sin(radToLat) + cos(radFromLat) * \
            cos(radToLat) * cos(radToLon - radFromLon) )
        theta = atan2( sin(radToLon - radFromLon) * cos(radToLat),
            cos(radFromLat) * sin(radToLat) - sin(radFromLat) * cos(radToLat) *\
            cos(radToLon - radFromLon) )

        i = 0.0
        while i < abs(d):
            intermediatePoints.append(self.waypoint(radFromLat, radFromLon, theta, i))
            i = i + stepsize

        return intermediatePoints


    def getRoute(self, fromLat, fromLon, toLat, toLon):
        result = requests.get(ROUTE_URL%(fromLat, fromLon, toLat, toLon))
        if result.status_code == 200:
            jsonResult = json.loads(result.text)
            return [(t[1], t[0]) for t in jsonResult["coordinates"]] #FIXME Sleppa fyrsta?
        return []

    def goto(self, toLat, toLon, mode):
        print "Goto: %0.9f, %0.9f"%(toLat, toLon)
        newRoute = self.getRoute(
            self.currentLat,
            self.currentLon,
            toLat,
            toLon)
        self.travelling = False
        self.currentRouteLock.acquire()
        self.currentRoute = newRoute
        self.currentRouteLock.release()
        self.currentLegLock.acquire()
        self.currentLeg = []
        self.currentLegLock.release()
        self.current_travel_mode = mode
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
                    self.currentLeg = self.getIntermediatePoints(
                        self.currentLat,
                        self.currentLon,
                        nextRoutePoint[0],
                        nextRoutePoint[1],
                        1.666/1000.0)
                    self.currentLegLock.release()

                self.currentLegLock.acquire()
                nextLegPoint = self.currentLeg[0]
                self.currentLeg = self.currentLeg[1:]
                self.currentLegLock.release()
                self.currentLat, self.currentLon = nextLegPoint
            for l in self.current_location_listeners:
                try:
                    l.send_current_location(self.currentLat, self.currentLon)
                    if not hasattr(l, "initial_route_sent"):
                        l.send_current_route(self.currentRoute)
                        l.initial_route_sent = True
                except AttributeError:
                    self.current_location_listeners.remove(l)
            print "Lat,Lon: %0.9f, %0.9f"%(self.currentLat, self.currentLon)
            time.sleep(0.2)


if __name__ == "__main__":
    # Heima 64.138865, -21.961221
    # Siminn 64.135782, -21.877460
    spoofer = Spoofer(64.135782, -21.877460)
    spoofer.start()
    # print spoofer.getRoute(64.138865, -21.961221)
    #print spoofer.getDistance(52.215676, 5.963946, 52.2573, 6.1799)
    # print spoofer.getIntermediatePoints(-33, -71.6, 31.4, 121.8, 2000)
    spoofer.goto(64.138865, -21.961221, DRIVING)
    time.sleep(10)
    spoofer.goto(64.135782, -21.877460, DRIVING)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            # TODO Clean up
            sys.stdout.write("Exiting!\n")
            sys.stdout.flush()
            break
