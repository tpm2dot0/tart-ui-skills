# tart-ui

An agent skill for driving a real macOS GUI inside a [Tart](https://tart.run)
VM: screenshot the guest screen, click and type into it, and run commands —
all over plain SSH.

Every operation is one `ssh` round trip. There is no daemon, no persistent
connection and no session state, so calls can be interleaved with other work
and resumed at any time.

```bash
export TART_VM=uitest
tart-ui up                          # clone + boot + provision
tart-ui shot /tmp/screen.png        # look
tart-ui open Terminal               # launch, and wait until it accepts input
tart-ui type 'echo hello'
tart-ui key return
tart-ui shot /tmp/after.png         # look again
```

Screenshot pixels map 1:1 onto click coordinates.

## Install

```bash
npx skills add tpm2dot0/tart-ui-skills --global --all
export PATH="$HOME/.agents/skills/tart-ui/bin:$PATH"
```

Requires `tart` (`brew install cirruslabs/cli/tart`), the Xcode command line
tools, and a macOS VM image to clone from.

## Provisioning

From a stock `cirruslabs/macos-*-vanilla` image, `tart-ui up` installs an SSH
key, disables SIP and reboots once, grants the SSH session the TCC permissions
needed for screen capture and synthetic input, and copies in a small
CoreGraphics helper. It then verifies capture and input over a fresh connection
before reporting the VM ready. `tart-ui bake <name>` freezes the result into a
reusable image.

[skills/tart-ui/references/tcc.md](skills/tart-ui/references/tcc.md) documents
the TCC mechanism behind those grants.

## Scope

These VMs run with SIP disabled and with the SSH session granted screen
recording and synthetic input. That is appropriate for a disposable test VM and
nothing else. The host's own security settings are never modified.

## License

MIT — see [LICENSE](LICENSE).
