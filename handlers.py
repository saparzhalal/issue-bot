from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ai_helper import get_description_keyboard
from config import ICT_GROUP_ID, MAINTENANCE_GROUP_ID
from database import (
    create_ticket,
    get_ticket,
    assign_ticket,
    update_ticket_status,
    get_ticket_history,
    get_tickets_by_status,
)
from keyboards import (
    main_menu_keyboard,
    item_keyboard,
    location_keyboard,
    status_keyboard,
    stats_keyboard,
)


# ─── Constants ────────────────────────────────────────────────────────────────

ICT_KEYWORDS = [
    "tv", "computer", "projector", "printer", "wifi", "wi-fi", "internet",
    "monitor", "keyboard", "mouse", "laptop", "pc", "screen", "camera",
    "speaker", "microphone", "router", "network",
]

MAINTENANCE_KEYWORDS = [
    "chair", "door", "light", "lamp", "air conditioner", "ac", "window",
    "desk", "table", "fan", "sink", "toilet", "wall", "floor", "ceiling",
    "lock", "handle", "water", "electric", "plug", "socket",
]

# Maps callback_data → display status string
STATUS_MAP = {
    "show_new":      "New",
    "show_progress": "In Progress",
    "show_fixed":    "Fixed",
    "show_rejected": "Rejected",
}

# Maps status_<key>_<id> callback key → display status string
STATUS_TEXT_MAP = {
    "progress": "In Progress",
    "fixed":    "Fixed",
    "rejected": "Rejected",
}

# Notification messages sent to the reporter
NOTIFY_TEXT = {
    "In Progress": "🟡 Your request is now IN PROGRESS.",
    "Fixed":       "✅ Your request has been FIXED.",
    "Rejected":    "❌ Your request was REJECTED.",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_team_for_item(item: str) -> tuple[str, int]:
    """Return (team_name, group_id) based on the item's keywords."""
    item_lower = item.lower()
    for keyword in ICT_KEYWORDS:
        if keyword in item_lower:
            return "ICT Team", ICT_GROUP_ID
    for keyword in MAINTENANCE_KEYWORDS:
        if keyword in item_lower:
            return "Maintenance Team", MAINTENANCE_GROUP_ID
    return "Maintenance Team", MAINTENANCE_GROUP_ID






def get_stats_message() -> str:
    statuses = ["New", "In Progress", "Fixed", "Rejected"]
    counts = {s: len(get_tickets_by_status(s)) for s in statuses}
    total = sum(counts.values())
    return (
        "📊 Current Issue Report\n\n"
        f"Total Issues: {total}\n\n"
        f"🆕 New: {counts['New']}\n"
        f"🔄 In Progress: {counts['In Progress']}\n"
        f"✅ Fixed: {counts['Fixed']}\n"
        f"❌ Rejected: {counts['Rejected']}"
    )


def build_full_ticket_caption(ticket: dict) -> str:
    status_history = get_ticket_history(ticket["id"])

    history_text = ""

    if status_history:
        for row in status_history:
            history_text += (
                f"\n- {row['new_status']} by {row['updated_by']}"
            )

            if row["notes"]:
                history_text += f"\n  Notes: {row['notes']}"
    else:
        history_text = "\nNo updates yet."

    return (
        f"📄 Ticket #{ticket['id']}\n\n"
        f"🔧 Item: {ticket['item_name']}\n"
        f"📍 Location: {ticket['location']}\n"
        f"📝 Description: {ticket['issue_description']}\n"
        f"👷 Assigned to: {ticket['assigned_to'] or 'Not assigned yet'}\n"
        f"📌 Status: {ticket['status']}\n"
        f"👤 Reported by: {ticket['requester_name']}\n"
        f"🕒 Created at: {ticket['created_at']}\n"
        f"🧾 Final Diagnosis: {ticket['final_diagnosis'] or 'Not added yet'}\n\n"
        f"📜 Status History:{history_text}"
    )


def update_caption_field(caption: str, updates: dict[str, str]) -> str:
    """
    Replace specific labeled lines in a caption string.
    updates = { "📌 Status:": "Fixed", "👷 Last updated by:": "Ali" }
    Lines not found are appended at the end.
    """
    lines = caption.split("\n")
    new_lines = []
    found = {key: False for key in updates}

    for line in lines:
        replaced = False
        for prefix, value in updates.items():
            if line.startswith(prefix):
                new_lines.append(f"{prefix} {value}")
                found[prefix] = True
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    # Append any fields that weren't found in the existing caption
    for prefix, value in updates.items():
        if not found[prefix]:
            new_lines.append(f"{prefix} {value}")

    return "\n".join(new_lines)


async def notify_reporter(context, reporter_user_id: int | None, text: str) -> None:
    """Silently send a status notification to the original reporter."""
    if not reporter_user_id:
        return
    try:
        await context.bot.send_message(chat_id=reporter_user_id, text=text)
    except Exception as e:
        print(f"[NOTIFY] Could not notify user {reporter_user_id}: {e}")


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome to Company Issue Reporter Bot\n\nPlease click below to report an issue.",
        reply_markup=main_menu_keyboard(),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        get_stats_message(),
        reply_markup=stats_keyboard(),
    )


