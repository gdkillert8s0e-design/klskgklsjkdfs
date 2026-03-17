import asyncio
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
# ====================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Хранилище данных пользователей (в памяти)
users = {}

# ===== FSM состояния =====
class States(StatesGroup):
    waiting_cookie  = State()
    waiting_year_from = State()
    waiting_year_to   = State()

# ===== Типы предметов Roblox =====
ASSET_TYPES_MAP = {
    "faces":    [18],                       # Лица
    "hats":     [8, 41, 42, 43, 44, 45, 46, 47],  # Шапки + Аксессуары
    "gear":     [11],                       # Снаряжение/Оружие
    "clothing": [12, 13],                   # Одежда
}

ASSET_TYPE_NAMES = {
    "faces":    "👤 Лица (Faces)",
    "hats":     "🎩 Шапки / Аксессуары",
    "gear":     "⚔️ Снаряжение (Gear)",
    "clothing": "👕 Одежда",
}

# ===== Утилиты =====
def get_user(uid: int) -> dict:
    """Получить или создать настройки пользователя"""
    if uid not in users:
        users[uid] = {
            "cookie":     None,
            "roblox_id":  None,
            "year_from":  2012,
            "year_to":    2024,
            "check_promo": True,
            "asset_types": {
                "faces":    True,
                "hats":     True,
                "gear":     True,
                "clothing": False,
            }
        }
    return users[uid]


def settings_keyboard(uid: int) -> InlineKeyboardMarkup:
    u = get_user(uid)
    rows = []

    # Типы предметов
    for key, name in ASSET_TYPE_NAMES.items():
        icon = "✅" if u["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {name}",
            callback_data=f"toggle_{key}"
        )])

    # Промо-предметы
    promo_icon = "✅" if u["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(
        text=f"{promo_icon} 🎁 Промо-предметы (бесплатные)",
        callback_data="toggle_promo"
    )])

    # Диапазон лет
    rows.append([
        InlineKeyboardButton(text=f"📅 С года: {u['year_from']}", callback_data="set_year_from"),
        InlineKeyboardButton(text=f"📅 По год: {u['year_to']}",   callback_data="set_year_to"),
    ])

    rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="settings_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===== Roblox API =====
async def get_roblox_user_id(cookie: str) -> int | None:
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    try:
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get("https://users.roblox.com/v1/users/authenticated", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("id")
    except Exception:
        pass
    return None


async def get_inventory(cookie: str, user_id: int, asset_type_ids: list) -> list:
    types_str = ",".join(map(str, asset_type_ids))
    items = []
    cursor = ""
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}

    async with aiohttp.ClientSession(headers=headers) as s:
        while True:
            url = (
                f"https://inventory.roblox.com/v2/users/{user_id}/inventory"
                f"?assetTypes={types_str}&limit=100&sortOrder=Asc"
                + (f"&cursor={cursor}" if cursor else "")
            )
            try:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        break
                    data = await r.json()
                    items.extend(data.get("data", []))
                    cursor = data.get("nextPageCursor") or ""
                    if not cursor:
                        break
            except Exception:
                break

    return items


async def get_asset_details(asset_id: int) -> dict | None:
    url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return None


# ===== Хендлеры =====
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎮 <b>Roblox Offsale Checker</b>\n\n"
        "Ищет оффсейл-предметы в инвентаре Roblox аккаунта.\n\n"
        "📌 <b>Команды:</b>\n"
        "🍪 /cookie — ввести .ROBLOSECURITY cookie\n"
        "🔍 /check — запустить проверку\n"
        "⚙️ /settings — настройки поиска\n"
        "ℹ️ /info — текущий аккаунт и настройки\n\n"
        "<i>Начни с /cookie — отправь свой cookie для авторизации</i>"
    )


@dp.message(Command("cookie"))
async def cmd_cookie(message: Message, state: FSMContext):
    await message.answer(
        "🍪 Отправь <code>.ROBLOSECURITY</code> cookie:\n\n"
        "<i>⚠️ Никому не передавай cookie — это полный доступ к аккаунту!</i>"
    )
    await state.set_state(States.waiting_cookie)


