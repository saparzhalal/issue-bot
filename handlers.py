

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




def get_team_for_item(item):
    item_lower = item.lower()

    ict_keywords = [
        "tv", "computer", "projector", "printer", "wifi", "wi-fi", "internet",
        "monitor", "keyboard", "mouse", "laptop", "pc", "screen", "camera",
        "speaker", "microphone", "router", "network"
    ]

    maintenance_keywords = [
        "chair", "door", "light", "lamp", "air conditioner", "ac", "window",
        "desk", "table", "fan", "sink", "toilet", "wall", "floor", "ceiling",
        "lock", "handle", "water", "electric", "plug", "socket"
    ]

    for keyword in ict_keywords:
        if keyword in item_lower:
            return "ICT Team", ICT_GROUP_ID

    for keyword in maintenance_keywords:
        if keyword in item_lower:
            return "Maintenance Team", MAINTENANCE_GROUP_ID

    return "Maintenance Team", MAINTENANCE_GROUP_ID


def get_location_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1st Floor", callback_data="loc_1st Floor")],
        [InlineKeyboardButton("2nd Floor", callback_data="loc_2nd Floor")],
        [InlineKeyboardButton("3rd Floor", callback_data="loc_3rd Floor")],
        [InlineKeyboardButton("4th Floor", callback_data="loc_4th Floor")],
        [InlineKeyboardButton("5th Floor", callback_data="loc_5th Floor")],
        [InlineKeyboardButton("Other", callback_data="loc_other")],
    ])


# === Stats and Issue Detail Helpers ===
def get_stats_message():
    statuses = ["New", "In Progress", "Fixed", "Rejected"]
    counts = {}
    total = 0

    for status in statuses:
        count = len(get_issues_by_status(status))
        counts[status] = count
        total += count

    return (
        "📊 Current Issue Report\n\n"
        f"Total Issues: {total}\n\n"
        f"🆕 New: {counts['New']}\n"
        f"🔄 In Progress: {counts['In Progress']}\n"
        f"✅ Fixed: {counts['Fixed']}\n"
        f"❌ Rejected: {counts['Rejected']}"
    )


def build_full_issue_caption(issue):
    issue_id, item, location, photo_file_id, team, status, reported_by, description, assigned_to, created_at, reporter_user_id = issue

    if not description:
        description = "No description"

    if not assigned_to:
        assigned_to = "Not assigned yet"

    status_history = get_status_history(issue_id)

    return (
        f"📄 Full Issue Details #{issue_id}\n\n"
        f"🔧 Item: {item}\n"
        f"📍 Location: {location}\n"
        f"📝 Description: {description}\n"
        f"👷 Assigned to: {assigned_to}\n"
        f"👥 Team: {team}\n"
        f"📌 Current Status: {status}\n"
        f"👤 Reported by: {reported_by}\n"
        f"🕒 Created at: {created_at}\n\n"
        f"👷 Status History:{status_history}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    keyboard = [[InlineKeyboardButton("🛠 Report Problem", callback_data="report_problem")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to Company Issue Reporter Bot\n\nClick below to report a problem.",
        reply_markup=reply_markup
    )


# === Stats and Issue Detail Commands ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Show New", callback_data="show_new")],
        [InlineKeyboardButton("🔄 Show In Progress", callback_data="show_progress")],
        [InlineKeyboardButton("✅ Show Fixed", callback_data="show_fixed")],
        [InlineKeyboardButton("❌ Show Rejected", callback_data="show_rejected")],
    ])

    await update.message.reply_text(
        get_stats_message(),
        reply_markup=keyboard
    )