async def issue_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /issue <id>   Example: /issue 3")
        return
    try:
        issue_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Issue ID must be a number.  Example: /issue 3")
        return

    issue = get_ticket(issue_id)
    if issue is None:
        await update.message.reply_text(f"Issue #{issue_id} not found.")
        return

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=issue["photo_file_id"],
        caption=build_full_ticket_caption(issue),
    )


# ─── Button Handler ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Show issues by status list ──────────────────────────────────────────
    if data in STATUS_MAP:
        status = STATUS_MAP[data]
        issues = get_tickets_by_status(status)

        try:
            issues = sorted(issues, key=lambda x: x[9], reverse=True)[:20]
        except Exception:
            issues = issues[:20]

        if not issues:
            await query.message.reply_text(f"No {status} issues found.")
            return

        buttons = []
        for issue in issues:
            issue_id = issue.get("id") if isinstance(issue, dict) else issue[0]
            if issue_id:
                buttons.append([
                    InlineKeyboardButton(f"#{issue_id}", callback_data=f"view_issue_{issue_id}")
                ])

        if not buttons:
            await query.message.reply_text(f"⚠️ No valid issues found for '{status}'.")
            return

        await query.message.reply_text(
            f"📋 {status} Issues — tap one to view details:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # ── View single issue detail ────────────────────────────────────────────
    if data.startswith("view_issue_"):
        issue_id = int(data.replace("view_issue_", ""))
        issue = get_ticket(issue_id)
        if issue is None:
            await query.message.reply_text(f"Issue #{issue_id} not found.")
            return
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=issue["photo_file_id"],
                caption=build_full_ticket_caption(issue),
            )
        except Exception as e:
            print(f"[VIEW PHOTO] {e}")
            await query.message.reply_text(build_full_ticket_caption(issue))
        return

    # ── Start report flow ───────────────────────────────────────────────────
    if data == "report_problem":
        context.user_data.clear()
        await query.edit_message_text(
            "🔧 What item has a problem?",
            reply_markup=item_keyboard(),
        )
        return

    # ── Select item ─────────────────────────────────────────────────────────
    if data.startswith("item_"):
        ITEM_MAP = {
            "item_tv":       "TV",
            "item_chair":    "Chair",
            "item_door":     "Door",
            "item_computer": "Computer",
            "item_light":    "Light",
        }
        if data == "item_other":
            context.user_data["step"] = "waiting_item"
            await query.edit_message_text("✍️ Please type the item name.")
            return
        item = ITEM_MAP.get(data)
        if item:
            context.user_data.update({"item": item, "step": "waiting_location"})
            await query.edit_message_text(
                "📍 Where is it? Choose a floor or select Other.",
                reply_markup=location_keyboard(),
            )
        return

    # ── Select floor / location ─────────────────────────────────────────────
    if data.startswith("loc_"):
        if not context.user_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start.")
            return
        if data == "loc_other":
            context.user_data["step"] = "waiting_location"
            await query.edit_message_text("📍 Please type the exact location.")
            return
        floor = data.replace("loc_", "")
        context.user_data.update({"floor": floor, "step": "waiting_room"})
        await query.edit_message_text(
            f"📍 Floor: {floor}\n\nNow type the room or area.\nExample: Room 305, Lab 2, Library"
        )
        return

    # ── Select description ──────────────────────────────────────────────────
    if data.startswith("desc_"):
        if not context.user_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start.")
            return
        if data == "desc_other":
            context.user_data["step"] = "waiting_description"
            await query.edit_message_text("📝 Please type the problem description.")
            return
        description = data.replace("desc_", "")
        context.user_data.update({"description": description, "step": "waiting_photo"})
        await query.edit_message_text("📸 Now send a photo of the broken item.")
        return

    # ── Assign technician ───────────────────────────────────────────────────
    if data.startswith("assign_"):
        issue_id = int(data.replace("assign_", ""))
        context.user_data.update({
            "step":       "waiting_assignment_name",
            "issue_id":   issue_id,
            "chat_id":    query.message.chat_id,
            "message_id": query.message.message_id,
            "caption":    query.message.caption or "",
        })
        await query.message.reply_text(f"👷 Type the technician name for Issue #{issue_id}.")
        return

    # ── Update status ───────────────────────────────────────────────────────
    if data.startswith("status_"):
        # callback format: status_<key>_<issue_id>
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("Invalid status data.", show_alert=True)
            return

        status_key = parts[1]
        try:
            issue_id = int(parts[2])
        except ValueError:
            await query.answer("Invalid issue ID.", show_alert=True)
            return

        status_text = STATUS_TEXT_MAP.get(status_key)
        if not status_text:
            await query.answer("Unknown status.", show_alert=True)
            return

        # Rejected requires a typed reason — defer to handle_message
        if status_text == "Rejected":
            context.user_data.update({
                "step":       "waiting_reject_reason",
                "issue_id":   issue_id,
                "chat_id":    query.message.chat_id,
                "message_id": query.message.message_id,
                "caption":    query.message.caption or "",
            })
            await query.message.reply_text(f"❌ Type the rejection reason for Issue #{issue_id}.")
            return

        changed_by = query.from_user.first_name
        update_ticket_status(issue_id, status_text, changed_by)

        issue = get_ticket(issue_id)
        if issue:
            notify_msg = NOTIFY_TEXT.get(status_text, f"ℹ️ Your request status changed to {status_text}.")
            await notify_reporter(context, issue["requester_id"], notify_msg)

        new_caption = update_caption_field(
            query.message.caption or "",
            {
                "📌 Status:":          status_text,
                "👷 Last updated by:": changed_by,
            },
        )

        try:
            await query.edit_message_caption(
                caption=new_caption,
                reply_markup=status_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[STATUS CAPTION] {e}")
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"⚠️ Status updated to {status_text}, but the message could not be edited.",
            )

        await query.answer(f"Issue #{issue_id} → {status_text} by {changed_by}")
        return

    # ── Fallback ────────────────────────────────────────────────────────────
    await query.answer("Unknown action.", show_alert=True)


