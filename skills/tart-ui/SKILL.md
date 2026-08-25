---
name: tart-ui
description: Drive a real macOS GUI inside a disposable Tart VM - take screenshots of the guest screen, click and type into it, and run commands (including xcodebuild / XCUITest) over plain SSH. Use when a change needs verifying in an actual Mac GUI, when GUI/UI-automation work must be isolated from the user's own desktop, or when the user mentions tart, a macOS VM, screenshotting a VM, or clicking inside a VM.
---

# tart-ui

Eyes and hands on a throwaway macOS desktop: `shot` returns a PNG of the guest
screen, `click`/`type`/`key` post real HID events into it, and `sh` runs
arbitrary commands. Each command is one `ssh` round trip, with no session to
open, keep alive, or clean up, so calls can be interleaved with other work and
resumed after a context switch.

`bin/tart-ui` is the only entry point. Add it to PATH, or call it by path:

```bash
export PATH="$PWD/skills/tart-ui/bin:$PATH"   # or wherever the skill lives
export TART_VM=uitest                         # every command targets this VM
```

## Bring a VM up

```bash
TART_VM=uitest tart-ui up                     # TART_IMAGE selects the base image
```

`TART_IMAGE` defaults to `ghcr.io/cirruslabs/macos-tahoe-vanilla:latest`, whose
first use downloads tens of GB; set it to a local image name to clone that
instead. `up` is idempotent and safe to re-run.

From a stock *vanilla* image the first run takes about a minute, most of it the
SIP-off reboot (see [references/tcc.md](references/tcc.md) for why that is
needed). From an image you have already baked it is a ~11 second boot.

**macOS runs at most two VMs at once.** `tart list` shows what is up; `tart-ui
up` fails immediately when the slot is taken instead of hanging until timeout.

## Look at the screen

```bash
tart-ui shot /tmp/screen.png     # then read the PNG with your image tool
tart-ui shot - > /tmp/screen.png # raw PNG on stdout
tart-ui size                     # e.g. 1440x900
```

**Screenshot pixels map 1:1 to click coordinates.** `tart-ui up` pins the
display in `px` units, which keeps macOS out of HiDPI mode — so a button you
measure at (719, 445) in the PNG is exactly `tart-ui click 719 445`. Do not
halve anything.

## Drive it

```bash
tart-ui click 719 445            # also: rclick, dclick, move
tart-ui drag 100 100 400 300
tart-ui scroll -5                # negative scrolls down
tart-ui type 'echo hello'
tart-ui key cmd+space            # key return / key escape / key cmd+shift+4
tart-ui button Save              # click a button by its accessibility name
tart-ui allow                    # clear macOS's screen-recording consent sheet
```

`button` scans every process, so it also reaches system sheets that do not
belong to the app being driven. Prefer it to pixel coordinates whenever the
target has an accessibility name.

## Run commands

```bash
tart-ui sh 'sw_vers -productVersion'
tart-ui push ./MyApp.app /tmp/   ;  tart-ui pull /tmp/result.log ./
tart-ui open Terminal            # launches AND waits until it owns the keyboard
tart-ui xctest -project My.xcodeproj -scheme MyAppUITests test
```

`xctest` needs an Xcode inside the guest; the vanilla image has none. Either
install one in the VM and bake it, or clone from
`ghcr.io/cirruslabs/macos-tahoe-xcode:latest` (a ~90 GB pull).

## The act-look-verify loop

Confirm each step before taking the next one:

```bash
tart-ui open Safari
tart-ui shot /tmp/1.png          # read it: is the window where you think?
tart-ui click 640 300
tart-ui shot /tmp/2.png          # confirm the click landed before the next one
```

**Never `sleep N` then type.** An app takes focus before its window exists, and
keystrokes sent into that gap are dropped silently while the launch still looks
successful. `tart-ui open` waits for both conditions; after any other action
that changes focus, confirm with `tart-ui frontmost` or a screenshot.

## Save your work into a new base image

```bash
tart-ui bake macos-ui            # shuts the guest down cleanly, then clones
TART_IMAGE=macos-ui TART_VM=next tart-ui up      # boots ready-to-use
```

Bake after installing anything worth keeping. **Shut down with `tart-ui down`,
never `tart stop`** — `tart stop` is a hard power cut that discards unsynced
writes without warning.

## What this VM is not

Provisioning disables SIP, so **the guest is not a faithful stand-in for a user's
Mac wherever SIP is what changes the behaviour**. Anything refused with
"Operation not permitted while System Integrity Protection is engaged" — most
`launchctl` verbs against system domains, writes under `/System`, attaching to
platform binaries — will *succeed here and fail in the field*. A test that
depends on that boundary passes in this VM and tells you nothing. Verify those
paths on a SIP-on machine.

Audio pass-through is off unless `TART_AUDIO=1`, and the guest has no camera.

## When something looks wrong

| Symptom | Cause |
|---|---|
| `could not create image from display` | TCC denial, *not* a missing display. Re-run `tart-ui provision`. |
| Screenshot fine, clicks do nothing | Accessibility/PostEvent grant missing, or SIP came back on. `tart-ui sh 'csrutil status'`. |
| A consent sheet covers the screen | `tart-ui allow`. macOS re-asks on its own timer; provisioning defers it but cannot fully suppress it. Captures still succeed — the sheet just pollutes the frame. |
| A capture "succeeded" but the file is missing | `screencapture` exits 0 even when it fails to write, and it refuses **any dot-prefixed filename** in any directory. Never name a capture `.something.png`, and check the file, not `$?`. |
| Typing goes to the wrong place | Focus, not input. Check `tart-ui frontmost`. |
| `exceeds the system limit` | Two VMs already running. |

[references/tcc.md](references/tcc.md) documents how the TCC grants are
derived, how to re-diagnose them from tccd's logs, and why SIP must be
disabled. Read it before changing `provision/provision.sh`.
