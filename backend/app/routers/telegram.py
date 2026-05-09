from fastapi import APIRouter, HTTPException, Depends, Header, Request
import requests
from typing import Dict, Any, Optional
import re
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models import (
    TelegramDonationResult, 
    TelegramLink, 
    TelegramLinkRequest, 
    TelegramActivationRequest,
    TelegramAuthState,
    SlaveBot,
    ConversationStep,
    ConversationState,
    Role,
    DonationCreate,
    DonationItem,
)
from app.services.demo_store import store
from app.services.auth_service import verify_firebase_token
from app.services.kms_service import kms_service
from app.services.time_scale import logical_minutes_from_timedelta
from app.services.certificate_service import (
    build_certificate_uid,
    ensure_fssai_certificate,
    generate_fssai_certificate_preview,
    get_certificate_meta,
    get_certificate_pdf_bytes,
    list_donor_fssai_certificates,
)
from app.services.csr_report_service import (
    generate_csr_report_for_donor,
    generate_csr_report_preview_for_donor,
    get_csr_pdf_bytes,
    list_donor_csr_reports,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# --- Master Bot Routes ---

@router.post("/auth/generate-link")
def generate_auth_link(decoded_token: dict = Depends(verify_firebase_token)):
    uid = decoded_token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    state_token = store.create_auth_state(uid)
    settings = get_settings()
    deep_link = f"https://t.me/{settings.telegram_master_bot_username}?start=auth_{state_token}"
    return {"deep_link": deep_link, "state_token": state_token}


@router.get("/auth/status/{state_token}")
def get_auth_status(state_token: str):
    state = store.get_auth_state(state_token)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    donor_id = state.donor_id
    if donor_id not in store.donors:
        user = store.users.get(donor_id)
        if user and user.entity_id:
            donor_id = user.entity_id
    slave_bot = store.get_slave_bot(donor_id) if donor_id in store.donors else None
    return {
        "confirmed": state.confirmed,
        "donor_id": donor_id if state.confirmed else None,
        "bot_registered": bool(slave_bot),
        "bot_username": slave_bot.bot_username if slave_bot else None,
        "bot_url": f"https://t.me/{slave_bot.bot_username}" if slave_bot else None,
    }


@router.get("/status")
def get_telegram_status(decoded_token: dict = Depends(verify_firebase_token)):
    uid = decoded_token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = store.users.get(uid)
    if not user or not user.entity_id:
        return {"connected": False, "bot_registered": False}
    donor_id = user.entity_id
    donor = store.donors.get(donor_id)
    if donor is None:
        return {"connected": False, "bot_registered": False}
    slave_bot = store.get_slave_bot(donor_id)
    bot_username = slave_bot.bot_username if slave_bot else donor.telegram_username
    return {
        "connected": bool(donor.telegram_enabled),
        "bot_registered": bool(slave_bot),
        "bot_username": bot_username,
        "bot_url": f"https://t.me/{bot_username}" if bot_username else None,
    }


@router.post("/deactivate")
def deactivate_telegram_bot(decoded_token: dict = Depends(verify_firebase_token)):
    uid = decoded_token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = store.users.get(uid)
    if not user or not user.entity_id:
        raise HTTPException(status_code=404, detail="Donor profile not found")
    donor_id = user.entity_id
    donor = store.donors.get(donor_id)
    if donor is None:
        raise HTTPException(status_code=404, detail="Donor profile not found")
    slave_bot = store.get_slave_bot(donor_id)

    if slave_bot:
        token = kms_service.decrypt(slave_bot.bot_token)
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                json={"drop_pending_updates": True},
                timeout=8,
            )
        except Exception:
            pass
        if donor_id in store.slave_bots:
            del store.slave_bots[donor_id]
        db = store._firestore()
        if db:
            db.collection("slave_bots").document(donor_id).delete()

    donor.telegram_enabled = False
    donor.telegram_username = None
    donor.telegram_chat_id = None
    store.donors[donor_id] = donor
    store._write_doc("donors", donor_id, donor)
    return {"ok": True, "message": "Telegram bot deactivated"}


