#!/usr/bin/env python3
"""One-shot RFB (VNC) client for Tart's built-in VNC server.

`tart run --vnc-experimental` serves the VM's real console framebuffer from
Virtualization.framework, so screenshots, pointer and keyboard all go through
this one channel while SIP stays enabled in the guest and nothing touches the
TCC databases. The endpoint (host, port, password) is random on every run;
tart-ui parses it from the boot log and passes it in.

Every invocation opens its own connection, does the work and closes: there is
no session to keep alive between calls.

Standard library only. DES (needed for VNC authentication) goes through
/usr/bin/openssl when that supports des-ecb -- macOS's LibreSSL does, while
Homebrew's OpenSSL 3 has dropped it -- and falls back to the implementation
below otherwise.
"""
import argparse
import os
import socket
import struct
import subprocess
import sys
import time
import zlib

# --------------------------------------------------------------------- DES
# Only ever used on VNC's 16-byte auth challenge.
_PC1 = [57,49,41,33,25,17,9,1,58,50,42,34,26,18,10,2,59,51,43,35,27,19,11,3,
        60,52,44,36,63,55,47,39,31,23,15,7,62,54,46,38,30,22,14,6,61,53,45,37,
        29,21,13,5,28,20,12,4]
_PC2 = [14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,26,8,16,7,27,20,13,2,
        41,52,31,37,47,55,30,40,51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32]
_IP  = [58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,62,54,46,38,30,22,14,6,
        64,56,48,40,32,24,16,8,57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,
        61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7]
_FP  = [40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,38,6,46,14,54,22,62,30,
        37,5,45,13,53,21,61,29,36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,
        34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25]
_E   = [32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,12,13,12,13,14,15,16,17,
        16,17,18,19,20,21,20,21,22,23,24,25,24,25,26,27,28,29,28,29,30,31,32,1]
_P   = [16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,
        2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25]
_SHIFT = [1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1]
_S = [
 [[14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7],[0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8],
  [4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0],[15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13]],
 [[15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10],[3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5],
  [0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15],[13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9]],
 [[10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8],[13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1],
  [13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7],[1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12]],
 [[7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15],[13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9],
  [10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4],[3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14]],
 [[2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9],[14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6],
  [4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14],[11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3]],
 [[12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11],[10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8],
  [9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6],[4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13]],
 [[4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1],[13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6],
  [1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2],[6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12]],
 [[13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7],[1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2],
  [7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8],[2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11]],
]


def _bits(data):
    return [(b >> i) & 1 for b in data for i in range(7, -1, -1)]


def _unbits(bits):
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)


def _perm(bits, table):
    return [bits[i - 1] for i in table]


