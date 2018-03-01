#!/usr/bin/env python3
from time import clock

import cv2
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.cap = cv2.VideoCapture(0)
        self.number_frames = 0
        self.fps = 30
        self.duration = 1 / self.fps * (10 ** 6)
        self.launch_string = 'appsrc name=source caps=video/x-raw,format=BGR,width=640,height=480,framerate=30/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'
        self.pipeline = None
        self.appsrc = None
        self.bus = None

    def on_need_data(self, src, lenght):
        print('need data')
        if self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                data = frame.tostring()
                buf = Gst.Buffer.new_allocate(None, len(data), None)
                buf.fill(0, data)
                buf.duration = self.duration
                timestamp = self.number_frames * self.duration
                buf.pts = buf.dts = int(timestamp)
                buf.offset = timestamp
                self.number_frames += 1
                retval = src.emit('push-buffer', buf)
                print('pushed buffer, frame {}, duration {}'.format(self.number_frames, self.duration))
                if retval != Gst.FlowReturn.OK:
                    print(retval)

    def on_status_changed(self, bus, message):
        msg = message.parse_state_changed()
        print('status_changed message -> {}'.format(msg))

    def on_eos(self, bus, message):
        print('eos message -> {}'.format(message))

    def on_error(self, bus, message):
        print('error message -> {}'.format(message.parse_error().debug))

    def do_create_element(self, url):
        self.pipeline = Gst.parse_launch(self.launch_string)
        self.appsrc = self.pipeline.get_child_by_name('source')
        # self.appsrc.get_property('caps').fixate()
        self.appsrc.set_property('format', Gst.Format.TIME)
        self.appsrc.set_property('is-live', 1)
        self.appsrc.set_property('block', 1)
        self.appsrc.connect('need-data', self.on_need_data)
        self.bus = self.pipeline.get_bus()
        self.bus.connect('message::error', self.on_error)
        self.bus.connect('message::state-changed', self.on_status_changed)
        self.bus.connect('message::eos', self.on_eos)
        self.bus.enable_sync_message_emission()
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
loop.run()
