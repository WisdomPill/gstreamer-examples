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
        self.number_frames = 0
        self.fps = 30.
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = 'appsrc name=source is-live=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=BGR,width=640,height=480,framerate={}/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=fast tune=zerolatency bitrate=256 ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'.format(int(self.fps))
        self.frame = None

    def set_last_frame(self, frame):
        self.frame = frame

    def on_need_data(self, src, lenght):
        if self.frame is not None:
            data = self.frame.tostring()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.duration = self.duration
            timestamp = self.number_frames * self.duration
            buf.pts = buf.dts = int(timestamp)
            buf.offset = timestamp
            self.number_frames += 1
            retval = src.emit('push-buffer', buf)
            print('pushed buffer, frame {}, duration {} ns, durations {} s'.format(self.number_frames,
                                                                                   self.duration,
                                                                                   self.duration / Gst.SECOND))
            if retval != Gst.FlowReturn.OK:
                print(retval)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/stream", self.factory)
        GObject.timeout_add_seconds(60, self.clean_pools)
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

    def clean_pools(self):
        clean_count = self.get_session_pool().cleanup()
        print('Cleaned {} sessions from the pool!'.format(clean_count))

        clean_count = self.get_thread_pool().cleanup()
        print('Cleaned {} threads from the pool!'.format(clean_count))

        return True


class LiveStreamingServer(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, daemon=None):
        super(LiveStreamingServer, self).__init__(group=group, target=target, name=name, args=args, kwargs=kwargs,
                                                  daemon=daemon)
        GObject.threads_init()
        Gst.init(None)
        self.server = GstServer()
        self.loop = GObject.MainLoop()
        self.thread = Thread(target=self.loop.run)

    def start(self):
        self.thread.start()

    def set_last_frame(self, frame):
        self.server.set_last_frame(frame)


s = LiveStreamingServer()
s.start()

cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if ret:

        # write the flipped frame
        s.set_last_frame(frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    else:
        break

# Release everything if job is finished
cap.release()
