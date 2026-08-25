#!/usr/bin/env bash
# Guest-side provisioning, copied in and run over SSH by `tart-ui up`.
# Idempotent. Exit 42 means "SIP was just turned off — reboot me and run again".
#
# Everything here serves one goal: a command arriving over SSH must be able to
# see and drive the Aqua session already logged in inside the VM.
set -uo pipefail
log() { printf '[provision] %s\n' "$*"; }

USER_DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"
SYS_DB="/Library/Application Support/com.apple.TCC/TCC.db"
GUEST_PASS="${TART_PASS:-admin}"
GUEST_USER="$(id -un)"

# ---------------------------------------------------------------------- SIP
# The screen-capture decision is made by the *system* tccd against
# /Library/.../TCC.db, and that file is read-only while SIP is on — root
# included. So SIP has to go first. In a VM (unlike real hardware) `csrutil
# disable` works from the booted OS: it asks three questions on the terminal
# instead of demanding Recovery.
if csrutil status | grep -q enabled; then
  log "SIP is on — disabling it (VM-only path, no Recovery needed)"
  cat > /tmp/.sipoff.exp <<'EXP'
#!/usr/bin/expect -f
set timeout 60
set user [lindex $argv 0]
set pass [lindex $argv 1]
spawn sudo csrutil disable
expect -ex {[y/n]}
send "y\r"
expect -ex {Authorized user}
sleep 0.5
send "$user\r"
expect -ex {Password}
sleep 0.5
send "$pass\r"
expect { timeout {puts "\nTIMEOUT"} eof {} }
EXP
  out="$(expect /tmp/.sipoff.exp "$GUEST_USER" "$GUEST_PASS" 2>&1)"
  rm -f /tmp/.sipoff.exp
  if echo "$out" | grep -q "System Integrity Protection is off"; then
    sync
    log "SIP disabled; a reboot is required before it takes effect"
    exit 42
  fi
  log "FATAL: could not disable SIP:"; echo "$out" | tail -8
  exit 1
fi
log "SIP is off"

# ---------------------------------------------------------------------- TCC
# An SSH command is attributed to the *responsible* process, which is the sshd
# session binary, not the command itself. The subject tccd matches on is
# the path /usr/libexec/sshd-keygen-wrapper with client_type 1; the other three
# spellings are included for compatibility across macOS versions.
row() { # service client client_type [indirect_object]
  echo "INSERT OR REPLACE INTO access
    (service,client,client_type,auth_value,auth_reason,auth_version,
     indirect_object_identifier_type,indirect_object_identifier,flags,last_modified)
    VALUES ('$1','$2',$3,2,2,1,0,'${4:-UNUSED}',0,strftime('%s','now'));"
}

SSH_PATHS="/usr/libexec/sshd-keygen-wrapper /usr/libexec/sshd-session"
SSH_IDS="com.apple.sshd-keygen-wrapper com.apple.sshd-session"
SERVICES="kTCCServiceScreenCapture kTCCServiceAccessibility kTCCServicePostEvent
          kTCCServiceListenEvent kTCCServiceDeveloperTool kTCCServiceSystemPolicyAllFiles"

log "granting TCC to the ssh session"
for s in $SERVICES; do
  for c in $SSH_PATHS; do
    sudo sqlite3 "$SYS_DB" "$(row "$s" "$c" 1)" 2>/dev/null
    sqlite3      "$USER_DB" "$(row "$s" "$c" 1)" 2>/dev/null
  done
  for c in $SSH_IDS; do
    sudo sqlite3 "$SYS_DB" "$(row "$s" "$c" 0)" 2>/dev/null
    sqlite3      "$USER_DB" "$(row "$s" "$c" 0)" 2>/dev/null
  done
done

# UI scripting: System Events needs Accessibility, and the session needs
# permission to send it AppleEvents. Together these allow addressing controls
# by accessibility name rather than by pixel coordinate.
sudo sqlite3 "$SYS_DB" "$(row kTCCServiceAccessibility com.apple.systemevents 0)" 2>/dev/null
for c in $SSH_PATHS; do
  sudo sqlite3 "$SYS_DB"  "$(row kTCCServiceAppleEvents "$c" 1 com.apple.systemevents)" 2>/dev/null
  sqlite3      "$USER_DB" "$(row kTCCServiceAppleEvents "$c" 1 com.apple.systemevents)" 2>/dev/null
done

# macOS 15+ re-asks "…is requesting to bypass the system private window picker"
# on a weekly timer driven by last_reminded. Push it ten years out.
sudo sqlite3 "$SYS_DB" \
  "update access set last_reminded=strftime('%s','now')+315360000 where service='kTCCServiceScreenCapture';" 2>/dev/null

sync
sudo killall tccd 2>/dev/null; killall tccd 2>/dev/null; sleep 2

# ------------------------------------------------------------------ settings
# Keep the screen on and still, so captures are reproducible.
sudo pmset -a displaysleep 0 sleep 0 disksleep 0 >/dev/null 2>&1
defaults -currentHost write com.apple.screensaver idleTime -int 0 2>/dev/null
defaults write com.apple.screencapture disable-shadow -bool true 2>/dev/null

# ------------------------------------------------------------------- verify
# Only what this session can check. tccd decides once per sshd session and
# caches the result, so this connection was denied before the grant existed and
# will keep failing regardless of the database contents. Confirming the grant
# requires a fresh connection, which the host opens.
[ -x "$HOME/bin/uictl" ] || { log "FATAL: ~/bin/uictl missing"; exit 1; }
sync
log "grants written — host will verify over a new connection"
