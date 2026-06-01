"""
Telegram outbound localization (Telugu / Hindi) for slave bot replies.

Resolution order: Telegram `language_code` → Unicode script (Telugu / Devanagari) → English.
Translation: Vertex when AI integration is enabled; when disabled, minimal canned Telugu/Hindi for
common /start and /help blocks only (dynamic donation messages stay English).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Literal

from app.core.cloud_clients import initialize_vertex_ai
from app.core.config import get_settings

Locale = Literal["en", "te", "hi"]

_TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def resolve_telegram_locale(from_user: dict | None, text: str, caption: str = "") -> Locale:
    if from_user:
        lc = (from_user.get("language_code") or "").strip().lower()
        if lc.startswith("te"):
            return "te"
        if lc.startswith("hi"):
            return "hi"
    combined = f"{text or ''}\n{caption or ''}"
    if _TELUGU_RE.search(combined):
        return "te"
    if _DEVANAGARI_RE.search(combined):
        return "hi"
    return "en"


def _offline_localize(text: str, locale: Locale) -> str | None:
    if locale == "en":
        return text
    first = (text.splitlines() or [""])[0].strip()
    if first.startswith("👋 Welcome to your FoodBridge bot"):
        lines = text.splitlines()
        restaurant = "Unknown"
        fssai = "N/A"
        for ln in lines:
            if ln.startswith("Restaurant:"):
                restaurant = ln.replace("Restaurant:", "").strip()
            if ln.startswith("FSSAI:"):
                fssai = ln.replace("FSSAI:", "").strip()
        if locale == "te":
            return (
                "👋 మీ FoodBridge బాట్‌కు స్వాగతం!\n\n"
                f"రెస్టారెంట్: {restaurant}\n"
                f"FSSAI: {fssai}\n\n"
                "ఆదేశాలు:\n/donation - ఆహారం పోస్ట్ చేయండి\n/track - సక్రియ దానాలు\n"
                "/reports - FSSAI సర్టిఫికేట్లు\n/generate - FSSAI జనరేట్/పంపు\n"
                "/csrreports - CSR నివేదికలు\n/csrgenerate - CSR జనరేట్/పంపు\n/help - సహాయం"
            )
        return (
            "👋 आपके FoodBridge बॉट में आपका स्वागत है!\n\n"
            f"रेस्तरां: {restaurant}\n"
            f"FSSAI: {fssai}\n\n"
            "कमांड:\n/donation - भोजन पोस्ट करें\n/track - सक्रिय दान\n"
            "/reports - FSSAI प्रमाणपत्र\n/generate - FSSAI जनरेट/भेजें\n"
            "/csrreports - CSR रिपोर्टें\n/csrgenerate - CSR जनरेट/भेजें\n/help - सहायता"
        )
    if text.strip().startswith("FoodBridge Bot Commands:"):
        if locale == "te":
            return (
                "FoodBridge బాట్ ఆదేశాలు:\n"
                "/donation - కొత్త దానం పోస్ట్ చేయండి\n"
                "/track - మీ సక్రియ దానాల స్థితి\n"
                "/reports - జనరేట్ చేసిన మరియు పెండింగ్ సర్టిఫికేట్లు\n"
                "/generate <UID|donation_id> - FSSAI సర్టిఫికేట్ జనరేట్/పంపు\n"
                "/generate preview <UID|donation_id> - నమూనా FSSAI PDF మాత్రమే\n"
                "/csrreports - CSR నివేదికల జాబితా\n"
                "/csrgenerate <report_id|latest> - CSR నివేదిక జనరేట్/పంపు\n"
                "/csrgenerate preview <report_id|latest> - నమూనా CSR PDF మాత్రమే\n"
                "/help - ఈ సహాయ సందేశం"
            )
        return (
            "FoodBridge बॉट कमांड:\n"
            "/donation - नया दान पोस्ट करें\n"
            "/track - अपने सक्रिय दान की स्थिति\n"
            "/reports - जेनरेट और लंबित प्रमाणपत्र\n"
            "/generate <UID|donation_id> - FSSAI प्रमाणपत्र जनरेट/भेजें\n"
            "/generate preview <UID|donation_id> - केवल नमूना FSSAI PDF\n"
            "/csrreports - CSR रिपोर्ट सूची\n"
            "/csrgenerate <report_id|latest> - CSR रिपोर्ट जनरेट/भेजें\n"
            "/csrgenerate preview <report_id|latest> - केवल नमूना CSR PDF\n"
            "/help - यह सहायता संदेश"
        )
    return None


@lru_cache(maxsize=256)
def _vertex_translate_cached(text: str, locale: str) -> str:
    settings = get_settings()
    if not initialize_vertex_ai(settings):
        return text
    try:
        from vertexai.generative_models import GenerativeModel

        lang = "Telugu" if locale == "te" else "Hindi"
        model = GenerativeModel(settings.vertex_ai_model_id)
        prompt = (
            f"Translate the following FoodBridge restaurant-assistant message into {lang}. "
            "Keep emojis, numbers, slash commands like /donation and /help, donation IDs, and URLs unchanged. "
            "Preserve line breaks. Output only the translated text, no markdown fences."
        )
        resp = model.generate_content([prompt, text])
        out = (resp.text or "").strip()
        if out.startswith("```"):
            out = out.strip("`")
            if out.lower().startswith("text"):
                out = out[4:].lstrip()
        return out or text
    except Exception as exc:
        print(f"[telegram_locale] translate failed: {exc}")
        return text


def localize_outbound_message(text: str, locale: Locale) -> str:
    if locale == "en" or not (text or "").strip():
        return text

    if os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true":
        canned = _offline_localize(text, locale)
        return canned if canned is not None else text

    return _vertex_translate_cached(text, locale)
