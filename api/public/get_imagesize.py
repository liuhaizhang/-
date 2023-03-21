import io
import os
import re
import struct
#from xml.etree import ElementTree

'''
1、这里是imagesize==1.4.1版本获取文件宽度和高度和源码
2、使用imagesize==1.2.0版本，无法实现对大tiff文件的宽度和高度的获取，且不想将原来环境中的imagesize升级到1.4.1 （担心会影响到其他的项目，）
3、就直接将imagesize==1.4.1中获取图片宽度和高度的原来提取出来
'''

_UNIT_KM = -3
_UNIT_100M = -2
_UNIT_10M = -1
_UNIT_1M = 0
_UNIT_10CM = 1
_UNIT_CM = 2
_UNIT_MM = 3
_UNIT_0_1MM = 4
_UNIT_0_01MM = 5
_UNIT_UM = 6
_UNIT_INCH = 6

_TIFF_TYPE_SIZES = {
  1: 1,
  2: 1,
  3: 2,
  4: 4,
  5: 8,
  6: 1,
  7: 1,
  8: 2,
  9: 4,
  10: 8,
  11: 4,
  12: 8,
}


def _convertToDPI(density, unit):
    if unit == _UNIT_KM:
        return int(density * 0.0000254 + 0.5)
    elif unit == _UNIT_100M:
        return int(density * 0.000254 + 0.5)
    elif unit == _UNIT_10M:
        return int(density * 0.00254 + 0.5)
    elif unit == _UNIT_1M:
        return int(density * 0.0254 + 0.5)
    elif unit == _UNIT_10CM:
        return int(density * 0.254 + 0.5)
    elif unit == _UNIT_CM:
        return int(density * 2.54 + 0.5)
    elif unit == _UNIT_MM:
        return int(density * 25.4 + 0.5)
    elif unit == _UNIT_0_1MM:
        return density * 254
    elif unit == _UNIT_0_01MM:
        return density * 2540
    elif unit == _UNIT_UM:
        return density * 25400
    return density


def _convertToPx(value):
    matched = re.match(r"(\d+(?:\.\d+)?)?([a-z]*)$", value)
    if not matched:
        raise ValueError("unknown length value: %s" % value)

    length, unit = matched.groups()
    if unit == "":
        return float(length)
    elif unit == "cm":
        return float(length) * 96 / 2.54
    elif unit == "mm":
        return float(length) * 96 / 2.54 / 10
    elif unit == "in":
        return float(length) * 96
    elif unit == "pc":
        return float(length) * 96 / 6
    elif unit == "pt":
        return float(length) * 96 / 6
    elif unit == "px":
        return float(length)

    raise ValueError("unknown unit type: %s" % unit)


