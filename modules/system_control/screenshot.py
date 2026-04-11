import os
import time
import subprocess
import shutil
from core.logger import logger

def take_screenshot():
    """
    Takes a screenshot of the primary display.
    Includes fallbacks for Wayland (gnome-screenshot) where pyautogui fails.
    """
    save_dir = os.path.expanduser("~/Pictures/FRIDAY_Screenshots")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = os.path.join(save_dir, filename)
    
    # Try GNOME screenshot first on Linux if available (best for Wayland compatibility)
    if os.name != 'nt' and shutil.which("gnome-screenshot"):
        try:
            result = subprocess.run(["gnome-screenshot", "-f", filepath], capture_output=True)
            if result.returncode == 0:
                logger.info(f"Screenshot taken via gnome-screenshot: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
        except Exception as e:
            logger.warning(f"gnome-screenshot failed: {e}")
            
    # Try grim (common on non-GNOME Wayland like Sway/Hyperland)
    if os.name != 'nt' and shutil.which("grim"):
        try:
            result = subprocess.run(["grim", filepath], capture_output=True)
            if result.returncode == 0:
                logger.info(f"Screenshot taken via grim: {filepath}")
                return f"Screenshot saved successfully at: {filepath}"
        except Exception as e:
            logger.warning(f"grim failed: {e}")

    # Fallback to pyautogui for X11/Windows
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        logger.info(f"Screenshot taken via pyautogui: {filepath}")
        return f"Screenshot saved successfully at: {filepath}"
    except Exception as e:
        err_msg = f"Failed to take screenshot with all methods. PyAutoGUI error: {str(e)}"
        logger.error(err_msg)
        return err_msg