@router.post("/master/webhook")
async def master_webhook(update: Dict[str, Any], x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    # Verify secret token if configured in BotFather
    settings = get_settings()
    if settings.telegram_master_secret and x_telegram_bot_api_secret_token != settings.telegram_master_secret:
        raise HTTPException(status_code=403)

    message = update.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))
    
    # Handle Callback Queries
    if "callback_query" in update:
        return await _handle_master_callback(update["callback_query"])

    # Auth Deep Link: /start auth_{state_token}
    if text.startswith("/start auth_"):
        state_token = text.replace("/start auth_", "")
        return await _handle_master_auth_start(chat_id, state_token)

    # Conversation State Handling
    conv_state = store.get_conversation_state(chat_id)
    if conv_state and conv_state.step == ConversationStep.awaiting_bot_token:
        return await _handle_master_bot_token(chat_id, text)

    # Default Commands
    if text.startswith("/start"):
        reply = (
            "Welcome to FoodBridge Master Bot! 🍲\n\n"
            "To link your restaurant, please use the 'Connect' button in your FoodBridge Dashboard."
        )
        _send_telegram_reply(chat_id, reply, is_master=True)
    
    elif text.startswith("/help"):
        reply = "This is the FoodBridge Master Bot. It handles authentication and setup. Use your personal restaurant bot for donations."
        _send_telegram_reply(chat_id, reply, is_master=True)

    return {"ok": True}


# --- Slave Bot Routes ---

@router.post("/slave/webhook")
async def slave_webhook(
    update: Dict[str, Any], 
    x_telegram_bot_api_secret_token: str = Header(...)
):
    # In this architecture, x_telegram_bot_api_secret_token IS the donor_id.
    # Backward compatibility: older bots may still send Firebase UID as secret.
    donor_id = x_telegram_bot_api_secret_token
    if donor_id not in store.donors:
        user = store.users.get(donor_id)
        if user and user.entity_id:
            donor_id = user.entity_id
    slave_bot = store.get_slave_bot(donor_id)
    
    if not slave_bot:
        return {"ok": False, "error": "Bot not registered"}

    message = update.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))
    callback = update.get("callback_query", {})
    callback_data = (callback.get("data") or "").strip()
    callback_chat_id = str(callback.get("message", {}).get("chat", {}).get("id") or "")
    effective_chat_id = chat_id or callback_chat_id
    
    # Handle /start for first-time slave activation
    if text.startswith("/start"):
        if not slave_bot.slave_chat_id:
            slave_bot.slave_chat_id = chat_id
            store.register_slave_bot(slave_bot)
        
        donor = store.donors.get(donor_id)
        reply = (
            f"👋 Welcome to your FoodBridge bot!\n\n"
            f"Restaurant: {donor.name if donor else 'Unknown'}\n"
            f"FSSAI: {donor.fssai_license if donor else 'N/A'}\n\n"
            "Commands:\n/donation - Post food\n/track - Active donations\n/reports - FSSAI certificates\n/generate - FSSAI generate/send\n/csrreports - CSR report list\n/csrgenerate - Generate/send CSR report\n/help - Support"
        )
        _send_telegram_reply(chat_id, reply, token_encrypted=slave_bot.bot_token)
        return {"ok": True}

    if text.startswith("/help"):
        _send_telegram_reply(
            chat_id,
            (
                "FoodBridge Bot Commands:\n"
                "/donation - Post a new food donation\n"
                "/track - View your active donation statuses\n"
                "/reports - View generated and pending certificates\n"
                "/generate <UID|donation_id> - Generate/send FSSAI certificate\n"
                "/generate preview <UID|donation_id> - Send sample FSSAI PDF only\n"
                "/csrreports - View CSR reports list\n"
                "/csrgenerate <report_id|latest> - Generate/send CSR report\n"
                "/csrgenerate preview <report_id|latest> - Send sample CSR PDF only\n"
                "/help - Show this help message"
            ),
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    if text.startswith("/track"):
        return await _handle_slave_track(donor_id, slave_bot, chat_id)
    if text.startswith("/reports"):
        return await _handle_slave_reports(donor_id, slave_bot, chat_id)
    if text.startswith("/generate"):
        return await _handle_slave_generate(donor_id, slave_bot, chat_id, text)
    if text.startswith("/csrreports"):
        return await _handle_slave_csr_reports(donor_id, slave_bot, chat_id)
    if text.startswith("/csrgenerate"):
        return await _handle_slave_csr_generate(donor_id, slave_bot, chat_id, text)
    if callback_data.startswith("slave_regen_confirm|") or callback_data.startswith("slave_regen_cancel|"):
        return await _handle_slave_regenerate_callback(donor_id, slave_bot, effective_chat_id, callback_data)
    if callback_data.startswith("slave_csr_regen_confirm|") or callback_data.startswith("slave_csr_regen_cancel|"):
        return await _handle_slave_csr_regenerate_callback(donor_id, slave_bot, effective_chat_id, callback_data)
    if callback_data.startswith("slave_preview_approve|") or callback_data.startswith("slave_preview_discard|"):
        return await _handle_slave_preview_callback(donor_id, slave_bot, effective_chat_id, callback_data)
    if callback_data.startswith("slave_csr_preview_approve|") or callback_data.startswith("slave_csr_preview_discard|"):
        return await _handle_slave_csr_preview_callback(donor_id, slave_bot, effective_chat_id, callback_data)

    # Handle /donation flow
    conv_state = store.get_conversation_state(chat_id)
    if text.startswith("/donation") or "callback_query" in update or (
        conv_state and conv_state.step in {
            ConversationStep.awaiting_food_type,
            ConversationStep.awaiting_quantity,
            ConversationStep.awaiting_quantity_text,
            ConversationStep.awaiting_more_items,
        }
    ):
        return await _handle_slave_donation_flow(donor_id, slave_bot, update)

    # Handle Photo Upload (Donation)
    if "photo" in message:
        return await _handle_slave_photo(donor_id, slave_bot, update)

    return {"ok": True}


# --- Internal Handlers ---

async def _handle_master_auth_start(chat_id: str, state_token: str):
    auth_state = store.get_auth_state(state_token)
    if not auth_state or auth_state.used or auth_state.expires_at < datetime.now(timezone.utc):
        _send_telegram_reply(chat_id, "❌ This link is invalid or expired.", is_master=True)
        return {"ok": False}
    
    # auth_state stores Firebase UID; donor records are keyed by donor entity_id.
    donor = store.donors.get(auth_state.donor_id)
    if donor is None:
        user = store.users.get(auth_state.donor_id)
        if user and user.entity_id:
            donor = store.donors.get(user.entity_id)
    if not donor:
        _send_telegram_reply(chat_id, "❌ Donor profile not found.", is_master=True)
        return {"ok": False}
    # Persist chat binding so bot-token submission resolves the same donor.
    store.update_auth_state(state_token, link_token=chat_id)

    reply = (
        f"🔐 *Account Link Request*\n\n"
        f"Restaurant: {donor.name}\n"
        f"Email: {donor.email}\n\n"
        "Link this Telegram account to FoodBridge?"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Yes, Link", "callback_data": f"confirm_auth_{state_token}"},
            {"text": "❌ Cancel", "callback_data": "cancel_auth"}
        ]]
    }
    _send_telegram_reply(chat_id, reply, is_master=True, reply_markup=keyboard)
    return {"ok": True}


