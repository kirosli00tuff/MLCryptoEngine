# MLCryptoEngine desktop

Tauri 2 desktop shell: a Rust backend that supervises the Python recorder and
telemetry processes, and a React + TypeScript + Tailwind frontend rendering the
dashboard (venue status, cortex, latency, coverage, live logs) and settings.

The app never talks to exchanges itself — it starts/stops the Python services,
tails their structured logs, and reads what they write to disk.

## Prerequisites

- **Node.js 20+** and npm
- **Rust** (stable) via [rustup](https://rustup.rs): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **uv** on PATH (the backend launches `uv run python -m data.recorder`)
- Tauri's Linux system dependencies:

### Ubuntu 22.04 / 24.04 / 26.04 (and Debian-based)

```bash
sudo apt update
sudo apt install -y \
  libwebkit2gtk-4.1-dev libgtk-3-dev libdbus-1-dev pkg-config \
  build-essential curl wget file \
  libxdo-dev libssl-dev \
  libayatana-appindicator3-dev librsvg2-dev
```

> Status on the operator's machine (Ubuntu 26.04, checked 2026-07-30): `glib-2.0`
> is present but `webkit2gtk-4.1`, `gtk+-3.0`, and `dbus-1` development files are
> **missing** — the first `cargo check` stops in `libdbus-sys` until the packages
> above are installed. Rust itself is already installed via rustup (`~/.cargo`).

### Fedora 40+

```bash
sudo dnf install -y \
  webkit2gtk4.1-devel \
  openssl-devel curl wget file \
  libappindicator-gtk3-devel librsvg2-devel \
  gcc gcc-c++ make libxdo-devel
```

## Run in development

From the repo root:

```bash
make desktop          # = cd desktop && npm run tauri dev
```

Or manually:

```bash
cd desktop
npm install
npm run tauri dev
```

The first Rust build compiles the Tauri stack and takes several minutes;
subsequent builds are incremental.

## Build a release binary

```bash
cd desktop
npm install
npm run tauri build
```

Bundles land in `desktop/src-tauri/target/release/bundle/` (AppImage, deb, and
rpm depending on the host).

## Frontend-only checks

```bash
cd desktop
npm run build     # tsc typecheck + vite production build (no Rust needed)
npm run dev       # vite dev server; outside Tauri the app shows empty states
                  # and a banner, since live data needs the shell
```

## Where things live

- Settings (including API keys) persist to the OS config dir
  (`~/.config/com.mlcryptoengine.desktop/settings.json` on Linux) — never in
  the repo.
- Window size/position persist via the window-state plugin.
- The backend resolves the repo root by walking up from its working directory
  to the first directory containing `pyproject.toml` + `data/`; override it in
  Settings → Repository if you run the binary from elsewhere.

## Icons

`src-tauri/icons/*.png` are generated: `python3 src-tauri/icons/gen_icons.py`
regenerates them (stdlib only, deterministic).