def _des_block(key8, block8):
    k = _perm(_bits(key8), _PC1)
    c, d, ks = k[:28], k[28:], []
    for s in _SHIFT:
        c, d = c[s:] + c[:s], d[s:] + d[:s]
        ks.append(_perm(c + d, _PC2))
    b = _perm(_bits(block8), _IP)
    l, r = b[:32], b[32:]
    for rk in ks:
        x = [a ^ b2 for a, b2 in zip(_perm(r, _E), rk)]
        f = []
        for i in range(8):
            six = x[i * 6:i * 6 + 6]
            v = _S[i][(six[0] << 1) | six[5]][(six[1] << 3) | (six[2] << 2) | (six[3] << 1) | six[4]]
            f += [(v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1]
        l, r = r, [a ^ b2 for a, b2 in zip(l, _perm(f, _P))]
    return _unbits(_perm(r + l, _FP))


_OPENSSL_OK = None


def des_ecb(key8, data):
    """Encrypt data (multiple of 8 bytes) with DES-ECB."""
    global _OPENSSL_OK
    if _OPENSSL_OK is not False:
        try:
            p = subprocess.run(["/usr/bin/openssl", "enc", "-des-ecb",
                                "-K", key8.hex(), "-nopad"],
                               input=data, capture_output=True)
            if p.returncode == 0 and len(p.stdout) == len(data):
                _OPENSSL_OK = True
                return p.stdout
        except Exception:
            pass
        _OPENSSL_OK = False
    return b"".join(_des_block(key8, data[i:i + 8]) for i in range(0, len(data), 8))


# --------------------------------------------------------------------- PNG
def write_png(path, w, h, bgrx):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        row = bgrx[y * stride:(y + 1) * stride]
        rgb = bytearray(w * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        raw.append(0)
        raw += rgb

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    if path == "-":
        sys.stdout.buffer.write(png)
    else:
        with open(path, "wb") as f:
            f.write(png)
    return len(png)


# ------------------------------------------------------------------ keysyms
# Home, End, Page Up and Page Down are deliberately absent: the server drops
# those keysyms on the floor (probed with `cat -v` — Escape, Tab, the arrows,
# F-keys and forward delete all arrive, these four never do). Failing with
# "unknown key" beats silently doing nothing.
KEYSYMS = {
    "return": 0xFF0D, "enter": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B,
    "esc": 0xFF1B, "space": 0x20, "backspace": 0xFF08, "delete": 0xFF08,
    "forwarddelete": 0xFFFF,
    "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54,
    "f1": 0xFFBE, "f2": 0xFFBF, "f3": 0xFFC0, "f4": 0xFFC1, "f5": 0xFFC2,
    "f6": 0xFFC3, "f7": 0xFFC4, "f8": 0xFFC5, "f9": 0xFFC6, "f10": 0xFFC7,
    "f11": 0xFFC8, "f12": 0xFFC9,
}
# Virtualization.framework's keysym mapping, established empirically against
# its VNC server (macOS 26 guest): Alt_L/Alt_R are Command (cmd+q quits the
# frontmost app, cmd+shift+3 takes a screenshot, cmd+space opens Spotlight),
# Meta_L/Meta_R are Option (option+a inserts "å" in Terminal), and Super_L,
# Super_R, Hyper_L and ISO_Level3_Shift are ignored entirely.
MODSYMS = {
    "shift": 0xFFE1, "ctrl": 0xFFE3, "control": 0xFFE3,
    "alt": 0xFFE7, "opt": 0xFFE7, "option": 0xFFE7,   # Meta_L -> Option
    "cmd": 0xFFE9, "command": 0xFFE9,                 # Alt_L  -> Command
}
SHIFT = 0xFFE1

# Characters that need Shift held on the US layout. The server maps a keysym
# to a bare virtual key code, so "A" without Shift would land as "a"; the
# chord has to be explicit.
_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?') | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

# Keystroke pacing for ordinary apps, overridable per environment. Measured:
# even 0/0 typed long mixed-case strings into Terminal without a single drop
# over one connection, so these defaults are already conservative.
KEY_PRESS = float(os.environ.get("RFB_KEY_PRESS", "0.005"))   # down -> up
KEY_GAP = float(os.environ.get("RFB_KEY_GAP", "0.005"))       # between keys
# Settle before the first key of a `type`/`key` invocation. A focus change
# still animating when the events arrive swallows the first keystroke
# (observed: `click` into Terminal immediately followed by `type` lost the
# first character); this pause absorbs that.
KEY_SETTLE = float(os.environ.get("RFB_KEY_SETTLE", "0.3"))

# Login-window pacing. The loginwindow treats keystrokes as secure input and
# drops synthetic ones sent at app speed; one key per fresh connection with
# these settles landed 5/5 characters repeatably where a single sustained
# connection did not.
LOGIN_SETTLE = 0.15   # after connecting, before the key
LOGIN_HOLD = 0.05     # key down -> up
LOGIN_LINGER = 0.15   # after the key, before closing the connection
LOGIN_GAP = 0.2       # between connections


def keysym(name):
    n = name.lower()
    if n in KEYSYMS:
        return KEYSYMS[n]
    if len(name) == 1:
        cp = ord(name)
        return cp if cp < 0x100 else 0x01000000 + cp
    raise SystemExit("unknown key: %s" % name)


def char_keysym(ch):
    cp = ord(ch)
    return cp if cp < 0x100 else 0x01000000 + cp


# --------------------------------------------------------------------- RFB
class RFB:
    def __init__(self, host, port, password, timeout=20):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.recv(12)
        self.send(b"RFB 003.008\n")
        n = self.recv(1)[0]
        if n == 0:
            reason = self.recv(struct.unpack(">I", self.recv(4))[0])
            raise SystemExit("server refused: %s" % reason.decode(errors="replace"))
        types = list(self.recv(n))
        if 2 not in types:
            raise SystemExit("server does not offer VNC authentication (offered %s)" % types)
        self.send(b"\x02")
        challenge = self.recv(16)
        # VNC's DES key is the password, padded to 8 bytes, each byte bit-reversed.
        pw = password.encode()[:8].ljust(8, b"\x00")
        key = bytes(int("{:08b}".format(b)[::-1], 2) for b in pw)
        self.send(des_ecb(key, challenge))
        if struct.unpack(">I", self.recv(4))[0] != 0:
            raise SystemExit("VNC authentication failed (stale endpoint? re-run tart-ui boot)")
        self.send(b"\x01")                      # shared
        init = self.recv(24)
        self.w, self.h = struct.unpack(">HH", init[:4])
        self.recv(struct.unpack(">I", init[20:24])[0])
        # 32bpp true colour, little-endian, so pixels arrive as B,G,R,X.
        self.send(b"\x00\x00\x00\x00" + struct.pack(">BBBBHHHBBB3x",
                                                    32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        # Tart's server requires the desktop-size pseudo-encodings: a client
        # that offers only Raw crashes it ("FIXME IF: It is unclear if we can
        # support clients that don't support this pseudo encoding.") and takes
        # the VM down with it. It also sends Cursor and LastRect rectangles.
        encs = [0, -223, -308, -239, -224]   # Raw, DesktopSize, ExtendedDesktopSize, Cursor, LastRect
        self.send(struct.pack(">BxH", 2, len(encs))
                  + b"".join(struct.pack(">i", e) for e in encs))

    def send(self, data):
        self.s.sendall(data)

    def recv(self, n):
        out = bytearray()
        while len(out) < n:
            part = self.s.recv(n - len(out))
            if not part:
                raise SystemExit("connection closed by the server")
            out += part
        return bytes(out)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass

    # ---- input
    def pointer(self, x, y, mask=0):
        self.send(struct.pack(">BBHH", 5, mask, int(x), int(y)))

    def click(self, x, y, button=1, count=1):
        # Standard RFB button bits, which Tart's server follows: bit 0 left,
        # bit 1 middle, bit 2 right (verified: mask 4 opens the Finder
        # context menu, mask 2 does nothing visible).
        mask = {1: 1, 2: 2, 3: 4}.get(button, 1)
        self.pointer(x, y)
        time.sleep(0.15)
        for _ in range(count):
            self.pointer(x, y, mask)
            time.sleep(0.08)
            self.pointer(x, y, 0)
            time.sleep(0.10)

    def key(self, sym, down):
        self.send(struct.pack(">BBxxI", 4, 1 if down else 0, sym))

    def tap(self, sym, mods=()):
        for m in mods:
            self.key(m, True)
            time.sleep(0.05)
        self.key(sym, True)
        time.sleep(0.10)
        self.key(sym, False)
        for m in reversed(mods):
            time.sleep(0.05)
            self.key(m, False)
        time.sleep(0.12)

    def type_text(self, text):
        for ch in text:
            if ch == "\n":
                self.tap(0xFF0D)
                continue
            shifted = ch in _SHIFTED
            if shifted:
                self.key(SHIFT, True)
                time.sleep(KEY_PRESS)
            sym = char_keysym(ch)
            self.key(sym, True)
            time.sleep(KEY_PRESS)
            self.key(sym, False)
            if shifted:
                time.sleep(KEY_PRESS)
                self.key(SHIFT, False)
            time.sleep(KEY_GAP)

    def scroll(self, x, y, dy):
        # The server has no working wheel: the RFB wheel button bits (3/4)
        # are ignored outright — pulsed or held, nothing ever scrolls — and
        # the Page Up/Down keysyms are dropped too. Arrow keys are the
        # scrolling that does arrive, so a unit here is three arrow taps.
        # They go to the focused view: click the target first if it does not
        # own the keyboard.
        self.pointer(x, y)
        time.sleep(0.1)
        sym = 0xFF52 if dy > 0 else 0xFF54
        for _ in range(3 * abs(dy)):
            self.tap(sym)

    # ---- framebuffer
    def frame(self):
        buf = bytearray(self.w * self.h * 4)
        self.send(struct.pack(">BBHHHH", 3, 0, 0, 0, self.w, self.h))
        covered, guard = 0, 0
        while guard < 300:
            guard += 1
            msg = self.recv(1)[0]
            if msg == 0:                                    # FramebufferUpdate
                self.recv(1)
                nrect = struct.unpack(">H", self.recv(2))[0]
                done = False
                for _ in range(nrect):
                    x, y, w, h, enc = struct.unpack(">HHHHi", self.recv(12))
                    if enc == 0:            # Raw: the only rect with pixels
                        data = self.recv(w * h * 4)
                        for row in range(h):
                            dst = ((y + row) * self.w + x) * 4
                            buf[dst:dst + w * 4] = data[row * w * 4:(row + 1) * w * 4]
                        covered += w * h
                    elif enc == -239:       # Cursor: image + 1-bpp mask, discard
                        self.recv(w * h * 4 + ((w + 7) // 8) * h)
                    elif enc == -223:       # DesktopSize: w,h are new dimensions
                        self.w, self.h = w, h
                        buf = bytearray(self.w * self.h * 4)
                    elif enc == -308:       # ExtendedDesktopSize: x is the screen count
                        self.recv(4 + 16 * x)
                    elif enc == -224:       # LastRect: end of this update
                        done = True
                        break
                    else:
                        raise SystemExit("server used unexpected encoding %d" % enc)
                if (done or covered >= self.w * self.h) and covered > 0:
                    break
            elif msg == 1:                                  # SetColourMapEntries
                self.recv(3)
                _, count = struct.unpack(">HH", self.recv(4))
                self.recv(count * 6)
            elif msg == 2:                                  # Bell
                pass
            elif msg == 3:                                  # ServerCutText
                self.recv(3)
                self.recv(struct.unpack(">I", self.recv(4))[0])
            else:
                raise SystemExit("unexpected server message %d" % msg)
        return buf

    def shot(self, path):
        buf = self.frame()
        # A sleeping display answers with a uniform frame. Nudge the pointer
        # to wake it and take the next one; harmless when already awake.
        if len(set(bytes(buf[::4093]))) <= 1:
            self.pointer(self.w // 2, self.h // 2)
            time.sleep(1.2)
            buf = self.frame()
        return write_png(path, self.w, self.h, buf)


def login(host, port, password, text):
    """Type the login password at the loginwindow / lock screen and submit.

    One key per fresh connection: the loginwindow's secure input drops keys
    sent at app speed over a sustained connection, and this per-connection
    pacing is the one that proved 100% reliable. The first connection nudges
    the pointer to wake the display and a Backspace clears any stray
    character; Return submits from its own connection.
    """
    def one_key(sym):
        v = RFB(host, port, password)
        time.sleep(LOGIN_SETTLE)
        v.key(sym, True)
        time.sleep(LOGIN_HOLD)
        v.key(sym, False)
        time.sleep(LOGIN_LINGER)
        v.close()
        time.sleep(LOGIN_GAP)

    v = RFB(host, port, password)
    v.pointer(v.w // 2, v.h // 2)
    time.sleep(0.5)
    v.close()
    time.sleep(LOGIN_GAP)
    one_key(0xFF08)
    for ch in text:
        one_key(char_keysym(ch))
    one_key(0xFF0D)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=os.environ.get("RFB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("RFB_PORT", "0")))
    ap.add_argument("--password", default=os.environ.get("RFB_PASSWORD", ""))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("size")
    p = sub.add_parser("shot");   p.add_argument("path", nargs="?", default="-")
    p = sub.add_parser("click");  p.add_argument("x", type=int); p.add_argument("y", type=int)
    p.add_argument("--button", type=int, default=1); p.add_argument("--count", type=int, default=1)
    p = sub.add_parser("move");   p.add_argument("x", type=int); p.add_argument("y", type=int)
    p = sub.add_parser("drag")
    for a in ("x1", "y1", "x2", "y2"):
        p.add_argument(a, type=int)
    p = sub.add_parser("scroll"); p.add_argument("dy", type=int)
    p.add_argument("x", type=int, nargs="?", default=-1); p.add_argument("y", type=int, nargs="?", default=-1)
    p = sub.add_parser("key");    p.add_argument("combo")
    p = sub.add_parser("type");   p.add_argument("text")
    p = sub.add_parser("login");  p.add_argument("--login-password", default="admin")
    a = ap.parse_args()
    if not a.port:
        raise SystemExit("--port (or RFB_PORT) is required")

    if a.cmd == "login":
        # Multiple short-lived connections; see login().
        login(a.host, a.port, a.password, a.login_password)
        return

    v = RFB(a.host, a.port, a.password)
    if a.cmd == "size":
        print("%dx%d" % (v.w, v.h))
    elif a.cmd == "shot":
        n = v.shot(a.path)
        if a.path != "-":
            print("%s (%dx%d, %d bytes)" % (a.path, v.w, v.h, n))
    elif a.cmd == "click":
        v.click(a.x, a.y, a.button, a.count)
    elif a.cmd == "move":
        v.pointer(a.x, a.y)
    elif a.cmd == "drag":
        v.pointer(a.x1, a.y1); time.sleep(0.15)
        v.pointer(a.x1, a.y1, 1); time.sleep(0.15)
        for i in range(1, 11):
            v.pointer(a.x1 + (a.x2 - a.x1) * i // 10,
                      a.y1 + (a.y2 - a.y1) * i // 10, 1)
            time.sleep(0.03)
        v.pointer(a.x2, a.y2, 0)
    elif a.cmd == "scroll":
        x = a.x if a.x >= 0 else v.w // 2
        y = a.y if a.y >= 0 else v.h // 2
        v.scroll(x, y, a.dy)
    elif a.cmd == "key":
        parts = a.combo.split("+")
        mods = [MODSYMS[p2.lower()] for p2 in parts[:-1] if p2.lower() in MODSYMS]
        time.sleep(KEY_SETTLE)
        v.tap(keysym(parts[-1]), mods)
    elif a.cmd == "type":
        time.sleep(KEY_SETTLE)
        v.type_text(a.text)
    time.sleep(0.25)   # let the last event reach the guest before the socket closes


if __name__ == "__main__":
    main()