async def issue_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please type issue ID. Example: /issue 3")
        return

    try:
        issue_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Issue ID must be a number. Example: /issue 3")
        return

    issue = get_issue_by_id(issue_id)
    if issue is None:
        await update.message.reply_text(f"Issue #{issue_id} was not found.")
        return

    caption = build_full_issue_caption(issue)
    photo_file_id = issue[3]

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=photo_file_id,
        caption=caption
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data.startswith("show_"):
        status_map = {
            "show_new": "New",
            "show_progress": "In Progress",
            "show_fixed": "Fixed",
            "show_rejected": "Rejected",
        }

        status = status_map[query.data]
        issues = get_issues_by_status(status)
        # sort newest first by created_at (index 9)
        try:
            issues = sorted(issues, key=lambda x: x[9], reverse=True)
        except Exception:
            pass
        issues = issues[:20]

        if not issues:
            await query.message.reply_text(f"No {status} issues.")
            return

        buttons = []
        for issue in issues:
            try:
                issue_id = int(issue[0])
            except Exception:
                print("❌ BAD ISSUE DATA:", issue)
                continue

            buttons.append([
                InlineKeyboardButton(
                    text=f"#{issue_id}",
                    callback_data=f"view_issue_{issue_id}"
                )
            ])

        await query.message.reply_text(
            f"📋 {status} Issues:\n\nChoose an issue below to view full details.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if query.data.startswith("view_issue_"):
        issue_id = int(query.data.replace("view_issue_", ""))
        issue = get_issue_by_id(issue_id)

        if issue is None:
            await query.message.reply_text(f"Issue #{issue_id} was not found.")
            return

        caption = build_full_issue_caption(issue)
        photo_file_id = issue[3]

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_file_id,
            caption=caption
        )
        return

    if query.data == "report_problem":
        context.user_data.clear()

        keyboard = [
            [InlineKeyboardButton("📺 TV", callback_data="item_tv")],
            [InlineKeyboardButton("🪑 Chair", callback_data="item_chair")],
            [InlineKeyboardButton("🚪 Door", callback_data="item_door")],
            [InlineKeyboardButton("💻 Computer", callback_data="item_computer")],
            [InlineKeyboardButton("💡 Light", callback_data="item_light")],
            [InlineKeyboardButton("📦 Other", callback_data="item_other")],
        ]

        await query.edit_message_text(
            "🔧 What is broken?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if query.data.startswith("item_"):
        item_map = {
            "item_tv": "TV",
            "item_chair": "Chair",
            "item_door": "Door",
            "item_computer": "Computer",
            "item_light": "Light",
        }

        if query.data == "item_other":
            context.user_data.update({"step": "waiting_item"})
            await query.edit_message_text("✍️ Please type the item name.")
            return

        item = item_map.get(query.data)
        if item:
            context.user_data.update({"item": item, "step": "waiting_location"})
            await query.edit_message_text(
                "📍 Where is it? Choose a floor or select Other.",
                reply_markup=get_location_keyboard()
            )
            return

    if query.data.startswith("loc_"):
        if not context.user_data:
            await query.message.reply_text("Please start again with /start.")
            return

        if query.data == "loc_other":
            context.user_data["step"] = "waiting_location"
            await query.edit_message_text("📍 Please type the exact location.")
            return

        floor = query.data.replace("loc_", "")
        context.user_data["floor"] = floor
        context.user_data["step"] = "waiting_room"

        await query.edit_message_text(
            f"📍 Floor selected: {floor}\n\nPlease type the exact room or place.\nExample: Room 305, Lab 2, Library, Corridor"
        )
        return

    if query.data.startswith("desc_"):
        if not context.user_data:
            await query.message.reply_text("Please start again with /start.")
            return

        if query.data == "desc_other":
            context.user_data["step"] = "waiting_description"
            await query.edit_message_text("📝 Please type the problem description.")
            return

        description = query.data.replace("desc_", "")
        context.user_data["description"] = description
        context.user_data["step"] = "waiting_photo"

        await query.edit_message_text("📸 Now send a photo of the broken item.")
        return

    if query.data.startswith("assign_"):
        issue_id = int(query.data.replace("assign_", ""))
        context.user_data.update({
            "step": "waiting_assignment_name",
            "issue_id": issue_id,
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "caption": query.message.caption or "",
            "reply_markup": query.message.reply_markup,
        })
        await query.message.reply_text(f"👷 Please type the technician name for Issue #{issue_id}.")
        return

    if query.data.startswith("status_"):
        parts = query.data.split("_")
        new_status = parts[1]
        issue_id = int(parts[2])

        status_text = {
            "progress": "In Progress",
            "fixed": "Fixed",
            "rejected": "Rejected",
        }[new_status]

        if status_text == "Rejected":
            context.user_data.update({
                "step": "waiting_reject_reason",
                "issue_id": issue_id,
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
                "caption": query.message.caption or "",
                "reply_markup": query.message.reply_markup,
            })
            await query.message.reply_text(f"❌ Please type the rejection reason for Issue #{issue_id}.")
            return

        changed_by = query.from_user.first_name
        update_issue_status(issue_id, status_text, changed_by)

        # 🔥 Notify reporter (user who created the issue)
        issue = get_issue_by_id(issue_id)
        if issue:
            reporter_user_id = issue[10]  # index of user_id in tuple

            if status_text == "In Progress":
                notify_text = "🟡 Your request is now IN PROGRESS"
            elif status_text == "Fixed":
                notify_text = "✅ Your request has been FIXED"
            elif status_text == "Rejected":
                notify_text = "❌ Your request was REJECTED"
            else:
                notify_text = f"ℹ️ Your request status changed to {status_text}"

            try:
                if reporter_user_id:
                    await context.bot.send_message(
                        chat_id=reporter_user_id,
                        text=notify_text
                    )
            except Exception as e:
                print(f"Failed to notify user (user didn’t start bot): {e}")

        old_caption = query.message.caption or ""
        lines = old_caption.split("\n")
        new_lines = []
        updated_by_found = False

        for line in lines:
            if line.startswith("📌 Status:"):
                new_lines.append(f"📌 Status: {status_text}")
            elif line.startswith("👷 Last updated by:"):
                new_lines.append(f"👷 Last updated by: {changed_by}")
                updated_by_found = True
            else:
                new_lines.append(line)

        if not updated_by_found:
            new_lines.append(f"👷 Last updated by: {changed_by}")

        try:
            await query.edit_message_caption(
                caption="\n".join(new_lines),
                reply_markup=query.message.reply_markup
            )
        except Exception as e:
            print(f"Edit skipped: {e}")

        await query.answer(f"Issue #{issue_id} updated to {status_text} by {changed_by}")
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text.lower() in ["start", "starts", "/start", "/starts"]:
        await start(update, context)
        return

    if text.lower() == "aliadmin":
        await stats(update, context)
        return

    clean_text = text.replace("#", "")
    if clean_text.isdigit():
        issue_id = int(clean_text)
        issue = get_issue_by_id(issue_id)

        if issue is None:
            await update.message.reply_text(f"Issue #{issue_id} was not found.")
            return

        caption = build_full_issue_caption(issue)
        photo_file_id = issue[3]

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo_file_id,
            caption=caption
        )
        return

    if context.user_data.get("step") == "waiting_item":
        context.user_data["item"] = text
        context.user_data["step"] = "waiting_location"
        await update.message.reply_text(
            "📍 Where is it? Choose a floor or select Other.",
            reply_markup=get_location_keyboard()
        )
        return

    if context.user_data.get("step") == "waiting_room":
        floor = context.user_data.get("floor", "")
        context.user_data["location"] = f"{floor} - {text}"
        context.user_data["step"] = "waiting_description"

        item = context.user_data["item"]
        await update.message.reply_text(
            "📝 What is the problem? Choose one or select Other.",
            reply_markup=get_description_keyboard(item)
        )
        return

    if context.user_data.get("step") == "waiting_location":
        context.user_data["location"] = text
        context.user_data["step"] = "waiting_description"

        item = context.user_data["item"]
        await update.message.reply_text(
            "📝 What is the problem? Choose one or select Other.",
            reply_markup=get_description_keyboard(item)
        )
        return

    if context.user_data.get("step") == "waiting_description":
        context.user_data["description"] = text
        context.user_data["step"] = "waiting_photo"
        await update.message.reply_text("📸 Now send a photo of the broken item.")
        return


    if context.user_data.get("step") == "waiting_reject_reason":
        reject_data = context.user_data
        issue_id = reject_data["issue_id"]
        reason = text
        changed_by = update.effective_user.first_name

        update_issue_status(issue_id, "Rejected", changed_by, reason)

        # 🔥 Notify reporter about rejection
        issue = get_issue_by_id(issue_id)
        if issue:
            reporter_user_id = issue[10]

            notify_text = f"❌ Your request was REJECTED\nReason: {reason}"

            try:
                await context.bot.send_message(
                    chat_id=reporter_user_id,
                    text=notify_text
                )
            except Exception as e:
                print(f"Failed to notify user: {e}")

        old_caption = reject_data.get("caption", "")
        lines = old_caption.split("\n")
        new_lines = []
        updated_by_found = False
        reason_found = False

        for line in lines:
            if line.startswith("📌 Status:"):
                new_lines.append("📌 Status: Rejected")
            elif line.startswith("👷 Last updated by:"):
                new_lines.append(f"👷 Last updated by: {changed_by}")
                updated_by_found = True
            elif line.startswith("❌ Rejection reason:"):
                new_lines.append(f"❌ Rejection reason: {reason}")
                reason_found = True
            else:
                new_lines.append(line)

        if not updated_by_found:
            new_lines.append(f"👷 Last updated by: {changed_by}")

        if not reason_found:
            new_lines.append(f"❌ Rejection reason: {reason}")

        try:
            await context.bot.edit_message_caption(
                chat_id=reject_data["chat_id"],
                message_id=reject_data["message_id"],
                caption="\n".join(new_lines),
                reply_markup=reject_data.get("reply_markup")
            )
        except Exception as e:
            print(f"Edit skipped: {e}")

        await update.message.reply_text(
            f"✅ Issue #{issue_id} rejected by {changed_by}.\nReason: {reason}"
        )

        context.user_data.clear()
        return

    if context.user_data.get("step") == "waiting_assignment_name":
        assign_data = context.user_data
        issue_id = assign_data["issue_id"]
        technician_name = text
        assign_issue(issue_id, technician_name)

        old_caption = assign_data.get("caption", "")
        lines = old_caption.split("\n")
        new_lines = []
        assigned_found = False

        for line in lines:
            if line.startswith("👷 Assigned to:"):
                new_lines.append(f"👷 Assigned to: {technician_name}")
                assigned_found = True
            else:
                new_lines.append(line)

        if not assigned_found:
            new_lines.append(f"👷 Assigned to: {technician_name}")

        await context.bot.edit_message_caption(
            chat_id=assign_data["chat_id"],
            message_id=assign_data["message_id"],
            caption="\n".join(new_lines),
            reply_markup=assign_data.get("reply_markup")
        )

        await update.message.reply_text(f"✅ Issue #{issue_id} assigned to {technician_name}.")
        context.user_data.clear()
        return

    await update.message.reply_text("Please type /start first.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.user_data or context.user_data.get("step") != "waiting_photo":
        await update.message.reply_text(
            "Please complete the report steps first: item → location → problem → photo.\nType /start to restart."
        )
        return

    data = context.user_data
    description = data.get("description", "No description")
    photo_file_id = update.message.photo[-1].file_id

    team_name, group_id = get_team_for_item(data["item"])
    reported_by = update.effective_user.first_name

    issue_id = save_issue(
        item=data["item"],
        location=data["location"],
        photo_file_id=photo_file_id,
        team=team_name,
        reported_by=reported_by,
        user_id=user_id,
        description=description,
    )

    caption = (
        f"🆕 Issue #{issue_id}\n\n"
        f"🔧 Item: {data['item']}\n"
        f"📍 Location: {data['location']}\n"
        f"📝 Description: {description}\n"
        "👷 Assigned to: Not assigned yet\n"
        f"👥 Team: {team_name}\n"
        f"👤 Reported by: {reported_by}\n"
        "📌 Status: New"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 In Progress", callback_data=f"status_progress_{issue_id}"),
            InlineKeyboardButton("✅ Fixed", callback_data=f"status_fixed_{issue_id}"),
        ],
        [InlineKeyboardButton("❌ Rejected", callback_data=f"status_rejected_{issue_id}")],
        [InlineKeyboardButton("👷 Assign Technician", callback_data=f"assign_{issue_id}")],
    ])

    await context.bot.send_photo(
        chat_id=group_id,
        photo=photo_file_id,
        caption=caption,
        reply_markup=keyboard
    )

    await update.message.reply_text(
        f"✅ Report sent successfully!\n\nIssue ID: #{issue_id}\nItem: {data['item']}\nLocation: {data['location']}\nAssigned Team: {team_name}\nPhoto: received"
    )

    context.user_data.clear()