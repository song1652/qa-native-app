"""Device registry route module boundary."""

from types import SimpleNamespace
from pathlib import Path
import sys

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from routes.env_registry import attach_device_registry_routes


def test_attached_android_add_route_keeps_validation_contract():
    router = APIRouter()
    dependencies = SimpleNamespace(
        is_capture_active=lambda _platform: False,
        is_pipeline_active=lambda: False,
        list_system_avds=lambda: [],
        list_system_simulators=lambda: [],
        load_devices_json=lambda: {},
        save_devices_json=lambda _data: None,
    )
    attach_device_registry_routes(router, dependencies)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post("/api/env/android/add", json={"mode": "emulator"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "deviceName is required"}
