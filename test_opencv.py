#!/usr/bin/env python3
from threading import Thread
from time import clock

import cv2
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.launch_string = 'appsrc caps=video/x-raw,format=GRAY8,width=320,height=240,framerate=30/1 size=-1 ' \
                             '! videoconvert ! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'
        self.pipeline = Gst.parse_launch(self.launch_string)
        self.appsrc = self.pipeline.get_child_by_index(3)
        self.appsrc.get_property('caps').fixate()
        self.appsrc.set_property('format', Gst.Format.TIME)

        self.bus = self.appsrc.get_bus()
        self.bus.connect('message::error', self.on_error)
        self.bus.connect('message::state-changed', self.on_status_changed)
        self.bus.connect('message::eos', self.on_eos)

    def on_status_changed(self, bus, message):
        msg = message.parse_state_changed()
        print('status_changed message -> {}'.format(msg))

    def on_eos(self, bus, message):
        print('eos message -> {}'.format(message))

    def on_error(self, bus, message):
        print('error message -> {}'.format(message.parse_error().debug))

    def do_create_element(self, url):
        return self.pipeline


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/test", self.factory)
        self.attach(None)


GObject.threads_init()
Gst.init(None)

server = GstServer()

loop = GObject.MainLoop()
th = Thread(target=loop.run)
th.start()

print('Thread started')

cap = cv2.VideoCapture(0)

print(cap.isOpened())

frame_number = 0

fps = 30
duration = 1 / fps

timestamp = clock()

while cap.isOpened():
    ret, frame = cap.read()
    if ret:

        print('Writing buffer')

        data = frame.tostring()

        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        buf.duration = fps
        timestamp = clock() - timestamp
        buf.pts = buf.dts = int(timestamp)
        buf.offset = frame_number
        frame_number += 1
        retval = server.factory.appsrc.emit('push-buffer', buf)
        if retval != Gst.FlowReturn.OK:
            print(retval)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
