# BigShot Business OS Windows Launcher

Double-click **BigShot Business OS.exe** to locate the Mac mini automatically and open Business OS in Google Chrome. If Chrome is not installed, the launcher falls back to the Windows default browser.

## How discovery works

1. Checks the last successful IPv4 address stored in `%LOCALAPPDATA%\BigShotBusinessOS\server.json`.
2. If that fails, scans each local IPv4 `/24` subnet for port 5059 using concurrent, short requests.
3. Accepts only an HTTP 200 JSON response from `/status` containing `"status": "running"`.
4. Saves the successful address and opens `http://<detected-ip>:5059/business-os` in Chrome.

All discovery runs on worker threads, so the connecting window remains responsive. The launcher sends only HTTP GET requests and never writes Business OS data.

## Install on Windows

1. Copy this entire folder to the Windows data-entry computer.
2. If **BigShot Business OS.exe** is present, no Python installation is required. Double-click it.
3. Keep the Mac mini and Windows computer on the same office LAN/Wi-Fi.
4. If Windows Firewall displays a prompt, allow access on **Private networks**.

## Build the executable on Windows

PyInstaller builds for the operating system on which it runs. To build the Windows executable:

1. Install 64-bit Python 3.11 or newer from <https://www.python.org/downloads/windows/> and enable **Add Python to PATH**.
2. Double-click `BUILD_WINDOWS.bat`, or run it from Command Prompt.
3. The exact output is `BigShot Business OS.exe` in this folder.

Equivalent build command:

```bat
py -3 -m pip install -r requirements-build.txt
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name "BigShot Business OS" BigShotBusinessOS.py
```

## Create the Desktop shortcut

Right-click `BigShot Business OS.exe`, select **Show more options** → **Send to** → **Desktop (create shortcut)**, then rename the shortcut to `BigShot Business OS`.

Alternatively, right-click `CREATE_DESKTOP_SHORTCUT.ps1`, select **Run with PowerShell**, or run:

```powershell
powershell -ExecutionPolicy Bypass -File .\CREATE_DESKTOP_SHORTCUT.ps1
```

## Test the source on Windows

```bat
py -3 -m unittest discover -s tests -v
```

The tests cover current server discovery, stale saved-IP fallback, subnet scanning, manual-IP validation, server unavailable handling, and malformed `/status` responses.
