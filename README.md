# Teensy Panel downloads

Windows and macOS installers for the Teensy 4.1 experiment controller. This
repository contains release downloads; application source is maintained privately.

**The release pipeline is being set up. Installers will appear in Releases once
the initial validation and publication setup are complete.**

## Choose a release

- [Stable releases](https://github.com/venkatkidambi/teensy-panel-releases/releases/latest)
  are versioned builds for regular use.
- [All releases](https://github.com/venkatkidambi/teensy-panel-releases/releases)
  includes nightly development builds, marked as prereleases.

Stable and nightly are separate applications. Only one can connect to a Teensy
at a time. Updates stay on the application's installed channel.

## Install

| Computer | Download |
| --- | --- |
| Windows 10/11, x64 | `x86_64-pc-windows-msvc-…setup.exe` |
| Mac with Apple Silicon, macOS 12+ | `aarch64-apple-darwin-….dmg` |
| Intel Mac, macOS 12+ | `x86_64-apple-darwin-….dmg` |

On Windows, run the setup EXE. It includes WebView2 for offline installation.
On Mac, open the DMG and drag the application into Applications. Initial Mac
builds are not Apple-notarized, so macOS may require approval in Privacy &
Security. Windows builds currently have no Authenticode signature, so SmartScreen
may prompt. App-update signatures are separate from these platform signatures.

The installer includes the dashboard, force calibration, matching firmware and
a native Teensy flasher. No Rust, Node, ARM GNU, Arduino, or Homebrew installation
is needed.

## Install or update Teensy firmware

1. Stop the rig and save any experiment data.
2. Connect only the Teensy 4.1 you intend to flash. Close other serial tools and
   Teensy loaders.
3. Open **App & firmware**, acknowledge the preparation steps, and click
   **Install bundled firmware**.
4. Press the Teensy Program button when prompted. Keep USB connected until
   flashing completes.
5. Wait for the board to restart, then click **Refresh** and **Connect Teensy**.

Updating the desktop app does not automatically flash hardware. Install its
bundled firmware separately. Flashing resets temporary board settings and data.

Release notes and metadata identify the source commit and firmware hash.
`SHA256SUMS.txt` lists asset checksums. The bundled Teensy loader's GPL license
and corresponding source archive are included in the application's resources.
