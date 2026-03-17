import asyncio
import aiohttp
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─────────────────────────────────────────────
#  КОНФИГ — замени на свой токен бота
# ─────────────────────────────────────────────
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"

# ─────────────────────────────────────────────
from aiogram.client.default import DefaultBotProperties

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


# ══════════════════════════════════════════════
#  FSM — состояния диалога
# ══════════════════════════════════════════════
class CheckStates(StatesGroup):
    waiting_cookie = State()
    waiting_years   = State()


# ══════════════════════════════════════════════
#  Roblox API helpers
# ══════════════════════════════════════════════
HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

async def get_auth_user(session: aiohttp.ClientSession, cookie: str):
    """Получаем userId и username по куки."""
    headers = {**HEADERS_BASE, "Cookie": f".ROBLOSECURITY={cookie}"}
    try:
        async with session.get(
            "https://users.roblox.com/v1/users/authenticated",
            headers=headers
        ) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json()
            return data.get("id"), data.get("name")
    except Exception:
        return None, None


async def get_collectibles(session: aiohttp.ClientSession, user_id: int, cookie: str) -> list:
    """Забираем все лимитки из инвентаря (пагинация)."""
    headers = {**HEADERS_BASE, "Cookie": f".ROBLOSECURITY={cookie}"}
    items = []
    cursor = ""
    while True:
        url = (
            f"https://inventory.roblox.com/v1/users/{user_id}"
            f"/assets/collectibles?limit=100&cursor={cursor}"
        )
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
                items.extend(data.get("data", []))
                cursor = data.get("nextPageCursor") or ""
                if not cursor:
                    break
        except Exception:
            break
        await asyncio.sleep(0.15)
    return items


async def get_asset_created_date(session: aiohttp.ClientSession, asset_id: int):
    """Дата создания (релиза) предмета через Economy API."""
    url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
    try:
        async with session.get(url, headers=HEADERS_BASE) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            raw = data.get("Created", "")
            if raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════
#  Handlers
# ══════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎮 <b>Roblox Limited Checker</b>\n\n"
        "Отправь мне свой <b>.ROBLOSECURITY</b> куки.\n\n"
        "Как найти куки:\n"
        "1. Открой <b>roblox.com</b> в браузере\n"
        "2. F12 → Application → Cookies → <code>.ROBLOSECURITY</code>\n"
        "3. Скопируй значение и отправь сюда\n\n"
        "⚠️ <i>Куки нигде не сохраняется — используется только для текущей проверки.</i>"
    )
    await state.set_state(CheckStates.waiting_cookie)


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Проверка отменена. Напиши /start чтобы начать заново.")


@dp.message(CheckStates.waiting_cookie)
async def process_cookie(message: types.Message, state: FSMContext):
    raw = message.text.strip()

    # Поддержка формата: ".ROBLOSECURITY=_|WARNING..." или просто значение
    if ".ROBLOSECURITY=" in raw:
        raw = raw.split(".ROBLOSECURITY=", 1)[1].strip()
    # Убираем пробелы/кавычки если вдруг скопировалось
    cookie = raw.strip('"').strip("'")

    wait_msg = await message.answer("🔄 Проверяю куки...")

    async with aiohttp.ClientSession() as session:
        user_id, username = await get_auth_user(session, cookie)

    if not user_id:
        await wait_msg.edit_text(
            "❌ Не удалось войти! Проверь куки и попробуй снова.\n"
            "Возможные причины:\n"
            "• Куки устарел — выйди и войди в Roblox заново\n"
            "• Скопировал не полностью"
        )
        return

    await state.update_data(cookie=cookie, user_id=user_id, username=username)

    await wait_msg.edit_text(
        f"✅ Вошёл как <b>{username}</b> (ID: <code>{user_id}</code>)\n\n"
        f"Теперь введи <b>диапазон лет</b> для фильтрации лимиток по дате создания.\n\n"
        f"Примеры:\n"
        f"• <code>2015-2020</code> — все лимитки вышедшие с 2015 по 2020\n"
        f"• <code>2019</code> — только 2019 год\n\n"
        f"Отмена: /cancel"
    )
    await state.set_state(CheckStates.waiting_years)


