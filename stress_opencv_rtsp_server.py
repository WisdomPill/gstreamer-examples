#!/usr/bin/env python3
import json
from threading import Thread, current_thread

import cv2
import gi

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


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.cap = cv2.VideoCapture(0)
        self.number_frames = 0
        self.fps = 30
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.source = Gst.ElementFactory.make('appsrc', 'source')
        self.source.set_property('is-live', True)
        self.source.set_property('block', True)
        self.source.set_property('format', Gst.Format.TIME)
        self.source.set_property('caps', Gst.Caps.from_string(
            'video/x-raw,format=BGR,width=1280,height=720,framerate={}/1'.format(self.fps)))
        self.source.connect('need-data', self.on_need_data)
        self.converter = Gst.ElementFactory.make('videoconvert', 'converter')
        self.filter = Gst.ElementFactory.make('capsfilter', 'filter')
        self.filter.set_property('caps', Gst.Caps.from_string('video/x-raw,format=I420'))
        self.encoder = Gst.ElementFactory.make('x264enc', 'encoder')
        self.encoder.set_property('speed-preset', 'ultrafast')
        self.encoder.set_property('tune', 'zerolatency')
        self.payloader = Gst.ElementFactory.make('rtph264pay', 'payloader')
        self.payloader.set_property('config-interval', 1)
        self.payloader.set_property('pt', 96)

        self.pipeline = Gst.Pipeline.new('player')
        self.pipeline.add(self.source)
        self.pipeline.add(self.converter)
        self.pipeline.add(self.filter)
        self.pipeline.add(self.encoder)
        self.pipeline.add(self.payloader)

        self.source.link(self.converter)
        self.converter.link(self.filter)
        self.filter.link(self.encoder)
        self.encoder.link(self.payloader)

        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=BGR,width=1280,height=720,framerate={}/1 ' \
                             '! videoconvert ! capsfilter caps=video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'.format(self.fps)
        self.set_eos_shutdown(True)
        print('is_eos_shutdown {}'.format(self.is_eos_shutdown()))

    def on_need_data(self, src, lenght):
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
                # print('pushed buffer, frame {}, duration {} ns, durations {} s'.format(self.number_frames,
                #                                                                        self.duration,
                #                                                                        self.duration / Gst.SECOND))
                if retval != Gst.FlowReturn.OK:
                    print(retval)

    def do_create_element(self, url):
        # return self.pipeline
        response = dict()
        pipeline = Gst.parse_launch(self.launch_string)

        response['pipeline'] = {
            'pads': {
                pad.name: get_pad_info(pad) for pad in pipeline.pads
            }
        }

        clock = pipeline.clock
        if clock:
            response['pipeline']['clock'] = {
                'time': clock.get_time(),
                'resolution': clock.get_resolution(),
                'timeout': clock.get_timeout(),
                'internal time': clock.get_internal_time(),
                'floating': clock.is_floating(),
                'synced': clock.is_synced(),
                'name': clock.get_name(),
                'calibration': clock.get_calibration()
            }

        response['elements'] = [
            {
                'name': child.name,
                'state': child.current_state.value_nick,
                'flags': child.flags,
                'pads': {
                    pad.name: get_pad_info(pad) for pad in child.pads
                }
            }
            for child in pipeline.children]

        print(json.dumps(response, indent=4))
        return pipeline

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


def infinite_loop():
    current_thread()
    print('started stress thread')
    while True:
        pass


Gst.init(None)

server = GstServer()

thread_count = 10
stress_thread_pool = [Thread(target=infinite_loop) for _ in range(thread_count)]
for  t in stress_thread_pool:
    t.start()

loop = GObject.MainLoop()
loop.run()
