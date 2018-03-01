#!/usr/bin/env python
# -*- coding:utf-8 vi:ts=4:noexpandtab
# Simple RTSP server. Run as-is or with a command-line to replace the default pipeline

import gi
import sys

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject

loop = GObject.MainLoop()
GObject.threads_init()
Gst.init(None)


class MyFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self):
        GstRtspServer.RTSPMediaFactory.__init__(self)

    def do_create_element(self, url):
        s_src = "v4l2src ! video/x-raw,rate=30,width=320,height=240 ! videoconvert ! video/x-raw,format=I420"
        # s_h264 = "videoconvert ! vaapiencode_h264 bitrate=1000"
        # s_src = "videotestsrc ! video/x-raw,rate=30,width=320,height=240,format=I420"
        s_h264 = "x264enc tune=zerolatency"
        pipeline_str = "( {s_src} ! queue max-size-buffers=1 name=q_enc ! {s_h264} ! rtph264pay name=pay0 pt=96 )".format(
            **locals())
        if len(sys.argv) > 1:
            pipeline_str = " ".join(sys.argv[1:])
        print(pipeline_str)
        return Gst.parse_launch(pipeline_str)


class CameraFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(CameraFactory, self).__init__(**properties)

    def do_create_element(self, url):
        launch_string = 'v4l2src ! video/x-raw,rate=30,width=320,height=240 ! videoconvert ' \
                        '! video/x-raw,format=I420 ! queue max-size-buffers=1 ' \
                        '! x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ' \
                        '! rtph264pay name=pay0 pt=96'
        return Gst.parse_launch(launch_string)


class LaunchCameraFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(LaunchCameraFactory, self).__init__(**properties)
        launch_String = 'v4l2src ! video/x-raw,rate=30,width=320,height=240 ! videoconvert ' \
                        '! video/x-raw,format=I420 ! queue max-size-buffers=1 ' \
                        '! x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ' \
                        '! rtph264pay name=pay0 pt=96'
        self.set_launch(launch_String)


class RedirectFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(RedirectFactory, self).__init__(**properties)

    def do_create_element(self, url):
        launch_string = 'tcpclientsrc host=localhost port=5000 ! gdpdepay ' \
                        '! rtph264depay ! avdec_h264 ! videoconvert ' \
                        '! video/x-raw,format=I420 ' \
                        '! x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ' \
                        '! rtph264pay name=pay0 pt=96'
        return Gst.parse_launch(launch_string)


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

    def do_create_element(self, url):
        launch_string = 'v4l2src ! video/x-raw,rate=30,width=320,height=240 ! videoconvert ' \
                        '! video/x-raw,format=I420 ! queue max-size-buffers=1 ' \
                        '! x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ' \
                        '! rtph264pay name=pay0 pt=96'
        return Gst.parse_launch(launch_string)


class FakeFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(FakeFactory, self).__init__(**properties)
        launch_string = 'v4l2src ! video/x-raw,rate=30,width=320,height=240 ! videoconvert ' \
                        '! video/x-raw,format=I420 ! queue max-size-buffers=1 ' \
                        '! x264enc bitrate=256 speed-preset=ultrafast tune=zerolatency bitrate=256 ' \
                        '! rtph264pay name=pay0 pt=96'
        self.set_launch(launch_string)


class CompressedRedirectFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(CompressedRedirectFactory, self).__init__(**properties)
        self.launch_string = 'tcpclientsrc host=localhost port=5000 ! gdpdepay ' \
                             '! rtph264depay ' \
                             '! rtph264pay name=pay0 pt=96'
        self.pipeline = None
        self.bus = None

    def do_create_element(self, url):
        self.pipeline = Gst.parse_launch(self.launch_string)
        self.bus = self.pipeline.get_bus()
        self.bus.connect('message::error', self.on_error)
        self.bus.connect('message::state-changed', self.on_status_changed)
        self.bus.connect('message::eos', self.on_eos)
        self.bus.enable_sync_message_emission()
        return self.pipeline

    def on_status_changed(self, bus, message):
        msg = message.parse_state_changed()
        print('status_changed message -> {}'.format(msg))

    def on_eos(self, bus, message):
        print('eos message -> {}'.format(message))

    def on_error(self, bus, message):
        print('error message -> {}'.format(message.parse_error().debug))


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = GstRtspServer.RTSPMediaFactory()
        launch_string = 'videotestsrc ! video/x-raw,width=1280,height=720 ' \
                        '! videoconvert ! x264enc speed-preset=ultrafast tune=zerolatency ' \
                        '! rtph264pay name=pay0 pt=96'
        self.factory.set_launch(launch_string)
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/test", self.factory)
        # self.factory = SensorFactory()
        # self.factory.set_shared(True)
        # self.get_mount_points().add_factory("/test", self.factory)
        self.attach(None)


if __name__ == '__main__':
    s = GstServer()
    loop.run()
