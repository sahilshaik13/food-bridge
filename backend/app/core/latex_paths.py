"""
Resolve where FSSAI / CSR LaTeX templates live (repo root, backend/templates, or Docker).
Set FOODBRIDGE_TEMPLATE_ROOT to an absolute path in containers.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_latex_template_root() -> Path:
    override = os.environ.get("FOODBRIDGE_TEMPLATE_ROOT")
    if override:
        return Path(override).resolve()

    # backend/app/core/latex_paths.py → backend root = parents[2]
    here = Path(__file__).resolve()
    backend_root = here.parents[2]
    templates_dir = backend_root / "templates"
    repo_root = here.parents[3]

    if (templates_dir / "foodbridge_certificate.tex").exists():
        return templates_dir
    if (repo_root / "foodbridge_certificate.tex").exists():
        return repo_root
    return templates_dir
