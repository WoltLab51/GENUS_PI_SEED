import psutil


def read_cpu() -> dict:
    return {
        "source": "psutil.cpu_percent",
        "raw_value": psutil.cpu_percent(interval=1.0),
        "unit": "percent",
        "interval": 1.0,
    }


def read_memory() -> dict:
    return {
        "source": "psutil.virtual_memory.percent",
        "raw_value": psutil.virtual_memory().percent,
        "unit": "percent",
        "interval": 0.0,
    }


def read_disk(path: str = "/") -> dict:
    usage = psutil.disk_usage(path)
    return {
        "source": "psutil.disk_usage",
        "raw_value": usage.percent,
        "unit": "percent",
        "interval": 0.0,
        "path": path,
    }


def read_activity() -> dict:
    users = psutil.users()
    cpu = psutil.cpu_percent(interval=0.5)
    active = 1.0 if len(users) > 0 and cpu > 2.0 else 0.0
    return {
        "source": "psutil.activity",
        "raw_value": active,
        "unit": "binary",
        "interval": 0.5,
        "user_count": len(users),
        "cpu_sample": cpu,
    }


def read_temperature() -> dict | None:
    try:
        temperatures = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        return None
    if not temperatures:
        return None

    for key in ("coretemp", "acpitz", "cpu_thermal", "k10temp"):
        if key in temperatures and temperatures[key]:
            return {
                "source": f"psutil.sensors_temperatures.{key}",
                "raw_value": temperatures[key][0].current,
                "unit": "celsius",
                "interval": 0.0,
            }

    first_key = next(iter(temperatures))
    if temperatures[first_key]:
        return {
            "source": f"psutil.sensors_temperatures.{first_key}",
            "raw_value": temperatures[first_key][0].current,
            "unit": "celsius",
            "interval": 0.0,
        }
    return None


def mock_cpu(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
    }


def mock_memory(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
    }


def mock_disk(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
        "path": "/",
    }


def mock_activity(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "binary",
        "interval": 0.0,
        "user_count": 1 if value > 0 else 0,
        "cpu_sample": 50.0 if value > 0 else 0.5,
    }


def mock_temperature(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "celsius",
        "interval": 0.0,
    }
