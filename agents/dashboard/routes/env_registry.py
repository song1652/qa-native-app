"""HTTP adapters for Android and iOS device registry operations."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import Body
from fastapi.responses import JSONResponse

from utils.device_registry import (
    DeviceRegistryError,
    add_android_device,
    add_ios_device,
    remove_device,
)


def attach_device_registry_routes(router, deps) -> None:
    # ── US-3: POST /api/env/android/add ──────────────────────────────

    @router.post("/api/env/android/add")
    def post_android_add(body: Optional[dict] = Body(default=None)):
        """Android 디바이스를 devices.json에 추가한다.

        body:
            mode: "emulator" | "real_device"
            deviceName: str (필수)
            avd: str (mode=emulator 시 필수)
            udid: str (mode=real_device 시 필수)
            default: bool (선택, 기본 false)
        """
        if deps.is_capture_active("android"):
            return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)
        if deps.is_pipeline_active():
            return JSONResponse({"ok": False, "error": "pipeline_running"}, status_code=409)

        if body is None:
            body = {}

        mode = (body.get("mode") or "").strip()
        device_name = (body.get("deviceName") or "").strip()

        if not device_name:
            return JSONResponse({"ok": False, "error": "deviceName is required"}, status_code=400)
        if mode not in ("emulator", "real_device"):
            return JSONResponse({"ok": False, "error": "mode must be emulator or real_device"}, status_code=400)
        if mode == "emulator" and not (body.get("avd") or "").strip():
            return JSONResponse({"ok": False, "error": "avd is required for emulator"}, status_code=400)
        if mode == "emulator" and not (body.get("platformVersion") or "").strip():
            return JSONResponse(
                {"ok": False, "error": "platformVersion is required for emulator"},
                status_code=400,
            )
        if mode == "real_device" and not (body.get("udid") or "").strip():
            return JSONResponse({"ok": False, "error": "udid is required for real_device"}, status_code=400)

        discovered_avd = None
        if mode == "emulator":
            avd = body["avd"].strip()
            try:
                discovered_avd = next(
                    (item for item in deps.list_system_avds() if item.get("avd") == avd),
                    None,
                )
            except Exception as exc:
                return JSONResponse(
                    {"ok": False, "error": "discovery_failed", "message": str(exc)},
                    status_code=500,
                )
            if discovered_avd is None:
                return JSONResponse(
                    {"ok": False, "error": "invalid_avd"}, status_code=400
                )
            device_name = discovered_avd.get("deviceName") or device_name

        try:
            data, new_entry = add_android_device(
                deps.load_devices_json(),
                body,
                discovered=discovered_avd,
            )
        except DeviceRegistryError as exc:
            payload = {"ok": False, "error": exc.code}
            if exc.detail:
                payload["detail"] = exc.detail
            return JSONResponse(payload, status_code=exc.status_code)

        try:
            deps.save_devices_json(data)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        return JSONResponse({"ok": True, "entry": new_entry})


    # ── US-3: POST /api/env/android/remove ───────────────────────────

    @router.post("/api/env/android/remove")
    def post_android_remove(body: Optional[dict] = Body(default=None)):
        """Android 디바이스를 devices.json에서 제거한다.

        body:
            mode: "emulator" | "real_device"
            deviceName: str (제거할 항목의 deviceName)
        """
        if deps.is_capture_active("android"):
            return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)
        if deps.is_pipeline_active():
            return JSONResponse({"ok": False, "error": "pipeline_running"}, status_code=409)

        if body is None:
            body = {}

        mode = (body.get("mode") or "").strip()
        device_name = (body.get("deviceName") or "").strip()

        if not device_name:
            return JSONResponse({"ok": False, "error": "deviceName is required"}, status_code=400)
        if mode not in ("emulator", "real_device"):
            return JSONResponse({"ok": False, "error": "mode must be emulator or real_device"}, status_code=400)

        try:
            data = remove_device(deps.load_devices_json(), "android", mode, device_name)
        except DeviceRegistryError as exc:
            return JSONResponse({"ok": False, "error": exc.code}, status_code=exc.status_code)

        try:
            deps.save_devices_json(data)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        return JSONResponse({"ok": True})


    # ── US-3: POST /api/env/ios/add ──────────────────────────────────

    @router.post("/api/env/ios/add")
    def post_ios_add(body: Optional[dict] = Body(default=None)):
        """iOS 디바이스를 devices.json에 추가한다.

        body:
            mode: "simulator" | "real_device"
            deviceName: str (필수)
            udid: str (real_device 시 필수)
            default: bool (선택, 기본 false)
        """
        if deps.is_capture_active("ios"):
            return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)
        if deps.is_pipeline_active():
            return JSONResponse({"ok": False, "error": "pipeline_running"}, status_code=409)

        if body is None:
            body = {}

        mode = (body.get("mode") or "").strip()
        device_name = (body.get("deviceName") or "").strip()

        if not device_name:
            return JSONResponse({"ok": False, "error": "deviceName is required"}, status_code=400)
        if mode not in ("simulator", "real_device"):
            return JSONResponse({"ok": False, "error": "mode must be simulator or real_device"}, status_code=400)
        if mode == "simulator" and not (body.get("udid") or "").strip():
            return JSONResponse(
                {"ok": False, "error": "udid is required for simulator"}, status_code=400
            )
        if mode == "simulator" and not (body.get("platformVersion") or "").strip():
            return JSONResponse(
                {"ok": False, "error": "platformVersion is required for simulator"},
                status_code=400,
            )
        if mode == "real_device" and not (body.get("udid") or "").strip():
            return JSONResponse({"ok": False, "error": "udid is required for real_device"}, status_code=400)

        discovered_simulator = None
        if mode == "simulator":
            udid = body["udid"].strip().upper()
            if not re.fullmatch(
                r"[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}", udid
            ):
                return JSONResponse(
                    {"ok": False, "error": "invalid_udid"}, status_code=400
                )
            try:
                discovered_simulator = next(
                    (
                        item
                        for item in deps.list_system_simulators()
                        if (item.get("udid") or "").upper() == udid
                    ),
                    None,
                )
            except Exception as exc:
                return JSONResponse(
                    {"ok": False, "error": "discovery_failed", "message": str(exc)},
                    status_code=500,
                )
            if discovered_simulator is None:
                return JSONResponse(
                    {"ok": False, "error": "invalid_udid"}, status_code=400
                )
            device_name = discovered_simulator.get("deviceName") or device_name

        try:
            data, new_entry = add_ios_device(
                deps.load_devices_json(),
                body,
                discovered=discovered_simulator,
            )
        except DeviceRegistryError as exc:
            payload = {"ok": False, "error": exc.code}
            if exc.detail:
                payload["detail"] = exc.detail
            return JSONResponse(payload, status_code=exc.status_code)

        try:
            deps.save_devices_json(data)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        return JSONResponse({"ok": True, "entry": new_entry})


    # ── US-3: POST /api/env/ios/remove ───────────────────────────────

    @router.post("/api/env/ios/remove")
    def post_ios_remove(body: Optional[dict] = Body(default=None)):
        """iOS 디바이스를 devices.json에서 제거한다.

        body:
            mode: "simulator" | "real_device"
            deviceName: str (제거할 항목의 deviceName)
        """
        if deps.is_capture_active("ios"):
            return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)
        if deps.is_pipeline_active():
            return JSONResponse({"ok": False, "error": "pipeline_running"}, status_code=409)

        if body is None:
            body = {}

        mode = (body.get("mode") or "").strip()
        device_name = (body.get("deviceName") or "").strip()

        if not device_name:
            return JSONResponse({"ok": False, "error": "deviceName is required"}, status_code=400)
        if mode not in ("simulator", "real_device"):
            return JSONResponse({"ok": False, "error": "mode must be simulator or real_device"}, status_code=400)

        try:
            data = remove_device(deps.load_devices_json(), "ios", mode, device_name)
        except DeviceRegistryError as exc:
            return JSONResponse({"ok": False, "error": exc.code}, status_code=exc.status_code)

        try:
            deps.save_devices_json(data)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        return JSONResponse({"ok": True})
