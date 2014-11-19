#!/usr/bin/env python

# after http://pygstdocs.berlios.de/pygst-tutorial/webcam-viewer.html
# add ffmpegcolorspace (videoconvert for 1.0)

import sys
import os
import pygtk
import gtk
import gobject
import pygst
pygst.require("0.10")
import gst

import numpy as np
import cv2
import tesseract
import cv2.cv as cv

MAX_BUFFERS = 10
WIDTH = 720
HEIGHT = 480
DEPTH = 3

api = tesseract.TessBaseAPI()
api.Init(".", "eng", tesseract.OEM_DEFAULT)
api.SetPageSegMode(tesseract.PSM_AUTO)


class Main(object):
    def __init__(self):
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        window.set_title("Webcam-Viewer")
        window.set_default_size(500, 400)
        window.connect("destroy", gtk.main_quit, "WM destroy")
        vbox = gtk.VBox()
        window.add(vbox)
        self.movie_window = gtk.DrawingArea()
        vbox.add(self.movie_window)
        hbox = gtk.HBox()
        vbox.pack_start(hbox, False)
        hbox.set_border_width(10)
        hbox.pack_start(gtk.Label())
        self.button = gtk.Button("Start")
        self.button.connect("clicked", self.start_stop)
        hbox.pack_start(self.button, False)
        self.button2 = gtk.Button("Quit")
        self.button2.connect("clicked", self.exit)
        hbox.pack_start(self.button2, False)
        hbox.add(gtk.Label())
        window.show_all()
        # Set up the gstreamer pipeline
        filename = './Become_a_logging_expert_in_30_.mp4'
        source = gst.element_factory_make("filesrc", "filesource")
        source.set_property("location", filename)
        mux = gst.element_factory_make("qtdemux", "demux")
        mux_queue = gst.element_factory_make("queue", "muxqueue")
        decoder = gst.element_factory_make("ffdec_h264", "decoder")
        self.videosink = gst.element_factory_make("autovideosink",
                                                  "video-output")
        self.appsink = gst.element_factory_make("appsink",
                                                "decoded-output")
        self.appsink.set_property("drop", False)
        self.appsink.set_property("max-buffers", MAX_BUFFERS)
        self.appsink.set_property("sync", True)
        self.appsink.set_property("emit-signals", True)
        self.appsink.connect("new-buffer", self.new_data)
        appsink_queue = gst.element_factory_make('queue',
                                                 'appsink-queue')
        self.tee = gst.element_factory_make('tee', 'tee')
        self.capsfilter = gst.element_factory_make('capsfilter',
                                                   'capsfilter')
        caps = gst.caps_from_string('video/x-raw-rgb')
        print "caps", caps
        self.capsfilter.set_property('caps', caps)
        self.videoconvert = gst.element_factory_make('ffmpegcolorspace',
                                                     'converter')
        self.player = gst.Pipeline("videocontroller")
        self.player.add_many(source,
                             mux,
                             mux_queue,
                             decoder,
                             self.tee,
                             self.videosink,
                             appsink_queue,
                             self.appsink,
                             self.capsfilter,
                             self.videoconvert)
        spad = source.get_static_pad('src')
        dpad = mux.get_static_pad('sink')
        spad.link(dpad)

        def on_pad_added(object, pad):
            # we also get called w/ audio_00
            if pad.get_name() == 'video_00':
                dpad = mux_queue.get_static_pad('sink')
                pad.link(dpad)
        mux.connect('pad-added', on_pad_added)
        spad = mux_queue.get_static_pad('src')
        dpad = decoder.get_static_pad('sink')
        spad.link(dpad)

        spad = decoder.get_static_pad('src')
        dpad = self.tee.get_static_pad('sink')
        spad.link(dpad)

        src_for_videosink = self.tee.get_request_pad('src0')
        dpad = self.videosink.get_static_pad('sink')
        src_for_videosink.link(dpad)

        src_for_appsink_queue = self.tee.get_request_pad('src1')
        dpad = appsink_queue.get_static_pad('sink')
        src_for_appsink_queue.link(dpad)
        src_for_videoconvert = appsink_queue.get_static_pad('src')
        dpad = self.videoconvert.get_static_pad('sink')
        src_for_videoconvert.link(dpad)
        # http://gstreamer-devel.966125.n4.nabble.com/YUV-to-RGB-conversion-of-decoder-output-td3154650.html claims this works ...
        # http://talk.maemo.org/showthread.php?t=47584
        src_for_capsfilter = self.videoconvert.get_static_pad('src')
        dpad = self.capsfilter.get_static_pad('sink')
        src_for_capsfilter.link(dpad)

        self.src_for_appsink = self.capsfilter.get_static_pad('src')
        dpad = self.appsink.get_static_pad('sink')
        self.src_for_appsink.link(dpad)
        self.appsink_pad = dpad

        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect("message", self.on_message)
        bus.connect("sync-message::element", self.on_sync_message)

    def start_stop(self, w):
        if self.button.get_label() == "Start":
            self.button.set_label("Stop")
            self.player.set_state(gst.STATE_PLAYING)
        else:
            self.player.set_state(gst.STATE_NULL)
            self.button.set_label("Start")

    def exit(self, widget, data=None):
        gtk.main_quit()

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.player.set_state(gst.STATE_NULL)
            self.button.set_label("Start")
        elif t == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            print "Error: %s" % err, debug
            self.player.set_state(gst.STATE_NULL)
            self.button.set_label("Start")

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        message_name = message.structure.get_name()
        if message_name == "prepare-xwindow-id":
            imagesink = message.src
            imagesink.set_property("force-aspect-ratio", True)
            imagesink.set_xwindow_id(self.movie_window.window.xid)

    counter = 0

    def new_data(self, sink):
        caps = self.videoconvert.get_static_pad('sink').get_negotiated_caps()
        if self.counter == 0:
            print caps
            print "capsfilter", self.capsfilter.get_property('caps')
        height = caps[0]['height']
        width = caps[0]['width']
        # If we get interlaced data here, it's probably better
        # to get gstreamer to convert than to deinterlace in numpy.
        assert not caps[0]['interlaced']

#       print caps[0]['format'].fourcc # 'I420'
        buf = sink.emit('pull-buffer')
        self.counter += 1
        if self.counter % 30 != 0:
            return

        # frames can be split across calls, so the following code
        # is wrong
        # print self.appsink_pad.get_negotiated_caps()
        # print len(buf) # 1036800
        frame = np.ndarray((height, width, DEPTH),
                           dtype=np.int8,
                           buffer=buf)
        # copy so we can write to it
        frame = np.array(frame, copy=True)

        # add a black border.
        # without a border, apparently tesseract will
        # complain about "Please call SetImage before attempting recognition."
        frame[0:15,:,:] = 0
        frame[-15:,:,:] = 0

        height1, width1, channel1 = frame.shape
        iplimage = cv.CreateImageHeader((width1, height1),
                                        cv.IPL_DEPTH_8U,
                                        channel1)
        cv.SetData(iplimage,
                   frame.data,
                   frame.dtype.itemsize * channel1 * width1)
        offset = 15

        tesseract.SetCvImage(iplimage, api)
        text = api.GetUTF8Text()
        # we don't use confidence yet, but if we 
        # conf=api.MeanTextConf()
        display(text)


def display(text):
    for line in text.split('\n'):
        if '@' in line:
            print line

Main()
gtk.gdk.threads_init()
gtk.main()