async def _handle_master_callback(callback: Dict[str, Any]):
    data = callback.get("data", "")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id"))
    
    if data.startswith("confirm_auth_"):
        state_token = data.replace("confirm_auth_", "")
        state = store.update_auth_state(state_token, confirmed=True, used=True)
        
        reply = (
            "✅ *Account linked successfully!*\n\n"
            "Next: Set up your personal donation bot.\n"
            "This is your private channel for posting donations."
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "🤖 How to create my bot", "callback_data": "guide_slave_bot"}
            ]]
        }
        _send_telegram_reply(chat_id, reply, is_master=True, reply_markup=keyboard)
        
    elif data == "guide_slave_bot":
        reply = (
            "🤖 *Create Your Personal Bot*\n\n"
            "1. Open @BotFather\n"
            "2. Send `/newbot`\n"
            "3. Name it (e.g. 'My Restaurant Bot')\n"
            "4. Give it a username\n"
            "5. *Copy the token* and paste it here."
        )
        store.update_conversation_state(chat_id, step=ConversationStep.awaiting_bot_token)
        _send_telegram_reply(chat_id, reply, is_master=True)

    return {"ok": True}


async def _handle_master_bot_token(chat_id: str, token: str):
    if not re.match(r"^\d{8,10}:[A-Za-z0-9_-]{35}$", token):
        _send_telegram_reply(chat_id, "❌ Invalid token format. Please copy it exactly from BotFather.", is_master=True)
        return {"ok": False}
    
    # Validate with Telegram
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe").json()
        if not resp.get("ok"):
            raise Exception("Invalid token")
        
        bot_info = resp["result"]
        # Resolve donor from the authenticated chat that initiated this setup flow.
        session = next(
            (s for s in store.auth_states.values() if s.confirmed and s.link_token == chat_id),
            None,
        )
        if not session:
            raise Exception("No active session")
        donor_id = session.donor_id
        user = store.users.get(donor_id)
        if user and user.entity_id:
            donor_id = user.entity_id
        
        encrypted_token = kms_service.encrypt(token)
        slave_bot = SlaveBot(
            donor_id=donor_id,
            bot_token=encrypted_token,
            bot_username=bot_info["username"],
            bot_id=bot_info["id"]
        )
        
        # Set webhook for slave bot using configured backend public URL.
        settings = get_settings()
        if not settings.telegram_slave_webhook_base_url:
            raise Exception("Missing TELEGRAM_SLAVE_WEBHOOK_BASE_URL")
        webhook_url = f"{settings.telegram_slave_webhook_base_url.rstrip('/')}/telegram/slave/webhook"
        requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": donor_id
            }
        )
        
        store.register_slave_bot(slave_bot)
        store.clear_conversation_state(chat_id)
        
        reply = (
            f"✅ *Bot registered successfully!*\n\n"
            f"Your bot: @{bot_info['username']}\n\n"
            f"Open it and send `/start` to begin."
        )
        _send_telegram_reply(chat_id, reply, is_master=True)
        
    except Exception as e:
        _send_telegram_reply(chat_id, f"❌ Error: {str(e)}", is_master=True)

    return {"ok": True}


