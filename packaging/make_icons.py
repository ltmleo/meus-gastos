"""Builds icon.ico (Windows) and icon.icns (macOS) from the PNG renders of web/favicon.svg.

Both formats can embed PNG data directly, so no image library is needed.
Usage: python packaging/make_icons.py  (expects packaging/icon-<size>.png)
"""
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def png(size):
    return (HERE / f'icon-{size}.png').read_bytes()


def make_ico(sizes=(16, 32, 48, 64, 128, 256)):
    images = [png(s) for s in sizes]
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b'', b''
    for size, image in zip(sizes, images):
        dimension = 0 if size >= 256 else size  # 0 means 256 in the ICO directory
        entries += struct.pack('<BBBBHHII', dimension, dimension, 0, 0, 1, 32, len(image), offset + len(data))
        data += image
    (HERE / 'icon.ico').write_bytes(header + entries + data)


def make_icns():
    chunks = b''
    for kind, size in ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64), (b'ic07', 128), (b'ic08', 256), (b'ic09', 512), (b'ic10', 1024)):
        image = png(size)
        chunks += kind + struct.pack('>I', len(image) + 8) + image
    (HERE / 'icon.icns').write_bytes(b'icns' + struct.pack('>I', len(chunks) + 8) + chunks)


if __name__ == '__main__':
    make_ico()
    make_icns()
    print('icon.ico and icon.icns written')
