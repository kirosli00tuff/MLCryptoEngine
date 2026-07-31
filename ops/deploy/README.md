# Continuous recording

From Stage 1.6 onward the recorder is treated as always-on infrastructure
rather than something started by hand for a particular day. Phase B needs many
days across different volatility regimes, and no amount of modeling recovers
data that was never captured — a missed day is gone permanently, at any price.

These are **systemd user units**, not system units. The recorder needs no root,
no privileged port, and no credentials (Stage 1 is public market data only, and
CLAUDE.md rule 4 forbids the project from persisting any), so it has no reason
to run as a system service.

## ⚠ Do not activate during the current run

A full-day capture started **2026-07-30T19:58:34Z** to enclose **2026-07-31
UTC** and is running now as detached `setsid nohup` processes. Enabling these
units before it finishes would start a *second* recorder writing into the same
hour files and a second telemetry probe rewriting the same day partition.

**Leave these units installed but inactive.** Activate only after:

1. the run is stopped (`pkill -TERM -f "python -m data.recorder"; pkill -TERM -f
   "python -m ops.telemetry"` — SIGTERM so the zstd frame closes cleanly),
2. `uv run python -m data.validate --date 2026-07-31` has been run, and
3. `report.md` shows PASS on both venues against all four Phase A criteria.

Verify nothing is running before you enable anything:

```bash
pgrep -af "data.recorder|ops.telemetry"   # must print nothing
```

## Install

The units hard-code `WorkingDirectory` and the absolute path to `uv`, because
systemd expands neither `~` nor `$HOME` in either directive. Confirm both match
this machine before installing:

```bash
command -v uv        # must match ExecStart in both unit files
pwd                  # must match WorkingDirectory (run from the repo root)
```

Then link and load them:

```bash
mkdir -p ~/.config/systemd/user
ln -sf "$PWD/ops/deploy/mlce-recorder.service"  ~/.config/systemd/user/
ln -sf "$PWD/ops/deploy/mlce-telemetry.service" ~/.config/systemd/user/
systemctl --user daemon-reload
```

Symlinking rather than copying means `git pull` updates the units; re-run
`systemctl --user daemon-reload` after any change to a unit file.

## Enable (only when the section above says it is safe)

```bash
systemctl --user enable --now mlce-recorder.service
systemctl --user enable --now mlce-telemetry.service
```

`--now` starts the unit immediately as well as enabling it at login.

### Survive logout and reboot

A user manager normally exits with your last session, which would stop the
recorder every time you log out. Linger keeps it running:

```bash
loginctl enable-linger "$USER"
loginctl show-user "$USER" --property=Linger   # expect Linger=yes
```

Without this, `enable` only means "start when I next log in" — which is not
what always-on means. This is the step most easily forgotten, and its failure
mode is silent: everything looks correct until the first reboot.

## Operate

```bash
make status                                  # liveness, heartbeat age, today's bytes, free disk
systemctl --user status mlce-recorder        # unit state and last restart
journalctl --user -u mlce-recorder -f        # live JSON log lines
journalctl --user -u mlce-recorder -p warning --since today
```

`make status` exits non-zero when a process is down, a venue heartbeat is
stale, or free space is below the critical threshold, so it works in a cron
check as well as by eye.

Both units use `Restart=always` with `StartLimitIntervalSec=0`. The rate-limit
default would put a unit into permanent `failed` state after five restarts in
ten seconds — exactly the outcome `Restart=always` exists to avoid. Venue-side
disconnects never reach systemd at all: the recorder reconnects internally with
jittered exponential backoff and logs each gap to `gaps.jsonl`.

## Stopping

```bash
systemctl --user stop mlce-recorder.service     # SIGTERM: closes the zstd frame cleanly
systemctl --user disable --now mlce-recorder.service
```

Always stop through systemd rather than `kill -9`. `SIGKILL` truncates the
current zstd block; the reader tolerates it, but the final partial block of
that hour is lost.

## Disk

The recorder logs a loud warning below `disk.warn_free_gb` (default 50 GB) and
an error below `disk.critical_free_gb` (default 20 GB), configurable in
`config/default.yaml` or via `MLCE_DISK__WARN_FREE_GB`. It **warns only** —
nothing stops recording and nothing is ever deleted. A full disk costs the tail
of one day; a guard that reacts by pruning costs days already banked. Raw
recorded data is immutable (CLAUDE.md), so the response to low disk is a human
moving completed days elsewhere, never an automatic one.
