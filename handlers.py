from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ai_helper import get_description_keyboard
from config import ICT_GROUP_ID, MAINTENANCE_GROUP_ID
from services.ticket_service import new_ticket, fetch_ticket, assign, set_status, history, by_status
from services.notification_service import notify_user
from keyboards import main_menu_keyboard, item_keyboard, location_keyboard, status_keyboard

ICT_KEYWORDS = ["tv","computer","projector","printer","wifi","wi-fi","internet","monitor",
                "keyboard","mouse","laptop","pc","screen","camera","speaker","microphone","router","network"]
ITEM_MAP = {"item_tv":"TV","item_chair":"Chair","item_door":"Door","item_computer":"Computer","item_light":"Light"}
STATUS_MAP = {"show_new":"New","show_progress":"In Progress","show_fixed":"Fixed","show_rejected":"Rejected"}
STATUS_KEY_MAP = {"progress":"In Progress","fixed":"Fixed","rejected":"Rejected"}
NOTIFY_TEXT = {
    "In Progress": "🟡 [Issue #{id}] Your request is now IN PROGRESS.",
    "Fixed":       "✅ [Issue #{id}] Your request has been FIXED.",
    "Rejected":    "❌ [Issue #{id}] Your request was REJECTED.",
}

def get_team(item):
    lo = item.lower()
    return ("ICT Team", ICT_GROUP_ID) if any(k in lo for k in ICT_KEYWORDS) else ("Maintenance Team", MAINTENANCE_GROUP_ID)

def get_group_id(issue_id):
    issue = fetch_ticket(issue_id)
    return get_team(issue.get("item_name", issue.get("item", "")))[1] if issue else MAINTENANCE_GROUP_ID

def get_stats_message():
    from collections import Counter

    statuses = ["New", "In Progress", "Fixed", "Rejected"]
    counts = {x: len(by_status(x)) for x in statuses}
    total = sum(counts.values())

    fixed_items = [i.get("item_name") if isinstance(i, dict) else None for i in by_status("Fixed")]
    rejected_items = [i.get("item_name") if isinstance(i, dict) else None for i in by_status("Rejected")]

    fixed_counter = Counter([i for i in fixed_items if i])
    rejected_counter = Counter([i for i in rejected_items if i])

    top_fixed = fixed_counter.most_common(3)
    top_rejected = rejected_counter.most_common(3)

    fixed_text = "\n".join([f"   - {k}: {v}" for k, v in top_fixed]) if top_fixed else "   - No data"
    rejected_text = "\n".join([f"   - {k}: {v}" for k, v in top_rejected]) if top_rejected else "   - No data"

    return (
        "📊 Current Issue Report\n\n"
        f"Total Issues: {total}\n\n"
        f"🆕 New: {counts['New']}\n"
        f"🔄 In Progress: {counts['In Progress']}\n"
        f"✅ Fixed: {counts['Fixed']}\n"
        f"❌ Rejected: {counts['Rejected']}\n\n"
        f"📈 Top Fixed Items:\n{fixed_text}\n\n"
        f"📉 Top Rejected Items:\n{rejected_text}"
    )

def build_caption(t):
    hist = "".join(
        f"\n- {r['new_status']} by {r['updated_by']}" + (f"\n  Notes: {r['notes']}" if r["notes"] else "")
        for r in history(t["id"])) or "\nNo updates yet."
    return (f"📄 Ticket #{t['id']}\n\n🔧 Item: {t['item_name']}\n📍 Location: {t['location']}\n"
            f"📝 Description: {t['issue_description']}\n👷 Assigned to: {t['assigned_to'] or 'Not assigned yet'}\n"
            f"📌 Status: {t['status']}\n👤 Reported by: {t['requester_name']}\n🕒 Created at: {t['created_at']}\n"
            f"🧾 Final Diagnosis: {t['final_diagnosis'] or 'Not added yet'}\n\n📜 Status History:{hist}")

def patch_caption(caption, updates):
    found = {k: False for k in updates}
    result = []
    for line in caption.split("\n"):
        matched = next((p for p in updates if line.startswith(p)), None)
        result.append(f"{matched} {updates[matched]}" if matched else line)
        if matched: found[matched] = True
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
            chat_id=chat_id,
            message_id=msg_id,
            caption=patch_caption(old_cap, updates),
            reply_markup=status_keyboard(issue_id)
        )
    except Exception as e:
        print(f"[EDIT_CAPTION] {e}")

