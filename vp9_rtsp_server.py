#!/usr/bin/env python3

import cv2
import gi
import sys

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject


def get_pad_info(pad):
    return {
        'name': pad.name,
        'is_linked': pad.is_linked(),
        'is_blocking': pad.is_blocking(),
        'is_blocked': pad.is_blocked(),
    }


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
        self.cap = cv2.VideoCapture(0)
        if sys.platform == 'darwin':
            self.width = 1280
            self.height = 720
        else:
            self.width = 640
            self.height = 480
        self.buffer_frames = 1
        self.buffer_size = self.width * self.height * 3 * self.buffer_frames
        self.fps = 30
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = 'appsrc name=source is-live=true format=GST_FORMAT_TIME blocksize={} ' \
                             'caps=video/x-raw,format=BGR,width={},height={},framerate={}/1 ' \
                             '! videoconvert ! capsfilter caps=video/x-raw,format=I420 ' \
                             '! vp9enc ' \
                             '! rtpvp9pay name=pay0 pt=96'.format(self.buffer_size, self.width,
                                                                                     self.height, self.fps)
        self.set_eos_shutdown(True)
        print('is_eos_shutdown {}'.format(self.is_eos_shutdown()))

    def on_need_data(self, src, lenght, context):
        print('context address -> {}'.format(id(context)))
        print('need_data lenght -> {}, context -> {}'.format(lenght, context))
        context.need_data = True
        while context.need_data:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    data = frame.tostring()
                    buf = Gst.Buffer.new_allocate(None, len(data), None)
                    buf.fill(0, data)
                    buf.duration = self.duration
                    buf.pts = context.timestamp
                    context.timestamp += buf.duration
                    retval = src.emit('push-buffer', buf)
                    # print('pushed buffer, frame {}, duration {} ns, durations {} s'.format(self.number_frames,
                    #                                                                        self.duration,
                    #                                                                        self.duration / Gst.SECOND))
                    print(retval)
                    if retval != Gst.FlowReturn.OK:
                        # client has disconnected, I suppose
                        print(retval)
                        context.need_data = False
        print('context -> {}'.format(context))

    def on_enough_data(self, src, context):
        print('context address -> {}'.format(id(context)))
        print('enough_data context -> {}'.format(context))
        context.need_data = False

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        ctx = Context()
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data, ctx)
        appsrc.connect('enough-data', self.on_enough_data, ctx)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/stream", self.factory)
        GObject.timeout_add_seconds(60, self.clean_pools)
        GObject.timeout_add_seconds(3, self.check_health)
        self.attach(None)

    def check_health(self):
        thread_pool = self.get_thread_pool()
        session_pool = self.get_session_pool()
        print('thread_pool: max_threads {}'.format(thread_pool.get_max_threads()))
        print('session_pool: max_sessions {}, n_sessions {}'.format(session_pool.get_max_sessions(),
                                                                    session_pool.get_n_sessions()))

        return True

    def clean_pools(self):
        clean_count = self.get_session_pool().cleanup()
        print('Cleaned {} sessions from the pool!'.format(clean_count))

        clean_count = self.get_thread_pool().cleanup()
        print('Cleaned {} threads from the pool!'.format(clean_count))

        return True


Gst.init(None)

server = GstServer()

loop = GObject.MainLoop()
loop.run()
