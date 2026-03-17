import asyncio
import io
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

# ================================================================
#  ⚙️ НАСТРОЙКИ — МЕНЯЙ ТОЛЬКО ЗДЕСЬ
# ================================================================
BOT_TOKEN   = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_ID    = 5883796026   # Твой Telegram ID (узнать: @userinfobot)

YEAR_FROM   = 2012        # Предметы созданные С этого года
YEAR_TO     = 2024        # Предметы созданные ДО этого года
CHECK_PROMO = True        # Искать промо-предметы

ASSET_TYPES = {
    "faces":    True,     # 👤 Лица      (тип 18)
    "hats":     True,     # 🎩 Шапки     (тип 8)
    "hair":     True,     # 💇 Волосы     (тип 41)
    "neck":     True,     # 📿 Шея       (тип 42)
    "shoulder": True,     # 🦴 Плечи     (тип 45)
    "front":    True,     # 🧣 Передние  (тип 46)
    "back":     True,     # 🎒 Задние    (тип 47)
    "waist":    True,     # 🩱 Пояс      (тип 43)
    "gear":     True,     # ⚔️ Снаряжение (тип 11)
    "clothing": False,    # 👕 Одежда    (типы 12,13)
}
# ================================================================

# Roblox asset type IDs (по одному за запрос через v1 API)
ASSET_TYPE_IDS = {
    "faces":    [18],
    "hats":     [8],
    "hair":     [41],
    "neck":     [42],
    "shoulder": [45],
    "front":    [46],
    "back":     [47],
    "waist":    [43],
    "gear":     [11],
    "clothing": [12, 13],
}

ASSET_LABELS = {
    "faces":    "👤 Лица",
    "hats":     "🎩 Шапки",
    "hair":     "💇 Волосы",
    "neck":     "📿 Шея",
    "shoulder": "🦴 Плечи",
    "front":    "🧣 Передние",
    "back":     "🎒 Задние",
    "waist":    "🩱 Пояс",
    "gear":     "⚔️ Снаряжение",
    "clothing": "👕 Одежда",
}

CODE_ITEMS = {
    189934238:  "Fireman",
    4342314393: "Rainbow Squid Unicorn",
    263405835:  "Chicken Headrow",
    263405839:  "Black Iron Tentacles",
    263405842:  "Code Review Specs",
    263405844:  "Stickpack",
    263405846:  "Shark Fin",
    263405849:  "Federation Necklace",
    263405851:  "Backup Mr. Robot",
    263405853:  "Dark Lord of SQL",
    263405855:  "Roblox visor 1",
    263405857:  "Silver Bow Tie",
    263405859:  "Dodgeball Helmet",
    263405861:  "Shoulder Raccoon",
    263405863:  "Dued1",
    263405865:  "Pauldrons",
    263405867:  "Octember Encore",
    263405869:  "Umberhorns",
    128540404:  "Police Cap",
    128540406:  "American Baseball Cap",
    128540408:  "Orange Cap",
    218491492:  "Navy Queen otn",
    128540410:  "Zombie Knit",
    128540412:  "Epic Miners Headlamp",
    128540414:  "Beast Mode Bandana",
    162295698:  "Golden Reingment",
    128540416:  "Beast Scythe",
    128540418:  "Hare Hoodie",
    128540420:  "Diamond Tiara",
    128540422:  "Callmehbob",
    128540424:  "Sword Cane",
    128540426:  "Selfie Stick",
    128540428:  "Phantom Forces Combat Knife",
    128540430:  "Golden Horns",
    128540432:  "The Soup is Dry",
    128540434:  "Monster Grumpy Face",
    128540436:  "Elegant Evening Face",
    128540438:  "Super Pink Make-Up",
    128540440:  "Cyanskeleface",
    128540442:  "Pizza Face",
    128540444:  "Bakonetta",
    128540446:  "Isabella",
    128540448:  "Mon Cheri",
    128540450:  "Rogueish Good Looks",
    128540452:  "Mixologist's Smile",
    128540454:  "BiteyMcFace",
    128540456:  "Performing Mime",
    128540458:  "Rainbow Spirit Face",
    128540460:  "Mermaid Mystique",
    128540462:  "Starry Eyes Sparkling",
    128540464:  "Sparkling Friendly Wink",
    128540466:  "Kandi's Sprinkle Face",
    128540468:  "Tears of Sorrow",
    128540470:  "Fashion Face",
    128540472:  "Princess Alexis",
    128540474:  "Otakufaic",
    128540476:  "Pop Queen",
    128540478:  "Assassin Face",
    128540480:  "Sapphire Gaze",
    128540482:  "Persephone's E-Girl",
    128540484:  "Arachnid Queen",
    128540486:  "Rainbow Barf Face",
    128540488:  "Star Sorority",
    128540490:  "Tsundere Face",
    128540492:  "Winning Smile",
}

