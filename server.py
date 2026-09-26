#!/usr/bin/env python3
"""
PC Info & Tech Assistant Bot — Python Flask backend
Reads real hardware specs and serves them to index.html via HTTP.

Run:
    pip install -r requirements.txt
    python server.py
"""

import platform
import subprocess
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

try:
    import psutil
except ImportError:
    raise SystemExit("psutil not found. Run: pip install -r requirements.txt")

PORT = 3000


# ─── Spec readers ─────────────────────────────────────────────────────────────

def get_os():
    system = platform.system()
    if system == "Windows":
        return platform.system() + " " + platform.version()
    elif system == "Darwin":
        return "macOS " + platform.mac_ver()[0]
    else:
        # Try to get pretty name from /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return f"Linux {platform.release()}"


def get_cpu():
    system = platform.system()

    # Windows — use wmic for a clean model name
    if system == "Windows":
        try:
            out = subprocess.check_output(
                ["wmic", "cpu", "get", "Name", "/value"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if line.startswith("Name="):
                    name = line.split("=", 1)[1].strip()
                    if name:
                        return name
        except Exception:
            pass

    # macOS
    if system == "Darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            )
            return out.strip()
        except Exception:
            pass

    # Linux
    if system == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass

    # Fallback — psutil / platform
    cpu = platform.processor()
    count = psutil.cpu_count(logical=False)
    freq = psutil.cpu_freq()
    parts = [cpu or "Unknown CPU"]
    if count:
        parts.append(f"{count} cores")
    if freq:
        parts.append(f"{freq.max / 1000:.1f} GHz")
    return ", ".join(parts)


def get_ram():
    mem = psutil.virtual_memory()
    total_gb = round(mem.total / (1024 ** 3), 1)
    return f"{total_gb} GB"


def get_gpu():
    system = platform.system()
    gpus = []

    # Windows — wmic
    if system == "Windows":
        try:
            out = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/value"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            )
            current = {}
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    if current.get("Name"):
                        vram = int(current.get("AdapterRAM") or 0)
                        vram_str = f" ({round(vram / (1024**3))} GB VRAM)" if vram > 0 else ""
                        gpus.append(current["Name"] + vram_str)
                    current = {}
                elif line.startswith("AdapterRAM="):
                    current["AdapterRAM"] = line.split("=", 1)[1].strip()
                elif line.startswith("Name="):
                    current["Name"] = line.split("=", 1)[1].strip()
            if current.get("Name"):
                vram = int(current.get("AdapterRAM") or 0)
                vram_str = f" ({round(vram / (1024**3))} GB VRAM)" if vram > 0 else ""
                gpus.append(current["Name"] + vram_str)
        except Exception:
            pass

    # macOS — system_profiler
    elif system == "Darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                timeout=8, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if "Chipset Model:" in line:
                    gpus.append(line.split(":", 1)[1].strip())
        except Exception:
            pass

    # Linux — lspci
    else:
        try:
            out = subprocess.check_output(
                ["lspci"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if any(k in line.lower() for k in ["vga", "3d controller", "display controller"]):
                    # Strip the PCI address prefix
                    parts = line.split(":", 2)
                    gpus.append(parts[-1].strip() if len(parts) >= 2 else line.strip())
        except Exception:
            pass

    return gpus if gpus else ["Unknown"]


def get_disks():
    disks = []
    for part in psutil.disk_partitions(all=False):
        # Skip snap/loop mounts on Linux and optical drives
        if "loop" in part.device or "cdrom" in part.opts:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            total_gb = round(usage.total / (1024 ** 3), 1)
            used_gb  = round(usage.used  / (1024 ** 3), 1)
            free_gb  = round(usage.free  / (1024 ** 3), 1)
            if total_gb < 0.1:
                continue
            disks.append({
                "drive": part.device,
                "total": f"{total_gb} GB",
                "used":  f"{used_gb} GB",
                "free":  f"{free_gb} GB",
            })
        except PermissionError:
            continue
    return disks


def collect_specs():
    return {
        "os":       get_os(),
        "cpu":      get_cpu(),
        "ram":      get_ram(),
        "gpu":      get_gpu(),
        "disks":    get_disks(),
        "platform": platform.system().lower(),
    }


# ─── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Suppress default access log noise; print clean lines instead
        print(f"  {self.address_string()} → {args[0]}")

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        # ── /api/specs ──────────────────────────────────────────────────────────
        if path == "/api/specs":
            try:
                data = collect_specs()
                body = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors()
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_cors()
                self.end_headers()
                self.wfile.write(err)
            return

        # ── / → serve index.html ────────────────────────────────────────────────
        if path in ("/", "/index.html"):
            try:
                import os
                html_path = os.path.join(os.path.dirname(__file__), "index.html")
                with open(html_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"index.html not found")
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    httpd = HTTPServer(("localhost", PORT), Handler)
    print(f"✅  PC Info Bot server running → http://localhost:{PORT}")
    print(f"   API endpoint  → http://localhost:{PORT}/api/specs")
    print(f"   Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑  Server stopped.")
