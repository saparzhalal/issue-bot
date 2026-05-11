from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ai_helper import get_description_keyboard
from config import ICT_GROUP_ID, MAINTENANCE_GROUP_ID
from services.ticket_service import new_ticket, fetch_ticket, assign, set_status, history, by_status
from services.notification_service import notify_user
from keyboards import main_menu_keyboard, item_keyboard, location_keyboard, status_keyboard, stats_keyboard

# ─── Constants ────────────────────────────────────────────────────────────────

ICT_KEYWORDS = ["tv","computer","projector","printer","wifi","wi-fi","internet","monitor",
                "keyboard","mouse","laptop","pc","screen","camera","speaker","microphone","router","network"]
MAINTENANCE_KEYWORDS = ["chair","door","light","lamp","air conditioner","ac","window","desk","table",
                        "fan","sink","toilet","wall","floor","ceiling","lock","handle","water","electric","plug","socket"]
ITEM_MAP = {"item_tv":"TV","item_chair":"Chair","item_door":"Door","item_computer":"Computer","item_light":"Light"}
STATUS_MAP = {"show_new":"New","show_progress":"In Progress","show_fixed":"Fixed","show_rejected":"Rejected"}
STATUS_KEY_MAP = {"progress":"In Progress","fixed":"Fixed","rejected":"Rejected"}
NOTIFY_TEXT = {
    "In Progress": "🟡 [Issue #{id}] Your request is now IN PROGRESS.",
    "Fixed":       "✅ [Issue #{id}] Your request has been FIXED.",
    "Rejected":    "❌ [Issue #{id}] Your request was REJECTED.",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_team(item: str) -> tuple[str, int]:
    lo = item.lower()
    if any(k in lo for k in ICT_KEYWORDS):
        return "ICT Team", ICT_GROUP_ID
    return "Maintenance Team", MAINTENANCE_GROUP_ID

def get_group_id(issue_id: int) -> int:
    issue = fetch_ticket(issue_id)
    return get_team(issue.get("item_name", issue.get("item", "")))[1] if issue else MAINTENANCE_GROUP_ID

def get_stats_message() -> str:
    s = ["New", "In Progress", "Fixed", "Rejected"]
    c = {x: len(by_status(x)) for x in s}
    return (f"📊 Current Issue Report\n\nTotal Issues: {sum(c.values())}\n\n"
            f"🆕 New: {c['New']}\n🔄 In Progress: {c['In Progress']}\n"
            f"✅ Fixed: {c['Fixed']}\n❌ Rejected: {c['Rejected']}")

def build_caption(t: dict) -> str:
    rows = history(t["id"])
    hist = "".join(
        f"\n- {r['new_status']} by {r['updated_by']}" + (f"\n  Notes: {r['notes']}" if r["notes"] else "")
        for r in rows) or "\nNo updates yet."
    return (f"📄 Ticket #{t['id']}\n\n🔧 Item: {t['item_name']}\n📍 Location: {t['location']}\n"
            f"📝 Description: {t['issue_description']}\n👷 Assigned to: {t['assigned_to'] or 'Not assigned yet'}\n"
            f"📌 Status: {t['status']}\n👤 Reported by: {t['requester_name']}\n🕒 Created at: {t['created_at']}\n"
            f"🧾 Final Diagnosis: {t['final_diagnosis'] or 'Not added yet'}\n\n📜 Status History:{hist}")

def patch_caption(caption: str, updates: dict) -> str:
    lines, found = caption.split("\n"), {k: False for k in updates}
    result = []
    for line in lines:
        matched = next((p for p in updates if line.startswith(p)), None)
        if matched:
            result.append(f"{matched} {updates[matched]}")
            found[matched] = True
        else:
            result.append(line)
    result += [f"{p} {v}" for p, v in updates.items() if not found[p]]
    return "\n".join(result)

async def send_issue(bot, chat_id, issue, caption=None):
    cap = caption or build_caption(issue)
    try:
        await bot.send_photo(chat_id=chat_id, photo=issue["photo_file_id"], caption=cap)
    except Exception:
        await bot.send_message(chat_id=chat_id, text=cap)

async def edit_caption(ctx, chat_id, msg_id, updates, issue_id, old_cap):
    try:
        await ctx.bot.edit_message_caption(
            chat_id=chat_id, message_id=msg_id,
            caption=patch_caption(old_cap, updates), reply_markup=status_keyboard(issue_id))
    except Exception as e:
        print(f"[EDIT_CAPTION] {e}")

async def group_msg(ctx, issue_id, text):
    try:
        await ctx.bot.send_message(chat_id=get_group_id(issue_id), text=text)
    except Exception as e:
        print(f"[GROUP_MSG] {e}")

# ─── Commands ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.clear()
    await update.message.reply_text(
        "👋 Welcome to Company Issue Reporter Bot\n\nPlease click below to report an issue.",
        reply_markup=main_menu_keyboard())

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 Admin Dashboard\n\nSelect a filter to view latest issues:",
        reply_markup=stats_keyboard()
    )