# ================================================================
#  ИНИЦИАЛИЗАЦИЯ
# ================================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp  = Dispatcher(storage=MemoryStorage())

settings = {
    "year_from":   YEAR_FROM,
    "year_to":     YEAR_TO,
    "check_promo": CHECK_PROMO,
    "asset_types": dict(ASSET_TYPES),
}


class SetYear(StatesGroup):
    from_year = State()
    to_year   = State()


# ================================================================
#  ROBLOX API HELPERS
# ================================================================
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def ch(cookie: str) -> dict:
    return {"Cookie": f".ROBLOSECURITY={cookie}", "User-Agent": UA, "Accept": "application/json"}

def clean(raw: str) -> str:
    c = raw.strip()
    if "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1]
    return c.strip()


async def get_user_info(session: aiohttp.ClientSession, cookie: str) -> dict | None:
    """Авторизация — получаем ID и имя"""
    try:
        async with session.get(
            "https://users.roblox.com/v1/users/authenticated",
            headers=ch(cookie), timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status == 200:
                d = await r.json()
                return {"id": d["id"], "name": d.get("displayName") or d.get("name", "?")}
    except Exception:
        pass
    return None


async def get_csrf_token(session: aiohttp.ClientSession, cookie: str) -> str | None:
    """Получаем X-CSRF-Token через любой POST запрос"""
    try:
        async with session.post(
            "https://auth.roblox.com/v2/logout",
            headers=ch(cookie), timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            return r.headers.get("x-csrf-token")
    except Exception:
        pass
    return None


async def open_inventory(session: aiohttp.ClientSession, cookie: str) -> None:
    """Открываем инвентарь на публичный (Everyone)"""
    csrf = await get_csrf_token(session, cookie)
    if not csrf:
        return
    try:
        async with session.post(
            "https://accountsettings.roblox.com/v1/inventory-privacy",
            json={"inventoryPrivacy": 1},
            headers={**ch(cookie), "x-csrf-token": csrf, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=12)
        ) as r:
            pass  # 200 или 204 — всё ок
    except Exception:
        pass


async def get_inventory_by_type(
    session: aiohttp.ClientSession,
    cookie: str,
    user_id: int,
    asset_type_id: int
) -> list:
    """
    Получает инвентарь по ОДНОМУ типу предмета через v1 API.
    Возвращает список словарей с полями assetId, name и т.д.
    """
    items  = []
    cursor = ""
    url_base = f"https://inventory.roblox.com/v1/users/{user_id}/inventory/{asset_type_id}"

    while True:
        params = {"pageSize": 100, "sortOrder": "Asc"}
        if cursor:
            params["cursor"] = cursor
        try:
            async with session.get(
                url_base, params=params,
                headers=ch(cookie),
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                if r.status == 403:
                    # Инвентарь закрыт — попробуем ещё раз через 1 сек
                    await asyncio.sleep(1)
                    async with session.get(
                        url_base, params=params,
                        headers=ch(cookie),
                        timeout=aiohttp.ClientTimeout(total=20)
                    ) as r2:
                        if r2.status != 200:
                            break
                        data   = await r2.json()
                elif r.status != 200:
                    break
                else:
                    data = await r.json()

                page_items = data.get("data", [])
                items.extend(page_items)
                cursor = data.get("nextPageCursor") or ""
                if not cursor:
                    break
        except Exception:
            break
        await asyncio.sleep(0.4)

    return items


async def catalog_batch_details(session: aiohttp.ClientSession, asset_ids: list[int]) -> dict:
    """
    Батч-запрос к catalog API — до 120 предметов за раз.
    Возвращает {asset_id: {...details...}}
    """
    result = {}
    chunk_size = 120

    for i in range(0, len(asset_ids), chunk_size):
        chunk = asset_ids[i:i + chunk_size]
        payload = {"items": [{"itemType": "Asset", "id": aid} for aid in chunk]}
        try:
            async with session.post(
                "https://catalog.roblox.com/v1/catalog/items/details",
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for item in data.get("data", []):
                        aid = item.get("id")
                        if aid:
                            result[aid] = item
        except Exception:
            pass
        await asyncio.sleep(0.3)

    return result


async def owns_item(session: aiohttp.ClientSession, cookie: str, user_id: int, asset_id: int) -> bool:
    """Проверяет владение конкретным предметом"""
    try:
        async with session.get(
            f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/{asset_id}",
            headers=ch(cookie),
            timeout=aiohttp.ClientTimeout(total=12)
        ) as r:
            if r.status == 200:
                d = await r.json()
                return len(d.get("data", [])) > 0
    except Exception:
        pass
    return False


# ================================================================
#  ГЛАВНАЯ ФУНКЦИЯ ПРОВЕРКИ
# ================================================================
async def check_cookie_full(cookie: str, status_msg: Message) -> dict:
    result = {
        "valid":       False,
        "user_id":     None,
        "username":    None,
        "offsale":     [],
        "promo_found": [],
        "inv_total":   0,
    }

    async with aiohttp.ClientSession() as session:

        # 1. Авторизация
        user_info = await get_user_info(session, cookie)
        if not user_info:
            return result

        result.update({"valid": True, "user_id": user_info["id"], "username": user_info["name"]})
        uid   = user_info["id"]
        uname = user_info["name"]

        # 2. Открываем инвентарь
        await status_msg.edit_text(f"✅ <b>{uname}</b>\n🔓 Открываю инвентарь...")
        await open_inventory(session, cookie)
        await asyncio.sleep(1)

        # 3. Промо-предметы (прямая проверка владения)
        if settings["check_promo"]:
            total_p = len(CODE_ITEMS)
            await status_msg.edit_text(f"✅ <b>{uname}</b>\n🎁 Проверяю промо (0/{total_p})...")
            for i, (asset_id, name) in enumerate(CODE_ITEMS.items()):
                if i % 10 == 0:
                    try:
                        await status_msg.edit_text(
                            f"✅ <b>{uname}</b>\n🎁 Промо: {i}/{total_p}..."
                        )
                    except Exception:
                        pass
                if await owns_item(session, cookie, uid, asset_id):
                    result["promo_found"].append({"id": asset_id, "name": name})
                await asyncio.sleep(0.2)

        # 4. Сбор инвентаря по типам
        all_asset_ids = set()
        enabled_type_ids = []
        for key, on in settings["asset_types"].items():
            if on:
                enabled_type_ids.extend(ASSET_TYPE_IDS[key])

        if enabled_type_ids:
            await status_msg.edit_text(f"✅ <b>{uname}</b>\n📦 Загружаю инвентарь...")

            for type_id in enabled_type_ids:
                items = await get_inventory_by_type(session, cookie, uid, type_id)
                for item in items:
                    aid = item.get("assetId") or item.get("id")
                    if aid:
                        all_asset_ids.add(int(aid))
                await asyncio.sleep(0.3)

            result["inv_total"] = len(all_asset_ids)
            await status_msg.edit_text(
                f"✅ <b>{uname}</b>\n"
                f"🔍 Проверяю {len(all_asset_ids)} предметов на оффсейл..."
            )

            # 5. Батч-проверка через catalog API
            asset_id_list = list(all_asset_ids)
            catalog_data  = await catalog_batch_details(session, asset_id_list)

            for asset_id, details in catalog_data.items():
                # priceStatus: "Off Sale" | "No Price" | "Free" | числовая цена
                price_status = details.get("priceStatus", "")
                is_offsale   = (price_status == "Off Sale")

                if not is_offsale:
                    continue

                # Фильтр по году через поле createdUtc или itemStatus
                year = 0
                created_str = details.get("createdUtc") or details.get("created") or ""
                if created_str:
                    try:
                        dt   = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        year = dt.year
                    except Exception:
                        pass

                if year and not (settings["year_from"] <= year <= settings["year_to"]):
                    continue

                is_limited = "Limited" in str(details.get("itemRestrictions", []))
                is_unique  = "LimitedUnique" in str(details.get("itemRestrictions", []))

                result["offsale"].append({
                    "id":      asset_id,
                    "name":    details.get("name") or details.get("Name", "?"),
                    "year":    year,
                    "limited": is_limited,
                    "unique":  is_unique,
                })

    return result


# ================================================================
#  ОТЧЁТ
# ================================================================
def build_report(result: dict) -> str:
    uid, uname = result["user_id"], result["username"]
    offsale, promo = result["offsale"], result["promo_found"]

    lines = [
        "📋 <b>Отчёт проверки</b>",
        f'👤 <a href="https://www.roblox.com/users/{uid}/profile">{uname}</a>  (ID: {uid})',
        f"📅 Период: <b>{settings['year_from']} – {settings['year_to']}</b>",
        f"📦 Предметов в инвентаре: <b>{result.get('inv_total', 0)}</b>",
        "",
    ]

    if offsale:
        lines.append(f"🛑 <b>Оффсейл — {len(offsale)} шт.:</b>")
        by_year: dict = {}
        for it in sorted(offsale, key=lambda x: x["year"] or 9999):
            by_year.setdefault(it["year"] or 0, []).append(it)
        for year in sorted(by_year):
            lines.append(f"\n  📆 <b>{year or 'Год неизвестен'}:</b>")
            for it in by_year[year]:
                badge = " 🔴LimitedU" if it["unique"] else (" 🟡Limited" if it["limited"] else "")
                lines.append(
                    f'    • <a href="https://www.roblox.com/catalog/{it["id"]}">'
                    f'{it["name"]}</a>{badge}'
                )
    else:
        lines.append(f"🛑 Оффсейл предметов <b>не найдено</b>")

    lines.append("")

    if settings["check_promo"]:
        if promo:
            lines.append(f"🎁 <b>Промо — {len(promo)} шт.:</b>")
            for it in promo:
                lines.append(
                    f'    • <a href="https://www.roblox.com/catalog/{it["id"]}">'
                    f'{it["name"]}</a>'
                )
        else:
            lines.append("🎁 Промо-предметов <b>не найдено</b>")

    return "\n".join(lines)


# ================================================================
#  ЗАПУСК ПРОВЕРКИ
# ================================================================
async def run_check(message: Message, cookie: str) -> None:
    cookie = clean(cookie)
    if len(cookie) < 50:
        await message.answer("❌ Cookie слишком короткий, пропускаю.")
        return

    status_msg = await message.answer("⏳ <b>Авторизация...</b>")
    try:
        result = await check_cookie_full(cookie, status_msg)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка:\n<code>{e}</code>")
        return

    if not result["valid"]:
        await status_msg.edit_text("❌ <b>Невалидный cookie</b>")
        return

    report = build_report(result)

    if len(report) > 3800:
        await status_msg.delete()
        buf = io.BytesIO(report.encode("utf-8"))
        buf.name = f"report_{result['user_id']}.txt"
        await message.answer_document(buf, caption=f"📋 {result['username']} — отчёт")  # type: ignore
    else:
        await status_msg.edit_text(
            report,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )


# ================================================================
#  КЛАВИАТУРА НАСТРОЕК
# ================================================================
def settings_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"tog_{key}")])
    promo_icon = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text=f"{promo_icon} 🎁 Промо-предметы", callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text=f"📅 С {settings['year_from']}", callback_data="set_yf"),
        InlineKeyboardButton(text=f"📅 По {settings['year_to']}",  callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(obj) -> bool:
    return obj.from_user.id == ADMIN_ID


# ================================================================
#  ХЕНДЛЕРЫ
# ================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message): return
    await message.answer(
        "🎮 <b>Roblox Offsale Checker</b>\n\n"
        "Отправь мне:\n"
        "• <b>Текст</b> — один или несколько cookie (каждый с новой строки)\n"
        "• <b>.txt файл</b> — один cookie на строку\n\n"
        "⚙️ /settings — настройки\n"
        "ℹ️ /info — текущие настройки"
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [ASSET_LABELS[k] for k, v in settings["asset_types"].items() if v]
    await message.answer(
        "ℹ️ <b>Текущие настройки</b>\n\n"
        f"📅 Годы: <b>{settings['year_from']} – {settings['year_to']}</b>\n"
        f"🎁 Промо: {'✅' if settings['check_promo'] else '❌'}\n"
        f"📦 Типы:\n" + "\n".join(f"  • {t}" for t in types_on)
    )


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if not is_admin(message): return
    await message.answer("⚙️ <b>Настройки поиска</b>", reply_markup=settings_kb())


@dp.callback_query(F.data.startswith("tog_"))
async def cb_toggle(cb: CallbackQuery):
    if not is_admin(cb): return await cb.answer("⛔")
    key = cb.data.replace("tog_", "")
    if key == "promo":
        settings["check_promo"] = not settings["check_promo"]
    elif key in settings["asset_types"]:
        settings["asset_types"][key] = not settings["asset_types"][key]
    await cb.message.edit_reply_markup(reply_markup=settings_kb())
    await cb.answer("✅")


@dp.callback_query(F.data == "set_yf")
async def cb_yf(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer(f"📅 Введи начальный год (сейчас: {settings['year_from']}):")
    await state.set_state(SetYear.from_year)
    await cb.answer()


@dp.callback_query(F.data == "set_yt")
async def cb_yt(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer(f"📅 Введи конечный год (сейчас: {settings['year_to']}):")
    await state.set_state(SetYear.to_year)
    await cb.answer()


@dp.message(SetYear.from_year)
async def save_yf(message: Message, state: FSMContext):
    try:
        y = int(message.text.strip())
        assert 2006 <= y <= 2030
        settings["year_from"] = y
        await message.answer(f"✅ Начальный год: <b>{y}</b>")
        await state.clear()
    except (ValueError, AssertionError):
        await message.answer("❌ Введи число от 2006 до 2030")


@dp.message(SetYear.to_year)
async def save_yt(message: Message, state: FSMContext):
    try:
        y = int(message.text.strip())
        assert 2006 <= y <= 2030
        settings["year_to"] = y
        await message.answer(f"✅ Конечный год: <b>{y}</b>")
        await state.clear()
    except (ValueError, AssertionError):
        await message.answer("❌ Введи число от 2006 до 2030")


@dp.message(F.document)
async def handle_file(message: Message):
    if not is_admin(message): return
    doc = message.document
    if not doc.file_name.endswith(".txt"):  # type: ignore
        await message.answer("❌ Нужен .txt файл (один cookie на строку)")
        return

    file = await bot.get_file(doc.file_id)  # type: ignore
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)  # type: ignore
    buf.seek(0)

    lines   = buf.read().decode("utf-8", errors="ignore").splitlines()
    cookies = [l.strip() for l in lines if len(l.strip()) > 50]

    if not cookies:
        await message.answer("❌ Не нашёл cookie в файле")
        return

    await message.answer(f"📂 Найдено <b>{len(cookies)}</b> cookie. Начинаю...")
    for i, cookie in enumerate(cookies, 1):
        hdr = await message.answer(f"🔄 <b>{i}/{len(cookies)}</b>")
        await run_check(message, cookie)
        try:
            await hdr.delete()
        except Exception:
            pass
        await asyncio.sleep(1)
    await message.answer(f"✅ <b>Готово!</b> Проверено {len(cookies)} аккаунтов.")


@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return

    lines = [l.strip() for l in message.text.splitlines() if len(l.strip()) > 50]
    if not lines:
        await message.answer("ℹ️ Отправь cookie текстом или .txt файлом.\n/settings — настройки")
        return

    if len(lines) == 1:
        await run_check(message, lines[0])
    else:
        await message.answer(f"📋 Найдено <b>{len(lines)}</b> cookie. Начинаю...")
        for i, cookie in enumerate(lines, 1):
            hdr = await message.answer(f"🔄 <b>{i}/{len(lines)}</b>")
            await run_check(message, cookie)
            try:
                await hdr.delete()
            except Exception:
                pass
            await asyncio.sleep(1)
        await message.answer(f"✅ Готово! Проверено <b>{len(lines)}</b> аккаунтов.")


# ================================================================
async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
