# TCC and the SSH session

The grants written by `provision.sh` all follow from how macOS attributes a
screen-capture request that arrives over SSH. This page records that mechanism
so the grants can be re-derived rather than taken on trust.

## The error message is misleading

```
$ ssh vm 'screencapture -x /tmp/s.png'
could not create image from display
```

This suggests a missing display, but it is what CoreGraphics returns whenever
a capture is refused, and TCC refusal is the most common reason. The same
message appears on a physical Mac with a working screen when the calling
terminal lacks Screen Recording. Rule out TCC before investigating the
display.

To rule it out, ask CoreGraphics directly — display enumeration is not gated:

```bash
tart-ui sh 'python3 -c "
import ctypes
cg = ctypes.CDLL(\"/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics\")
n = ctypes.c_uint32(); a = (ctypes.c_uint32*8)()
cg.CGGetActiveDisplayList(8, a, ctypes.byref(n)); print(\"displays:\", n.value)"'
```

(`--no-graphics` does *not* remove the guest's display; a headless Tart VM still
runs a full WindowServer and Aqua session.)

## Ask tccd what it actually checked

```bash
tart-ui sh 'screencapture -x /tmp/probe.png; sleep 2;
  log show --last 20s --predicate "subsystem == \"com.apple.TCC\"" --style compact |
  grep -E "AUTHREQ_SUBJECT|AUTHREQ_RESULT|Platform"'
```

On an unprovisioned guest this prints, in order:

```
AUTHREQ_ATTRIBUTION: attribution={responsible={identifier=com.apple.sshd-keygen-wrapper,
    responsible_path=/usr/libexec/sshd-keygen-wrapper, binary_path=/usr/libexec/sshd-session},
    accessing={identifier=com.apple.screencapture, binary_path=/usr/sbin/screencapture}, …}
AUTHREQ_SUBJECT: subject=/usr/libexec/sshd-keygen-wrapper
Platform binary prompting is 'Deny' because: is Platform Binary
Service kTCCServiceScreenCapture does not allow prompting; returning denied.
AUTHREQ_RESULT: authValue=0, authReason=5
```

Three properties follow, and together they determine the grants:

1. **The subject is the SSH session, not your command.** TCC attributes to the
   *responsible* process. Granting `screencapture` itself would do nothing;
   the row has to name `/usr/libexec/sshd-keygen-wrapper`, `client_type` 1
   (a path, not a bundle id).
2. **You will never be prompted.** sshd is a platform binary, so macOS refuses
   to even show a consent dialog. There is no interactive path to this
   permission — the database is the only way in.
3. **The verdict comes from `tccd` running as uid 0**, which reads
   `/Library/Application Support/com.apple.TCC/TCC.db` — the *system* database.
   Writing the per-user database at `~/Library/…` changes nothing for this
   service, even though that file is writable and looks like the obvious target.

## SIP must be disabled

The system database is SIP-protected: root gets `attempt to write a readonly
database (8)`. `cirruslabs/macos-*-vanilla` images ship with SIP **on** (their
`-base`/`-xcode` images ship with it off).

In a VM — unlike real hardware — `csrutil disable` works from the booted OS and
asks its three questions on the terminal rather than demanding Recovery:

```
Allow booting unsigned operating systems and any kernel extensions…? [y/n]: y
Authorized user: admin
Password       : ****
System Integrity Protection is off.
```

`provision.sh` drives that with `expect` and returns exit 42 so the host knows
to reboot and come back. The account must be a volume owner with a Secure Token
— the stock `admin` user is (`sysadminctl -secureTokenStatus admin`).

## The grant

```sql
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version,
   indirect_object_identifier_type, indirect_object_identifier, flags, last_modified)
VALUES ('kTCCServiceScreenCapture', '/usr/libexec/sshd-keygen-wrapper', 1,
        2, 2, 1, 0, 'UNUSED', 0, strftime('%s','now'));
```

`auth_value` 2 is "allowed". `csreq` may be left NULL — the stock database
already ships rows with a NULL csreq (`com.apple.screensharing.agent`), so TCC
does not require one. `kTCCServiceAccessibility` and `kTCCServicePostEvent`
(what `uictl` needs to post clicks) live in the same system database;
`kTCCServiceAppleEvents` is per-user and needs the target's bundle id in
`indirect_object_identifier`.

**tccd caches its verdict per sshd session.** The connection that ran the
`INSERT` was already denied and will keep failing however correct the database
now is. Verification must therefore happen over a *new* SSH connection, which
is why `provision.sh` does not check its own result.

## Two undocumented screencapture behaviours

- **It refuses any dot-prefixed filename**, in every directory:
  `screencapture -x /tmp/.probe.png` → `cannot write file to intended
  destination`. `/tmp/probe.png` succeeds. A hidden temp file therefore never
  works, without a distinguishing error.
- **It exits 0 when that write fails.** `screencapture … && cat file`
  consequently "succeeds" into a missing file. Test the file, not the exit
  code.

## The consent sheet

macOS 15+ periodically shows *"com.apple.sshd-session is requesting to bypass
the system private window picker…"*. Captures still succeed, but the sheet sits
on top and pollutes every frame. Pushing `last_reminded` far into the future
defers it but does not reliably prevent it.

The sheet belongs to **UserNotificationCenter**, not to the app being driven,
so a click targeting the frontmost process does not reach it. `tart-ui allow`
scans every process for a button named `Allow`.
