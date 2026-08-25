# tart-ui

An agent skill for driving a real macOS GUI inside a [Tart](https://tart.run)
VM: screenshot the guest screen, click and type into it, and run commands —
all against a disposable, throwaway desktop.

The screen is reached through Tart's own VNC server: the VM's real console
framebuffer, read on the host side of the virtualization boundary. Nothing
inside the guest captures the screen or posts events, so **SIP stays enabled
and no TCC database is ever written** — the guest is a faithful stand-in for a
real Mac, not a security-relaxed one.

Every operation is one round trip. There is no daemon, no persistent
connection and no session state, so calls can be interleaved with other work
and resumed at any time.

```bash
export TART_VM=uitest
tart-ui up                          # clone + boot + provision, ends on a real desktop
tart-ui shot /tmp/screen.png        # look
tart-ui open Terminal               # launch, and wait until it is frontmost
tart-ui type 'echo hello'
tart-ui key return
tart-ui shot /tmp/after.png         # look again
```

Screenshot pixels map 1:1 onto click coordinates.

## Install

```bash
npx skills add tpm2dot0/tart-ui-skills --global --all
export PATH="$HOME/.claude/skills/tart-ui/bin:$PATH"
```

Requires `tart` (`brew install cirruslabs/cli/tart`), the Xcode command line
tools, and a macOS VM image to clone from.

## How it works

`tart-ui up` clones the image, boots it with `tart run --vnc-experimental`
(which attaches a real Virtualization.framework display and serves it over VNC
on the host loopback), installs an SSH key, and quiets the desktop — disabling
display sleep, the screen saver and the screen lock so the auto-logged-in
session stays on a usable desktop. It then confirms over the VNC channel that
the guest is on a real logged-in desktop before reporting the VM ready.
`tart-ui bake <name>` freezes the result into a reusable image.

Screen capture, pointer and keyboard all travel over the one VNC channel; the
guest is never asked to grant a permission or relax a protection.
[skills/tart-ui/references/how-it-works.md](skills/tart-ui/references/how-it-works.md)
documents the mechanism in detail.

## Scope

These VMs are disposable test machines. SIP stays enabled and the guest's
privacy settings are left as macOS shipped them; the host's own security
settings are never modified. Anything that needs the guest's Accessibility
permission (addressing controls by accessibility name) is out of scope, since
that would require writing TCC — drive by pixel coordinates and screenshots
instead.

## License

MIT — see [LICENSE](LICENSE).