def get(filepath):
    """
    Return (width, height) for a given img file content
    no requirements
    :type filepath: Union[bytes, str, pathlib.Path]
    :rtype Tuple[int, int]
    """
    height = -1
    width = -1

    if isinstance(filepath, io.BytesIO):  # file-like object
        fhandle = filepath
    else:
        fhandle = open(filepath, 'rb')

    try:
        head = fhandle.read(31)
        size = len(head)
        # handle GIFs
        if size >= 10 and head[:6] in (b'GIF87a', b'GIF89a'):
            print('gif文件')
            # Check to see if content_type is correct
            try:
                width, height = struct.unpack("<hh", head[6:10])
            except struct.error:
                raise ValueError("Invalid GIF file")
        # see png edition spec bytes are below chunk length then and finally the
        elif size >= 24 and head.startswith(b'\211PNG\r\n\032\n') and head[12:16] == b'IHDR':
            print('png文件,size>24')
            try:
                width, height = struct.unpack(">LL", head[16:24])
            except struct.error:
                raise ValueError("Invalid PNG file")
        # Maybe this is for an older PNG version.
        elif size >= 16 and head.startswith(b'\211PNG\r\n\032\n'):
            print('png文件，size>16')
            # Check to see if we have the right content type
            try:
                width, height = struct.unpack(">LL", head[8:16])
            except struct.error:
                raise ValueError("Invalid PNG file")
        # handle JPEGs
        elif size >= 2 and head.startswith(b'\377\330'):
            try:
                fhandle.seek(0)  # Read 0xff next
                size = 2
                ftype = 0
                while not 0xc0 <= ftype <= 0xcf or ftype in [0xc4, 0xc8, 0xcc]:
                    fhandle.seek(size, 1)
                    byte = fhandle.read(1)
                    while ord(byte) == 0xff:
                        byte = fhandle.read(1)
                    ftype = ord(byte)
                    size = struct.unpack('>H', fhandle.read(2))[0] - 2
                # We are at a SOFn block
                fhandle.seek(1, 1)  # Skip `precision' byte.
                height, width = struct.unpack('>HH', fhandle.read(4))
            except (struct.error, TypeError):
                raise ValueError("Invalid JPEG file")
        # handle JPEG2000s
        elif size >= 12 and head.startswith(b'\x00\x00\x00\x0cjP  \r\n\x87\n'):
            fhandle.seek(48)
            try:
                height, width = struct.unpack('>LL', fhandle.read(8))
            except struct.error:
                raise ValueError("Invalid JPEG2000 file")
        # handle big endian TIFF
        elif size >= 8 and head.startswith(b"\x4d\x4d\x00\x2a"):
            print('1、tiff文件，size>=8,开头=',b'\x4d\x4d\x00\x2a')
            offset = struct.unpack('>L', head[4:8])[0]
            fhandle.seek(offset)
            ifdsize = struct.unpack(">H", fhandle.read(2))[0]
            for i in range(ifdsize):
                tag, datatype, count, data = struct.unpack(">HHLL", fhandle.read(12))
                if tag == 256:
                    if datatype == 3:
                        width = int(data / 65536)
                    elif datatype == 4:
                        width = data
                    else:
                        raise ValueError("Invalid TIFF file: width column data type should be SHORT/LONG.")
                elif tag == 257:
                    if datatype == 3:
                        height = int(data / 65536)
                    elif datatype == 4:
                        height = data
                    else:
                        raise ValueError("Invalid TIFF file: height column data type should be SHORT/LONG.")
                if width != -1 and height != -1:
                    break
            if width == -1 or height == -1:
                raise ValueError("Invalid TIFF file: width and/or height IDS entries are missing.")
        elif size >= 8 and head.startswith(b"\x49\x49\x2a\x00"):
            print('2、tiff文件，开头',b"\x49\x49\x2a\x00")
            offset = struct.unpack('<L', head[4:8])[0]
            fhandle.seek(offset)
            ifdsize = struct.unpack("<H", fhandle.read(2))[0]
            for i in range(ifdsize):
                tag, datatype, count, data = struct.unpack("<HHLL", fhandle.read(12))
                if tag == 256:
                    width = data
                elif tag == 257:
                    height = data
                if width != -1 and height != -1:
                    break
            if width == -1 or height == -1:
                raise ValueError("Invalid TIFF file: width and/or height IDS entries are missing.")
        # handle little endian BigTiff
        elif size >= 8 and head.startswith(b"\x49\x49\x2b\x00"):
            print('3、tiff文件，开头', b"\x49\x49\x2b\x00")
            bytesize_offset = struct.unpack('<L', head[4:8])[0]
            if bytesize_offset != 8:
                raise ValueError('Invalid BigTIFF file: Expected offset to be 8, found {} instead.'.format(offset))
            offset = struct.unpack('<Q', head[8:16])[0]
            fhandle.seek(offset)
            ifdsize = struct.unpack("<Q", fhandle.read(8))[0]
            for i in range(ifdsize):
                tag, datatype, count, data = struct.unpack("<HHQQ", fhandle.read(20))
                if tag == 256:
                    width = data
                elif tag == 257:
                    height = data
                if width != -1 and height != -1:
                    break
            if width == -1 or height == -1:
                raise ValueError("Invalid BigTIFF file: width and/or height IDS entries are missing.")

        # handle SVGs
        elif size >= 5 and (head.startswith(b'<?xml') or head.startswith(b'<svg')):
            fhandle.seek(0)
            data = fhandle.read(1024)
            try:
                data = data.decode('utf-8')
                width = re.search(r'[^-]width="(.*?)"', data).group(1)
                height = re.search(r'[^-]height="(.*?)"', data).group(1)
            except Exception:
                raise ValueError("Invalid SVG file")
            width = _convertToPx(width)
            height = _convertToPx(height)

        # handle Netpbm
        elif head[:1] == b"P" and head[1:2] in b"123456":
            fhandle.seek(2)
            sizes = []

            while True:
                next_chr = fhandle.read(1)

                if next_chr.isspace():
                    continue

                if next_chr == b"":
                    raise ValueError("Invalid Netpbm file")

                if next_chr == b"#":
                    fhandle.readline()
                    continue

                if not next_chr.isdigit():
                    raise ValueError("Invalid character found on Netpbm file")

                size = next_chr
                next_chr = fhandle.read(1)

                while next_chr.isdigit():
                    size += next_chr
                    next_chr = fhandle.read(1)

                sizes.append(int(size))

                if len(sizes) == 2:
                    break

                fhandle.seek(-1, os.SEEK_CUR)
            width, height = sizes
        elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            if head[12:16] == b"VP8 ":
                width, height = struct.unpack("<HH", head[26:30])
            elif head[12:16] == b"VP8X":
                width = struct.unpack("<I", head[24:27] + b"\0")[0]
                height = struct.unpack("<I", head[27:30] + b"\0")[0]
            elif head[12:16] == b"VP8L":
                b = head[21:25]
                width = (((b[1] & 63) << 8) | b[0]) + 1
                height = (((b[3] & 15) << 10) | (b[2] << 2) | ((b[1] & 192) >> 6)) + 1
            else:
                raise ValueError("Unsupported WebP file")

    finally:
        fhandle.close()

    return width, height
