async def notify_user(context, user_id: int, message: str):
    if not user_id:
        return
    try:
        await context.bot.send_message(chat_id=user_id, text=message)
    except Exception as e:
        print("[NOTIFY ERROR]", e)


def build_fix_message(reason: str):
    return f"✅ Your issue has been FIXED\n\nWhat was done:\n{reason}"


def build_reject_message(reason: str):
    return f"❌ Your request was REJECTED\n\nReason:\n{reason}"