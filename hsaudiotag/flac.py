# Created By: Virgil Dupras
# Created On: 2005/12/17
# Copyright 2010 Hardcoded Software (http://www.hardcoded.net)

# This software is licensed under the "BSD" License as described in the "LICENSE" file, 
# which should be included with this package. The terms are also available at 
# http://www.hardcoded.net/licenses/bsd_license

from __future__ import with_statement
from struct import unpack

from .util import FileOrPath
from . import ogg

import struct

STREAMINFO = 0
PADDING = 1
APPLICATION = 2
SEEKTABLE = 3
VORBIS_COMMENT = 4
CUESHEET = 5
PICTURE = 6

class InvalidFileError(Exception):
    pass

class MetaDataBlockHeader(object):
    HEADER_SIZE = 4
    def __init__(self, infile):
        self.file = infile
        self.offset = infile.tell()
        data = infile.read(self.HEADER_SIZE)
        unpacked = unpack('!I', data)[0]
        self.last_before_audio = bool(unpacked >> 31)
        self.type = (unpacked >> 24) & 0x7f
        self.size = unpacked & 0xffffff
        self.valid = self.type != 0x7f #invalid type

    def data(self):
        self.file.seek(self.offset + self.HEADER_SIZE)
        return BLOCK_CLASSES.get(self.type, MetaDataBlock)(self.file, self)

    def next(self):
        self.file.seek(self.offset + self.HEADER_SIZE + self.size)
        return MetaDataBlockHeader(self.file)

class MetaDataBlock(object):
    def __init__(self, infile, header):
        self.data = infile.read(header.size)
    

class StreamInfo(MetaDataBlock):
    def __init__(self, infile, header):
        MetaDataBlock.__init__(self, infile, header)
        block_size, frame_size1, frame_size2, sample1, sample2, md5 = unpack('!2IH2I16s', self.data)
        self.sample_rate = sample1 >> 12
        self.sample_count = sample2 + ((sample1 & 0xf) << 32)


class VorbisComment(MetaDataBlock):
    def __init__(self, infile, header):
        MetaDataBlock.__init__(self, infile, header)
        self.comment = ogg.VorbisComment(self.data)

class Picture(MetaDataBlock):
    def __init__(self, infile, header):
        MetaDataBlock.__init__(self, infile, header)
        self.picture = None
        try:
            self.picture = self._read_picture()
        except:
            pass

    def _read_picture(self):
        raw = self.data
        offset = 8
        _, length = struct.unpack('>2I', raw[:offset])
        # get the mimetype
        mime = raw[offset:offset+length].decode('UTF-8', 'replace')
        offset = offset + length

        # read the length for description
        length, = struct.unpack('>I', raw[offset:offset+4])
        offset+=4
        # read the description
        desc = raw[offset:offset+length].decode('UTF-8', 'replace')
        offset = offset + length
        # infos about the thumbs
        (width, height, depth, colors, length) = struct.unpack('>5I', raw[offset:offset+20])
        offset+=20

        # finnally, read the image content
        return raw[offset:]




BLOCK_CLASSES = {
    STREAMINFO: StreamInfo,
    VORBIS_COMMENT: VorbisComment,
    PICTURE: Picture
}

class FLAC(object):
    ID = 'fLaC'
    def __init__(self, infile):
        with FileOrPath(infile) as fp:
            fp.seek(0, 2)
            self.size = fp.tell()
            fp.seek(0, 0)
            try:
                self._read(fp)
            except Exception: #The unpack error doesn't seem to have a class. I have to catch all here
                self._empty()
    
    def _empty(self):
        self.valid = False
        self.bitrate = 0
        self.artist = u''
        self.album = u''
        self.title = u''
        self.genre = u''
        self.year = u''
        self.comment = u''
        self.track = 0
        self.sample_rate = 0
        self.sample_count = 0
        self.duration = 0
        self.audio_offset = 0
        self.audio_size = 0
        self.picture = None

    def _read(self, fp):
        id = fp.read(len(self.ID))
        if id != self.ID:
            raise InvalidFileError()
        self.first_header = MetaDataBlockHeader(fp)
        info = self.get_first_block(STREAMINFO)

        self.sample_rate = info.sample_rate
        if self.sample_rate > 0:
            self.duration = info.sample_count // self.sample_rate
        else:
            self.duration = 0
        self.bitrate = 0
        info = self.get_first_block(VORBIS_COMMENT)
        comment = info.comment
        self.artist = comment.artist
        self.album = comment.album
        self.title = comment.title
        self.track = comment.track
        self.year = comment.year
        self.genre = comment.genre
        self.comment = comment.comment
        self.picture = comment.picture

        last = self.get_last_block()
        self.audio_offset = last.offset + last.HEADER_SIZE + last.size
        self.audio_size = self.size - self.audio_offset
        self.valid = True

        if not self.picture:
            # could not read picture from ogg comment, try flac frame
            block_picture = self.get_first_block(PICTURE)
            self.picture = block_picture.picture


    def get_first_block(self, type):
        header = self.first_header
        while header.valid:
            if header.type == type:
                return header.data()
            header = header.next()

    def get_last_block(self):
        header = self.first_header
        while header.valid:
            if header.last_before_audio:
                return header
            header = header.next()