async def _handle_slave_donation_flow(donor_id: str, slave_bot: SlaveBot, update: Dict[str, Any]):
    callback = update.get("callback_query", {})
    callback_data = (callback.get("data") or "").strip()
    callback_chat_id = callback.get("message", {}).get("chat", {}).get("id")
    chat_id = str(update.get("message", {}).get("chat", {}).get("id") or callback_chat_id or slave_bot.slave_chat_id or "")
    if not chat_id:
        return {"ok": False}
    text = (update.get("message", {}).get("text", "") or "").strip()
    conv_state = store.get_conversation_state(chat_id)

    if text == "/donation":
        store.update_conversation_state(
            chat_id,
            step=ConversationStep.awaiting_food_type,
            food_type=None,
            quantity_kg=None,
            meal_count=None,
            donation_items=[],
        )
        _send_telegram_reply(
            chat_id,
            "What food are you donating? (e.g. Biryani, Rice, Dal)",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    if not conv_state:
        return {"ok": True}

    if conv_state and callback_data in {"slave_add_more_item", "slave_post_surplus"}:
        if callback_data == "slave_add_more_item":
            store.update_conversation_state(
                chat_id,
                step=ConversationStep.awaiting_food_type,
                food_type=None,
                quantity_kg=None,
                meal_count=None,
            )
            _send_telegram_reply(
                chat_id,
                "Great. Enter the next food item name.",
                token_encrypted=slave_bot.bot_token,
            )
            return {"ok": True}
        return _finalize_multi_item_donation(donor_id, slave_bot, chat_id, conv_state)

    if conv_state.step == ConversationStep.awaiting_food_type:
        if not text or text.startswith("/"):
            _send_telegram_reply(chat_id, "Please enter a valid food name.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        store.update_conversation_state(
            chat_id,
            step=ConversationStep.awaiting_quantity,
            food_type=text,
        )
        _send_telegram_reply(chat_id, "Enter quantity in kgs (example: 12.5)", token_encrypted=slave_bot.bot_token)
        return {"ok": True}

    if conv_state.step == ConversationStep.awaiting_quantity:
        qty_match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not qty_match:
            _send_telegram_reply(chat_id, "I need a number in kg. Example: 10", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        quantity_kg = float(qty_match.group(1))
        if quantity_kg <= 0:
            _send_telegram_reply(chat_id, "Quantity must be more than 0 kg.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        store.update_conversation_state(
            chat_id,
            step=ConversationStep.awaiting_quantity_text,
            quantity_kg=quantity_kg,
        )
        _send_telegram_reply(
            chat_id,
            "How many people can this feed? (enter a number)",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    if conv_state.step == ConversationStep.awaiting_quantity_text:
        meals_match = re.search(r"(\d+)", text)
        if not meals_match:
            _send_telegram_reply(chat_id, "Please enter meal count as a whole number.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        meal_count = int(meals_match.group(1))
        if meal_count <= 0:
            _send_telegram_reply(chat_id, "Meal count must be at least 1.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        food_type = conv_state.food_type or "mixed food"
        quantity_kg = conv_state.quantity_kg or 0
        existing_items = list(conv_state.donation_items or [])
        existing_items.append(
            DonationItem(food_type=food_type, quantity_kg=quantity_kg, meal_count=meal_count)
        )
        store.update_conversation_state(
            chat_id,
            step=ConversationStep.awaiting_more_items,
            donation_items=existing_items,
            food_type=None,
            quantity_kg=None,
            meal_count=None,
        )
        keyboard = {
            "inline_keyboard": [[
                {"text": "➕ Add more item", "callback_data": "slave_add_more_item"},
                {"text": "✅ Post surplus", "callback_data": "slave_post_surplus"},
            ]]
        }
        _send_telegram_reply(
            chat_id,
            (
                f"Added item {len(existing_items)}: {food_type} ({quantity_kg:g} kg, serves {meal_count}).\n"
                "Do you want to add more items or post the surplus now?"
            ),
            token_encrypted=slave_bot.bot_token,
            reply_markup=keyboard,
        )
        return {"ok": True}

    if conv_state.step == ConversationStep.awaiting_more_items:
        normalized = text.lower()
        if normalized in {"add", "add more", "more", "yes"}:
            store.update_conversation_state(
                chat_id,
                step=ConversationStep.awaiting_food_type,
                food_type=None,
                quantity_kg=None,
                meal_count=None,
            )
            _send_telegram_reply(chat_id, "Enter the next food item name.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        if normalized in {"post", "post now", "submit", "done", "no"}:
            return _finalize_multi_item_donation(donor_id, slave_bot, chat_id, conv_state)
        _send_telegram_reply(
            chat_id,
            "Please choose: 'Add more item' or 'Post surplus'.",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    return {"ok": True}


def _finalize_multi_item_donation(donor_id: str, slave_bot: SlaveBot, chat_id: str, conv_state: ConversationState):
    items = list(conv_state.donation_items or [])
    if not items:
        _send_telegram_reply(chat_id, "No items captured yet. Use /donation to start.", token_encrypted=slave_bot.bot_token)
        store.clear_conversation_state(chat_id)
        return {"ok": True}

    total_qty = round(sum(item.quantity_kg for item in items), 2)
    total_meals = int(sum(item.meal_count for item in items))
    primary_food = items[0].food_type
    donation = store.create_donation(
        DonationCreate(
            donor_id=donor_id,
            food_type=primary_food,
            quantity_kg=total_qty,
            meal_count=total_meals,
            items=items,
            source="telegram",
            telegram_chat_id=chat_id,
            notes=f"Posted from Telegram bot chat {chat_id}",
        )
    )
    store.clear_conversation_state(chat_id)

    top_ngo_name = "nearest NGO"
    maps_link = "https://maps.google.com"
    if donation.ngo_queue:
        top = donation.ngo_queue[0]
        top_ngo_name = top.ngo_name
        donor = store.donors.get(donor_id)
        ngo = store.ngos.get(top.ngo_id)
        if donor and ngo:
            maps_link = (
                f"https://www.google.com/maps/dir/?api=1&origin={donor.location.lat},{donor.location.lng}"
                f"&destination={ngo.location.lat},{ngo.location.lng}&travelmode=driving"
            )

    item_lines = "\n".join([f"{idx + 1}. {item.food_type} - {item.quantity_kg:g} kg, serves {item.meal_count}" for idx, item in enumerate(items)])
    _send_telegram_reply(
        chat_id,
        (
            f"Donation request has been sent to {top_ngo_name}.\n"
            f"Items:\n{item_lines}\n"
            f"Total Quantity: {donation.quantity_kg:g} kg\n"
            f"Total Serves: {donation.meal_count}\n"
            f"Pickup timer: {logical_minutes_from_timedelta((donation.expires_at - datetime.now(timezone.utc)).total_seconds())} min\n"
            f"Track route: {maps_link}"
        ),
        token_encrypted=slave_bot.bot_token,
    )
    return {"ok": True}


async def _handle_slave_photo(donor_id: str, slave_bot: SlaveBot, update: Dict[str, Any]):
    # Process donation creation logic
    return {"ok": True}


async def _handle_slave_track(donor_id: str, slave_bot: SlaveBot, chat_id: str):
    active_statuses = {
        "notified",
        "accepted",
        "assigned",
        "pending_match",
        "needs_review",
        "escalated_radius_2",
        "escalated_radius_3",
    }
    donations = [
        item
        for item in store.donations.values()
        if item.donor_id == donor_id and item.status.value in active_statuses
    ]
    donations = sorted(donations, key=lambda item: item.created_at, reverse=True)[:5]

    if not donations:
        _send_telegram_reply(
            chat_id,
            "No active donations right now. Use /donation to create one.",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    lines = ["Your active donations:"]
    now = datetime.now(timezone.utc)
    for item in donations:
        remaining_min = logical_minutes_from_timedelta((item.expires_at - now).total_seconds())
        ngo_name = item.assigned_ngo_name or (item.ngo_queue[0].ngo_name if item.ngo_queue else "Matching...")
        lines.append(
            f"- {item.food_type} ({item.quantity_kg:g} kg) | {item.status.value.upper()} | NGO: {ngo_name} | Timer: {remaining_min} min"
        )

    _send_telegram_reply(chat_id, "\n".join(lines), token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_reports(donor_id: str, slave_bot: SlaveBot, chat_id: str):
    generated = list_donor_fssai_certificates(donor_id)
    generated_by_donation = {item.get("donation_id") for item in generated}
    pending = []
    for donation in store.donations.values():
        if donation.donor_id != donor_id:
            continue
        is_completed = (
            donation.status.value == "completed"
            or donation.completed_at
            or donation.delivery_confirmed_at
            or (donation.volunteer_task_status and donation.volunteer_task_status.value == "delivered_confirmed")
        )
        if is_completed and donation.id not in generated_by_donation:
            pending.append(donation)
    pending.sort(key=lambda x: x.updated_at, reverse=True)

    lines = ["FSSAI Certificate Report List"]
    lines.append("")
    lines.append("Generated:")
    if not generated:
        lines.append("- None")
    else:
        for item in generated[:10]:
            ts = item.get("generated_at", "")
            lines.append(f"- {item.get('certificate_uid')} | {ts}")
    lines.append("")
    lines.append("Pending:")
    if not pending:
        lines.append("- None")
    else:
        for item in pending[:10]:
            uid_preview = build_certificate_uid(item.id)
            lines.append(f"- {item.id} (suggested UID: {uid_preview})")
    _send_telegram_reply(chat_id, "\n".join(lines), token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_generate(donor_id: str, slave_bot: SlaveBot, chat_id: str, text: str):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        _send_telegram_reply(
            chat_id,
            (
                "Usage:\n"
                "/generate <UID|donation_id>\n"
                "/generate preview <UID|donation_id>\n"
                "Example: /generate don_abc123_080526"
            ),
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}

    raw = parts[1].strip()
    preview_only = False
    if raw.lower().startswith("preview "):
        preview_only = True
        token = raw[8:].strip()
    elif raw.lower() == "preview":
        _send_telegram_reply(
            chat_id,
            "Usage: /generate preview <UID|donation_id>",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}
    else:
        token = raw
    donation_id = token
    uid_override = None
    if "_" in token and re.search(r"_\d{6}$", token):
        uid_override = token
        donation_id = token.rsplit("_", 1)[0]

    donation = store.donations.get(donation_id)
    if not donation or donation.donor_id != donor_id:
        _send_telegram_reply(chat_id, "Donation not found for this account.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}

    try:
        if preview_only:
            preview_meta = generate_fssai_certificate_preview(
                donation_id=donation_id,
                requested_by=donor_id,
                requested_via="telegram_preview",
                uid_override=uid_override,
            )
            preview_url = preview_meta.get("signed_url")
            if not preview_url:
                _send_telegram_reply(chat_id, "Preview created but URL is missing.", token_encrypted=slave_bot.bot_token)
                return {"ok": True}
            preview_resp = requests.get(preview_url, timeout=20)
            if preview_resp.status_code >= 400:
                _send_telegram_reply(chat_id, f"Preview generated but download failed ({preview_resp.status_code}).", token_encrypted=slave_bot.bot_token)
                return {"ok": True}
            _send_telegram_document(
                chat_id=chat_id,
                filename=f"{preview_meta['certificate_uid']}_preview.pdf",
                document_bytes=preview_resp.content,
                caption=f"Sample FSSAI preview: {preview_meta['certificate_uid']} | Generated at: {preview_meta['generated_at']}",
                token_encrypted=slave_bot.bot_token,
            )
            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": "Approve & Regenerate",
                        "callback_data": f"slave_preview_approve|{donation_id}|{preview_meta['certificate_uid']}",
                    },
                    {
                        "text": "Discard",
                        "callback_data": f"slave_preview_discard|{donation_id}|{preview_meta['certificate_uid']}",
                    },
                ]]
            }
            _send_telegram_reply(
                chat_id,
                "Review the sample PDF. Approve to regenerate final certificate, or discard.",
                token_encrypted=slave_bot.bot_token,
                reply_markup=keyboard,
            )
            return {"ok": True}

        certificate_uid = uid_override or build_certificate_uid(donation_id)
        meta = get_certificate_meta(certificate_uid)
        if meta is None:
            meta = ensure_fssai_certificate(
                donation_id=donation_id,
                requested_by=donor_id,
                requested_via="telegram",
                uid_override=uid_override,
            )
        else:
            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": "Yes, regenerate",
                        "callback_data": f"slave_regen_confirm|{donation_id}|{meta['certificate_uid']}",
                    },
                    {
                        "text": "No, keep existing",
                        "callback_data": f"slave_regen_cancel|{donation_id}|{meta['certificate_uid']}",
                    },
                ]]
            }
            _send_telegram_reply(
                chat_id,
                (
                    "If regenerated, the previous certificate will be deleted.\n"
                    "The date and time of delivery will remain the same; only certificate generation timestamp will change.\n"
                    "Are you sure you want to proceed?"
                ),
                token_encrypted=slave_bot.bot_token,
                reply_markup=keyboard,
            )
            return {"ok": True}

        payload = get_certificate_pdf_bytes(meta["certificate_uid"])
        if payload is None:
            _send_telegram_reply(chat_id, "Certificate metadata exists but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"FSSAI certificate: {meta['certificate_uid']} | Generated at: {meta['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to generate certificate: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_csr_reports(donor_id: str, slave_bot: SlaveBot, chat_id: str):
    reports = list_donor_csr_reports(donor_id)
    lines = ["CSR Report List", ""]
    if not reports:
        lines.append("- None generated yet")
    else:
        for item in reports[:10]:
            lines.append(f"- {item.get('report_id')} | {item.get('generated_at', '')}")
    _send_telegram_reply(chat_id, "\n".join(lines), token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_csr_generate(donor_id: str, slave_bot: SlaveBot, chat_id: str, text: str):
    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    preview_only = False
    if token.lower().startswith("preview "):
        preview_only = True
        token = token[8:].strip()
    elif token.lower() == "preview":
        _send_telegram_reply(
            chat_id,
            "Usage: /csrgenerate preview <report_id|latest>",
            token_encrypted=slave_bot.bot_token,
        )
        return {"ok": True}
    report_id = token if token and token.lower() not in {"latest", "new"} else None
    try:
        if preview_only:
            result = generate_csr_report_preview_for_donor(
                donor_id=donor_id,
                requested_by=donor_id,
                requested_via="telegram_preview",
                report_id_override=report_id,
            )
            preview_url = result.get("signed_url")
            if not preview_url:
                _send_telegram_reply(chat_id, "CSR preview created but URL is missing.", token_encrypted=slave_bot.bot_token)
                return {"ok": True}
            preview_resp = requests.get(preview_url, timeout=20)
            if preview_resp.status_code >= 400:
                _send_telegram_reply(chat_id, f"CSR preview generated but download failed ({preview_resp.status_code}).", token_encrypted=slave_bot.bot_token)
                return {"ok": True}
            _send_telegram_document(
                chat_id=chat_id,
                filename=f"{result['report_id']}_preview.pdf",
                document_bytes=preview_resp.content,
                caption=f"Sample CSR preview: {result['report_id']} | Generated at: {result['generated_at']}",
                token_encrypted=slave_bot.bot_token,
            )
            keyboard = {
                "inline_keyboard": [[
                    {"text": "Approve & Regenerate", "callback_data": f"slave_csr_preview_approve|{result['report_id']}"},
                    {"text": "Discard", "callback_data": f"slave_csr_preview_discard|{result['report_id']}"},
                ]]
            }
            _send_telegram_reply(
                chat_id,
                "Review the sample CSR PDF. Approve to regenerate final report, or discard.",
                token_encrypted=slave_bot.bot_token,
                reply_markup=keyboard,
            )
            return {"ok": True}

        if report_id:
            existing = list_donor_csr_reports(donor_id)
            report = next((r for r in existing if r.get("report_id") == report_id), None)
            if report:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "Yes, regenerate", "callback_data": f"slave_csr_regen_confirm|{report_id}"},
                        {"text": "No, keep existing", "callback_data": f"slave_csr_regen_cancel|{report_id}"},
                    ]]
                }
                _send_telegram_reply(
                    chat_id,
                    (
                        "If regenerated, the previous CSR report will be deleted.\n"
                        "Impact period data remains the same; only report generation timestamp changes.\n"
                        "Are you sure you want to proceed?"
                    ),
                    token_encrypted=slave_bot.bot_token,
                    reply_markup=keyboard,
                )
                return {"ok": True}

        result = generate_csr_report_for_donor(
            donor_id=donor_id,
            requested_by=donor_id,
            requested_via="telegram",
            force=False,
            report_id_override=report_id,
        )
        payload = get_csr_pdf_bytes(result["report_id"])
        if payload is None:
            _send_telegram_reply(chat_id, "CSR metadata exists but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"CSR report: {result['report_id']} | Generated at: {result['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to generate CSR report: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_regenerate_callback(
    donor_id: str,
    slave_bot: SlaveBot,
    chat_id: str,
    callback_data: str,
):
    if not chat_id:
        return {"ok": False}
    parts = callback_data.split("|")
    if len(parts) != 3:
        return {"ok": True}
    action, donation_id, certificate_uid = parts
    donation = store.donations.get(donation_id)
    if not donation or donation.donor_id != donor_id:
        _send_telegram_reply(chat_id, "Donation not found for this account.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    if action == "slave_regen_cancel":
        _send_telegram_reply(chat_id, "Regeneration cancelled. Keeping existing certificate.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    try:
        meta = ensure_fssai_certificate(
            donation_id=donation_id,
            requested_by=donor_id,
            requested_via="telegram",
            force=True,
            uid_override=certificate_uid,
        )
        payload = get_certificate_pdf_bytes(meta["certificate_uid"])
        if payload is None:
            _send_telegram_reply(chat_id, "Certificate regenerated but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"Regenerated FSSAI certificate: {meta['certificate_uid']} | Generated at: {meta['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to regenerate certificate: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_csr_regenerate_callback(
    donor_id: str,
    slave_bot: SlaveBot,
    chat_id: str,
    callback_data: str,
):
    if not chat_id:
        return {"ok": False}
    parts = callback_data.split("|")
    if len(parts) != 2:
        return {"ok": True}
    action, report_id = parts
    existing = list_donor_csr_reports(donor_id)
    report = next((r for r in existing if r.get("report_id") == report_id), None)
    if not report:
        _send_telegram_reply(chat_id, "CSR report not found for this donor.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    if action == "slave_csr_regen_cancel":
        _send_telegram_reply(chat_id, "CSR regeneration cancelled. Keeping existing report.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    try:
        result = generate_csr_report_for_donor(
            donor_id=donor_id,
            requested_by=donor_id,
            requested_via="telegram",
            force=True,
            report_id_override=report_id,
        )
        payload = get_csr_pdf_bytes(result["report_id"])
        if payload is None:
            _send_telegram_reply(chat_id, "CSR report regenerated but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"Regenerated CSR report: {result['report_id']} | Generated at: {result['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to regenerate CSR report: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_preview_callback(
    donor_id: str,
    slave_bot: SlaveBot,
    chat_id: str,
    callback_data: str,
):
    if not chat_id:
        return {"ok": False}
    parts = callback_data.split("|")
    if len(parts) != 3:
        return {"ok": True}
    action, donation_id, certificate_uid = parts
    donation = store.donations.get(donation_id)
    if not donation or donation.donor_id != donor_id:
        _send_telegram_reply(chat_id, "Donation not found for this account.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    if action == "slave_preview_discard":
        _send_telegram_reply(chat_id, "Preview discarded. No regeneration was performed.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    try:
        meta = ensure_fssai_certificate(
            donation_id=donation_id,
            requested_by=donor_id,
            requested_via="telegram",
            force=True,
            uid_override=certificate_uid,
        )
        payload = get_certificate_pdf_bytes(meta["certificate_uid"])
        if payload is None:
            _send_telegram_reply(chat_id, "Certificate regenerated but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"Regenerated FSSAI certificate: {meta['certificate_uid']} | Generated at: {meta['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to regenerate from preview: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


async def _handle_slave_csr_preview_callback(
    donor_id: str,
    slave_bot: SlaveBot,
    chat_id: str,
    callback_data: str,
):
    if not chat_id:
        return {"ok": False}
    parts = callback_data.split("|")
    if len(parts) != 2:
        return {"ok": True}
    action, report_id = parts
    if action == "slave_csr_preview_discard":
        _send_telegram_reply(chat_id, "CSR preview discarded. No regeneration was performed.", token_encrypted=slave_bot.bot_token)
        return {"ok": True}
    try:
        result = generate_csr_report_for_donor(
            donor_id=donor_id,
            requested_by=donor_id,
            requested_via="telegram",
            force=True,
            report_id_override=report_id,
        )
        payload = get_csr_pdf_bytes(result["report_id"])
        if payload is None:
            _send_telegram_reply(chat_id, "CSR report regenerated but file is missing.", token_encrypted=slave_bot.bot_token)
            return {"ok": True}
        pdf_bytes, filename = payload
        _send_telegram_document(
            chat_id=chat_id,
            filename=filename,
            document_bytes=pdf_bytes,
            caption=f"Regenerated CSR report: {result['report_id']} | Generated at: {result['generated_at']}",
            token_encrypted=slave_bot.bot_token,
        )
    except Exception as exc:
        _send_telegram_reply(chat_id, f"Failed to regenerate CSR from preview: {exc}", token_encrypted=slave_bot.bot_token)
    return {"ok": True}


def _send_telegram_reply(
    chat_id: str, 
    text: str, 
    is_master: bool = False, 
    token_encrypted: str = None,
    reply_markup: dict = None,
    parse_mode: str = None
) -> None:
    settings = get_settings()
    
    if is_master:
        token = settings.telegram_bot_token
    elif token_encrypted:
        token = kms_service.decrypt(token_encrypted)
    else:
        return

    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
        
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=8)
        if response.status_code >= 400:
            print(f"Telegram sendMessage HTTP {response.status_code}: {response.text}")
            return
        parsed = response.json()
        if not parsed.get("ok", False):
            print(f"Telegram sendMessage API error: {parsed}")
    except Exception as e:
        print(f"Telegram error: {e}")


def _send_telegram_document(
    chat_id: str,
    filename: str,
    document_bytes: bytes,
    caption: str,
    token_encrypted: str,
) -> None:
    token = kms_service.decrypt(token_encrypted)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, document_bytes, "application/pdf")},
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Telegram sendDocument HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Telegram document error: {e}")
