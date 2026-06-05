import psutil


def read_cpu() -> dict:
    return {
        "source": "psutil.cpu_percent",
        "raw_value": psutil.cpu_percent(interval=1.0),
        "unit": "percent",
        "interval": 1.0,
    }


def mock_cpu(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
    }
