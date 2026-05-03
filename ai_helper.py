import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import OPENAI_API_KEY


def get_ai_problem_options(item: str):
    """
    Uses OpenAI to generate 5 short problem options for a given item.
    Falls back to generic options if API is not available.
    """
    fallback = ["Broken", "Missing", "Damaged", "Not working", "Unsafe"]

    if not OPENAI_API_KEY:
        return fallback

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate issue options for a school maintenance bot. "
                        "Given an item, return exactly 5 short problem phrases (1-4 words each). "
                        "Return ONLY a JSON array of strings."
                    ),
                },
                {"role": "user", "content": f"Item: {item}"},
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content.strip()
        options = json.loads(content)

        if not isinstance(options, list):
            return fallback

        clean = []
        for opt in options:
            if isinstance(opt, str) and opt.strip():
                clean.append(opt.strip()[:30])

        if len(clean) < 3:
            return fallback

        return clean[:5]

    except Exception:
        return fallback


def get_description_keyboard(item: str):
    """
    Returns Telegram keyboard with problem options.
    Uses AI for unknown items.
    """
    item = item.strip()

    if item == "TV":
        options = ["TV not turning on", "No signal", "Screen broken", "Remote missing", "Other"]
    elif item == "Chair":
        options = ["Chair leg broken", "Backrest broken", "Chair unstable", "Seat damaged", "Other"]
    elif item == "Door":
        options = ["Door broken", "Door lock problem", "Door handle broken", "Door not closing", "Other"]
    elif item == "Computer":
        options = ["Not turning on", "Keyboard/mouse problem", "Screen problem", "Software problem", "Other"]
    elif item == "Light":
        options = ["Light not working", "Light flickering", "Switch problem", "Electrical issue", "Other"]
    else:
        options = get_ai_problem_options(item)
        if "Other" not in options:
            options.append("Other")

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"desc_{opt}")]
        for opt in options
    ])