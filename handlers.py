from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ai_helper import get_description_keyboard
from config import ICT_GROUP_ID, MAINTENANCE_GROUP_ID
from database import (
    save_issue,
    get_issue_by_id,
    assign_issue,
    update_issue_status,
    get_status_history,
    get_issues_by_status,
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

STATUS_MAP = {
    "show_new":      "New",
    "show_progress": "In Progress",
    "show_fixed":    "Fixed",
    "show_rejected": "Rejected",
}

STATUS_TEXT_MAP = {
    "progress": "In Progress",
    "fixed":    "Fixed",
    "rejected": "Rejected",
}

NOTIFY_TEXT = {
    "In Progress": "🟡 Your request is now IN PROGRESS.",
    "Fixed":       "✅ Your request has been FIXED.",
    "Rejected":    "❌ Your request was REJECTED.",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_team_for_item(item: str) -> tuple[str, int]:
    item_lower = item.lower()
    for keyword in ICT_KEYWORDS:
        if keyword in item_lower:
            return "ICT Team", ICT_GROUP_ID
    for keyword in MAINTENANCE_KEYWORDS:
        if keyword in item_lower:
            return "Maintenance Team", MAINTENANCE_GROUP_ID
    return "Maintenance Team", MAINTENANCE_GROUP_ID


def get_location_keyboard() -> InlineKeyboardMarkup:
    floors = ["1st Floor", "2nd Floor", "3rd Floor", "4th Floor", "5th Floor"]
    buttons = [[InlineKeyboardButton(f, callback_data=f"loc_{f}")] for f in floors]
    buttons.append([InlineKeyboardButton("📌 Other", callback_data="loc_other")])
    return InlineKeyboardMarkup(buttons)


def get_issue_action_keyboard(issue_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 In Progress", callback_data=f"status_progress_{issue_id}"),
            InlineKeyboardButton("✅ Fixed",        callback_data=f"status_fixed_{issue_id}"),
        ],
        [InlineKeyboardButton("❌ Rejected",          callback_data=f"status_rejected_{issue_id}")],
        [InlineKeyboardButton("👷 Assign Technician", callback_data=f"assign_{issue_id}")],
    ])


def get_stats_message() -> str:
    statuses = ["New", "In Progress", "Fixed", "Rejected"]
    counts = {s: len(get_issues_by_status(s)) for s in statuses}
    total = sum(counts.values())
    return (
        "📊 Current Issue Report\n\n"
        f"Total Issues: {total}\n\n"
        f"🆕 New: {counts['New']}\n"
        f"🔄 In Progress: {counts['In Progress']}\n"
        f"✅ Fixed: {counts['Fixed']}\n"
        f"❌ Rejected: {counts['Rejected']}"
    )


def build_full_issue_caption(issue: tuple) -> str:
    (issue_id, item, location, photo_file_id, team,
     status, reported_by, description, assigned_to,
     created_at, reporter_user_id) = issue

    description = description or "No description"
    assigned_to = assigned_to or "Not assigned yet"
    status_history = get_status_history(issue_id)

    return (
        f"📄 Issue #{issue_id}\n\n"
        f"🔧 Item: {item}\n"
        f"📍 Location: {location}\n"
        f"📝 Description: {description}\n"
        f"👷 Assigned to: {assigned_to}\n"
        f"👥 Team: {team}\n"
        f"📌 Status: {status}\n"
        f"👤 Reported by: {reported_by}\n"
        f"🕒 Created at: {created_at}\n\n"
        f"📜 Status History:\n{status_history}"
    )


def build_group_caption(issue_id, item, location, description, team, reported_by) -> str:
    """
    Short caption for group messages — well under Telegram's 1024-char
    photo caption limit so status/assign edits always succeed.
    """
    return (
        f"🆕 Issue #{issue_id}\n"
        f"🔧 Item: {item}\n"
        f"📍 Location: {location}\n"
        f"📝 Description: {description}\n"
        f"👥 Team: {team}\n"
        f"👤 Reported by: {reported_by}\n"
        f"📌 Status: New\n"
        f"👷 Assigned to: Not assigned yet\n"
        f"👷 Last updated by: —\n"
    )


def update_caption_field(caption: str, updates: dict[str, str]) -> str:
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

    for prefix, value in updates.items():
        if not found[prefix]:
            new_lines.append(f"{prefix} {value}")

    return "\n".join(new_lines)


