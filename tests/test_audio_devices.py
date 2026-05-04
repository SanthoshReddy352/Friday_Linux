import os
import sys
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.voice_io.audio_devices import (
    AudioInputDevice,
    apply_input_device_selection,
    choose_startup_input_device,
    _pipewire_node_is_internal_source,
    parse_wpctl_inputs,
)
from core.config import ConfigManager
from modules.voice_io.stt import STTEngine


WPCTL_SAMPLE = """
Audio
 ├─ Devices:
 │      48. Built-in Audio                      [alsa]
 │      89. Nirvana Ion                         [bluez5]
 │
 ├─ Sinks:
 │      52. Built-in Audio Analog Stereo        [vol: 1.07]
 │      88. Nirvana Ion                         [vol: 1.17]
 │
 ├─ Sources:
 │  *   53. Built-in Audio Analog Stereo        [vol: 0.27]
 │
 ├─ Filters:
 │    - loopback-2500-19
 │      83. bluez_input.01:02:03:04:1C:B6       [Audio/Source]
 │      93. bluez_capture_internal.01:02:03:04:1C:B6 [Stream/Input/Audio/Internal]
 │
 └─ Streams:
"""


def test_parse_wpctl_inputs_includes_bluetooth_filter_source():
    with patch("modules.voice_io.audio_devices._pipewire_node_description", side_effect=["Built-in Audio Analog Stereo", "Nirvana Ion"]):
        devices = parse_wpctl_inputs(WPCTL_SAMPLE)
        # enrich manually like _list_pipewire_inputs does
        for device in devices:
            label = {
                "pw:53": "Built-in Audio Analog Stereo",
                "pw:83": "Nirvana Ion",
            }.get(device.id)
            if label:
                device.label = label

    labels = [device.label for device in devices]
    assert "Built-in Audio Analog Stereo" in labels
    assert "Nirvana Ion" in labels


def test_pipewire_internal_source_is_detected():
    inspect_output = 'media.class = "Audio/Source/Internal"\nnode.description = "Internal Capture"'
    with patch("modules.voice_io.audio_devices.shutil.which", return_value="/usr/bin/wpctl"), \
         patch("modules.voice_io.audio_devices.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout=inspect_output, stderr="")

        assert _pipewire_node_is_internal_source(115) is True


def test_apply_input_device_selection_pipewire_sets_default():
    with patch("modules.voice_io.audio_devices.shutil.which", return_value="/usr/bin/wpctl"), \
         patch("modules.voice_io.audio_devices.subprocess.run") as run, \
         patch("modules.voice_io.audio_devices._resolve_pipewire_sounddevice_input", return_value=7):
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = apply_input_device_selection({"kind": "pipewire", "id": 83, "label": "Nirvana Ion"})

    assert result == {"device": 7, "label": "Nirvana Ion"}
    run.assert_called_once()


def test_stt_set_device_accepts_pipewire_target():
    app = MagicMock()
    stt = STTEngine(app)
    stt._start_hardware_stream = MagicMock()
    stt.listen_thread = MagicMock()
    stt.listen_thread.is_alive.return_value = False

    with patch("modules.voice_io.stt.apply_input_device_selection", return_value={"device": None, "label": "Nirvana Ion"}), \
         patch("modules.voice_io.stt.time.sleep"):
        stt.set_device({"kind": "pipewire", "id": 83, "label": "Nirvana Ion"})

    assert stt.device_id is None
    assert stt.device_label == "Nirvana Ion"
    stt._start_hardware_stream.assert_called_once()


def test_stt_set_device_persists_selected_input(tmp_path):
    app = MagicMock()
    app.config = ConfigManager(str(tmp_path / "config.yaml"))
    app.config.config = {"voice": {}}
    stt = STTEngine(app)
    stt._start_hardware_stream = MagicMock()
    stt.listen_thread = MagicMock()
    stt.listen_thread.is_alive.return_value = False
    target = {"kind": "pipewire", "id": 83, "label": "Nirvana Ion"}

    with patch("modules.voice_io.stt.apply_input_device_selection", return_value={"device": None, "label": "Nirvana Ion"}), \
         patch("modules.voice_io.stt.time.sleep"):
        stt.set_device(target)

    reloaded = ConfigManager(str(tmp_path / "config.yaml"))
    reloaded.load()
    assert reloaded.get("voice.input_device") == target


def test_stt_selects_default_startup_microphone():
    app = MagicMock()
    stt = STTEngine(app)

    devices = [
        AudioInputDevice(
            id="pw:53",
            label="Built-in Audio Analog Stereo",
            backend="pipewire",
            target={"kind": "pipewire", "id": 53, "label": "Built-in Audio Analog Stereo"},
            is_default=True,
        )
    ]

    with patch("modules.voice_io.stt.list_audio_input_devices", return_value=devices), \
         patch("modules.voice_io.stt.apply_input_device_selection", return_value={"device": None, "label": "Built-in Audio Analog Stereo"}):
        stt._ensure_startup_input_device()

    assert stt.device_id is None
    assert stt.device_label == "Built-in Audio Analog Stereo"
    assert stt._startup_device_selected is True


def test_choose_startup_input_device_prefers_builtin_over_bluetooth_default():
    devices = [
        AudioInputDevice(
            id="pw:83",
            label="Nirvana Ion",
            backend="pipewire",
            target={"kind": "pipewire", "id": 83, "label": "Nirvana Ion"},
            is_default=True,
        ),
        AudioInputDevice(
            id="pw:53",
            label="Built-in Audio Analog Stereo",
            backend="pipewire",
            target={"kind": "pipewire", "id": 53, "label": "Built-in Audio Analog Stereo"},
        ),
    ]

    preferred = choose_startup_input_device(devices)

    assert preferred is not None
    assert preferred.id == "pw:53"


def test_choose_startup_input_device_avoids_monitor_inputs():
    devices = [
        AudioInputDevice(
            id="sd:0",
            label="default",
            backend="sounddevice",
            target={"kind": "sounddevice", "id": 0, "label": "default"},
            is_default=True,
        ),
        AudioInputDevice(
            id="sd:1",
            label="Monitor of Built-in Audio Analog Stereo",
            backend="sounddevice",
            target={"kind": "sounddevice", "id": 1, "label": "Monitor of Built-in Audio Analog Stereo"},
        ),
        AudioInputDevice(
            id="sd:2",
            label="USB Microphone",
            backend="sounddevice",
            target={"kind": "sounddevice", "id": 2, "label": "USB Microphone"},
        ),
    ]

    preferred = choose_startup_input_device(devices)

    assert preferred is not None
    assert preferred.id == "sd:2"


def test_stt_prepares_stereo_high_rate_audio_for_whisper():
    app = MagicMock()
    stt = STTEngine(app)
    stt.stream_samplerate = 44100

    audio = np.column_stack([
        np.linspace(-1.0, 1.0, 4410, dtype=np.float32),
        np.linspace(1.0, -1.0, 4410, dtype=np.float32),
    ])
    prepared = stt._prepare_audio_for_transcription(audio)

    assert prepared.dtype == np.float32
    assert prepared.ndim == 1
    assert 1500 <= len(prepared) <= 1700
