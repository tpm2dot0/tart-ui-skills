#!/usr/bin/env bash
# Guest-side provisioning, copied in and run over SSH by `tart-ui up`.
# Idempotent, and deliberately small: the screen is reached through Tart's own
# VNC server, which needs nothing from the guest — no SIP change, no TCC
# grant, no Screen Sharing daemon. All that has to hold inside the guest is
# that the console stays on a usable desktop.
set -uo pipefail
log() { printf '[provision] %s\n' "$*"; }

GUEST_PASS="${TART_PASS:-admin}"

# The base image auto-logs `admin` into the console at boot; with Tart's VNC
# display attached that lands straight on a real desktop. What remains is
# keeping it there: captures have to be reproducible, and a display allowed to
# sleep answers VNC with a black frame.
sudo pmset -a displaysleep 0 sleep 0 disksleep 0 >/dev/null 2>&1
defaults -currentHost write com.apple.screensaver idleTime -int 0 2>/dev/null

# Screenshots taken inside the guest should not carry window shadows.
defaults write com.apple.screencapture disable-shadow -bool true 2>/dev/null

# The screen lock is separate from display sleep and the screen saver, and it
# is the one that matters: a locked console treats keystrokes as secure input
# and drops most synthetic ones. Turning it off keeps the VM drivable after a
# pause; `tart-ui login` covers the residual case.
sysadminctl -screenLock off -password "$GUEST_PASS" >/dev/null 2>&1
defaults write com.apple.screensaver askForPassword -int 0 2>/dev/null
defaults -currentHost write com.apple.screensaver askForPassword -int 0 2>/dev/null

sync
log "desktop quieted ($(csrutil status))"