async def notify_reporter(context, reporter_user_id, text: str) -> None:
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
        "👋 Welcome to Company Issue Reporter Bot\n\nClick below to report a problem.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Report Problem", callback_data="report_problem")]
        ]),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        get_stats_message(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 Show New",         callback_data="show_new")],
            [InlineKeyboardButton("🔄 Show In Progress", callback_data="show_progress")],
            [InlineKeyboardButton("✅ Show Fixed",        callback_data="show_fixed")],
            [InlineKeyboardButton("❌ Show Rejected",     callback_data="show_rejected")],
        ]),
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

    issue = get_issue_by_id(issue_id)
    if issue is None:
        await update.message.reply_text(f"Issue #{issue_id} not found.")
        return

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=issue[3],
        caption=build_full_issue_caption(issue),
    )


# ─── Button Handler ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Show issues by status ───────────────────────────────────────────────
    if data in STATUS_MAP:
        status = STATUS_MAP[data]
        issues = get_issues_by_status(status)
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
            f"📋 {status} Issues — tap one to view:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # ── View single issue ───────────────────────────────────────────────────
    if data.startswith("view_issue_"):
        issue_id = int(data.replace("view_issue_", ""))
        issue = get_issue_by_id(issue_id)
        if issue is None:
            await query.message.reply_text(f"Issue #{issue_id} not found.")
            return
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=issue[3],
                caption=build_full_issue_caption(issue),
            )
        except Exception as e:
            print(f"[VIEW PHOTO] {e}")
            await query.message.reply_text(build_full_issue_caption(issue))
        return

    # ── Start report flow ───────────────────────────────────────────────────
    if data == "report_problem":
        context.user_data.clear()
        await query.edit_message_text(
            "🔧 What is broken?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 TV",       callback_data="item_tv")],
                [InlineKeyboardButton("🪑 Chair",    callback_data="item_chair")],
                [InlineKeyboardButton("🚪 Door",     callback_data="item_door")],
                [InlineKeyboardButton("💻 Computer", callback_data="item_computer")],
                [InlineKeyboardButton("💡 Light",    callback_data="item_light")],
                [InlineKeyboardButton("📦 Other",    callback_data="item_other")],
            ]),
        )
        return

    # ── Select item ─────────────────────────────────────────────────────────
    if data.startswith("item_"):
        ITEM_MAP = {
            "item_tv": "TV", "item_chair": "Chair", "item_door": "Door",
            "item_computer": "Computer", "item_light": "Light",
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
                reply_markup=get_location_keyboard(),
            )
        return

    # ── Select floor ────────────────────────────────────────────────────────
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
    # FIX: prompt goes to admin's PRIVATE chat, not the group
    if data.startswith("assign_"):
        issue_id = int(data.replace("assign_", ""))
        admin_id = query.from_user.id

        context.user_data.update({
            "step":       "waiting_assignment_name",
            "issue_id":   issue_id,
            "chat_id":    query.message.chat_id,
            "message_id": query.message.message_id,
            "caption":    query.message.caption or "",
        })

        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"👷 Type the technician name for Issue #{issue_id}.\n"
                    f"(Reply here in private, not in the group)"
                ),
            )
        except Exception:
            await query.message.reply_text(
                "⚠️ Please open a private chat with this bot first, then try again."
            )
        return

    # ── Update status ───────────────────────────────────────────────────────
    if data.startswith("status_"):
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

        # FIX: rejection reason prompt goes to admin's PRIVATE chat
        if status_text == "Rejected":
            admin_id = query.from_user.id
            context.user_data.update({
                "step":       "waiting_reject_reason",
                "issue_id":   issue_id,
                "chat_id":    query.message.chat_id,
                "message_id": query.message.message_id,
                "caption":    query.message.caption or "",
            })
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"❌ Type the rejection reason for Issue #{issue_id}.\n"
                        f"(Reply here in private, not in the group)"
                    ),
                )
            except Exception:
                await query.message.reply_text(
                    "⚠️ Please open a private chat with this bot first, then try again."
                )
            return

        changed_by = query.from_user.first_name
        update_issue_status(issue_id, status_text, changed_by)

        issue = get_issue_by_id(issue_id)
        if issue:
            notify_msg = NOTIFY_TEXT.get(status_text, f"ℹ️ Status changed to {status_text}.")
            await notify_reporter(context, issue[10], notify_msg)

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
                reply_markup=get_issue_action_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[STATUS CAPTION ERROR] {e}")
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"⚠️ Status updated to '{status_text}' in DB but caption edit failed.\nError: {e}",
            )

        await query.answer(f"Issue #{issue_id} → {status_text} by {changed_by}")
        return

    # ── Fallback ────────────────────────────────────────────────────────────
    await query.answer("Unknown action.", show_alert=True)