@dp.message(States.waiting_cookie)
async def save_cookie(message: Message, state: FSMContext):
    cookie = message.text.strip()
    # Удаляем предупреждение которое Roblox добавляет в начало
    if "_|WARNING" in cookie and "--|" in cookie:
        cookie = cookie.split("--|", 1)[-1]

    msg = await message.answer("⏳ Проверяю cookie...")
    roblox_id = await get_roblox_user_id(cookie)

    if not roblox_id:
        await msg.edit_text(
            "❌ <b>Неверный cookie!</b>\n\n"
            "Убедись что скопировал правильно и аккаунт не заблокирован.\n"
            "Попробуй ещё раз /cookie"
        )
        await state.clear()
        return

    u = get_user(message.from_user.id)
    u["cookie"]    = cookie
    u["roblox_id"] = roblox_id

    await msg.edit_text(
        f"✅ <b>Авторизован!</b>\n\n"
        f"🆔 Roblox ID: <code>{roblox_id}</code>\n\n"
        f"Используй /check для проверки или /settings для настроек."
    )
    await state.clear()


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer(
        "⚙️ <b>Настройки поиска</b>\n\n"
        "Выбери типы предметов и диапазон годов создания:",
        reply_markup=settings_keyboard(message.from_user.id)
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    u = get_user(message.from_user.id)
    auth = f"✅ ID: <code>{u['roblox_id']}</code>" if u.get("cookie") else "❌ Не авторизован"
    types_on = [ASSET_TYPE_NAMES[k] for k, v in u["asset_types"].items() if v]

    await message.answer(
        f"ℹ️ <b>Текущие настройки</b>\n\n"
        f"🔑 Аккаунт: {auth}\n"
        f"📅 Диапазон лет: {u['year_from']} – {u['year_to']}\n"
        f"🎁 Промо-предметы: {'✅' if u['check_promo'] else '❌'}\n"
        f"📦 Типы предметов:\n" +
        "\n".join(f"  • {t}" for t in types_on)
    )


# ----- Коллбэки настроек -----
@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_setting(cb: CallbackQuery):
    uid = cb.from_user.id
    u   = get_user(uid)
    key = cb.data.replace("toggle_", "")

    if key == "promo":
        u["check_promo"] = not u["check_promo"]
    elif key in u["asset_types"]:
        u["asset_types"][key] = not u["asset_types"][key]

    await cb.message.edit_reply_markup(reply_markup=settings_keyboard(uid))
    await cb.answer()


@dp.callback_query(F.data == "set_year_from")
async def cb_year_from(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("📅 Введи начальный год (например: <code>2015</code>):")
    await state.set_state(States.waiting_year_from)
    await cb.answer()


@dp.callback_query(F.data == "set_year_to")
async def cb_year_to(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("📅 Введи конечный год (например: <code>2023</code>):")
    await state.set_state(States.waiting_year_to)
    await cb.answer()


@dp.message(States.waiting_year_from)
async def save_year_from(message: Message, state: FSMContext):
    try:
        year = int(message.text.strip())
        if 2006 <= year <= 2030:
            get_user(message.from_user.id)["year_from"] = year
            await message.answer(f"✅ Начальный год: <b>{year}</b>\n\nОткрой /settings чтобы продолжить.")
            await state.clear()
        else:
            await message.answer("❌ Год должен быть от 2006 до 2030")
    except ValueError:
        await message.answer("❌ Введи число!")


@dp.message(States.waiting_year_to)
async def save_year_to(message: Message, state: FSMContext):
    try:
        year = int(message.text.strip())
        if 2006 <= year <= 2030:
            get_user(message.from_user.id)["year_to"] = year
            await message.answer(f"✅ Конечный год: <b>{year}</b>\n\nОткрой /settings чтобы продолжить.")
            await state.clear()
        else:
            await message.answer("❌ Год должен быть от 2006 до 2030")
    except ValueError:
        await message.answer("❌ Введи число!")


@dp.callback_query(F.data == "settings_done")
async def settings_done(cb: CallbackQuery):
    await cb.message.edit_text("✅ Настройки сохранены! Используй /check для проверки.")
    await cb.answer("Сохранено!")


# ----- Основная проверка -----
@dp.message(Command("check"))
async def cmd_check(message: Message):
    uid = message.from_user.id
    u   = get_user(uid)

    if not u.get("cookie"):
        await message.answer("❌ Сначала авторизуйся: /cookie")
        return

    # Собираем включённые типы предметов
    enabled_ids = []
    for key, enabled in u["asset_types"].items():
        if enabled:
            enabled_ids.extend(ASSET_TYPES_MAP[key])

    if not enabled_ids:
        await message.answer("❌ Включи хотя бы один тип предметов в /settings")
        return

    msg = await message.answer("⏳ Загружаю инвентарь...")

    # Загружаем инвентарь
    try:
        items = await get_inventory(u["cookie"], u["roblox_id"], enabled_ids)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка загрузки инвентаря:\n<code>{e}</code>")
        return

    if not items:
        await msg.edit_text(
            "📦 <b>Инвентарь пуст или закрыт.</b>\n\n"
            "<i>Убедись что инвентарь публичный в настройках Roblox.</i>"
        )
        return

    # Убираем дубликаты
    seen = set()
    unique_items = []
    for item in items:
        aid = item.get("assetId")
        if aid and aid not in seen:
            seen.add(aid)
            unique_items.append(item)

    total = len(unique_items)
    await msg.edit_text(f"⏳ Найдено {total} уникальных предметов. Проверяю каждый...\n<i>Это может занять время</i>")

    offsale_items = []
    promo_items   = []
    year_from     = u["year_from"]
    year_to       = u["year_to"]

    for i, item in enumerate(unique_items):
        # Прогресс каждые 15 предметов
        if i > 0 and i % 15 == 0:
            await msg.edit_text(f"⏳ Проверено {i}/{total} предметов...")

        asset_id = item.get("assetId")
        if not asset_id:
            continue

        details = await get_asset_details(asset_id)
        if not details:
            continue

        is_for_sale = details.get("IsForSale", True)

        # Нас интересуют только ОФФСЕЙЛ предметы
        if is_for_sale:
            continue

        # Парсим дату создания
        created_str = details.get("Created", "")
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            year = created.year
        except Exception:
            year = 0

        # Фильтр по годам
        if year and not (year_from <= year <= year_to):
            continue

        name  = details.get("Name", "Неизвестно")
        price = details.get("PriceInRobux")
        is_limited        = details.get("IsLimited", False)
        is_limited_unique = details.get("IsLimitedUnique", False)

        item_data = {
            "id":       asset_id,
            "name":     name,
            "year":     year,
            "price":    price,
            "limited":  is_limited,
            "unique":   is_limited_unique,
        }

        # Промо = бесплатный оффсейл предмет (не лимитка)
        if u["check_promo"] and price == 0 and not is_limited:
            promo_items.append(item_data)
        else:
            offsale_items.append(item_data)

    # ===== Генерация отчёта =====
    if not offsale_items and not promo_items:
        await msg.edit_text(
            f"🔍 <b>Проверка завершена!</b>\n\n"
            f"📅 Период: {year_from} – {year_to}\n"
            f"📦 Проверено предметов: {total}\n\n"
            f"😔 Оффсейл предметов в этом диапазоне лет <b>не найдено</b>."
        )
        return

    # Сортировка по году
    offsale_items.sort(key=lambda x: x["year"] or 9999)

    report_lines = [
        "📋 <b>Отчёт проверки инвентаря</b>",
        f"📅 Период: <b>{year_from} – {year_to}</b>",
        f"📦 Проверено предметов: <b>{total}</b>",
        f"🛑 Оффсейл найдено: <b>{len(offsale_items)}</b>",
    ]
    if u["check_promo"]:
        report_lines.append(f"🎁 Промо найдено: <b>{len(promo_items)}</b>")
    report_lines.append("")

    # Оффсейл — группировка по годам
    if offsale_items:
        report_lines.append("🛑 <b>ОФФСЕЙЛ ПРЕДМЕТЫ:</b>")
        by_year: dict[int, list] = {}
        for item in offsale_items:
            y = item["year"] or 0
            by_year.setdefault(y, []).append(item)

        for year in sorted(by_year.keys()):
            label = str(year) if year else "Год неизвестен"
            report_lines.append(f"\n📆 <b>{label}:</b>")
            for item in by_year[year]:
                badges = ""
                if item["unique"]:  badges += " 🔴 LimitedU"
                elif item["limited"]: badges += " 🟡 Limited"
                link = f'<a href="https://www.roblox.com/catalog/{item["id"]}">{item["name"]}</a>'
                report_lines.append(f"  • {link}{badges}")

    # Промо-предметы
    if promo_items and u["check_promo"]:
        report_lines.append("\n🎁 <b>ПРОМО-ПРЕДМЕТЫ (бесплатные оффсейл):</b>")
        for item in sorted(promo_items, key=lambda x: x["year"] or 9999):
            year_label = f" ({item['year']})" if item["year"] else ""
            link = f'<a href="https://www.roblox.com/catalog/{item["id"]}">{item["name"]}</a>'
            report_lines.append(f"  • {link}{year_label}")

    full_report = "\n".join(report_lines)

    # Telegram limit 4096 — разбиваем при необходимости
    if len(full_report) <= 4000:
        await msg.edit_text(
            full_report,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    else:
        # Разбиваем на части по 3800 символов
        chunks, current = [], ""
        for line in report_lines:
            if len(current) + len(line) + 1 > 3800:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)

        await msg.edit_text(
            chunks[0],
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        for chunk in chunks[1:]:
            await message.answer(
                chunk,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )


# Авто-определение cookie если пользователь просто вставил его в чат
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    text = message.text.strip()
    # Выглядит как Roblox cookie (длинная строка с типичными символами)
    if len(text) > 100 and ("_|WARNING" in text or text.startswith("_|")):
        u = get_user(message.from_user.id)
        cookie = text
        if "_|WARNING" in cookie and "--|" in cookie:
            cookie = cookie.split("--|", 1)[-1]

        msg = await message.answer("⏳ Определил cookie, проверяю...")
        roblox_id = await get_roblox_user_id(cookie)
        if roblox_id:
            u["cookie"]    = cookie
            u["roblox_id"] = roblox_id
            await msg.edit_text(
                f"✅ <b>Авторизован!</b> Roblox ID: <code>{roblox_id}</code>\n\n"
                f"Используй /check или /settings"
            )
        else:
            await msg.edit_text("❌ Не удалось авторизоваться. Проверь cookie.")


# ===== Запуск =====
async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
