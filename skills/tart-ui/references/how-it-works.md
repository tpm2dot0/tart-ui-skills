# How tart-ui reaches the guest screen

tart-ui has a single mechanism: Tart's built-in VNC server. `tart-ui boot`
launches the VM with `tart run --vnc-experimental --no-graphics`, which
attaches a real Virtualization.framework display to the guest and serves that
display's framebuffer over RFB on the host loopback. Screenshots, pointer
events and keyboard events all travel over this one channel.

Because the framebuffer is read on the host side of the virtualization
boundary, the guest needs nothing:

- **SIP stays enabled.** Nothing inside the guest captures the screen or
  posts events, so nothing needs a System Integrity Protection exception.
- **No TCC database is written.** Screen capture and input happen below the
  guest OS, where TCC does not apply. The guest's privacy databases stay
  exactly as macOS shipped them.
- **No Screen Sharing daemon is armed.** The RFB server is Tart's, on the
  host; the guest's Remote Management stack stays off.

The attached display is also what makes the desktop reachable at all: macOS
only fronts an auto-logged-in user session on a console that has a display.
The same image booted with `--no-graphics` alone (no VNC display) parks the
console on loginwindow indefinitely. `--no-graphics` next to
`--vnc-experimental` only suppresses opening a host viewer window.

## The endpoint is random on every run

`tart run --vnc-experimental` prints exactly one line naming the endpoint,
`vnc://:<password>@127.0.0.1:<port>` (prefixed "Opening ..." in viewer mode,
"VNC server is running at ..." with `--no-graphics`). Port and password are
freshly generated each run and there is no flag to pin them. `tart-ui boot`
parses this line from the VM's log and persists `HOST PORT PASSWORD` to
`~/.config/tart-ui/<vm>.vnc` (mode 600); every screen and input command reads
that file. Authentication is standard VNC security type 2 (DES challenge).

## The pseudo-encoding requirement

Tart's server requires the client to advertise the desktop-size
pseudo-encodings. A client that offers only Raw crashes the server — and the
VM with it — with:

    FIXME IF: "It is unclear if we can support clients that don't support this pseudo encoding."

`bin/rfb.py` therefore advertises, as signed 32-bit values: `0` (Raw), `-223`
(DesktopSize), `-308` (ExtendedDesktopSize), `-239` (Cursor), `-224`
(LastRect), and its framebuffer loop consumes all five rectangle types (only
Raw carries pixels; Cursor rectangles are discarded, DesktopSize resizes the
buffer, ExtendedDesktopSize is skipped over, LastRect ends the update).

## Keyboard mapping and pacing

The server maps RFB keysyms to Mac virtual keys with a convention that was
established empirically against a macOS 26 guest:

| Modifier | Keysym | Notes |
|----------|--------|-------|
| Shift    | `0xFFE1` Shift_L | |
| Control  | `0xFFE3` Control_L | |
| Command  | `0xFFE9` Alt_L (also `0xFFEA` Alt_R) | verified via cmd+q, cmd+shift+3, cmd+space |
| Option   | `0xFFE7` Meta_L (also `0xFFE8` Meta_R) | verified via option+a → "å" |

Super_L/R, Hyper_L and ISO_Level3_Shift are ignored by the server, and so are
the Home, End, Page Up and Page Down keysyms (probed with `cat -v`: Escape,
Tab, the arrows, F-keys and forward delete arrive; those four never do).
Letter and symbol keysyms map to unshifted virtual keys, so `rfb.py` holds
Shift explicitly for characters that need it.

Pointer buttons follow the RFB standard: mask bit 0 is left, bit 1 middle,
bit 2 right (bit 2 opens context menus). The wheel bits (3/4) are ignored
outright — pulsed or held, nothing scrolls — so `scroll` is implemented as
arrow-key taps into the focused view instead of wheel events.

Into an ordinary app the channel is fast and lossless: long mixed-case
strings typed with zero inter-key delay arrive intact. `rfb.py` still spaces
keys by 5 ms (`RFB_KEY_PRESS`/`RFB_KEY_GAP` override this) as margin. The
loginwindow and lock screen are the exception: their secure input drops keys
sent at that speed, and only one key per fresh RFB connection (~0.15 s settle
before, ~0.2 s pause after) proved fully reliable. `tart-ui login` uses that
pacing.

## Latency and limits

- Every command opens a fresh RFB connection; an operation costs roughly a
  round of handshake plus its events. A full 1440x900 Raw framebuffer read
  (`shot`) transfers ~5 MB and completes in about a second.
- Anything that needs the guest's Accessibility permission — addressing
  controls by accessibility name through System Events, `AXUIElement`
  automation — is out of scope: that would require a TCC grant, and tart-ui
  does not write TCC. `frontmost`/`open` use `lsappinfo`, which needs no
  grant; everything else is pixels and coordinates.
- No camera pass-through. Audio pass-through only with `TART_AUDIO=1`.
- The framebuffer is the console: if the guest locks or logs out, that is
  what the channel sees. Provisioning disables display sleep, the screen
  saver and the screen lock so the desktop stays up; `tart-ui login` types
  the account password if a lock still appears.
- A window dragged partly past the display edge can stop repainting in the
  framebuffer (its contents freeze while input keeps working); dragging it
  fully back on-screen repaints it. Keep windows inside the display bounds
  when screenshots of them matter.