# ─── Message Handler ──────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    step = context.user_data.get("step")

    if text.lower() in {"/start", "start"}:
        await start(update, context)
        return

    if text.lower() == "aliadmin":
        await stats(update, context)
        return

    clean = text.lstrip("#")
    if clean.isdigit():
        issue_id = int(clean)
        issue = get_issue_by_id(issue_id)
        if issue is None:
            await update.message.reply_text(f"Issue #{issue_id} not found.")
            return
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=issue[3],
                caption=build_full_issue_caption(issue),
            )
        except Exception as e:
            print(f"[LOOKUP PHOTO] {e}")
            await update.message.reply_text(build_full_issue_caption(issue))
        return

    # ── Report flow ────────────────────────────────────────────────────────

    if step == "waiting_item":
        context.user_data.update({"item": text, "step": "waiting_location"})
        await update.message.reply_text(
            "📍 Where is it? Choose a floor or select Other.",
            reply_markup=get_location_keyboard(),
        )
        return

    if step == "waiting_room":
        floor = context.user_data.get("floor", "")
        context.user_data.update({"location": f"{floor} - {text}", "step": "waiting_description"})
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
        await update.message.reply_text("📸 Please send a *photo*, not text.", parse_mode="Markdown")
        return

    # ── Admin flow (runs in PRIVATE chat) ─────────────────────────────────

    if step == "waiting_reject_reason":
        issue_id   = context.user_data["issue_id"]
        reason     = text
        changed_by = update.effective_user.first_name

        update_issue_status(issue_id, "Rejected", changed_by, reason)

        issue = get_issue_by_id(issue_id)
        if issue:
            await notify_reporter(
                context, issue[10],
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
                reply_markup=get_issue_action_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[REJECT CAPTION ERROR] {e}")
            await context.bot.send_message(
                chat_id=context.user_data["chat_id"],
                text=f"⚠️ Issue #{issue_id} rejected but group caption could not be updated.\nError: {e}",
            )

        await update.message.reply_text(
            f"✅ Issue #{issue_id} rejected by {changed_by}.\nReason: {reason}"
        )
        context.user_data.clear()
        return

    if step == "waiting_assignment_name":
        issue_id = context.user_data["issue_id"]
        assign_issue(issue_id, text)

        new_caption = update_caption_field(
            context.user_data.get("caption", ""),
            {"👷 Assigned to:": text},
        )

        try:
            await context.bot.edit_message_caption(
                chat_id=context.user_data["chat_id"],
                message_id=context.user_data["message_id"],
                caption=new_caption,
                reply_markup=get_issue_action_keyboard(issue_id),
            )
        except Exception as e:
            print(f"[ASSIGN CAPTION ERROR] {e}")

        await update.message.reply_text(f"✅ Issue #{issue_id} assigned to {text}.")
        context.user_data.clear()
        return

    await update.message.reply_text("Please type /start to begin reporting an issue.")


# ─── Photo Handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("step") != "waiting_photo":
        await update.message.reply_text(
            "Please complete all steps first.\nType /start to begin."
        )
        return

    data          = context.user_data
    user_id       = update.effective_user.id
    reported_by   = update.effective_user.first_name
    photo_file_id = update.message.photo[-1].file_id
    description   = data.get("description", "No description")

    team_name, group_id = get_team_for_item(data["item"])

    issue_id = save_issue(
        item=data["item"],
        location=data["location"],
        photo_file_id=photo_file_id,
        team=team_name,
        reported_by=reported_by,
        user_id=user_id,
        description=description,
    )

    # FIX: use short caption so Telegram's 1024-char limit is never hit
    caption = build_group_caption(
        issue_id=issue_id,
        item=data["item"],
        location=data["location"],
        description=description,
        team=team_name,
        reported_by=reported_by,
    )

    try:
        await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_file_id,
            caption=caption,
            reply_markup=get_issue_action_keyboard(issue_id),
        )
    except Exception as e:
        print(f"[GROUP SEND ERROR] Failed to post Issue #{issue_id} to group {group_id}: {e}")

    await update.message.reply_text(
        f"✅ Report submitted!\n\n"
        f"Issue ID: #{issue_id}\n"
        f"Item: {data['item']}\n"
        f"Location: {data['location']}\n"
        f"Team: {team_name}\n"
        f"Photo: ✅ Received"
    )

    context.user_data.clear()