async def group_msg(ctx, issue_id, text):
    try:
        await ctx.bot.send_message(chat_id=get_group_id(issue_id), text=text)
    except Exception as e:
        print(f"[GROUP_MSG] {e}")

# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.clear()
    await update.message.reply_text(
        "👋 Welcome to Company Issue Reporter Bot\n\nPlease click below to report an issue.",
        reply_markup=main_menu_keyboard()
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_stats_message(),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🆕 New", callback_data="show_new"),
                InlineKeyboardButton("🔄 In Progress", callback_data="show_progress")
            ],
            [
                InlineKeyboardButton("✅ Fixed", callback_data="show_fixed"),
                InlineKeyboardButton("❌ Rejected", callback_data="show_rejected")
            ],
            [
                InlineKeyboardButton("📈 View Fixed Details", callback_data="fixed_details")
            ],
            [
                InlineKeyboardButton("📉 View Rejected Details", callback_data="rejected_details")
            ]
        ])
    )

async def issue_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /issue <id>   Example: /issue 3")
        return
    issue = fetch_ticket(int(context.args[0]))
    if issue:
        await send_issue(context.bot, update.effective_chat.id, issue)
    else:
        await update.message.reply_text(f"Issue #{context.args[0]} not found.")

# ── Button Handler ────────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # ✅ FIX: Do NOT call query.answer() here globally.
    # Each branch answers the query exactly once to avoid BadRequest errors.
    data = query.data

    # ── Show issues by status ─────────────────────────────────────────────────
    if data in STATUS_MAP:
        await query.answer()
        status = STATUS_MAP[data]
        issues = by_status(status)
        try:
            issues = sorted(issues, key=lambda x: x["id"] if isinstance(x, dict) else x[0], reverse=True)[:20]
        except Exception:
            issues = issues[:20]
        buttons = [
            [InlineKeyboardButton(
                f"#{i['id'] if isinstance(i, dict) else i[0]}",
                callback_data=f"view_issue_{i['id'] if isinstance(i, dict) else i[0]}"
            )]
            for i in issues
        ]
        if not buttons:
            await query.message.reply_text(f"No {status} issues found.")
            return
        await query.message.reply_text(
            f"📋 {status} Issues — tap one to view details:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ── View a single issue ───────────────────────────────────────────────────
    if data.startswith("view_issue_"):
        await query.answer()
        issue = fetch_ticket(int(data.replace("view_issue_", "")))
        if issue:
            await send_issue(context.bot, query.message.chat.id, issue)
        else:
            await query.message.reply_text("Issue not found.")
        return

    # ── Start report flow ─────────────────────────────────────────────────────
    if data == "report_problem":
        await query.answer()
        context.chat_data.clear()
        await query.edit_message_text("What item?", reply_markup=item_keyboard())
        return

    # ── Item selection ────────────────────────────────────────────────────────
    if data.startswith("item_"):
        await query.answer()
        if data == "item_other":
            context.chat_data["step"] = "waiting_item"
            await query.edit_message_text("Item?")
            return
        item = ITEM_MAP.get(data)
        if item:
            context.chat_data.update({"item": item, "step": "waiting_location"})
            await query.edit_message_text("Where?", reply_markup=location_keyboard())
        return

    # ── Location selection ────────────────────────────────────────────────────
    if data.startswith("loc_"):
        await query.answer()
        if not context.chat_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start.")
            return
        if data == "loc_other":
            context.chat_data["step"] = "waiting_location"
            await query.edit_message_text("Location?")
            return
        floor = data.replace("loc_", "")
        context.chat_data.update({"floor": floor, "step": "waiting_room"})
        await query.edit_message_text(f"Floor: {floor}\nRoom?")
        return

    # ── Description selection ─────────────────────────────────────────────────
    if data.startswith("desc_"):
        await query.answer()
        if not context.chat_data.get("item"):
            await query.message.reply_text("⚠️ Session expired. Please type /start.")
            return
        if data == "desc_other":
            context.chat_data["step"] = "waiting_description"
            await query.edit_message_text("Problem?")
            return
        context.chat_data.update({"description": data.replace("desc_", ""), "step": "waiting_photo"})
        await query.edit_message_text("Send photo 📸")
        return

    # ── Assign technician ─────────────────────────────────────────────────────
    if data.startswith("assign_"):
        await query.answer()
        issue_id = int(data.replace("assign_", ""))
        context.chat_data.update({
            "step": "waiting_assignment_name",
            "issue_id": issue_id,
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id,
            "caption": query.message.caption or ""
        })
        await query.message.reply_text(f"👷 Type the technician name for Issue #{issue_id}.")
        return

    # ── Change status ─────────────────────────────────────────────────────────
    if data.startswith("status_"):
        parts = data.split("_")
        if len(parts) < 3:
            await query.answer("Invalid status data.", show_alert=True)
            return
        status_text = STATUS_KEY_MAP.get(parts[1])
        if not status_text:
            await query.answer("Unknown status.", show_alert=True)
            return
        issue_id = int(parts[2])

        if status_text in ("Rejected", "Fixed"):
            await query.answer()
            context.chat_data.update({
                "step": "waiting_reject_reason" if status_text == "Rejected" else "waiting_fixed_reason",
                "issue_id": issue_id,
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id,
                "caption": query.message.caption or ""
            })
            await query.message.reply_text(
                f"❌ Type the rejection reason for Issue #{issue_id}." if status_text == "Rejected"
                else f"✅ Please type what was fixed for Issue #{issue_id}."
            )
            return

        # In Progress — no note needed
        changed_by = query.from_user.first_name
        set_status(issue_id, status_text, changed_by)
        issue = fetch_ticket(issue_id)
        if issue:
            await notify_user(context, issue["requester_id"], NOTIFY_TEXT[status_text].format(id=issue_id))
        await edit_caption(
            context, query.message.chat_id, query.message.message_id,
            {"📌 Status:": status_text, "👷 Last updated by:": changed_by},
            issue_id, query.message.caption or ""
        )
        # ✅ FIX: answer ONCE here, after all the work is done
        await query.answer(f"Issue #{issue_id} → {status_text} by {changed_by}")
        return

    # ── Fixed details ─────────────────────────────────────────────────────────
    if data == "fixed_details":
        await query.answer()
        issues = by_status("Fixed")[:20]
        if not issues:
            await query.message.reply_text("No fixed issues found.")
            return
        text = "✅ FIXED ISSUES (DETAILS)\n\n"
        for i in issues:
            issue_id = i.get("id") if isinstance(i, dict) else i[0]
            issue = fetch_ticket(issue_id)
            if not issue:
                continue
            text += (
                f"#{issue_id} - {issue.get('item_name') or issue.get('item')}\n"
                f"🧾 What was done:\n{issue.get('final_diagnosis') or 'Not added'}\n"
                f"👷 By: {issue.get('assigned_to') or 'Unknown'}\n\n"
            )
        await query.message.reply_text(text)
        return

    # ── Rejected details ──────────────────────────────────────────────────────
    if data == "rejected_details":
        await query.answer()
        issues = by_status("Rejected")[:20]
        if not issues:
            await query.message.reply_text("No rejected issues found.")
            return
        text = "❌ REJECTED ISSUES (DETAILS)\n\n"
        for i in issues:
            issue_id = i.get("id") if isinstance(i, dict) else i[0]
            issue = fetch_ticket(issue_id)
            if not issue:
                continue
            text += (
                f"#{issue_id} - {issue.get('item_name') or issue.get('item')}\n"
                f"🧾 Reason:\n{issue.get('rejection_reason') or 'Not added'}\n"
                f"👷 By: {issue.get('assigned_to') or 'Unknown'}\n\n"
            )
        await query.message.reply_text(text)
        return

    # ── Fallback ──────────────────────────────────────────────────────────────
    await query.answer("Unknown action.", show_alert=True)

# ── Message Handler ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    step = context.chat_data.get("step")
    cd = context.chat_data

    if text.lower() in {"/start", "start"}:
        await start(update, context)
        return

    if text.lower() == "aliadmin":
        await stats(update, context)
        return

    clean = text.lstrip("#")
    if clean.isdigit():
        issue = fetch_ticket(int(clean))
        if issue:
            await send_issue(context.bot, update.effective_chat.id, issue)
        else:
            await update.message.reply_text(f"Issue #{clean} not found.")
        return

    # ── Report flow ───────────────────────────────────────────────────────────
    if step == "waiting_item":
        cd.update({"item": text, "step": "waiting_location"})
        await update.message.reply_text("Where?", reply_markup=location_keyboard())
        return

    if step in ("waiting_room", "waiting_location"):
        loc = f"{cd.get('floor', '')} - {text}" if step == "waiting_room" else text
        cd.update({"location": loc, "step": "waiting_description"})
        await update.message.reply_text("Problem?", reply_markup=get_description_keyboard(cd["item"]))
        return

    if step == "waiting_description":
        cd.update({"description": text, "step": "waiting_photo"})
        await update.message.reply_text("Send photo 📸")
        return

    if step == "waiting_photo":
        await update.message.reply_text("📸 Please send a *photo*, not text.", parse_mode="Markdown")
        return

    # ── Admin flow — reject / fix ─────────────────────────────────────────────
    if step in ("waiting_reject_reason", "waiting_fixed_reason"):
        is_reject = step == "waiting_reject_reason"
        status = "Rejected" if is_reject else "Fixed"
        issue_id = cd["issue_id"]
        by = update.effective_user.first_name

        set_status(issue_id, status, by, text)
        issue = fetch_ticket(issue_id)

        if issue:
            await notify_user(
                context, issue["requester_id"],
                f"❌ Your request was REJECTED\nReason: {text}" if is_reject
                else f"✅ Your issue has been FIXED\n\nWhat was done:\n{text}"
            )
            await group_msg(
                context, issue_id,
                f"❌ Issue #{issue_id} REJECTED\n\nReason: {text}\n\n👷 By: {by}" if is_reject
                else f"✅ Issue #{issue_id} marked as FIXED\n\n🧾 What was done:\n{text}\n\n👷 By: {by}"
            )

        extra_key = "❌ Rejection reason:" if is_reject else "🧾 Final Diagnosis:"
        await edit_caption(
            context, cd["chat_id"], cd["message_id"],
            {"📌 Status:": status, "👷 Last updated by:": by, extra_key: text},
            issue_id, cd.get("caption", "")
        )
        await update.message.reply_text(
            f"✅ Issue #{issue_id} rejected.\nReason: {text}" if is_reject
            else f"✅ Issue #{issue_id} marked as fixed."
        )
        context.chat_data.clear()
        return

    # ── Admin flow — assign ───────────────────────────────────────────────────
    if step == "waiting_assignment_name":
        issue_id = cd["issue_id"]
        assign(issue_id, text)
        await edit_caption(
            context, cd["chat_id"], cd["message_id"],
            {"👷 Assigned to:": text},
            issue_id, cd.get("caption", "")
        )
        await update.message.reply_text(f"✅ Issue #{issue_id} assigned to {text}.")
        await group_msg(context, issue_id, f"👷 Issue #{issue_id} ASSIGNED\n\nAssigned to: {text}")
        context.chat_data.clear()
        return

    # ── Auto-start: no step yet, treat as description ─────────────────────────
    if not step:
        cd.update({
            "item": "Other",
            "description": text,
            "step": "waiting_location"
        })
        await update.message.reply_text("Where?", reply_markup=location_keyboard())
        return

    await update.message.reply_text("Please type /start to begin reporting an issue.")

# ── Photo Handler ─────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.chat_data

    if d.get("step") != "waiting_photo":
        await update.message.reply_text("Please complete all steps first.\nType /start to begin.")
        return

    if not d.get("item"):
        d["item"] = "Other"
    if not d.get("location"):
        d["location"] = "Unknown"
    if not d.get("description"):
        d["description"] = "No description"

    user_id = update.effective_user.id
    reported_by = update.effective_user.first_name
    photo_file_id = update.message.photo[-1].file_id
    description = d.get("description", "No description")
    team_name, group_id = get_team(d["item"])

    issue_id = new_ticket(
        category=team_name,
        item=d["item"],
        location=d["location"],
        photo=photo_file_id,
        name=reported_by,
        user_id=user_id,
        description=description
    )

    caption = (
        f"🆕 Issue #{issue_id}\n\n"
        f"🔧 Item: {d['item']}\n"
        f"📍 Location: {d['location']}\n"
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
            reply_markup=status_keyboard(issue_id)
        )
    except Exception as e:
        print(f"[GROUP SEND] Issue #{issue_id}: {e}")

    await update.message.reply_text(
        f"✅ Report submitted!\n\n"
        f"Issue ID: #{issue_id}\n"
        f"Item: {d['item']}\n"
        f"Location: {d['location']}\n"
        f"Team: {team_name}\n"
        f"Photo: ✅ Received"
    )
    context.chat_data.clear()