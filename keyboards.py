from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import FLOORS


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Report Problem", callback_data="report_problem")]
    ])


def item_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 TV", callback_data="item_tv")],
        [InlineKeyboardButton("🪑 Chair", callback_data="item_chair")],
        [InlineKeyboardButton("🚪 Door", callback_data="item_door")],
        [InlineKeyboardButton("💻 Computer", callback_data="item_computer")],
        [InlineKeyboardButton("💡 Light", callback_data="item_light")],
        [InlineKeyboardButton("📦 Other", callback_data="item_other")],
    ])


def location_keyboard():
    rows = [[InlineKeyboardButton(floor, callback_data=f"loc_{floor}")] for floor in FLOORS]
    rows.append([InlineKeyboardButton("Other", callback_data="loc_other")])
    return InlineKeyboardMarkup(rows)


def status_keyboard(issue_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 In Progress", callback_data=f"status_progress_{issue_id}"),
            InlineKeyboardButton("✅ Fixed", callback_data=f"status_fixed_{issue_id}"),
        ],
        [InlineKeyboardButton("❌ Rejected", callback_data=f"status_rejected_{issue_id}")],
        [InlineKeyboardButton("👷 Assign Technician", callback_data=f"assign_{issue_id}")],
    ])


def stats_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Show New", callback_data="show_new")],
        [InlineKeyboardButton("🔄 Show In Progress", callback_data="show_progress")],
        [InlineKeyboardButton("✅ Show Fixed", callback_data="show_fixed")],
        [InlineKeyboardButton("❌ Show Rejected", callback_data="show_rejected")],
    ])