async def issue_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /issue <id>   Example: /issue 3"); return
    issue = fetch_ticket(int(context.args[0]))
    if issue:
        await send_issue(context.bot, update.effective_chat.id, issue)
    else:
        await update.message.reply_text(f"Issue #{context.args[0]} not found.")

# ─── Button Handler ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in STATUS_MAP:
        status = STATUS_MAP[data]
        issues = by_status(status)
        try:
            issues = sorted(
                issues,
                key=lambda x: x["id"] if isinstance(x, dict) else x[0],
                reverse=True
            )[:20]
        except Exception:
            issues = issues[:20]
        def iid(i):
            return i["id"] if isinstance(i, dict) and "id" in i else (i[0] if isinstance(i, (list, tuple)) else None)
        buttons = [[InlineKeyboardButton(f"#{iid(i)}", callback_data=f"view_issue_{iid(i)}")] for i in issues if iid(i)]
        if not buttons:
            await query.message.reply_text(f"No {status} issues found."); return
        await query.message.reply_text(f"📋 {status} Issues — tap one to view details:",
                                       reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("view_issue_"):
        issue = fetch_ticket(int(data.replace("view_issue_", "")))
        await (send_issue(context.bot, query.message.chat.id, issue) if issue
               else query.message.reply_text("Issue not found."))
        return

    if data == "report_problem":
        context.chat_data.clear()
        await query.edit_message_text("🔧 What item has a problem?", reply_markup=item_keyboard())
        return

    if data.startswith("item_"):
        if data == "item_other":
            context.chat_data["step"] = "waiting_item"
            await query.edit_message_text("✍️ Please type the item name."); return
        if item := ITEM_MAP.get(data):
            context.chat_data.update({"item": item, "step": "waiting_location"})
            await query.edit_message_text("📍 Where is it? Choose a floor or select Other.",
                                          reply_markup=location_keyboard())
        return

    if data.startswith("loc_"):
        if not context.chat_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start."); return
        if data == "loc_other":
            context.chat_data["step"] = "waiting_location"
            await query.edit_message_text("📍 Please type the exact location."); return
        floor = data.replace("loc_", "")
        context.chat_data.update({"floor": floor, "step": "waiting_room"})
        await query.edit_message_text(
            f"📍 Floor: {floor}\n\nNow type the room or area.\nExample: Room 305, Lab 2, Library")
        return

    if data.startswith("desc_"):
        if not context.chat_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start."); return
        if data == "desc_other":
            context.chat_data["step"] = "waiting_description"
            await query.edit_message_text("📝 Please type the problem description."); return
        context.chat_data.update({"description": data.replace("desc_", ""), "step": "waiting_photo"})
        await query.edit_message_text("📸 Now send a photo of the broken item.")
        return

    if data.startswith("assign_"):
        issue_id = int(data.replace("assign_", ""))
        context.chat_data.update({"step": "waiting_assignment_name", "issue_id": issue_id,
                                   "chat_id": query.message.chat_id, "message_id": query.message.message_id,
                                   "caption": query.message.caption or ""})
        await query.message.reply_text(f"👷 Type the technician name for Issue #{issue_id}.")
        return

    if data.startswith("status_"):
        parts = data.split("_")
        if len(parts) < 3: await query.answer("Invalid status data.", show_alert=True); return
        status_text = STATUS_KEY_MAP.get(parts[1])
        if not status_text: await query.answer("Unknown status.", show_alert=True); return
        issue_id = int(parts[2])

        if status_text in ("Rejected", "Fixed"):
            context.chat_data.update({
                "step": "waiting_reject_reason" if status_text == "Rejected" else "waiting_fixed_reason",
                "issue_id": issue_id, "chat_id": query.message.chat_id,
                "message_id": query.message.message_id, "caption": query.message.caption or ""})
            prompt = (f"❌ Type the rejection reason for Issue #{issue_id}." if status_text == "Rejected"
                      else f"✅ Please type what was fixed for Issue #{issue_id}.")
            await query.message.reply_text(prompt)
            return

        changed_by = query.from_user.first_name
        set_status(issue_id, status_text, changed_by)
        issue = fetch_ticket(issue_id)
        if issue:
            await notify_user(context, issue["requester_id"], NOTIFY_TEXT[status_text].format(id=issue_id))
        await edit_caption(context, query.message.chat_id, query.message.message_id,
                           {"📌 Status:": status_text, "👷 Last updated by:": changed_by},
                           issue_id, query.message.caption or "")
        await query.answer(f"Issue #{issue_id} → {status_text} by {changed_by}")
        return

    await query.answer("Unknown action.", show_alert=True)

# ─── Message Handler ──────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, step = update.message.text.strip(), context.chat_data.get("step")

    if text.lower() in {"/start", "start"}: await start(update, context); return
    if text.lower() == "aliadmin":
        await stats(update, context)
        return

    clean = text.lstrip("#")
    if clean.isdigit():
        issue = fetch_ticket(int(clean))
        await (send_issue(context.bot, update.effective_chat.id, issue) if issue
               else update.message.reply_text(f"Issue #{clean} not found."))
        return

    # Report flow
    if step == "waiting_item":
        context.chat_data.update({"item": text, "step": "waiting_location"})
        await update.message.reply_text("📍 Where is it? Choose a floor or select Other.",
                                        reply_markup=location_keyboard()); return
    if step == "waiting_room":
        context.chat_data.update({"location": f"{context.chat_data.get('floor','')} - {text}", "step": "waiting_description"})
        await update.message.reply_text("📝 What is the problem? Choose one or select Other.",
                                        reply_markup=get_description_keyboard(context.chat_data["item"])); return
    if step == "waiting_location":
        context.chat_data.update({"location": text, "step": "waiting_description"})
        await update.message.reply_text("📝 What is the problem? Choose one or select Other.",
                                        reply_markup=get_description_keyboard(context.chat_data["item"])); return
    if step == "waiting_description":
        context.chat_data.update({"description": text, "step": "waiting_photo"})
        await update.message.reply_text("📸 Now send a photo of the broken item."); return
    if step == "waiting_photo":
        await update.message.reply_text("📸 Please send a *photo*, not text.", parse_mode="Markdown"); return

    # Admin flow
    cd = context.chat_data
    if step == "waiting_reject_reason":
        issue_id, by = cd["issue_id"], update.effective_user.first_name
        set_status(issue_id, "Rejected", by, text)
        issue = fetch_ticket(issue_id)
        if issue:
            await notify_user(context, issue["requester_id"], f"❌ Your request was REJECTED\nReason: {text}")
            await group_msg(context, issue_id, f"❌ Issue #{issue_id} REJECTED\n\nReason: {text}\n\n👷 By: {by}")
        await edit_caption(context, cd["chat_id"], cd["message_id"],
                           {"📌 Status:": "Rejected", "👷 Last updated by:": by, "❌ Rejection reason:": text},
                           issue_id, cd.get("caption", ""))
        await update.message.reply_text(f"✅ Issue #{issue_id} rejected.\nReason: {text}")
        context.chat_data.clear(); return

    if step == "waiting_assignment_name":
        issue_id = cd["issue_id"]
        assign(issue_id, text)
        await edit_caption(context, cd["chat_id"], cd["message_id"],
                           {"👷 Assigned to:": text}, issue_id, cd.get("caption", ""))
        await update.message.reply_text(f"✅ Issue #{issue_id} assigned to {text}.")
        await group_msg(context, issue_id, f"👷 Issue #{issue_id} ASSIGNED\n\nAssigned to: {text}")
        context.chat_data.clear(); return

    if step == "waiting_fixed_reason":
        issue_id, by = cd["issue_id"], update.effective_user.first_name
        set_status(issue_id, "Fixed", by, text)
        issue = fetch_ticket(issue_id)
        if issue:
            await notify_user(context, issue["requester_id"], f"✅ Your issue has been FIXED\n\nWhat was done:\n{text}")
            await group_msg(context, issue_id, f"✅ Issue #{issue_id} marked as FIXED\n\n🧾 What was done:\n{text}\n\n👷 By: {by}")
        await edit_caption(context, cd["chat_id"], cd["message_id"],
                           {"📌 Status:": "Fixed", "👷 Last updated by:": by, "🧾 Final Diagnosis:": text},
                           issue_id, cd.get("caption", ""))
        await update.message.reply_text(f"✅ Issue #{issue_id} marked as fixed.")
        context.chat_data.clear(); return

    await update.message.reply_text(
        "Please type /start to begin reporting an issue.\n\n"
        "💡 Admin tip: send 'aliadmin' to open dashboard."
    )

# ─── Photo Handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.chat_data.get("step") != "waiting_photo":
        await update.message.reply_text("Please complete all steps first.\nType /start to begin."); return

    d = context.chat_data
    user_id, reported_by = update.effective_user.id, update.effective_user.first_name
    photo_file_id = update.message.photo[-1].file_id
    description = d.get("description", "No description")
    team_name, group_id = get_team(d["item"])

    issue_id = new_ticket(category=team_name, item=d["item"], location=d["location"],
                          photo=photo_file_id, name=reported_by, user_id=user_id, description=description)
    caption = (f"🆕 Issue #{issue_id}\n\n🔧 Item: {d['item']}\n📍 Location: {d['location']}\n"
               f"📝 Description: {description}\n👷 Assigned to: Not assigned yet\n"
               f"👥 Team: {team_name}\n👤 Reported by: {reported_by}\n📌 Status: New\n")
    try:
        await context.bot.send_photo(chat_id=group_id, photo=photo_file_id,
                                     caption=caption, reply_markup=status_keyboard(issue_id))
    except Exception as e:
        print(f"[GROUP SEND] Issue #{issue_id}: {e}")

    await update.message.reply_text(
        f"✅ Report submitted!\n\nIssue ID: #{issue_id}\nItem: {d['item']}\n"
        f"Location: {d['location']}\nTeam: {team_name}\nPhoto: ✅ Received")
    context.chat_data.clear()