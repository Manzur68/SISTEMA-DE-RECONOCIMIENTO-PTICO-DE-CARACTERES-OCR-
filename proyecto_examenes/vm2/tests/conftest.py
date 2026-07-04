import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests que levantan contenedores Docker reales"
    )
    config.addinivalue_line(
        "markers", "unit: tests de lógica Python pura"
    )
