"""BigShot Business OS Windows LAN launcher.

Runtime dependencies are limited to the Python standard library. Network work
runs outside Tk's UI thread so the connecting window remains responsive.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
import urllib.error
import urllib.request
import webbrowser


APP_NAME = "BigShot Business OS"
PORT = 5059
STATUS_PATH = "/status"
BUSINESS_OS_PATH = "/business-os"
REQUEST_TIMEOUT = 0.45
SCAN_WORKERS = 64


def cache_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "BigShotBusinessOS" / "server.json"


def load_saved_ip(path: Path | None = None) -> str | None:
    try:
        payload = json.loads((path or cache_path()).read_text(encoding="utf-8"))
        return str(ipaddress.IPv4Address(payload["server_ip"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_ip(ip: str, path: Path | None = None) -> None:
    destination = path or cache_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps({"server_ip": str(ipaddress.IPv4Address(ip))}), encoding="utf-8")
    temporary.replace(destination)


def validate_server(ip: str, timeout: float = REQUEST_TIMEOUT) -> bool:
    try:
        normalized = str(ipaddress.IPv4Address(ip.strip()))
        request = urllib.request.Request(
            f"http://{normalized}:{PORT}{STATUS_PATH}",
            headers={"Accept": "application/json", "User-Agent": "BigShot-Business-OS-Launcher/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                return False
            payload = json.loads(response.read(64 * 1024).decode("utf-8"))
            return isinstance(payload, dict) and payload.get("status") == "running"
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, urllib.error.URLError):
        return False


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass
    return sorted(ip for ip in addresses if not ipaddress.IPv4Address(ip).is_loopback)


def subnet_candidates(local_ips: list[str] | None = None) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for local_ip in local_ips if local_ips is not None else local_ipv4_addresses():
        try:
            # Office networks normally use /24. This bounded scan completes
            # quickly and avoids probing unrelated routed networks.
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
        except ValueError:
            continue
        for address in network.hosts():
            candidate = str(address)
            if candidate != local_ip and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return candidates


def scan_candidates(candidates: list[str], validator=validate_server) -> str | None:
    if not candidates:
        return None
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(SCAN_WORKERS, len(candidates)))
    futures = {executor.submit(validator, candidate): candidate for candidate in candidates}
    try:
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    for pending in futures:
                        pending.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return futures[future]
            except Exception:
                continue
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return None


def discover_server(saved_ip: str | None = None, candidates: list[str] | None = None, validator=validate_server) -> str | None:
    if saved_ip and validator(saved_ip):
        return saved_ip
    scan_list = candidates if candidates is not None else subnet_candidates()
    if saved_ip:
        scan_list = [candidate for candidate in scan_list if candidate != saved_ip]
    return scan_candidates(scan_list, validator)


def chrome_executable() -> str | None:
    """Locate Chrome in standard Windows installations or on PATH."""
    candidates = [
        shutil.which("chrome.exe"),
        shutil.which("chrome"),
    ]
    for environment_name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(environment_name)
        if base:
            candidates.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def open_business_os(ip: str) -> str:
    url = f"http://{ip}:{PORT}{BUSINESS_OS_PATH}"
    chrome = chrome_executable()
    if chrome:
        subprocess.Popen([chrome, url])
    else:
        # Chrome is preferred. The system browser keeps the launcher usable on
        # machines where Chrome is not installed or is in a nonstandard path.
        webbrowser.open(url, new=2)
    return url


class NotFoundDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.result = "cancel"
        self.title(APP_NAME)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        tk.Label(self, text="BigShot Business Server not found.", padx=24, pady=20).pack()
        buttons = tk.Frame(self, padx=12, pady=12)
        buttons.pack()
        tk.Button(buttons, text="Retry", width=12, command=lambda: self.close("retry")).pack(side=tk.LEFT, padx=4)
        tk.Button(buttons, text="Enter IP Manually", width=18, command=lambda: self.close("manual")).pack(side=tk.LEFT, padx=4)
        tk.Button(buttons, text="Cancel", width=12, command=lambda: self.close("cancel")).pack(side=tk.LEFT, padx=4)
        self.protocol("WM_DELETE_WINDOW", lambda: self.close("cancel"))
        self.wait_window(self)

    def close(self, result: str) -> None:
        self.result = result
        self.destroy()


class Launcher:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.resizable(False, False)
        self.root.geometry("380x130")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        tk.Label(self.root, text=APP_NAME, font=("Segoe UI", 16, "bold"), pady=18).pack()
        self.status_label = tk.Label(self.root, text="Connecting to Business Server...", font=("Segoe UI", 10))
        self.status_label.pack()
        self.results: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.root.after(100, self.check_results)
        self.start_discovery()

    def start_discovery(self) -> None:
        self.status_label.config(text="Connecting to Business Server...")
        threading.Thread(target=self.discovery_worker, daemon=True).start()

    def discovery_worker(self) -> None:
        server = discover_server(load_saved_ip())
        self.results.put(("found" if server else "not_found", server))

    def check_results(self) -> None:
        try:
            action, value = self.results.get_nowait()
        except queue.Empty:
            if self.root.winfo_exists():
                self.root.after(100, self.check_results)
            return
        if action == "found" and value:
            self.open_server(value)
        else:
            self.handle_not_found()

    def open_server(self, ip: str) -> None:
        try:
            save_ip(ip)
        except OSError:
            pass
        open_business_os(ip)
        self.root.destroy()

    def handle_not_found(self) -> None:
        dialog = NotFoundDialog(self.root)
        if dialog.result == "retry":
            self.start_discovery()
        elif dialog.result == "manual":
            self.manual_ip()
        else:
            self.root.destroy()

    def manual_ip(self) -> None:
        value = simpledialog.askstring(APP_NAME, "Enter the Business Server IPv4 address:", parent=self.root)
        if value is None:
            self.handle_not_found()
            return
        try:
            ip = str(ipaddress.IPv4Address(value.strip()))
        except ValueError:
            messagebox.showerror(APP_NAME, "Please enter a valid IPv4 address.", parent=self.root)
            self.manual_ip()
            return
        self.status_label.config(text=f"Checking {ip}...")
        threading.Thread(target=self.manual_worker, args=(ip,), daemon=True).start()

    def manual_worker(self, ip: str) -> None:
        found = validate_server(ip, timeout=2.0)
        self.results.put(("found" if found else "not_found", ip if found else None))

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    Launcher().run()
