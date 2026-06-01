from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import hmac
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.cloud_clients import get_firestore_client, get_gcp_storage_client
from app.core.config import get_settings
from app.core.latex_paths import get_latex_template_root
from app.models import Donation, DonationItem
from app.services.demo_store import store


CERT_COLLECTION = "certificates"
CERT_BUCKET_PREFIX = "certificates/fssai"
_local_certificate_cache: dict[str, dict[str, Any]] = {}
FSSAI_TEMPLATE_PATH = get_latex_template_root() / "foodbridge_certificate.tex"


def _is_donation_completed(donation: Donation) -> bool:
    return bool(
        donation.status.value == "completed"
        or donation.completed_at
        or donation.delivery_confirmed_at
        or (donation.volunteer_task_status and donation.volunteer_task_status.value == "delivered_confirmed")
    )


def build_certificate_uid(donation_id: str, dt: datetime | None = None) -> str:
    moment = dt or datetime.now(timezone.utc)
    return f"{donation_id}_{moment.strftime('%d%m%y')}"


def _signature_secret() -> str:
    settings = get_settings()
    return settings.report_verify_secret or "foodbridge-dev-secret"


def compute_verify_signature(certificate_uid: str, donation_id: str, generated_at_iso: str) -> str:
    payload = f"{certificate_uid}|{donation_id}|{generated_at_iso}".encode("utf-8")
    return hmac.new(_signature_secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()


def build_verify_url(certificate_uid: str, donation_id: str, generated_at_iso: str) -> str:
    settings = get_settings()
    signature = compute_verify_signature(certificate_uid, donation_id, generated_at_iso)
    base = (settings.report_verify_base_url or settings.frontend_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("REPORT_VERIFY_BASE_URL must be configured for certificate QR verification")
    return f"{base}/reports/verify/{certificate_uid}?sig={signature}"


def _normalize_for_pdflatex(value: str) -> str:
    """pdfLaTeX + inputenc T1 cannot handle many Unicode symbols; normalize before escaping."""
    if not value:
        return value
    s = value
    for u, rep in (
        ("\u2264", "<="),
        ("\u2265", ">="),
        ("\u2026", "..."),
        ("≤", "<="),
        ("≥", ">="),
        ("…", "..."),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("–", "-"),
        ("—", "-"),
        ("\u00a0", " "),
    ):
        s = s.replace(u, rep)
    return s


def _latex_escape(value: str) -> str:
    value = _normalize_for_pdflatex(str(value))
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = value
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def _latex_escape_table_cell(value: str) -> str:
    # Escape cell content only; row separators are injected separately.
    return _latex_escape(value).replace("\n", " ")


def _truncate_display(value: str, max_len: int = 220) -> str:
    value = (value or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "..."


def _normalized_items_list(donation: Donation) -> list[DonationItem]:
    if donation.items:
        return list(donation.items)
    return [
        DonationItem(
            food_type=donation.food_type,
            quantity_kg=donation.quantity_kg,
            meal_count=donation.meal_count,
            condition=None,
        )
    ]


def _condition_bullet_parts(donation: Donation, item: DonationItem, *, max_bullets: int = 6) -> list[str]:
    """Short bullet lines for PDF (scan summary column); avoids long prose paragraphs."""
    if item.condition and str(item.condition).strip():
        return [_truncate_display(str(item.condition).strip(), 140)]
    scan = donation.scan
    declared = (item.food_type or "").strip() or (donation.food_type or "")
    detected = (scan.detected_food_type or "").strip()
    bullets: list[str] = []
    bullets.append(
        "Pre-redistribution scan: passed"
        if scan.passed
        else "Pre-redistribution scan: see platform record"
    )
    if detected and declared and detected.lower() != declared.lower():
        bullets.append(f"Vision label: {detected}")
        bullets.append(f"Declared on listing: {declared}")
    elif detected:
        bullets.append(f"Vision classification: {detected}")
    else:
        bullets.append(f"Declared category: {declared or '-'}")
    bullets.append(f"Pickup window: <= {scan.freshness_window_minutes} min from listing")
    if donation.accuracy:
        acc = donation.accuracy
        bullets.append(f"Quality check: {acc.band} ({acc.score:.0%})")
    if scan.reason and scan.reason.strip():
        bullets.append(_truncate_display(scan.reason.strip(), 110))
    return bullets[:max_bullets]


def _scan_summary_body_latex(donation: Donation, item: DonationItem) -> str:
    """Second column of the separate Scan summary table; full-width X column wraps text."""
    bullets = _condition_bullet_parts(donation, item)
    if not bullets:
        return r"\footnotesize --"
    parts = [r"\textbullet~" + _latex_escape(b) for b in bullets]
    inner = r" \newline ".join(parts)
    return r"\raggedright\footnotesize\sloppy\setlength{\parskip}{3pt}" + inner


def _condition_for_line(donation: Donation, item: DonationItem) -> str:
    """Plain-text summary for APIs / Firestore (single line)."""
    return "; ".join(_condition_bullet_parts(donation, item))


def _primary_food_label(donation: Donation) -> str:
    items = _normalized_items_list(donation)
    if len(items) == 1:
        return items[0].food_type or donation.food_type
    names = [i.food_type for i in items if i.food_type]
    if not names:
        return donation.food_type
    return f"Multi-item ({len(items)}): " + ", ".join(names[:4]) + ("..." if len(names) > 4 else "")


def _certificate_food_attestation(donation: Donation) -> str:
    scan = donation.scan
    parts: list[str] = []
    if scan.model_id or scan.model_version:
        ver = " ".join(x for x in [scan.model_id, scan.model_version] if x)
        parts.append(f"Scan engine: {ver}")
    if scan.generated_at:
        ts = scan.generated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        parts.append(f"Scan time: {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    parts.append("Line items reflect donor declarations aligned with the intake photo analysis.")
    return _truncate_display(" · ".join(parts))


def _replace_newcommand(tex: str, command: str, value: str) -> str:
    pattern = rf"\\newcommand\{{\\{command}\}}\s*\{{.*?\}}"
    replacement = rf"\newcommand{{\{command}}}{{{value}}}"
    return re.sub(pattern, lambda _m: replacement, tex, count=1)


def _compile_latex_to_pdf(tex_source: str) -> bytes:
    pdflatex_path = (
        os.getenv("PDFLATEX_PATH")
        or shutil.which("pdflatex")
        or shutil.which("pdflatex.exe")
    )
    if not pdflatex_path:
        common_windows_candidates = [
            Path("C:/Program Files/MiKTeX/miktex/bin/x64/pdflatex.exe"),
            Path("C:/Program Files/MiKTeX/miktex/bin/pdflatex.exe"),
            Path("C:/texlive/2026/bin/win32/pdflatex.exe"),
            Path("C:/texlive/2025/bin/win32/pdflatex.exe"),
            Path("C:/texlive/2024/bin/win32/pdflatex.exe"),
        ]
        for candidate in common_windows_candidates:
            if candidate.exists():
                pdflatex_path = str(candidate)
                break
    if not pdflatex_path:
        raise RuntimeError(
            "pdflatex not found. Install TeX Live/MiKTeX and/or set PDFLATEX_PATH to pdflatex.exe."
        )

    with tempfile.TemporaryDirectory(prefix="foodbridge_fssai_") as temp_dir:
        temp_path = Path(temp_dir)
        tex_file = temp_path / "certificate.tex"
        tex_file.write_text(tex_source, encoding="utf-8")
        cmd = [
            pdflatex_path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(temp_path),
            str(tex_file),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError("pdflatex executable path is invalid. Verify PDFLATEX_PATH or PATH.") from exc
        pdf_file = temp_path / "certificate.pdf"
        if proc.returncode != 0 and not pdf_file.exists():
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            combined = "\n".join([part for part in [stderr, stdout] if part]).strip()
            log_tail = "\n".join(combined.splitlines()[-20:]) if combined else "unknown error"
            raise RuntimeError(f"LaTeX compile failed (no PDF produced): {log_tail}")
        if not pdf_file.exists():
            raise RuntimeError("LaTeX compile finished but certificate.pdf was not produced")
        return pdf_file.read_bytes()


def _render_fssai_pdf_bytes(
    donation: Donation,
    certificate_uid: str,
    generated_at: datetime,
    verify_url: str,
    verify_signature: str | None,
) -> bytes:
    if not FSSAI_TEMPLATE_PATH.exists():
        raise RuntimeError(f"FSSAI LaTeX template not found at {FSSAI_TEMPLATE_PATH}")
    tex = FSSAI_TEMPLATE_PATH.read_text(encoding="utf-8")
    donor_profile = store.donors.get(donation.donor_id)
    ngo_profile = store.ngos.get(donation.assigned_ngo_id) if donation.assigned_ngo_id else None
    donation_items = _normalized_items_list(donation)
    created_ts = donation.created_at
    completed_ts = donation.completed_at or donation.delivery_confirmed_at or donation.updated_at
    duration_seconds = int((completed_ts - created_ts).total_seconds())
    mins = max(0, duration_seconds // 60)
    secs = max(0, duration_seconds % 60)
    donor_city = donor_profile.location.area if donor_profile and donor_profile.location else "-"
    ngo_city = ngo_profile.location.area if ngo_profile and ngo_profile.location else "-"
    food_lines = []
    scan_summary_lines = []
    for idx, item in enumerate(donation_items, start=1):
        food_type = item.food_type
        qty = item.quantity_kg
        meals = item.meal_count
        safe_food = _latex_escape_table_cell(str(food_type or "-"))
        safe_qty = _latex_escape_table_cell(f"{float(qty or 0):g} kg")
        safe_meals = _latex_escape_table_cell(f"{int(meals or 0)} meals")
        food_lines.append(f"{idx} & {safe_food} & {safe_qty} & {safe_meals} \\\\ \\hline")
        detail = _scan_summary_body_latex(donation, item)
        scan_summary_lines.append(f"{idx} & {detail} \\\\ \\hline")
    verify_label = verify_url
    food_rows = " ".join(food_lines) if food_lines else "1 & - & 0 kg & 0 meals \\\\ \\hline"
    scan_summary_rows = (
        " ".join(scan_summary_lines) if scan_summary_lines else r"1 & \footnotesize -- \\ \hline"
    )
    primary_label = _primary_food_label(donation)
    attestation = _certificate_food_attestation(donation)
    command_values = {
        "CertUID": _latex_escape(certificate_uid),
        "DonationID": _latex_escape(donation.id),
        "GeneratedAt": _latex_escape(generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
        "DonorName": _latex_escape(donation.donor_name),
        "DonorID": _latex_escape(donation.donor_id),
        "DonorFSSAI": _latex_escape(donor_profile.fssai_license if donor_profile else "-"),
        "DonorCity": _latex_escape(donor_city),
        "NGOName": _latex_escape(donation.assigned_ngo_name or "-"),
        "NGOChapter": _latex_escape(getattr(ngo_profile, "area", "-") if ngo_profile else "-"),
        "NGOReg": _latex_escape(getattr(ngo_profile, "ngo_darpan_id", "-") if ngo_profile else "-"),
        "NGOContact": _latex_escape(getattr(ngo_profile, "coordinator_name", "-") if ngo_profile else "-"),
        "NGOCity": _latex_escape(ngo_city),
        "FoodItem": _latex_escape(primary_label),
        "FoodQty": _latex_escape(f"{donation.quantity_kg:g} kg"),
        "MealCount": _latex_escape(f"{donation.meal_count} meals"),
        "FoodCondition": _latex_escape(attestation),
        "FoodRows": food_rows,
        "ScanSummaryRows": scan_summary_rows,
        "CreatedAt": _latex_escape(created_ts.strftime("%Y-%m-%d %H:%M:%S UTC")),
        "CompletedAt": _latex_escape(completed_ts.strftime("%Y-%m-%d %H:%M:%S UTC")),
        "Duration": _latex_escape(f"{mins} minutes {secs} seconds"),
        "VerifyURL": _latex_escape(verify_url),
        "VerifyLabel": verify_label,
    }
    for key, value in command_values.items():
        tex = _replace_newcommand(tex, key, value)
    if verify_signature:
        tex = tex.replace(r"\texttt{[Cryptographic Hash]}", r"\texttt{" + _latex_escape(verify_signature[:32] + "...") + "}")
    else:
        tex = tex.replace(r"\texttt{[Cryptographic Hash]}", r"\texttt{-}")
    return _compile_latex_to_pdf(tex)


def _persist_certificate_meta(record: dict[str, Any]) -> None:
    try:
        db = get_firestore_client()
        db.collection(CERT_COLLECTION).document(record["certificate_uid"]).set(record, merge=True)
    except Exception:
        _local_certificate_cache[record["certificate_uid"]] = record


def get_certificate_meta(certificate_uid: str) -> dict[str, Any] | None:
    try:
        db = get_firestore_client()
        doc = db.collection(CERT_COLLECTION).document(certificate_uid).get()
        if doc.exists:
            data = doc.to_dict() or {}
            _local_certificate_cache[certificate_uid] = data
            return data
    except Exception:
        pass
    return _local_certificate_cache.get(certificate_uid)


def _make_signed_url(blob_path: str, expires_minutes: int = 20) -> str:
    bucket = _get_certificate_bucket()
    blob = bucket.blob(blob_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expires_minutes),
        method="GET",
        response_disposition=f'attachment; filename="{blob.name.split("/")[-1]}"',
    )


def _upload_pdf(blob_path: str, pdf_bytes: bytes) -> None:
    bucket = _get_certificate_bucket()
    blob = bucket.blob(blob_path)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")


def _delete_pdf(blob_path: str) -> None:
    bucket = _get_certificate_bucket()
    blob = bucket.blob(blob_path)
    if blob.exists():
        blob.delete()


def _candidate_bucket_names() -> list[str]:
    settings = get_settings()
    configured = (settings.firebase_storage_bucket or "").strip()
    project_firebase = (settings.firebase_project_id or "").strip()
    project_gcp = (settings.google_cloud_project or "").strip()
    names: list[str] = []
    if configured:
        names.append(configured)
        if configured.endswith(".firebasestorage.app"):
            names.append(configured.replace(".firebasestorage.app", ".appspot.com"))
    if project_firebase:
        names.append(f"{project_firebase}.appspot.com")
    if project_gcp and project_gcp != project_firebase:
        names.append(f"{project_gcp}.appspot.com")
    # de-duplicate while preserving order
    seen = set()
    unique = []
    for item in names:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _get_certificate_bucket():
    client = get_gcp_storage_client()
    last_error: Exception | None = None
    for name in _candidate_bucket_names():
        try:
            bucket = client.bucket(name)
            if bucket.exists():
                return bucket
        except Exception as exc:
            last_error = exc
            continue
    detail = f"No writable storage bucket found. Tried: {_candidate_bucket_names()}"
    if last_error:
        detail = f"{detail}. Last error: {last_error}"
    raise RuntimeError(detail)


def ensure_fssai_certificate(
    donation_id: str,
    requested_by: str,
    requested_via: str,
    force: bool = False,
    uid_override: str | None = None,
) -> dict[str, Any]:
    donation = store.donations.get(donation_id)
    if not donation:
        raise KeyError("Donation not found")
    if not _is_donation_completed(donation):
        raise ValueError("Certificate can only be generated for completed donations")

    generated_at = datetime.now(timezone.utc)
    certificate_uid = uid_override or build_certificate_uid(donation_id, generated_at)
    existing = get_certificate_meta(certificate_uid)
    if existing and not force:
        signed_url = _make_signed_url(existing["storage_path"])
        generated_iso = existing.get("generated_at") or generated_at.isoformat()
        verify_url = existing.get("verify_url") or build_verify_url(certificate_uid, donation.id, generated_iso)
        verify_sig = existing.get("verify_signature") or compute_verify_signature(certificate_uid, donation.id, generated_iso)
        return {**existing, "signed_url": signed_url, "verify_url": verify_url, "verify_signature": verify_sig}
    if existing and force:
        old_path = existing.get("storage_path")
        if old_path:
            try:
                _delete_pdf(old_path)
            except Exception:
                pass

    generated_iso = generated_at.isoformat()
    verify_url = build_verify_url(certificate_uid, donation.id, generated_iso)
    verify_signature = compute_verify_signature(certificate_uid, donation.id, generated_iso)
    pdf_bytes = _render_fssai_pdf_bytes(donation, certificate_uid, generated_at, verify_url, verify_signature)
    path = f"{CERT_BUCKET_PREFIX}/{donation.donor_id}/{certificate_uid}.pdf"
    _upload_pdf(path, pdf_bytes)
    signed_url = _make_signed_url(path)

    record = {
        "certificate_uid": certificate_uid,
        "type": "fssai_redistribution_certificate",
        "donation_id": donation.id,
        "donor_id": donation.donor_id,
        "donor_name": donation.donor_name,
        "ngo_id": donation.assigned_ngo_id,
        "ngo_name": donation.assigned_ngo_name,
        "food_type": donation.food_type,
        "quantity_kg": donation.quantity_kg,
        "meal_count": donation.meal_count,
        "certificate_food_summary": _certificate_food_attestation(donation),
        "scan_detected_food_type": donation.scan.detected_food_type,
        "scan_freshness_window_minutes": donation.scan.freshness_window_minutes,
        "items": [
            {
                "food_type": item.food_type,
                "quantity_kg": item.quantity_kg,
                "meal_count": item.meal_count,
                "condition": item.condition,
                "certificate_condition_line": _condition_for_line(donation, item),
                "certificate_condition_bullets": _condition_bullet_parts(donation, item),
            }
            for item in _normalized_items_list(donation)
        ],
        "generated_at": generated_iso,
        "storage_path": path,
        "verify_url": verify_url,
        "verify_signature": verify_signature,
        "requested_by": requested_by,
        "requested_via": requested_via,
    }
    _persist_certificate_meta(record)
    return {**record, "signed_url": signed_url}


def generate_fssai_certificate_preview(
    donation_id: str,
    requested_by: str,
    requested_via: str,
    uid_override: str | None = None,
) -> dict[str, Any]:
    donation = store.donations.get(donation_id)
    if not donation:
        raise KeyError("Donation not found")
    if not _is_donation_completed(donation):
        raise ValueError("Certificate preview can only be generated for completed donations")

    generated_at = datetime.now(timezone.utc)
    certificate_uid = uid_override or build_certificate_uid(donation_id, generated_at)
    generated_iso = generated_at.isoformat()
    verify_url = build_verify_url(certificate_uid, donation.id, generated_iso)
    verify_signature = compute_verify_signature(certificate_uid, donation.id, generated_iso)
    pdf_bytes = _render_fssai_pdf_bytes(donation, certificate_uid, generated_at, verify_url, verify_signature)

    preview_stamp = generated_at.strftime("%Y%m%d%H%M%S")
    path = f"{CERT_BUCKET_PREFIX}/previews/{donation.donor_id}/{certificate_uid}_{preview_stamp}.pdf"
    _upload_pdf(path, pdf_bytes)
    signed_url = _make_signed_url(path)
    return {
        "preview": True,
        "certificate_uid": certificate_uid,
        "donation_id": donation.id,
        "donor_id": donation.donor_id,
        "donor_name": donation.donor_name,
        "ngo_id": donation.assigned_ngo_id,
        "ngo_name": donation.assigned_ngo_name,
        "generated_at": generated_iso,
        "storage_path": path,
        "signed_url": signed_url,
        "verify_url": verify_url,
        "verify_signature": verify_signature,
        "requested_by": requested_by,
        "requested_via": requested_via,
    }


def list_donor_fssai_certificates(donor_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        db = get_firestore_client()
        docs = db.collection(CERT_COLLECTION).where("donor_id", "==", donor_id).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            if data.get("type") == "fssai_redistribution_certificate":
                records.append(data)
                _local_certificate_cache[data["certificate_uid"]] = data
    except Exception:
        records = [
            item
            for item in _local_certificate_cache.values()
            if item.get("donor_id") == donor_id and item.get("type") == "fssai_redistribution_certificate"
        ]
    valid_records: list[dict[str, Any]] = []
    for item in records:
        donation_id = item.get("donation_id")
        if not donation_id:
            continue
        donation = store.donations.get(donation_id)
        if not donation:
            continue
        if _is_donation_completed(donation):
            valid_records.append(item)
    valid_records.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    return valid_records


def get_certificate_pdf_bytes(certificate_uid: str) -> tuple[bytes, str] | None:
    meta = get_certificate_meta(certificate_uid)
    if not meta:
        return None
    bucket = _get_certificate_bucket()
    blob = bucket.blob(meta["storage_path"])
    if not blob.exists():
        return None
    return blob.download_as_bytes(), meta["storage_path"].split("/")[-1]


def verify_certificate(certificate_uid: str, signature: str) -> dict[str, Any]:
    meta = get_certificate_meta(certificate_uid)
    if not meta:
        return {"valid": False, "reason": "certificate_not_found"}
    expected = meta.get("verify_signature")
    if not expected:
        generated_iso = meta.get("generated_at", "")
        expected = compute_verify_signature(certificate_uid, meta.get("donation_id", ""), generated_iso)
    valid = bool(signature and expected and hmac.compare_digest(signature, expected))
    return {
        "valid": valid,
        "certificate_uid": certificate_uid,
        "donation_id": meta.get("donation_id"),
        "donor_name": meta.get("donor_name"),
        "ngo_name": meta.get("ngo_name"),
        "food_type": meta.get("food_type"),
        "quantity_kg": meta.get("quantity_kg"),
        "meal_count": meta.get("meal_count"),
        "items": meta.get("items") or [],
        "certificate_food_summary": meta.get("certificate_food_summary"),
        "scan_detected_food_type": meta.get("scan_detected_food_type"),
        "scan_freshness_window_minutes": meta.get("scan_freshness_window_minutes"),
        "generated_at": meta.get("generated_at"),
        "reason": None if valid else "signature_mismatch",
    }
