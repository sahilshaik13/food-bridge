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
from app.models import Donation
from app.services.demo_store import store

CSR_COLLECTION = "csr_reports"
CSR_PREFIX = "reports/csr"
_local_cache: dict[str, dict[str, Any]] = {}
ROOT_DIR = Path(__file__).resolve().parents[3]
CSR_TEMPLATE_PATH = ROOT_DIR / "csr.tex"


def _is_completed(donation: Donation) -> bool:
    return bool(
        donation.status.value == "completed"
        or donation.completed_at
        or donation.delivery_confirmed_at
        or (donation.volunteer_task_status and donation.volunteer_task_status.value == "delivered_confirmed")
    )


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
    seen: set[str] = set()
    unique: list[str] = []
    for item in names:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _get_bucket():
    client = get_gcp_storage_client()
    for name in _candidate_bucket_names():
        bucket = client.bucket(name)
        if bucket.exists():
            return bucket
    raise RuntimeError(f"No writable storage bucket found. Tried: {_candidate_bucket_names()}")


def _signed_url(path: str, expires_minutes: int = 20) -> str:
    blob = _get_bucket().blob(path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expires_minutes),
        method="GET",
        response_disposition=f'attachment; filename="{path.split("/")[-1]}"',
    )


def _delete_pdf(path: str) -> None:
    blob = _get_bucket().blob(path)
    if blob.exists():
        blob.delete()


def _signature_secret() -> str:
    settings = get_settings()
    return settings.report_verify_secret or "foodbridge-dev-secret"


def compute_csr_verify_signature(report_id: str, donor_id: str, generated_at_iso: str) -> str:
    payload = f"{report_id}|{donor_id}|{generated_at_iso}".encode("utf-8")
    return hmac.new(_signature_secret().encode("utf-8"), payload, hashlib.sha256).hexdigest()