@dp.message(CheckStates.waiting_years)
async def process_years(message: types.Message, state: FSMContext):
    text = message.text.strip()
    year_from = year_to = None

    try:
        if "-" in text:
            parts = text.split("-")
            year_from = int(parts[0].strip())
            year_to   = int(parts[1].strip())
        else:
            year_from = year_to = int(text)

        if not (2004 <= year_from <= 2100 and 2004 <= year_to <= 2100):
            raise ValueError
        if year_from > year_to:
            year_from, year_to = year_to, year_from

    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат! Попробуй:\n"
            "<code>2015-2020</code> или <code>2019</code>"
        )
        return

    data = await state.get_data()
    cookie   = data["cookie"]
    user_id  = data["user_id"]
    username = data["username"]

    progress_msg = await message.answer("⏳ Загружаю инвентарь лимиток...")

    async with aiohttp.ClientSession() as session:
        items = await get_collectibles(session, user_id, cookie)

        if not items:
            await progress_msg.edit_text(
                "😕 Лимитки не найдены.\n"
                "Инвентарь пуст или закрыт для проверки."
            )
            await state.clear()
            return

        total = len(items)
        await progress_msg.edit_text(
            f"🔍 Найдено <b>{total}</b> лимиток.\n"
            f"Проверяю даты создания каждого предмета...\n"
            f"<i>(это может занять несколько минут)</i>"
        )

        matched  = []
        no_date  = []

        for idx, item in enumerate(items, 1):
            asset_id   = item.get("assetId")
            asset_name = item.get("name", "Unknown")
            serial     = item.get("serialNumber")
            rap        = item.get("recentAveragePrice", 0)

            # Обновляем прогресс каждые 10 предметов
            if idx % 10 == 0 or idx == total:
                try:
                    await progress_msg.edit_text(
                        f"🔍 Обработано: <b>{idx}/{total}</b>\n"
                        f"Найдено в диапазоне {year_from}–{year_to}: <b>{len(matched)}</b>\n"
                        f"<i>Пожалуйста подожди...</i>"
                    )
                except Exception:
                    pass

            created_dt = await get_asset_created_date(session, asset_id)

            if created_dt is None:
                no_date.append(asset_name)
            else:
                year = created_dt.year
                if year_from <= year <= year_to:
                    matched.append({
                        "name"   : asset_name,
                        "id"     : asset_id,
                        "year"   : year,
                        "date"   : created_dt.strftime("%d.%m.%Y"),
                        "serial" : f"#{serial}" if serial else "—",
                        "rap"    : rap,
                    })

            await asyncio.sleep(0.2)  # уважаем rate-limit Roblox

    # ── Формируем отчёт ──────────────────────────────────────────────
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    header = (
        f"📋 <b>Отчёт по аккаунту: {username}</b>\n"
        f"🗓 Диапазон: <b>{year_from}–{year_to}</b>\n"
        f"📦 Всего лимиток: <b>{total}</b>\n"
        f"✅ Найдено в диапазоне: <b>{len(matched)}</b>\n"
        f"⚠️ Не удалось проверить: <b>{len(no_date)}</b>\n"
        f"🕐 {now_str}\n"
        f"{'━'*28}\n\n"
    )

    if not matched:
        body = "❌ <i>Лимиток за указанный период не найдено.</i>"
    else:
        matched.sort(key=lambda x: x["date"])
        lines = []
        for i, it in enumerate(matched, 1):
            rap_fmt = f"{it['rap']:,}".replace(",", " ")
            lines.append(
                f"<b>{i}. {it['name']}</b>\n"
                f"   📅 {it['date']}  |  💰 RAP: {rap_fmt}  |  {it['serial']}\n"
                f"   🔗 roblox.com/catalog/{it['id']}"
            )
        body = "\n\n".join(lines)

    full_report = header + body

    # Разбиваем если слишком длинно (лимит Telegram — 4096 символов)
    try:
        await progress_msg.delete()
    except Exception:
        pass

    chunks = [full_report[i:i+4096] for i in range(0, len(full_report), 4096)]
    for chunk in chunks:
        await message.answer(chunk, disable_web_page_preview=True)

    await state.clear()


# ══════════════════════════════════════════════
#  Запуск
# ══════════════════════════════════════════════
async def main():
    print("✅ Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
