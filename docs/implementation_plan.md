# Make FRIDAY a Windows Native Application

This implementation plan details the necessary changes to port FRIDAY from a Linux-native to a fully-supported Windows native application, while maintaining cross-platform compatibility where possible.

## User Review Required

> [!WARNING]
> Please review the changes proposed below. Porting to Windows requires creating new setup scripts (`setup.bat` or `setup.ps1`) and altering some core discovery algorithms (like how apps are found in the Start Menu instead of `/usr/share/applications/`).

## Open Questions

> [!IMPORTANT]
> 1. **Setup Script Preference**: Do you prefer a `setup.bat` (batch file) or a `setup.ps1` (PowerShell) for the Windows installation script?
> 2. **Browser Profile**: Should we migrate the browser profile from `~/.cache/friday/...` to a standard Windows AppData folder (`%LOCALAPPDATA%\Friday\browser-profile`)?

## Proposed Changes

---

### Setup and Configuration

#### [NEW] setup.bat or setup.ps1
Create a Windows equivalent of `setup.sh` that handles:
- Python virtual environment creation (`python -m venv .venv`).
- Activating the venv and installing `requirements.txt`.
- Downloading any necessary GGUF models (e.g. via `huggingface-cli` or `curl`).

#### [MODIFY] requirements.txt
Ensure cross-platform compatibility of requirements. Some Python libraries like `sounddevice`, `PyQt6`, and `pyautogui` already support Windows out of the box. No major changes expected here, but we will verify.

---

### Core Capabilities & Discovery

#### [MODIFY] core/system_capabilities.py
Update the `SystemCapabilities` class to correctly probe Windows capabilities:
- **Audio Backends**: Replace `wpctl`/`pactl` checks with Windows-native checks (e.g., detecting `sounddevice` / WASAPI availability).
- **Desktop App Discovery (`_discover_desktop_apps`)**: Currently only parses Linux `.desktop` files in `/usr/share/applications` and `~/.local/share/applications`. Add logic to parse Windows Start Menu shortcuts (`.lnk` files) located in:
  - `%APPDATA%\Microsoft\Windows\Start Menu\Programs`
  - `%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs`
  (Alternatively, use PowerShell/WMI to query installed applications).

---

### System Control Modules

#### [MODIFY] modules/system_control/app_launcher.py
- **Launch Command**: Enhance the Windows `subprocess.Popen(f"start {command}", shell=True)` logic to handle paths with spaces securely.
- **Registry Integration**: Ensure `_build_registry` works seamlessly with the new Windows apps discovered in `system_capabilities.py`.

#### [MODIFY] modules/system_control/file_search.py
- **Mount Scanning**: Update `ENABLE_MOUNT_SCAN` logic. Replace Linux mount checks (`/`) with Windows drive letter discovery (e.g., `C:\`, `D:\`) using `psutil`.

#### [MODIFY] modules/system_control/media_control.py
- The file currently uses `pyautogui` for Windows volume control (`volumeup`, `volumedown`, `volumemute`), which is functional but can be limited. We will keep this as a reliable fallback or enhance it with a more robust library like `pycaw` (Python Core Audio Windows Library) if fine-grained volume control (e.g., setting volume to exactly 50%) is needed.

#### [MODIFY] modules/system_control/screenshot.py
- Currently handles Windows gracefully by falling back to `pyautogui.screenshot()`. We will ensure the save directory path (`~/Pictures/FRIDAY_Screenshots`) expands correctly to the Windows User Pictures directory.

---

### Voice and Audio Handling

#### [MODIFY] modules/voice_io/audio_devices.py
- **PipeWire Bypass**: The current code heavily relies on `wpctl` (PipeWire) for discovering and managing audio inputs on Linux (`_list_pipewire_inputs`, `apply_input_device_selection`). We will add OS-checks to bypass PipeWire logic completely on Windows.
- **Sounddevice Default**: Ensure `_list_sounddevice_inputs` is the primary and only discovery method on Windows, properly identifying WASAPI/DirectSound microphones.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/` on a Windows environment to ensure no core logic breaks due to missing Linux binaries.
- Ensure `test_audio_devices.py` passes by correctly identifying Windows microphones via `sounddevice`.

### Manual Verification
- Run `setup.bat`/`setup.ps1` from a fresh Windows environment.
- Start FRIDAY (`python main.py`) and verify the UI loads.
- Ask FRIDAY to open a standard Windows app (e.g., "Open Calculator" or "Open Chrome").
- Ask FRIDAY to take a screenshot and verify it saves in the Windows Pictures folder.
- Test volume control ("mute the volume", "volume up").
- Test voice commands to ensure the microphone is correctly picked up by `sounddevice`.
