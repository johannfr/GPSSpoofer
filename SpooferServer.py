# -*- coding: utf-8 -*-
import argparse
import random
import os
import json

import cherrypy

from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
from ws4py.messaging import TextMessage

import Spoofer

class SpooferWebSocketHandler(WebSocket):
    def __init__(self, *args, **kwargs):
        super(SpooferWebSocketHandler, self).__init__(*args, **kwargs)
        self.spoofer = None

    def send_current_location(self, currentLat, currentLon):
        location_data = {
            "type" : "current_location",
            "lat" : currentLat,
            "lon" : currentLon
        }
        json_data = json.dumps(location_data)
        self.send(json_data)

    def send_current_route(self, route):
        route_data = {
            "type" : "current_route",
            "route" : route
        }
        json_data = json.dumps(route_data)
        self.send(json_data)

    def set_spoofer(self, spoofer):
        self.spoofer = spoofer

    def received_message(self, m):
        print m
        json_data = json.loads(m)
        if json_data["type"] == "goto":
            if self.spoofer is not None:
                self.spoofer.goto(json_data["lat"], json_data["lon"])
        #cherrypy.engine.publish('websocket-broadcast', m)

    def closed(self, code, reason="A client left the room without a proper explanation."):
        cherrypy.engine.publish('websocket-broadcast', TextMessage(reason))

class Root(object):
    def __init__(self, host, port, spoofer):
        self.host = host
        self.port = port
        self.scheme = "ws"
        self.spoofer = spoofer

    @cherrypy.expose
    def index(self):
        return """<html>
    <head>
    <style type="text/css">
      html, body, #map-canvas { height: 1000px; margin: 0; padding: 0;}
    </style>
    <script type="text/javascript"
      src="https://maps.googleapis.com/maps/api/js?key=AIzaSyDn11yH1h4kJfnN4BQU_Ok0g3lbT9si_Tg">
    </script>
      <script type='application/javascript' src='https://ajax.googleapis.com/ajax/libs/jquery/1.8.3/jquery.min.js'></script>
      <script type='application/javascript'>

        var mapInitialized = false;
        var map = null;
        var myLocationMarker = null;
        var routeEndpointMarker = null;
        var currentRoute = null;

        $(document).ready(function() {

          websocket = '%(scheme)s://%(host)s:%(port)s/ws';
          if (window.WebSocket) {
            ws = new WebSocket(websocket);
          }
          else if (window.MozWebSocket) {
            ws = MozWebSocket(websocket);
          }
          else {
            console.log('WebSocket Not Supported');
            return;
          }

          window.onbeforeunload = function(e) {
            $('#chat').val($('#chat').val() + 'Bye bye...\\n');
            ws.close(1000, '%(username)s left the room');

            if(!e) e = window.event;
            e.stopPropagation();
            e.preventDefault();
          };
          ws.onmessage = function (evt) {
             jsonObject = JSON.parse(evt.data)
             if (jsonObject.type == "current_location" &&!mapInitialized)
             {
                 var mapOptions = {
                    center: { lat: jsonObject.lat, lng: jsonObject.lon},
                    zoom: 15
                };
            map = new google.maps.Map(document.getElementById('map-canvas'),
            mapOptions);
            marker = new google.maps.Marker({
                position: { lat: jsonObject.lat, lng: jsonObject.lon},
                icon: 'http://maps.google.com/mapfiles/ms/icons/blue-dot.png',
                map: map
            });

            
            mapInitialized = true;
             }

            if (jsonObject.type == "current_location")
            {
                marker.setPosition(new google.maps.LatLng(jsonObject.lat, jsonObject.lon));
            }

            if (jsonObject.type == "current_route")
            {
                if (currentRoute != null)
                {
                    currentRoute.setMap(null);
                }
                var pointArray = [];
                $.each(jsonObject.route, function(k, v) {
                    pointArray.push(new google.maps.LatLng(v[0], v[1]));
                });
                currentRoute = new google.maps.Polyline({
                    path: pointArray,
                    geodesic: true,
                    strokeColor: '#FF0000',
                    strokeOpacity: 1.0,
                    strokeWeight: 2,
                });
                currentRoute.setMap(map);
                routeEndpointMarker = new google.maps.Marker({
                    position: pointArray[pointArray.length-1],
                    draggable: true,
                    map: map
                });

                google.maps.event.addListener(routeEndpointMarker, 'dragend', function() {
                    var newPosition = routeEndpointMarker.getPosition();
                    var jsonRequest = '{ "type" : "goto", "lat" : ' + newPosition.lat() + ', "lon" : ' + newPosition.lng() + '}';
                    ws.send(jsonRequest);
                });



            }




             $('#chat').val($('#chat').val() + evt.data + '\\n');
          };
          ws.onopen = function() {
             // ws.send("%(username)s entered the room");
          };
          ws.onclose = function(evt) {
             $('#chat').val($('#chat').val() + 'Connection closed by server: ' + evt.code + ' \"' + evt.reason + '\"\\n');
          };

          $('#send').click(function() {
             console.log($('#message').val());
             // ws.send('%(username)s: ' + $('#message').val());
             $('#message').val("");
             return false;
          });
        });
      </script>
    </head>
    <body>

    <div id="map-canvas"></div>
    <form action='#' id='chatform' method='get'>
      <textarea id='chat' cols='90' rows='10'></textarea>
      <br />
      <label for='message'>%(username)s: </label><input type='text' id='message' />
      <input id='send' type='submit' value='Send' />
      </form>
    </body>
    </html>
    """ % {'username': "User%d" % random.randint(0, 100), 'host': self.host, 'port': self.port, 'scheme': self.scheme}

    @cherrypy.expose
    def ws(self):
        cherrypy.log("Handler created: %s" % repr(cherrypy.request.ws_handler))
        self.spoofer.add_current_location_listener(cherrypy.request.ws_handler)
        cherrypy.request.ws_handler.set_spoofer(self.spoofer)

if __name__ == '__main__':
    import logging
    from ws4py import configure_logger
    configure_logger(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='Spoofer CherryPy Server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('-p', '--port', default=9000, type=int)
    args = parser.parse_args()

    cherrypy.config.update({'server.socket_host': args.host,
                            'server.socket_port': args.port,
                            'tools.staticdir.root': os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))})

    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()

    spoofer = Spoofer.Spoofer(64.135782, -21.877460)
    spoofer.start()
    spoofer.goto(64.138865, -21.961221, Spoofer.DRIVING)

    cherrypy.quickstart(Root(args.host, args.port, spoofer), '', config={
        '/ws': {
            'tools.websocket.on': True,
            'tools.websocket.handler_cls': SpooferWebSocketHandler
            },
        '/js': {
              'tools.staticdir.on': True,
              'tools.staticdir.dir': 'js'
            }
        }
    )
