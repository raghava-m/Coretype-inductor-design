#!/usr/bin/env python3
"""Cloud web app for three-phase inductor design inputs and trade-offs.

Serves the static UI and a small JSON API around the analytical engine.
No extra Python packages required (stdlib http.server).

    python -m webapp.server --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
REPO = ROOT.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from three_phase.material_library import CONDUCTOR_MATERIALS, CORE_MATERIALS  # noqa: E402
from three_phase.schema import DEFAULT_SPEC, compact_row, summarize_design  # noqa: E402
from three_phase.tradeoff import run_tradeoff  # noqa: E402

FIELD_SCHEMA = [
    {
        "group": "Electrical",
        "section": "electrical",
        "fields": [
            ("inductance_uh", "Target inductance", "µH"),
            ("irms_a", "Phase RMS current", "A"),
            ("short_term_peak_current_a", "Short-term peak current", "A"),
            ("rated_peak_current_a", "Rated peak current", "A"),
            ("frequency_hz", "Frequency", "Hz"),
            ("isolation_test_voltage_kv", "Isolation test voltage", "kV"),
        ],
    },
    {
        "group": "Materials & winding",
        "section": "variable",
        "fields": [
            ("core_type", "Core construction", None),
            ("core_material", "Core material", None),
            ("conductor_material", "Conductor", None),
            ("series_parallel", "Coil connection", None),
            ("no_of_layers", "Layers", None),
            ("cond_in_parallel_w", "Parallels in width", None),
            ("cond_in_parallel_t", "Parallels in thickness", None),
        ],
    },
    {
        "group": "Core geometry",
        "section": "variable_calc",
        "fields": [
            ("allowed_max_flux_density_t", "Max flux density Bmax", "T"),
            ("core_width_for_area_mm", "Limb iron width", "mm"),
            ("core_stack_mm", "Core stack / depth", "mm"),
            ("no_of_cores_in_stack", "Cores in stack", None),
            ("stacking_factor", "Stacking factor", None),
            ("overall_core_width_mm", "Overall 3-limb width", "mm"),
            ("window_height_mm", "Window height", "mm"),
            ("window_width_mm", "Window width", "mm"),
        ],
    },
    {
        "group": "Conductor strip",
        "section": "strip",
        "fields": [
            ("nom_area_mm2", "Nominal copper area", "mm²"),
            ("overall_max_width_mm", "Strip width", "mm"),
            ("overall_max_thickness_mm", "Strip thickness", "mm"),
        ],
    },
    {
        "group": "Winding gaps (advanced)",
        "section": "electrical",
        "advanced": True,
        "fields": [
            ("turn_to_turn_gap_mm", "Turn-to-turn gap", "mm"),
            ("gap_bet_layer_to_layer_mm", "Layer-to-layer gap", "mm"),
            ("strand_to_strand_gap_mm", "Strand-to-strand gap", "mm"),
            ("gap_between_bobbin_core_width_side_mm", "Clearance width side", "mm"),
            ("gap_between_bobbin_core_depth_side_mm", "Clearance depth side", "mm"),
            ("femm_total_airgap_limb_mm", "FEMM airgap / limb", "mm"),
            ("airgap_locations_limb", "Airgap locations / limb", None),
            ("extra_turns_for_window_height", "Extra turns for height stack", None),
        ],
    },
    {
        "group": "Feasibility limits",
        "section": "limits",
        "fields": [
            ("max_current_density_a_mm2", "Max current density", "A/mm²"),
            ("max_window_util_pct", "Max window utilisation", "%"),
            ("ambient_c", "Ambient", "°C"),
        ],
    },
]


def _json_bytes(payload: Any, status: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(payload, default=str).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def handle_api(method: str, path: str, body: bytes) -> tuple[int, bytes, str]:
    if path == "/api/meta" and method == "GET":
        return _json_bytes({
            "default_spec": DEFAULT_SPEC,
            "core_materials": CORE_MATERIALS,
            "conductor_materials": CONDUCTOR_MATERIALS,
            "core_types": ["Core type", "shell type"],
            "series_parallel": ["series", "parallel"],
            "fields": FIELD_SCHEMA,
        })
    if path == "/health" and method == "GET":
        return _json_bytes({"ok": True})
    raw: dict[str, Any] = {}
    if body:
        try:
            raw = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            return _json_bytes({"error": f"invalid JSON: {exc}"}, 400)
    if path == "/api/design" and method == "POST":
        row = compact_row(summarize_design(raw))
        return _json_bytes({"baseline": row})
    if path == "/api/tradeoff" and method == "POST":
        result = run_tradeoff(raw)
        return _json_bytes(result)
    return _json_bytes({"error": "not found"}, 404)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/api/meta", "/health"):
            try:
                status, body, ctype = handle_api("GET", parsed.path, b"")
            except Exception as exc:  # noqa: BLE001
                status, body, ctype = _json_bytes(
                    {"error": str(exc), "trace": traceback.format_exc()}, 500
                )
            self._send(status, body, ctype)
            return
        if parsed.path in ("", "/"):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            status, body_out, ctype = handle_api("POST", parsed.path, body)
        except Exception as exc:  # noqa: BLE001
            status, body_out, ctype = _json_bytes(
                {"error": str(exc), "trace": traceback.format_exc()}, 500
            )
        self._send(status, body_out, ctype)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Three-phase inductor trade-off web app")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Three-phase inductor web app http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
