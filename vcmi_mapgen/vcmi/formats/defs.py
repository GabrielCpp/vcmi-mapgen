import struct
from dataclasses import dataclass

from PIL import Image


def _decode_frame(data: bytes, foff: int) -> Image.Image:
    """Decode one DEF frame to RGBA PIL Image (32-bit).

    H3 SSpriteDef header (8 uint32): size, format, fullW, fullH, frameW, frameH,
    leftMargin, topMargin. Offsets in the formats below are relative to the data
    that starts right after this 32-byte header (`base`).
      format 0 : raw frameW*frameH palette indices.
      format 1 : one uint32 offset per line; segments are (code, len) pairs,
                 code 0xFF = raw run, else a run of palette[code].
      format 2 : one uint16 offset per line; single-byte segments
                 (type=bits7:5, len=bits4:0+1), type 7 = raw, else palette[type].
      format 3 : each line split into 32-px BLOCKS, one uint16 offset PER BLOCK
                 (row-major), each block decoded with the format-2 segment scheme.
    Palette indices 0-7 are special: render shadows (1/4/6) as semi-transparent
    black so objects read like the editor; 0/2/3 transparent, 5 selection and
    7 player-flag transparent for static renders.
    """
    _sz, comp, fw_full, fh_full, fw, fh, fleft, ftop = struct.unpack_from("<IIIIIIII", data, foff)
    pal_raw = data[16 : 16 + 256 * 3]
    SPECIAL: dict[int, tuple[int, int, int, int]] = {
        0: (0, 0, 0, 0),
        1: (0, 0, 0, 64),
        2: (0, 0, 0, 0),
        3: (0, 0, 0, 0),
        4: (0, 0, 0, 128),
        5: (0, 0, 0, 0),
        6: (0, 0, 0, 128),
        7: (0, 0, 0, 0),
    }
    palette: list[tuple[int, int, int, int]] = [
        SPECIAL[i] if i < 8 else (pal_raw[i * 3], pal_raw[i * 3 + 1], pal_raw[i * 3 + 2], 255)
        for i in range(256)
    ]

    img = Image.new("RGBA", (fw_full, fh_full), (0, 0, 0, 0))
    px = img.load()
    if px is None:
        raise RuntimeError("image has no pixel access")
    frame = _Frame(
        data=data, px=px, palette=palette, base=foff + 32, fw=fw, fh=fh, fleft=fleft, ftop=ftop
    )

    if comp == 0:
        frame.decode_raw()
    elif comp == 1:
        frame.decode_line_runs()
    elif comp == 2:
        frame.decode_line_segments()
    else:
        # comp == 3: per-line 32-px blocks, one uint16 offset per block (row-major)
        frame.decode_block_segments()
    return img


@dataclass(frozen=True, slots=True)
class _Frame:
    data: bytes
    px: "Image.core.PixelAccess"
    palette: list[tuple[int, int, int, int]]
    base: int
    fw: int
    fh: int
    fleft: int
    ftop: int

    def decode_raw(self) -> None:
        data, px, palette = self.data, self.px, self.palette
        fleft, ftop = self.fleft, self.ftop
        p = self.base
        for y in range(self.fh):
            for x in range(self.fw):
                px[fleft + x, ftop + y] = palette[data[p]]
                p += 1

    def decode_line_runs(self) -> None:
        offs: tuple[int, ...] = struct.unpack_from(f"<{self.fh}I", self.data, self.base)
        for y in range(self.fh):
            self._line_runs(self.base + offs[y], y)

    def _line_runs(self, p: int, y: int) -> None:
        data, px, palette = self.data, self.px, self.palette
        fw, fleft, ftop = self.fw, self.fleft, self.ftop
        x = 0
        while x < fw:
            code, length = data[p], data[p + 1] + 1
            p += 2
            if code == 0xFF:
                for _ in range(length):
                    if x < fw:
                        px[fleft + x, ftop + y] = palette[data[p]]
                    p += 1
                    x += 1
            else:
                c = palette[code]
                for _ in range(length):
                    if x < fw:
                        px[fleft + x, ftop + y] = c
                    x += 1

    def decode_line_segments(self) -> None:
        offs: tuple[int, ...] = struct.unpack_from(f"<{self.fh}H", self.data, self.base)
        for y in range(self.fh):
            self._segments(self.base + offs[y], 0, self.fw, y)

    def decode_block_segments(self) -> None:
        fw, fh, base = self.fw, self.fh, self.base
        blocks = (fw + 31) // 32
        offs: tuple[int, ...] = struct.unpack_from(f"<{blocks * fh}H", self.data, base)
        for y in range(fh):
            for b in range(blocks):
                self._segments(base + offs[y * blocks + b], b * 32, min(b * 32 + 32, fw), y)

    def _segments(self, p: int, x: int, xend: int, y: int) -> None:
        data, px, palette = self.data, self.px, self.palette
        fleft, ftop = self.fleft, self.ftop
        while x < xend:
            seg = data[p]
            p += 1
            typ, length = seg >> 5, (seg & 0x1F) + 1
            if typ == 7:
                for _ in range(length):
                    if x < xend:
                        px[fleft + x, ftop + y] = palette[data[p]]
                    p += 1
                    x += 1
            else:
                c = palette[typ]
                for _ in range(length):
                    if x < xend:
                        px[fleft + x, ftop + y] = c
                    x += 1


def parse_def(data: bytes) -> list[list[Image.Image]]:
    """Parse a DEF file -> list of groups, each group = list of PIL Images."""
    _dtype, fw, fh, nblocks = struct.unpack_from("<IIII", data, 0)  # 4 fields before palette
    if nblocks == 0 or nblocks > 64:
        nblocks = 1
    pos = 16 + 256 * 3
    groups: list[list[Image.Image]] = []
    for _ in range(max(1, nblocks)):
        if pos + 8 > len(data):
            break
        _bid, nframes = struct.unpack_from("<II", data, pos)
        pos += 16
        if nframes > 200 or nframes <= 0:
            break
        pos += nframes * 13  # skip names
        if pos + nframes * 4 > len(data):
            break
        offsets: list[int] = list(struct.unpack_from("<" + "I" * nframes, data, pos))
        pos += nframes * 4
        frames: list[Image.Image] = []
        for foff in offsets:
            try:
                img = _decode_frame(data, foff)
                frames.append(img)
            except Exception:
                frames.append(Image.new("RGBA", (fw, fh), (0, 0, 0, 0)))
        groups.append(frames)
    return groups
