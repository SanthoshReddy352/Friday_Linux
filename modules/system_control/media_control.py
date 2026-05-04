import platform
import subprocess
import shutil
from core.logger import logger

def _run_cmd(cmd):
    """Helper to run a shell command and return its exit code and output."""
    try:
        result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            logger.error(f"Command '{cmd}' failed. stderr: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error running command '{cmd}': {e}")
        return False

def set_volume(level="up", steps=1, percent=None):
    """
    Adjusts volume. Gracefully degrades and logs errors if tools are missing.
    """
    os_name = platform.system()
    steps = max(1, int(steps or 1))
    target_percent = None
    if percent is not None:
        try:
            target_percent = max(0, min(100, int(percent)))
        except Exception:
            target_percent = None
    step_percent = 5 * steps
    
    try:
        if os_name == "Windows":
            import pyautogui
            if level == "absolute":
                target = target_percent if target_percent is not None else 0
                target = max(0, min(100, int(target)))
                for _ in range(50):
                    pyautogui.press('volumedown')
                for _ in range(target // 2):
                    pyautogui.press('volumeup')
                return f"Volume set to ~{target}%."
            elif level == "up":
                for _ in range(steps):
                    pyautogui.press('volumeup')
                return f"Volume increased {steps} step{'s' if steps != 1 else ''}."
            elif level == "down":
                for _ in range(steps):
                    pyautogui.press('volumedown')
                return f"Volume decreased {steps} step{'s' if steps != 1 else ''}."
            elif level == "mute":
                pyautogui.press('volumemute')
                return "Volume muted."
            elif level == "unmute":
                pyautogui.press('volumemute')
                return "Volume unmuted."
        
        elif os_name == "Linux":
            # Check availability of wpctl (PipeWire), pactl, or amixer
            if shutil.which("wpctl"):
                volume_tool = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@"]
                mute_tool = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@"]
                backend = "wpctl"
            elif shutil.which("pactl"):
                volume_tool = ["pactl", "set-sink-volume", "@DEFAULT_SINK@"]
                mute_tool = ["pactl", "set-sink-mute", "@DEFAULT_SINK@"]
                backend = "pactl"
            elif shutil.which("amixer"):
                volume_tool = ["amixer", "-D", "pulse", "sset", "Master"]
                mute_tool = ["amixer", "-D", "pulse", "sset", "Master"]
                backend = "amixer"
            else:
                logger.error("No volume tools (wpctl/pactl/amixer) found on this system.")
                return "Error: No volume control tools found on this system."

            if level == "absolute":
                target_percent = max(0, min(100, int(target_percent if target_percent is not None else 0)))
                if backend == "wpctl":
                    cmd = volume_tool + [f"{target_percent / 100:.2f}"]
                else:
                    cmd = volume_tool + [f"{target_percent}%"]
                success = _run_cmd(cmd)
                return f"Volume set to {target_percent}%." if success else "Failed to set volume."
            if level == "up":
                if backend == "pactl":
                    cmd = volume_tool + [f"+{step_percent}%"]
                else:
                    cmd = volume_tool + [f"{step_percent}%+"]
                success = _run_cmd(cmd)
                return (
                    f"Volume increased {steps} step{'s' if steps != 1 else ''}."
                    if success else "Failed to increase volume."
                )
            elif level == "down":
                if backend == "pactl":
                    cmd = volume_tool + [f"-{step_percent}%"]
                else:
                    cmd = volume_tool + [f"{step_percent}%-"]
                success = _run_cmd(cmd)
                return (
                    f"Volume decreased {steps} step{'s' if steps != 1 else ''}."
                    if success else "Failed to decrease volume."
                )
            elif level == "mute":
                cmd = mute_tool + ["1"] if backend in {"wpctl", "pactl"} else mute_tool + ["mute"]
                success = _run_cmd(cmd)
                return "Volume muted." if success else "Failed to mute volume."
            elif level == "unmute":
                cmd = mute_tool + ["0"] if backend in {"wpctl", "pactl"} else mute_tool + ["unmute"]
                success = _run_cmd(cmd)
                return "Volume unmuted." if success else "Failed to unmute volume."
                
        return f"Volume control not fully supported on {os_name} yet."
    except Exception as e:
        logger.error(f"Volume adjustment exception: {e}")
        return f"Failed to adjust volume: {str(e)}"
