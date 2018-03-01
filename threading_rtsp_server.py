#!/usr/bin/env python3
import sys
from threading import Thread

import cv2
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject


class Context:
    def __init__(self):
        self._timestamp = 0
        self._need_data = True

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        self._timestamp = value

    @property
    def need_data(self):
        return self._need_data

    @need_data.setter
    def need_data(self, value):
        self._need_data = value

    def __str__(self):
        return 'timestamp -> {}, need_data -> {}'.format(self._timestamp, self._need_data)


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        if sys.platform == 'darwin':
            self.width = 1280
            self.height = 720
        else:
            self.width = 640
            self.height = 480
        self.fps = 6.
        self.bitrate = 256
        self.buffer_frames = 3
        self.frame_size = self.width * self.height * 3
        self.buffer_size = self.frame_size * self.buffer_frames
        self.key_int_max = 0
        self.duration = int(1 / self.fps * Gst.SECOND)  # duration of a frame in nanoseconds
        launch_string = '( appsrc name=source is-live=true format=GST_FORMAT_TIME blocksize={} ' \
                        'caps=video/x-raw,format=I420,width={},height={},framerate={}/1 ' \
                        '! x264enc key-int-max={} speed-preset=ultrafast bitrate={} tune=zerolatency ' \
                        '! rtph264pay config-interval=1 name=pay0 pt=96 )'.format(self.buffer_size, self.width,
                                                                                  self.height, int(self.fps),
                                                                                  self.key_int_max, self.bitrate)

        print(launch_string)
        self.set_launch(launch_string)
        self.set_shared(True)
        self.set_eos_shutdown(True)
        self.set_latency(500)
        self.frame = None

    def set_last_frame(self, frame):
        self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)

    def on_need_data(self, src, lenght, context):
        print('context address -> {}'.format(id(context)))
        print('need_data lenght -> {}, context -> {}'.format(lenght, context))
        context.need_data = True
        while context.need_data:
            if self.frame is not None:
                data = self.frame.tostring()
                buf = Gst.Buffer.new_allocate(None, len(data), None)
                buf.fill(0, data)
                buf.duration = self.duration
                buf.pts = buf.dts = context.timestamp
                context.timestamp += buf.duration
                retval = src.emit('push-buffer', buf)
                if retval != Gst.FlowReturn.OK:
                    print(retval)
                    context.need_data = False
        print('context -> {}'.format(context))

    def on_enough_data(self, src, context):
        print('context address -> {}'.format(id(context)))
        print('enough_data context -> {}'.format(context))
        context.need_data = False

    def do_configure(self, rtsp_media):
        ctx = Context()
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data, ctx)
        appsrc.connect('enough-data', self.on_enough_data, ctx)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        self.get_mount_points().add_factory("/stream", self.factory)
        print(self.get_backlog())
        GObject.timeout_add_seconds(3, self.check_health)
        self.attach(None)

    def set_last_frame(self, frame):
        self.factory.set_last_frame(frame)

    def check_health(self):
        thread_pool = self.get_thread_pool()
        session_pool = self.get_session_pool()
        print('thread_pool: max_threads {}'.format(thread_pool.get_max_threads()))
        print('session_pool: max_sessions {}, n_sessions {}'.format(session_pool.get_max_sessions(),
                                                                    session_pool.get_n_sessions()))

        return True


class LiveStreamingServer:
    def __init__(self):
        self.server = GstServer()
        self.loop = GObject.MainLoop()
        self.thread = Thread(target=self.loop.run)

    def start(self):
        self.thread.start()

    def set_last_frame(self, frame):
        self.server.set_last_frame(frame)


GObject.threads_init()
Gst.init(None)

s = LiveStreamingServer()
s.start()

cap = cv2.VideoCapture(0)

print('cap.isOpened() -> {}'.format(cap.isOpened()))

while cap.isOpened():
    ret, frame = cap.read()
    if ret:
        s.set_last_frame(frame)
        # print('Wrote frame to the server')

# Release everything if job is finished
cap.release()
