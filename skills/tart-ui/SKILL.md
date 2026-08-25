---
name: tart-ui
description: Drive a real macOS GUI inside a disposable Tart VM - take screenshots of the guest screen, click and type into it, and run commands (including xcodebuild / XCUITest) over plain SSH. Use when a change needs verifying in an actual Mac GUI, when GUI/UI-automation work must be isolated from the user's own desktop, or when the user mentions tart, a macOS VM, screenshotting a VM, or clicking inside a VM.
---

# tart-ui

Eyes and hands on a throwaway macOS desktop: `shot` returns a PNG of the guest
screen, `click`/`type`/`key` post real input into it, and `sh` runs arbitrary
commands. The screen is reached through Tart's own VNC server — the VM's real
console framebuffer, read on the host side of the virtualization boundary — so
**SIP stays enabled in the guest and no TCC database is ever written**. The
guest is a faithful stand-in for a real Mac, not a security-relaxed one.

Each command is one round trip with no session to open, keep alive, or clean
up, so calls can be interleaved with other work and resumed after a context
switch.

`bin/tart-ui` is the only entry point. Add it to PATH, or call it by path:

```bash
export PATH="$PWD/skills/tart-ui/bin:$PATH"   # or wherever the skill lives
export TART_VM=uitest                         # every command targets this VM
```

## Bring a VM up

```bash
TART_VM=uitest tart-ui up                     # TART_IMAGE selects the base image
```

`up` clones the image, boots it under Tart's VNC display, installs an SSH key,
quiets the desktop (no display sleep, screen saver, or screen lock), and does
not return until the guest is sitting on a **real logged-in desktop**, verified
by a screenshot. It is idempotent and safe to re-run.

`TART_IMAGE` defaults to `ghcr.io/cirruslabs/macos-tahoe-vanilla:latest`, whose
first use downloads tens of GB; set it to a local image name to clone that
instead. From an image you have already baked, `up` is a ~15 second boot.

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
tart-ui scroll -5                # negative scrolls down; scroll DY [X Y]
tart-ui type 'echo hello'
tart-ui key cmd+space            # key return / key escape / key cmd+shift+3
```

`type` and `key` are fast and lossless into ordinary apps. `cmd`, `opt`,
`ctrl` and `shift` modifiers all work (`key cmd+space`, `key cmd+shift+3`). If a
particularly picky app drops characters, slow typing with
`RFB_KEY_PRESS`/`RFB_KEY_GAP` (seconds per key press / gap).

## Run commands

```bash
tart-ui sh 'sw_vers -productVersion'
tart-ui push ./MyApp.app /tmp/   ;  tart-ui pull /tmp/result.log ./
tart-ui open Terminal            # launches AND waits until it is frontmost
tart-ui frontmost                # name of the frontmost app
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
successful. `tart-ui open` waits until the app is frontmost; after any other
action that changes focus, confirm with `tart-ui frontmost` or a screenshot.

## If the guest is showing a login screen

Auto-login and the disabled screen lock mean the VM normally sits on the
desktop. A guest paused long enough can still present a lock; `tart-ui login`
types the account password and confirms the desktop came back.

```bash
tart-ui login                    # get a locked guest back to its desktop
```

## Save your work into a new base image

```bash
tart-ui bake macos-ui            # shuts the guest down cleanly, then clones
TART_IMAGE=macos-ui TART_VM=next tart-ui up      # boots ready-to-use
```

Bake after installing anything worth keeping. **Shut down with `tart-ui down`,
never `tart stop`** — `tart stop` is a hard power cut that discards unsynced
writes without warning.

## What this VM is and is not

The guest runs with **SIP enabled** and its TCC databases untouched, so
behaviour that depends on System Integrity Protection — `launchctl` against
system domains, writes under `/System`, code-signing and platform-binary rules
— matches a real Mac. A test that turns on that boundary is meaningful here.

What it does not cover:

- **Accessibility-name automation.** Addressing controls by accessibility name
  (System Events, `AXUIElement`) needs the guest's Accessibility permission,
  which would mean writing TCC; tart-ui does not. Drive by pixel coordinates
  and screenshots instead. `frontmost` and `open` use `lsappinfo`, which needs
  no grant.
- **Camera:** none. **Audio:** off unless `TART_AUDIO=1`.

## When something looks wrong

| Symptom | Cause |
|---|---|
| `up` reports the desktop never came back | The console is on loginwindow. `tart-ui shot` to see it, then `tart-ui login`. |
| A screenshot is uniformly black | The display slept. Provisioning disables sleep; on a fresh unprovisioned guest, any input wakes it. |
| Clicks land, keystrokes don't | Focus, not input. Check `tart-ui frontmost`; a login/lock screen also drops normal-speed keys — use `tart-ui login`. |
| A modifier chord does nothing | Use `cmd`/`opt`/`ctrl`/`shift` names; wheel scrolling and Home/End/PageUp/PageDown are not delivered by the VNC server (see references/backends.md). |
| `exceeds the system limit` | Two VMs already running. |

[references/backends.md](references/backends.md) documents how the VNC channel
works — endpoint discovery, the pseudo-encoding requirement, the keysym and
button maps, pacing, and the channel's limits. Read it before changing
`bin/rfb.py` or `provision/provision.sh`.