def build_csr_verify_url(report_id: str, donor_id: str, generated_at_iso: str) -> str:
    settings = get_settings()
    base = (settings.frontend_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("FRONTEND_BASE_URL must be configured for CSR verification URL")
    sig = compute_csr_verify_signature(report_id, donor_id, generated_at_iso)
    return f"{base}/verify/csr/{report_id}?sig={sig}"


def _latex_escape(value: str) -> str:
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

    with tempfile.TemporaryDirectory(prefix="foodbridge_csr_") as temp_dir:
        temp_path = Path(temp_dir)
        tex_file = temp_path / "csr_report.tex"
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
        pdf_file = temp_path / "csr_report.pdf"
        if proc.returncode != 0 and not pdf_file.exists():
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            combined = "\n".join([part for part in [stderr, stdout] if part]).strip()
            log_tail = "\n".join(combined.splitlines()[-20:]) if combined else "unknown error"
            raise RuntimeError(f"LaTeX compile failed (no PDF produced): {log_tail}")
        if not pdf_file.exists():
            raise RuntimeError("LaTeX compile finished but csr_report.pdf was not produced")
        return pdf_file.read_bytes()


def _render_pdf(metrics: dict[str, Any], report_id: str) -> bytes:
    if not CSR_TEMPLATE_PATH.exists():
        raise RuntimeError(f"CSR LaTeX template not found at {CSR_TEMPLATE_PATH}")
    tex = CSR_TEMPLATE_PATH.read_text(encoding="utf-8")
    command_values = {
        "ReportID": _latex_escape(report_id),
        "GeneratedAt": _latex_escape(datetime.fromisoformat(metrics["generated_at"]).strftime("%Y-%m-%d %H:%M:%S UTC")),
        "PeriodLabel": _latex_escape(metrics["period_label"]),
        "DonorID": _latex_escape(metrics["donor_id"]),
        "DonorName": _latex_escape(metrics["donor_name"]),
        "SignedURL": _latex_escape(metrics.get("verify_url") or ""),
        "MonthlyMeals": _latex_escape(str(metrics["monthly_meals"])),
        "TotalKgSaved": _latex_escape(str(metrics["total_kg_saved"])),
        "COOffsetKg": _latex_escape(str(metrics["co2_offset_kg"])),
        "TotalPosted": _latex_escape(str(metrics["total_donations_posted"])),
        "CompletedDonations": _latex_escape(str(metrics["completed_donations"])),
        "CompletionRate": _latex_escape(str(metrics["completion_rate_pct"])),
        "PickupSuccessRate": _latex_escape(str(metrics["pickup_success_rate_pct"])),
        "OnTimeRate": _latex_escape(str(metrics["on_time_delivery_rate_pct"])),
        "AvgAcceptMin": _latex_escape(str(metrics["avg_acceptance_minutes"])),
        "AvgDeliveryMin": _latex_escape(str(metrics["avg_delivery_minutes"])),
        "UniqueNGOs": _latex_escape(str(metrics["unique_ngos_served"])),
        "MultiItemDonations": _latex_escape(str(metrics["multi_item_completed_donations"])),
        "DonatedItemCount": _latex_escape(str(metrics["donated_item_count"])),
        "VolunteerDeliveries": _latex_escape(str(metrics["volunteer_supported_deliveries"])),
        "EmergencyContribCount": _latex_escape(str(metrics["emergency_contributions_count"])),
        "EmergencyKg": _latex_escape(str(metrics["emergency_contribution_kg"])),
        "EmergencyRequestsSupported": _latex_escape(str(metrics["emergency_requests_supported"])),
    }
    for key, value in command_values.items():
        tex = _replace_newcommand(tex, key, value)
    return _compile_latex_to_pdf(tex)


def generate_csr_report_for_donor(
    donor_id: str,
    requested_by: str,
    requested_via: str = "web",
    force: bool = False,
    report_id_override: str | None = None,
) -> dict[str, Any]:
    donor = store.donors.get(donor_id)
    if donor is None:
        raise KeyError("Donor not found")

    donor_donations = [d for d in store.donations.values() if d.donor_id == donor_id]
    completed = [d for d in donor_donations if _is_completed(d)]
    total_meals = int(sum((d.completed_meals_served or d.meal_count or 0) for d in completed))
    total_kg = round(sum((d.quantity_kg or 0) for d in completed), 2)
    co2_offset = round(total_kg * 0.61, 2)
    unique_ngos_served = len({d.assigned_ngo_id for d in completed if d.assigned_ngo_id})
    completed_count = len(completed)
    posted_count = len(donor_donations)
    completion_rate = round((completed_count / posted_count) * 100, 2) if posted_count else 0.0
    pickup_success_rate = completion_rate
    on_time_count = len([d for d in completed if d.completed_at and d.expires_at and d.completed_at <= d.expires_at])
    on_time_rate = round((on_time_count / completed_count) * 100, 2) if completed_count else 0.0
    acceptance_samples = [d.acceptance_seconds for d in completed if d.acceptance_seconds is not None]
    delivery_samples = [d.delivery_seconds for d in completed if d.delivery_seconds is not None]
    avg_acceptance_minutes = round((sum(acceptance_samples) / len(acceptance_samples)) / 60, 2) if acceptance_samples else 0.0
    avg_delivery_minutes = round((sum(delivery_samples) / len(delivery_samples)) / 60, 2) if delivery_samples else 0.0
    multi_item_completed = len([d for d in completed if len(d.items or []) > 1])
    volunteer_supported = len([d for d in completed if d.volunteer_uid])
    donated_item_count = sum(len(d.items or []) if d.items else 1 for d in completed)
    fulfilled_emergency_count = 0
    emergency_contributions_count = 0
    emergency_contribution_kg = 0.0
    for req in store.emergency_requests.values():
        donor_entries = [c for c in req.contributions if c.donor_id == donor_id]
        if not donor_entries:
            continue
        emergency_contributions_count += len(donor_entries)
        emergency_contribution_kg += sum(c.quantity_kg for c in donor_entries)
        if req.status in {"fulfilled", "partial_accepted"}:
            fulfilled_emergency_count += 1
    emergency_contribution_kg = round(emergency_contribution_kg, 2)

    area_distribution: dict[str, int] = {}
    for donation in completed:
        ngo = store.ngos.get(donation.assigned_ngo_id) if donation.assigned_ngo_id else None
        area = ngo.area if ngo and ngo.area else "unknown"
        area_distribution[area] = area_distribution.get(area, 0) + 1
    area_coverage = sorted(
        [{"area": area, "completed_donations": count} for area, count in area_distribution.items()],
        key=lambda x: x["completed_donations"],
        reverse=True,
    )

    generated_at = datetime.now(timezone.utc)
    period_label = generated_at.strftime("%B %Y")
    report_id = report_id_override or f"csr_{donor_id}_{generated_at.strftime('%Y%m%d%H%M%S')}"
    existing = get_csr_report_meta(report_id)
    if existing and not force:
        storage_path = existing.get("storage_path")
        signed = _signed_url(storage_path) if storage_path else None
        return {**existing, "signed_url": signed}
    if existing and force:
        old_path = existing.get("storage_path")
        if old_path:
            try:
                _delete_pdf(old_path)
            except Exception:
                pass

    metrics = {
        "report_type": "csr_impact_report",
        "report_id": report_id,
        "donor_id": donor_id,
        "donor_name": donor.name,
        "period_label": period_label,
        "generated_at": generated_at.isoformat(),
        "requested_by": requested_by,
        "requested_via": requested_via,
        "completed_donations": completed_count,
        "total_donations_posted": posted_count,
        "completion_rate_pct": completion_rate,
        "pickup_success_rate_pct": pickup_success_rate,
        "on_time_delivery_rate_pct": on_time_rate,
        "avg_acceptance_minutes": avg_acceptance_minutes,
        "avg_delivery_minutes": avg_delivery_minutes,
        "monthly_meals": total_meals,
        "total_kg_saved": total_kg,
        "co2_offset_kg": co2_offset,
        "unique_ngos_served": unique_ngos_served,
        "multi_item_completed_donations": multi_item_completed,
        "volunteer_supported_deliveries": volunteer_supported,
        "donated_item_count": donated_item_count,
        "emergency_contributions_count": emergency_contributions_count,
        "emergency_contribution_kg": emergency_contribution_kg,
        "emergency_requests_supported": fulfilled_emergency_count,
        "area_coverage": area_coverage,
        "sdg_alignment": ["SDG 2", "SDG 12", "SDG 13"],
        "tax_note": "In-kind food donations are impact-tracked; this report does not claim 80G cash-deduction eligibility.",
    }
    path = f"{CSR_PREFIX}/{donor_id}/{report_id}.pdf"
    metrics["verify_signature"] = compute_csr_verify_signature(report_id, donor_id, metrics["generated_at"])
    metrics["verify_url"] = build_csr_verify_url(report_id, donor_id, metrics["generated_at"])
    pdf_bytes = _render_pdf(metrics, report_id)
    _get_bucket().blob(path).upload_from_string(pdf_bytes, content_type="application/pdf")
    signed = _signed_url(path)
    record = {**metrics, "storage_path": path, "signed_url": signed}
    _local_cache[report_id] = record
    try:
        db = get_firestore_client()
        db.collection(CSR_COLLECTION).document(report_id).set(record, merge=True)
    except Exception:
        pass
    return {**record}


def generate_csr_report_preview_for_donor(
    donor_id: str,
    requested_by: str,
    requested_via: str = "web_preview",
    report_id_override: str | None = None,
) -> dict[str, Any]:
    donor = store.donors.get(donor_id)
    if donor is None:
        raise KeyError("Donor not found")

    donor_donations = [d for d in store.donations.values() if d.donor_id == donor_id]
    completed = [d for d in donor_donations if _is_completed(d)]
    total_meals = int(sum((d.completed_meals_served or d.meal_count or 0) for d in completed))
    total_kg = round(sum((d.quantity_kg or 0) for d in completed), 2)
    co2_offset = round(total_kg * 0.61, 2)
    unique_ngos_served = len({d.assigned_ngo_id for d in completed if d.assigned_ngo_id})
    completed_count = len(completed)
    posted_count = len(donor_donations)
    completion_rate = round((completed_count / posted_count) * 100, 2) if posted_count else 0.0
    pickup_success_rate = completion_rate
    on_time_count = len([d for d in completed if d.completed_at and d.expires_at and d.completed_at <= d.expires_at])
    on_time_rate = round((on_time_count / completed_count) * 100, 2) if completed_count else 0.0
    acceptance_samples = [d.acceptance_seconds for d in completed if d.acceptance_seconds is not None]
    delivery_samples = [d.delivery_seconds for d in completed if d.delivery_seconds is not None]
    avg_acceptance_minutes = round((sum(acceptance_samples) / len(acceptance_samples)) / 60, 2) if acceptance_samples else 0.0
    avg_delivery_minutes = round((sum(delivery_samples) / len(delivery_samples)) / 60, 2) if delivery_samples else 0.0
    multi_item_completed = len([d for d in completed if len(d.items or []) > 1])
    volunteer_supported = len([d for d in completed if d.volunteer_uid])
    donated_item_count = sum(len(d.items or []) if d.items else 1 for d in completed)
    fulfilled_emergency_count = 0
    emergency_contributions_count = 0
    emergency_contribution_kg = 0.0
    for req in store.emergency_requests.values():
        donor_entries = [c for c in req.contributions if c.donor_id == donor_id]
        if not donor_entries:
            continue
        emergency_contributions_count += len(donor_entries)
        emergency_contribution_kg += sum(c.quantity_kg for c in donor_entries)
        if req.status in {"fulfilled", "partial_accepted"}:
            fulfilled_emergency_count += 1
    emergency_contribution_kg = round(emergency_contribution_kg, 2)

    area_distribution: dict[str, int] = {}
    for donation in completed:
        ngo = store.ngos.get(donation.assigned_ngo_id) if donation.assigned_ngo_id else None
        area = ngo.area if ngo and ngo.area else "unknown"
        area_distribution[area] = area_distribution.get(area, 0) + 1
    area_coverage = sorted(
        [{"area": area, "completed_donations": count} for area, count in area_distribution.items()],
        key=lambda x: x["completed_donations"],
        reverse=True,
    )

    generated_at = datetime.now(timezone.utc)
    period_label = generated_at.strftime("%B %Y")
    report_id = report_id_override or f"csr_{donor_id}_{generated_at.strftime('%Y%m%d%H%M%S')}"
    metrics = {
        "report_type": "csr_impact_report",
        "report_id": report_id,
        "donor_id": donor_id,
        "donor_name": donor.name,
        "period_label": period_label,
        "generated_at": generated_at.isoformat(),
        "requested_by": requested_by,
        "requested_via": requested_via,
        "completed_donations": completed_count,
        "total_donations_posted": posted_count,
        "completion_rate_pct": completion_rate,
        "pickup_success_rate_pct": pickup_success_rate,
        "on_time_delivery_rate_pct": on_time_rate,
        "avg_acceptance_minutes": avg_acceptance_minutes,
        "avg_delivery_minutes": avg_delivery_minutes,
        "monthly_meals": total_meals,
        "total_kg_saved": total_kg,
        "co2_offset_kg": co2_offset,
        "unique_ngos_served": unique_ngos_served,
        "multi_item_completed_donations": multi_item_completed,
        "volunteer_supported_deliveries": volunteer_supported,
        "donated_item_count": donated_item_count,
        "emergency_contributions_count": emergency_contributions_count,
        "emergency_contribution_kg": emergency_contribution_kg,
        "emergency_requests_supported": fulfilled_emergency_count,
        "area_coverage": area_coverage,
        "sdg_alignment": ["SDG 2", "SDG 12", "SDG 13"],
        "tax_note": "In-kind food donations are impact-tracked; this report does not claim 80G cash-deduction eligibility.",
    }
    metrics["verify_signature"] = compute_csr_verify_signature(report_id, donor_id, metrics["generated_at"])
    metrics["verify_url"] = build_csr_verify_url(report_id, donor_id, metrics["generated_at"])
    pdf_bytes = _render_pdf(metrics, report_id)
    preview_stamp = generated_at.strftime("%Y%m%d%H%M%S")
    path = f"{CSR_PREFIX}/previews/{donor_id}/{report_id}_{preview_stamp}.pdf"
    _get_bucket().blob(path).upload_from_string(pdf_bytes, content_type="application/pdf")
    signed = _signed_url(path)
    return {**metrics, "preview": True, "storage_path": path, "signed_url": signed}


def get_csr_report_meta(report_id: str) -> dict[str, Any] | None:
    try:
        db = get_firestore_client()
        doc = db.collection(CSR_COLLECTION).document(report_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            _local_cache[report_id] = data
            return data
    except Exception:
        pass
    return _local_cache.get(report_id)


def list_donor_csr_reports(donor_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        db = get_firestore_client()
        docs = db.collection(CSR_COLLECTION).where("donor_id", "==", donor_id).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            if data.get("report_type") == "csr_impact_report":
                records.append(data)
                _local_cache[data.get("report_id", doc.id)] = data
    except Exception:
        records = [
            item
            for item in _local_cache.values()
            if item.get("donor_id") == donor_id and item.get("report_type") == "csr_impact_report"
        ]
    records.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    return records


def get_csr_pdf_bytes(report_id: str) -> tuple[bytes, str] | None:
    meta = get_csr_report_meta(report_id)
    if not meta:
        return None
    path = meta.get("storage_path")
    if not path:
        return None
    blob = _get_bucket().blob(path)
    if not blob.exists():
        return None
    return blob.download_as_bytes(), path.split("/")[-1]


def verify_csr_report(report_id: str, signature: str) -> dict[str, Any]:
    meta = get_csr_report_meta(report_id)
    if not meta:
        return {"valid": False, "reason": "report_not_found", "report_id": report_id}
    expected = meta.get("verify_signature")
    if not expected:
        expected = compute_csr_verify_signature(report_id, meta.get("donor_id", ""), meta.get("generated_at", ""))
    valid = bool(signature and expected and hmac.compare_digest(signature, expected))
    return {
        "valid": valid,
        "reason": None if valid else "signature_mismatch",
        "report_id": report_id,
        "donor_id": meta.get("donor_id"),
        "donor_name": meta.get("donor_name"),
        "period_label": meta.get("period_label"),
        "generated_at": meta.get("generated_at"),
        "monthly_meals": meta.get("monthly_meals"),
        "total_kg_saved": meta.get("total_kg_saved"),
        "co2_offset_kg": meta.get("co2_offset_kg"),
    }
