#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qr_pure.py — dependency-free QR code PNG generator (byte mode, error correction M).

Used as automatic fallback when the `qrcode` package is not installed or fails, so the
payment QR (FamPay / Paytm / Manual) is ALWAYS generated.  Pure Python 3 (zlib + struct only).
"""
import struct
import zlib

# Error-correction tables for level M, index = version (0 unused)
_ECC_PER_BLOCK = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26,
                  26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28]
_NUM_BLOCKS = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20,
               21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49]
_FORMAT_M = 0  # format bits for ECC level M


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        na = ver // 7 + 2
        r -= (25 * na - 10) * na - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _NUM_BLOCKS[ver]


def _rs_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _rs_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _rs_mul(root, 2)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, c in enumerate(divisor):
            result[i] ^= _rs_mul(c, factor)
    return result


def _make_codewords(data: bytes):
    ver = None
    for v in range(1, 41):
        cc_bits = 8 if v <= 9 else 16
        if 4 + cc_bits + len(data) * 8 <= _data_codewords(v) * 8:
            ver = v
            break
    if ver is None:
        raise ValueError("data too long for QR")
    cc_bits = 8 if ver <= 9 else 16
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(0b0100, 4)
    put(len(data), cc_bits)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    nb = _NUM_BLOCKS[ver]
    ecc_len = _ECC_PER_BLOCK[ver]
    raw_cw = _raw_modules(ver) // 8
    n_short = nb - raw_cw % nb
    short_len = raw_cw // nb
    div = _rs_divisor(ecc_len)
    blocks = []
    k = 0
    for i in range(nb):
        dat = cw[k:k + short_len - ecc_len + (0 if i < n_short else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, div)
        if i < n_short:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= n_short:
                out.append(blk[i])
    return ver, out


class _Matrix:
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.m = [[False] * self.size for _ in range(self.size)]
        self.f = [[False] * self.size for _ in range(self.size)]

    def setf(self, x, y, dark):
        self.m[y][x] = bool(dark)
        self.f[y][x] = True

    def draw_function_patterns(self):
        s = self.size
        for i in range(s):
            self.setf(6, i, i % 2 == 0)
            self.setf(i, 6, i % 2 == 0)
        for (cx, cy) in ((3, 3), (s - 4, 3), (3, s - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    xx, yy = cx + dx, cy + dy
                    if 0 <= xx < s and 0 <= yy < s:
                        self.setf(xx, yy, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self.align_positions()
        n = len(pos)
        for i in range(n):
            for j in range(n):
                if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.setf(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        self.draw_version()

    def align_positions(self):
        ver = self.ver
        if ver == 1:
            return []
        n = ver // 7 + 2
        step = 26 if ver == 32 else (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
        res = [ver * 4 + 10 - i * step for i in range(n - 1)][::-1]
        return [6] + res

    def draw_format(self, mask):
        s = self.size
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1
        for i in range(0, 6):
            self.setf(8, i, bit(i))
        self.setf(8, 7, bit(6))
        self.setf(8, 8, bit(7))
        self.setf(7, 8, bit(8))
        for i in range(9, 15):
            self.setf(14 - i, 8, bit(i))
        for i in range(0, 8):
            self.setf(s - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.setf(8, s - 15 + i, bit(i))
        self.setf(8, s - 8, True)

    def draw_version(self):
        if self.ver < 7:
            return
        rem = self.ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.ver << 12 | rem
        s = self.size
        for i in range(18):
            b = (bits >> i) & 1
            a = s - 11 + i % 3
            c = i // 3
            self.setf(a, c, b)
            self.setf(c, a, b)

    def draw_codewords(self, data):
        s = self.size
        i = 0
        right = s - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = s - 1 - vert if upward else vert
                    if not self.f[y][x] and i < len(data) * 8:
                        self.m[y][x] = ((data[i >> 3] >> (7 - (i & 7))) & 1) != 0
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        for y in range(self.size):
            for x in range(self.size):
                if self.f[y][x]:
                    continue
                inv = [(x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0,
                       (x // 3 + y // 2) % 2 == 0, x * y % 2 + x * y % 3 == 0,
                       (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0][mask]
                if inv:
                    self.m[y][x] = not self.m[y][x]

    def penalty(self):
        s = self.size
        m = self.m
        p = 0
        for rows in (m, [list(r) for r in zip(*m)]):
            for row in rows:
                run = 1
                for i in range(1, s):
                    if row[i] == row[i - 1]:
                        run += 1
                    else:
                        if run >= 5:
                            p += run - 2
                        run = 1
                if run >= 5:
                    p += run - 2
                line = "".join("1" if v else "0" for v in row)
                p += 40 * (line.count("10111010000") + line.count("00001011101"))
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        dark = sum(sum(1 for v in r if v) for r in m)
        p += (abs(dark * 20 - s * s * 10) // (s * s)) * 10
        return p


def make_matrix(text):
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    ver, cw = _make_codewords(data)
    best = None
    for mask in range(8):
        mx = _Matrix(ver)
        mx.draw_function_patterns()
        mx.draw_codewords(cw)
        mx.apply_mask(mask)
        mx.draw_format(mask)
        pen = mx.penalty()
        if best is None or pen < best[0]:
            best = (pen, mx, mask)
    return best[1].m, ver, best[2]


def _png(rows_bits, width, height):
    raw = bytearray()
    for row in rows_bits:
        raw.append(0)
        raw.extend(row)

    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def qr_png_bytes(text, scale=10, border=4):
    matrix, _, _ = make_matrix(text)
    n = len(matrix)
    size = (n + border * 2) * scale
    white = bytes([255]) * size
    rows = []
    for _ in range(border * scale):
        rows.append(white)
    for y in range(n):
        line = bytearray()
        line += bytes([255]) * (border * scale)
        for x in range(n):
            line += (bytes([0]) if matrix[y][x] else bytes([255])) * scale
        line += bytes([255]) * (border * scale)
        for _ in range(scale):
            rows.append(bytes(line))
    for _ in range(border * scale):
        rows.append(white)
    return _png(rows, size, size)
