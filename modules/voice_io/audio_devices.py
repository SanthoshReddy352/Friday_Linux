import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class AudioInputDevice:
    id: str
    label: str
    backend: str
    target: object
    is_default: bool = False


_STARTUP_INPUT_BUILTIN_HINTS = (
    "built-in",
    "analog",
    "internal mic",
    "internal microphone",
    "hda intel",
    "alc",
)
_STARTUP_INPUT_GENERIC_MIC_HINTS = (
    "microphone",
    " mic",
)
_STARTUP_INPUT_BLUETOOTH_HINTS = (
    "bluez",
    "bluetooth",
    "airpods",
    "buds",
    "earbuds",
    "headset",
    "hands-free",
    "nirvana",
)
_STARTUP_INPUT_VIRTUAL_HINTS = (
    "monitor",
    "loopback",
    "capture_internal",
    "stream/input/audio/internal",
)
_STARTUP_INPUT_PSEUDO_HINTS = (
    "default",
    "pipewire",
    "sysdefault",
)


def list_audio_input_devices():
    devices = _list_pipewire_inputs()
    if devices:
        return devices
    return _list_sounddevice_inputs()


def apply_input_device_selection(target):
    if isinstance(target, dict) and target.get("kind") == "pipewire":
        node_id = target.get("id")
        if node_id is None:
            raise RuntimeError("Missing PipeWire node id.")
        wpctl = shutil.which("wpctl")
        if not wpctl:
            raise RuntimeError("wpctl is not available on this system.")
        result = subprocess.run(
            [wpctl, "set-default", str(node_id)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"Failed to set default microphone: {error}")
        return {
            "device": _resolve_pipewire_sounddevice_input(),
            "label": target.get("label", f"PipeWire source {node_id}"),
        }

    if isinstance(target, dict) and target.get("kind") == "sounddevice":
        return {"device": target.get("id"), "label": target.get("label", f"Device {target.get('id')}")}

    if target is None:
        return {"device": None, "label": "System default"}

    return {"device": target, "label": str(target)}


def choose_startup_input_device(devices):
    if not devices:
        return None
    return min(devices, key=_startup_input_rank)


def _startup_input_rank(device):
    label = str(device.label or "").strip().lower()
    score = 0

    if any(token in label for token in _STARTUP_INPUT_BUILTIN_HINTS):
        score -= 60
    elif any(token in label for token in _STARTUP_INPUT_GENERIC_MIC_HINTS):
        score -= 20

    if device.backend == "pipewire":
        score -= 8
    if device.is_default:
        score -= 6

    if any(token in label for token in _STARTUP_INPUT_BLUETOOTH_HINTS):
        score += 28
    if any(token in label for token in _STARTUP_INPUT_VIRTUAL_HINTS):
        score += 90
    if label in _STARTUP_INPUT_PSEUDO_HINTS:
        score += 120

    return (score, label, str(device.id))


def parse_wpctl_inputs(status_text):
    if not status_text:
        return []

    devices = []
    section = None
    for raw_line in status_text.splitlines():
        stripped = raw_line.strip()
        normalized = re.sub(r"^[\s│├└─]+", "", raw_line).strip()
        if stripped == "├─ Sources:" or stripped == "└─ Sources:":
            section = "sources"
            continue
        if stripped == "├─ Filters:" or stripped == "└─ Filters:":
            section = "filters"
            continue
        if re.match(r"^[A-Za-z].*:$", stripped):
            section = None
            continue
        if not stripped:
            continue

        if section == "sources":
            parsed = _parse_wpctl_source_line(normalized)
            if parsed:
                devices.append(parsed)
            continue

        if section == "filters":
            parsed = _parse_wpctl_filter_source_line(normalized)
            if parsed:
                devices.append(parsed)

    deduped = []
    seen = set()
    for device in devices:
        key = (device.id, device.label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(device)
    return deduped


def _list_pipewire_inputs():
    wpctl = shutil.which("wpctl")
    if not wpctl:
        return []

    result = subprocess.run(
        [wpctl, "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    devices = parse_wpctl_inputs(result.stdout)
    if not devices:
        return []

    enriched = []
    for device in devices:
        if _pipewire_node_is_internal_source(device.target.get("id")):
            continue
        label = _pipewire_node_description(device.target.get("id"))
        if label:
            device.label = label
            device.target["label"] = label
        enriched.append(device)
    return enriched


def _list_sounddevice_inputs():
    try:
        import sounddevice as sd
    except Exception:
        return []

    devices = []
    default_input = None
    try:
        default_input = sd.default.device[0]
    except Exception:
        pass

    for index, device in enumerate(sd.query_devices()):
        if device.get("max_input_channels", 0) <= 0:
            continue
        label = device.get("name", f"Input {index}")
        devices.append(
            AudioInputDevice(
                id=f"sd:{index}",
                label=label,
                backend="sounddevice",
                target={"kind": "sounddevice", "id": index, "label": label},
                is_default=(index == default_input),
            )
        )
    return devices


def _parse_wpctl_source_line(line):
    match = re.match(r"^(?P<star>\*)?\s*(?P<id>\d+)\.\s+(?P<label>.+?)\s+\[vol:.*\]$", line)
    if not match:
        return None
    label = match.group("label").strip()
    node_id = int(match.group("id"))
    default = bool(match.group("star"))
    return AudioInputDevice(
        id=f"pw:{node_id}",
        label=label,
        backend="pipewire",
        target={"kind": "pipewire", "id": node_id, "label": label},
        is_default=default,
    )


def _parse_wpctl_filter_source_line(line):
    if "[Audio/Source]" not in line:
        return None
    match = re.match(r"^(?P<star>\*)?\s*(?P<id>\d+)\.\s+(?P<label>.+?)\s+\[Audio/Source\]$", line)
    if not match:
        return None
    raw_label = match.group("label").strip()
    label = _humanize_filter_label(raw_label)
    node_id = int(match.group("id"))
    default = bool(match.group("star"))
    return AudioInputDevice(
        id=f"pw:{node_id}",
        label=label,
        backend="pipewire",
        target={"kind": "pipewire", "id": node_id, "label": label},
        is_default=default,
    )


def _humanize_filter_label(label):
    if label.startswith("bluez_input."):
        return "Bluetooth Microphone"
    if label.startswith("alsa_input."):
        return "Built-in Microphone"
    return label.replace("_", " ")


def _pipewire_node_description(node_id):
    wpctl = shutil.which("wpctl")
    if not wpctl or node_id is None:
        return ""
    result = subprocess.run(
        [wpctl, "inspect", str(node_id)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""

    for line in result.stdout.splitlines():
        match = re.search(r"node\.description = \"([^\"]+)\"", line)
        if match:
            return match.group(1).strip()
    return ""


def _pipewire_node_is_internal_source(node_id):
    wpctl = shutil.which("wpctl")
    if not wpctl or node_id is None:
        return False
    result = subprocess.run(
        [wpctl, "inspect", str(node_id)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if "media.class" in line and "Audio/Source/Internal" in line:
            return True
    return False


def _resolve_pipewire_sounddevice_input():
    try:
        import sounddevice as sd
    except Exception:
        return None

    try:
        devices = list(sd.query_devices())
    except Exception:
        return None

    preferred = None
    fallback = None
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) <= 0:
            continue
        lowered = str(device.get("name", "")).strip().lower()
        if lowered == "pipewire":
            preferred = index
            break
        if lowered == "default":
            fallback = index

    return preferred if preferred is not None else fallback
