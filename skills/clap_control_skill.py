import os
import platform as _platform
import subprocess
import json
from typing import List, Dict, Any, Callable
from core.skill import Skill, SkillDescriptor

class ClapControlSkill(Skill):
    DESCRIPTOR = SkillDescriptor(
        name="clap_control_skill",
        supported_platforms=["Linux"],
        tool_specs=[
            {
                "type": "function",
                "function": {
                    "name": "toggle_clap_trigger",
                    "description": "Enable or disable the double-clap background trigger that starts Friday when it is closed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean", "description": "True to turn on, False to turn off."},
                            "permanent": {"type": "boolean", "description": "If True, also update system autostart settings (default False)."}
                        },
                        "required": ["enabled"]
                    }
                }
            }
        ],
    )

    @property
    def name(self) -> str:
        return "clap_control_skill"

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.DESCRIPTOR.tool_specs

    def get_functions(self) -> Dict[str, Callable]:
        return {"toggle_clap_trigger": self.toggle_clap_trigger}

    def toggle_clap_trigger(self, enabled: bool, permanent: bool = False):
        """
        Voice-accessible tool to turn the clap detector on/off.
        """
        # Skill is in /home/tricky/Friday_Linux/skills/
        skills_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(skills_dir)
        
        clap_script = os.path.join(project_root, "modules", "voice_io", "clap_detector.py")
        autostart_script = os.path.join(project_root, "modules", "voice_io", "register_autostart.py")
        if _platform.system() == "Windows":
            venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")
        else:
            venv_python = os.path.join(project_root, ".venv", "bin", "python3")

        try:
            if not enabled:
                # 1. Stop the running process
                subprocess.run([venv_python, clap_script, "--stop"], check=True)
                status_msg = "Clap trigger has been turned off."
                
                # 2. Handle permanent change
                if permanent:
                    # Run unregister() from register_autostart.py
                    subprocess.run([venv_python, "-c", 
                        f"import sys; sys.path.append('{os.path.dirname(autostart_script)}'); from register_autostart import unregister; unregister()"], 
                        check=True)
                    status_msg += " It has also been removed from system autostart."
                
                return json.dumps({"status": "success", "message": status_msg})
            
            else:
                # 1. Start the process in background
                popen_kwargs = dict(
                    cwd=project_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if _platform.system() == "Windows":
                    popen_kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_kwargs["start_new_session"] = True
                subprocess.Popen([venv_python, clap_script], **popen_kwargs)
                status_msg = "Clap trigger is now active."
                
                # 2. Handle permanent change
                if permanent:
                    subprocess.run([venv_python, autostart_script], check=True)
                    status_msg += " It will now start automatically when you boot your computer."
                
                return json.dumps({"status": "success", "message": status_msg})

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