# ─── Message Handler ──────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    step = context.user_data.get("step")

    # Start command (text alias)
    if text.lower() in {"/start", "start"}:
        await start(update, context)
        return

    # Admin stats shortcut
    if text.lower() == "aliadmin":
        await stats(update, context)
        return

    # Issue lookup by number or #number
    clean = text.lstrip("#")
    if clean.isdigit():
        issue_id = int(clean)
        issue = get_ticket(issue_id)
        if issue is None:
            await update.message.reply_text(f"Issue #{issue_id} not found.")
            return
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=issue["photo_file_id"],
                caption=build_full_ticket_caption(issue),
            )
        except Exception as e:
            print(f"[LOOKUP PHOTO] {e}")
            await update.message.reply_text(build_full_ticket_caption(issue))
        return

    # ── Report flow steps ──────────────────────────────────────────────────

    if step == "waiting_item":
        context.user_data.update({"item": text, "step": "waiting_location"})
        await update.message.reply_text(
            "📍 Where is it? Choose a floor or select Other.",
            reply_markup=location_keyboard(),
        )
        return

    if step == "waiting_room":
        floor = context.user_data.get("floor", "")
        context.user_data.update({
            "location": f"{floor} - {text}",
            "step": "waiting_description",
        })
        await update.message.reply_text(
            "📝 What is the problem? Choose one or select Other.",
            reply_markup=get_description_keyboard(context.user_data["item"]),
        )
        return

    if step == "waiting_location":
        context.user_data.update({"location": text, "step": "waiting_description"})
        await update.message.reply_text(
            "📝 What is the problem? Choose one or select Other.",
            reply_markup=get_description_keyboard(context.user_data["item"]),
        )
        return

    if step == "waiting_description":
        context.user_data.update({"description": text, "step": "waiting_photo"})
        await update.message.reply_text("📸 Now send a photo of the broken item.")
        return

    if step == "waiting_photo":
        # User sent text instead of a photo
        await update.message.reply_text("📸 Please send a *photo*, not text.", parse_mode="Markdown")
        return

    # ── Admin / technician flow steps ──────────────────────────────────────

    if step == "waiting_reject_reason":
        issue_id  = context.user_data["issue_id"]
        reason    = text
        changed_by = update.effective_user.first_name

        update_ticket_status(issue_id, "Rejected", changed_by, reason)

        issue = get_ticket(issue_id)
        if issue:
            await notify_reporter(
                context,
                issue["requester_id"],
                f"❌ Your request was REJECTED\nReason: {reason}",
            )

        new_caption = update_caption_field(
            context.user_data.get("caption", ""),
            {
                "📌 Status:":           "Rejected",
                "👷 Last updated by:":  changed_by,
                "❌ Rejection reason:": reason,
            },
        )

        try:
            await context.bot.edit_message_caption(
                chat_id=context.user_data["chat_id"],
                message_id=context.user_data["message_id"],
                caption=new_caption,
                reply_markup=status_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[REJECT CAPTION] {e}")
            await context.bot.send_message(
                chat_id=context.user_data["chat_id"],
                text="⚠️ Issue rejected, but the group message could not be updated.",
            )

        await update.message.reply_text(
            f"✅ Issue #{issue_id} rejected by {changed_by}.\nReason: {reason}"
        )
        context.user_data.clear()
        return

    if step == "waiting_assignment_name":
        issue_id = context.user_data["issue_id"]
        assign_ticket(issue_id, text)

        new_caption = update_caption_field(
            context.user_data.get("caption", ""),
            {"👷 Assigned to:": text},
        )

        try:
            await context.bot.edit_message_caption(
                chat_id=context.user_data["chat_id"],
                message_id=context.user_data["message_id"],
                caption=new_caption,
                reply_markup=status_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[ASSIGN CAPTION] {e}")

        await update.message.reply_text(f"✅ Issue #{issue_id} assigned to {text}.")
        context.user_data.clear()
        return

    # Default fallback
    await update.message.reply_text("Please type /start to begin reporting an issue.")


# ─── Photo Handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("step") != "waiting_photo":
        await update.message.reply_text(
            "Please complete all steps first.\nType /start to begin."
        )
        return

    data        = context.user_data
    user_id     = update.effective_user.id
    reported_by = update.effective_user.first_name
    photo_file_id = update.message.photo[-1].file_id
    description   = data.get("description", "No description")

    team_name, group_id = get_team_for_item(data["item"])

    issue_id = create_ticket(
        category=team_name,
        item_name=data["item"],
        location=data["location"],
        photo_file_id=photo_file_id,
        requester_name=reported_by,
        requester_id=user_id,
        issue_description=description,
    )

    caption = (
        f"🆕 Issue #{issue_id}\n\n"
        f"🔧 Item: {data['item']}\n"
        f"📍 Location: {data['location']}\n"
        f"📝 Description: {description}\n"
        f"👷 Assigned to: Not assigned yet\n"
        f"👥 Team: {team_name}\n"
        f"👤 Reported by: {reported_by}\n"
        f"📌 Status: New\n"
    )

    try:
        await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=status_keyboard(issue_id),
        )
    except Exception as e:
        print(f"[GROUP SEND] Failed to post Issue #{issue_id} to group {group_id}: {e}")

    await update.message.reply_text(
        f"✅ Report submitted!\n\n"
        f"Issue ID: #{issue_id}\n"
        f"Item: {data['item']}\n"
        f"Location: {data['location']}\n"
        f"Team: {team_name}\n"
        f"Photo: ✅ Received"
    )

    context.user_data.clear()