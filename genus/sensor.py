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


def repo_commits_reading(
    commits: int,
    measured_on: str = "unknown",
    window_hours: int = 24,
) -> dict:
    return _structural_reading("git.commits_per_day", commits, measured_on, window_hours)


def repo_lines_reading(
    lines: int,
    measured_on: str = "unknown",
    window_hours: int = 24,
) -> dict:
    return _structural_reading(
        "git.lines_changed_per_day", lines, measured_on, window_hours
    )


def _structural_reading(
    source: str,
    value: int,
    measured_on: str,
    window_hours: int,
) -> dict:
    """Shape a structural reading from a count supplied by the membrane.

    The core never runs ``git``: the count is measured off-device (the membrane)
    and handed in. Only the count and its provenance travel — never commit
    messages, diffs, or file names.
    """
    return {
        "source": source,
        "raw_value": float(value),
        "unit": "count",
        "interval": 0.0,
        "window_hours": int(window_hours),
        "measured_on": measured_on or "unknown",
    }


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
