"""
Phase 8 smoke: GET /health and /health/ml (no auth).

Usage:
  python scripts/smoke_release_check.py
  set SMOKE_API_BASE=https://foodbridge-api-....run.app && python scripts/smoke_release_check.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.environ.get("SMOKE_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    paths = ("/health", "/health/ml")
    ok_all = True
    for path in paths:
        url = f"{base}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                status_ok = resp.status == 200 and data.get("ok") is True
                print(f"{resp.status} {path} ok={data.get('ok')} keys={list(data.keys())[:8]}...")
                if not status_ok:
                    ok_all = False
                    print(json.dumps(data, indent=2)[:2000])
        except urllib.error.HTTPError as e:
            print(f"FAIL {path}: HTTP {e.code}", file=sys.stderr)
            ok_all = False
        except Exception as e:
            print(f"FAIL {path}: {e}", file=sys.stderr)
            ok_all = False
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
