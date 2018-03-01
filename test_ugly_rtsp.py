#!/usr/bin/env python3
from threading import Thread

import cv2
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

    def do_create_element(self, url):
        launch_string = 'tcpclientsrc host=localhost port=5000 ! gdpdepay ' \
                        '! rtph264depay ' \
                        '! rtph264pay config-interval=1 name=pay0 pt=96'
        return Gst.parse_launch(launch_string)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, factory, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = factory
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/test", self.factory)
        self.attach(None)


GObject.threads_init()
Gst.init(None)

factory = SensorFactory()
server = GstServer(factory)

loop = GObject.MainLoop()
th = Thread(target=loop.run)
th.start()

print('Thread started')

cap = cv2.VideoCapture(0)

framerate = 5.0

out = cv2.VideoWriter('appsrc ! videoconvert ! '
                      'x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ! '
                      'rtph264pay config-interval=1 pt=96 ! gdppay ! '
                      'tcpserversink host=0.0.0.0 port=5000 sync=false',
                      0, framerate, (640, 480))

while cap.isOpened():
    ret, frame = cap.read()
    if ret:

        # write the flipped frame
        out.write(frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    else:
        break

# Release everything if job is finished
cap.release()
out.release()
