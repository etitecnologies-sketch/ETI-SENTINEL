import psutil
import platform


def get_metrics():
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_available_mb": psutil.virtual_memory().available / (1024 * 1024),
            "disk_percent": psutil.disk_usage('/').percent if platform.system() != 'Windows' else psutil.disk_usage('C:\\').percent,
            "platform": platform.system(),
            "python_version": platform.python_version(),
        }
    except Exception:
        return {
            "cpu_percent": 0,
            "ram_percent": 0,
            "ram_available_mb": 0,
            "disk_percent": 0,
            "platform": platform.system(),
            "python_version": platform.python_version(),
        }
