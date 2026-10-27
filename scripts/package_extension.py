"""Packages the browser extension so it talks to a hosted Kavach by default (for judges and testers).

    python scripts/package_extension.py [address]      (default https://kavach-dy03.onrender.com)

Writes release/Kavach-extension.zip. The extension/ folder itself keeps http://localhost:8000 for local use.
Unzip, then chrome://extensions > Developer mode > Load unpacked > pick the unzipped kavach-extension folder.
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extension"
OUT = ROOT / "release" / "Kavach-extension.zip"
LOCAL = "http://localhost:8000"
# Every place the default address appears; the build fails if one goes missing, so a change can't slip past.
DEFAULT_IN = ("shared.js", "content.js", "options.html")
README = """Kavach browser extension, set up for {address}

1. Unzip this file.
2. In Chrome, Edge or Brave open chrome://extensions and turn on Developer mode.
3. Click "Load unpacked" and pick the unzipped kavach-extension folder.
4. Open {address} in the same browser, create an account or sign in, and reload the page once.
   The extension connects itself; the popup then shows your email.
5. Open a terms or privacy page, for example https://openai.com/policies/terms-of-use/,
   and Kavach's six agents review the site in a panel on the page.

The free server sleeps when idle: the first visit can take about a minute.
To use another Kavach, change "Kavach address" in the extension's Settings.
Source code: https://github.com/Gagan21-R/kavach
"""


def build(address: str) -> Path:
    address = address.rstrip("/")
    if not address.startswith(("https://", "http://")):
        raise SystemExit(f"Not a web address: {address}")
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
            rel = f.relative_to(SOURCE).as_posix()
            data = f.read_bytes()
            if rel in DEFAULT_IN:
                text = data.decode("utf-8")
                if LOCAL not in text:
                    raise SystemExit(f"{rel} no longer contains {LOCAL}; update DEFAULT_IN")
                data = text.replace(LOCAL, address).encode("utf-8")
            elif rel == "manifest.json":
                manifest = json.loads(data)
                short = f"Reviews the terms and privacy policy of sites you visit against your Kavach rules. Uses {address}."
                if len(short) <= 132:  # Chrome's limit; a long address keeps the original description
                    manifest["description"] = short
                data = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            z.writestr(f"kavach-extension/{rel}", data)
        z.writestr("kavach-extension/README.txt", README.format(address=address))
    return OUT


if __name__ == "__main__":
    out = build(sys.argv[1] if len(sys.argv) > 1 else "https://kavach-dy03.onrender.com")
    print(f"Wrote {out.relative_to(ROOT)}")
