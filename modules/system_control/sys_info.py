import psutil

def get_battery_status():
    if not hasattr(psutil, "sensors_battery"):
        return "Battery monitoring not supported on this device."
        
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery detected."
        
    percent = int(battery.percent)
    plugged = "plugged in" if battery.power_plugged else "on battery power"
    return f"Battery is at {percent}% and is currently {plugged}."

def get_cpu_ram_status():
    cpu = psutil.cpu_percent(interval=0.5)
    
    ram = psutil.virtual_memory()
    ram_total = round(ram.total / (1024**3), 1)
    ram_used = round(ram.used / (1024**3), 1)
    
    return f"CPU Usage: {cpu}%. RAM: {ram_used}GB / {ram_total}GB ({ram.percent}% used)."

def get_system_status():
    return f"{get_cpu_ram_status()} {get_battery_status()}"
