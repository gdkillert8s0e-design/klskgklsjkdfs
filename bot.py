import asyncio
import aiohttp
import aiosqlite
import logging
import re
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import tempfile

# ========== НАСТРОЙКИ ==========
BOT_TOKEN  = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
OWNER_ID   = 5883796026
# Дополнительные админы через запятую: "123456,789012"
EXTRA_ADMINS = ""
# ================================

def get_admin_ids():
    ids = [OWNER_ID]
    for s in EXTRA_ADMINS.split(","):
        s = s.strip()
        if s.isdigit():
            ids.append(int(s))
    return ids

ADMIN_IDS = get_admin_ids()
REQUESTS_PER_SECOND = 3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

dp      = Dispatcher(storage=MemoryStorage())
DB_PATH = "roblox_checker.db"
bot     = None

user_settings: dict = {}

# ========== Премиум эмодзи ==========
def tge(eid: str, fb: str = '') -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'

EM_SEARCH = tge('6032850693348399258', '🔍')
EM_GEAR   = tge('5870982283724328568', '⚙️')
EM_STATS  = tge('5870921681735781843', '📊')
EM_HAT    = tge('5884479287171485878', '🎩')
EM_OK     = tge('5870633910337015697', '✅')
EM_ERR    = tge('5870657884844462243', '❌')
EM_LINK   = tge('5769289093221454192', '🔗')
EM_CAL    = tge('5890937706803894250', '📅')
EM_USER   = tge('5870994129244131212', '👤')
EM_LOAD   = tge('5345906554510012647', '🔄')
EM_ADMIN  = tge('6030400221232501136', '🤖')
EM_CODE   = tge('5940433880585605708', '💎')
EM_BACK   = tge('5893057118545646106', '◀️')
EM_FIRE   = tge('5199457120428249992', '🔥')
EM_BACK2  = tge('6039519841256214245', '⬅️')

# ========== Список кодовых вещей ==========
CODE_ITEMS = {
    "fireman", "rainbow squid unicorn", "chicken headrow",
    "black iron tentacles", "code review specs", "stickpack",
    "shark fin", "federation necklace", "backup mr. robot",
    "dark lord of sql", "roblox visor 1", "silver bow tie",
    "dodgeball helmet", "shoulder raccoon", "dued1", "pauldrons",
    "octember encore", "umberhorns", "police cap",
    "american baseball cap", "orange cap", "navy queen otn",
    "zombie knit", "epic miners headlamp", "beast mode bandana",
    "golden reingment", "beast scythe", "hare hoodie",
    "diamond tiara", "callmehbob", "sword cane", "selfie stick",
    "phantom forces combat knife", "golden horns", "the soup is dry",
    "monster grumpy face", "elegant evening face",
    "super pink make-up", "cyanskeleface", "pizza face",
    "bakonetta", "isabella", "mon cheri", "rogueish good looks",
    "mixologist's smile", "biteymcface", "performing mime",
    "rainbow spirit face", "mermaid mystique",
    "starry eyes sparkling", "sparkling friendly wink",
    "kandi's sprinkle face", "tears of sorrow", "fashion face",
    "princess alexis", "otakufaic", "pop queen", "assassin face",
    "sapphire gaze", "persephone's e-girl", "arachnid queen",
    "rainbow barf face", "star sorority", "tsundere face",
    "winning smile",
}

def is_code_item(name: str) -> bool:
    return name.strip().lower() in CODE_ITEMS

# ========== БД ==========
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items_cache (
                asset_id INTEGER PRIMARY KEY,
                name TEXT, type INTEGER, created TEXT,
                last_updated TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY, value INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await db.execute('INSERT OR IGNORE INTO stats VALUES ("total_checks", 0)')
        await db.execute('INSERT OR IGNORE INTO stats VALUES ("rare_finds", 0)')
        await db.execute('INSERT OR IGNORE INTO admins VALUES (?)', (OWNER_ID,))
        await db.commit()
    logger.info("БД инициализирована")

async def get_all_admins() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute('SELECT user_id FROM admins')).fetchall()
    ids = [r[0] for r in rows] + get_admin_ids()
    return list(set(ids))

async def add_admin(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO admins VALUES (?)', (uid,))
        await db.commit()

async def remove_admin(uid: int):
    if uid == OWNER_ID:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM admins WHERE user_id = ?', (uid,))
        await db.commit()
    return True

# ========== Roblox API ==========
async def fetch_json(session: aiohttp.ClientSession, url: str, headers=None):
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
            logger.warning(f"HTTP {r.status}: {url}")
    except Exception as e:
        logger.error(f"fetch_json error: {e}")
    return None

async def get_user_id_from_cookie(cookie: str):
    headers = {'Cookie': f'.ROBLOSECURITY={cookie}'}
    async with aiohttp.ClientSession() as s:
        data = await fetch_json(s, 'https://users.roblox.com/v1/users/authenticated', headers)
        if data and 'id' in data:
            return data['id'], data.get('name')
    return None, None

async def get_user_info(user_id: int, session: aiohttp.ClientSession) -> dict:
    data = await fetch_json(session, f'https://users.roblox.com/v1/users/{user_id}')
    if not data:
        return {}
    return {
        'created':      data.get('created', ''),
        'age_verified': data.get('hasVerifiedBadge', False),
    }

async def get_inventory_v2(user_id: int, session: aiohttp.ClientSession, cookie: str) -> list:
    """
    Перебирает несколько типов через v1/users/{id}/inventory
    Это более надёжный эндпоинт чем v2 с assetTypes параметром.
    """
    headers = {'Cookie': f'.ROBLOSECURITY={cookie}', 'Accept': 'application/json'}
    # assetTypeId: 8=Hat, 41=HairAccessory, 18=Face, 19=Gear, 42=NeckAccessory
    asset_type_ids = [8, 41, 18, 19, 42]
    all_items = []

    for type_id in asset_type_ids:
        cursor = ''
        while True:
            url = (f'https://inventory.roblox.com/v1/users/{user_id}/inventory/{type_id}'
                   f'?limit=100&sortOrder=Asc' + (f'&cursor={cursor}' if cursor else ''))
            try:
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get('data', [])
                        for item in items:
                            item['_assetTypeId'] = type_id
                        all_items.extend(items)
                        cursor = data.get('nextPageCursor') or ''
                        if not cursor:
                            break
                    else:
                        logger.warning(f"Inventory type {type_id}: HTTP {resp.status}")
                        break
            except Exception as e:
                logger.error(f"get_inventory error type {type_id}: {e}")
                break

    logger.info(f"Инвентарь: всего {len(all_items)} предметов")
    return all_items

async def get_item_details(asset_id: int, session: aiohttp.ClientSession) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            'SELECT name, type, created FROM items_cache WHERE asset_id = ?', (asset_id,)
        )).fetchone()
        if row:
            return {'name': row[0], 'type': row[1], 'created': row[2]}

    data = await fetch_json(session, f'https://economy.roblox.com/v2/assets/{asset_id}/details')
    if not data:
        return None

    item = {
        'name':    data.get('Name', 'Unknown'),
        'type':    data.get('AssetTypeId'),
        'created': data.get('Created', ''),
    }
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO items_cache (asset_id, name, type, created, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', (asset_id, item['name'], item['type'], item['created'], datetime.now().isoformat()))
        await db.commit()
    return item

async def check_account(cookie: str, settings: dict) -> dict:
    result = {
        'error': None, 'user_id': None, 'username': None,
        'created': None, 'age_verified': False,
        'items': [], 'code_items': [], 'rare_count': 0,
    }

    async with aiohttp.ClientSession() as session:
        user_id, username = await get_user_id_from_cookie(cookie)
        if not user_id:
            result['error'] = 'Недействительные куки'
            return result

        result['user_id']  = user_id
        result['username'] = username
        logger.info(f"Проверяем: {username} ({user_id})")

        info = await get_user_info(user_id, session)
        result['created']      = info.get('created', '')
        result['age_verified'] = info.get('age_verified', False)

        inventory = await get_inventory_v2(user_id, session, cookie)

        target_types = settings.get('item_types', [8, 41, 18, 19])
        y1, y2       = settings.get('year_range', (2006, 2016))
        show_codes   = settings.get('show_code_items', True)

        sem = asyncio.Semaphore(REQUESTS_PER_SECOND)

        async def process_item(item):
            async with sem:
                asset_id = item.get('assetId') or item.get('id')
                if not asset_id:
                    return
                details = await get_item_details(asset_id, session)
                if not details:
                    return
                if details['type'] not in target_types:
                    return

                name = details['name']

                # Кодовые вещи — отдельно
                if show_codes and is_code_item(name):
                    result['code_items'].append({
                        'id':   asset_id,
                        'name': name,
                    })
                    return

                # Старые вещи по году
                if details['created']:
                    try:
                        year = int(details['created'][:4])
                        if y1 <= year <= y2:
                            result['items'].append({
                                'id':      asset_id,
                                'name':    name,
                                'type':    details['type'],
                                'created': details['created'],
                            })
                            logger.info(f"Старый предмет: {name} ({year})")
                    except Exception:
                        pass

        tasks = [process_item(i) for i in inventory]
        await asyncio.gather(*tasks)

        result['items'].sort(key=lambda x: x['created'])
        result['rare_count'] = len(result['items'])
        return result

# ========== Состояния FSM ==========
class Settings(StatesGroup):
    waiting_for_years = State()
    waiting_for_admins = State()

# ========== Клавиатуры ==========
def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Проверить куки",    callback_data="check_cookie", icon_custom_emoji_id="6032850693348399258")],
        [InlineKeyboardButton(text="Настройки",         callback_data="settings",     icon_custom_emoji_id="5870982283724328568")],
        [InlineKeyboardButton(text="Статистика",        callback_data="stats",        icon_custom_emoji_id="5870921681735781843")],
        [InlineKeyboardButton(text="Управление админами",callback_data="admin_panel", icon_custom_emoji_id="6030400221232501136")],
    ])

def settings_keyboard(uid: int):
    settings  = user_settings.get(uid, {})
    y1, y2    = settings.get('year_range', (2006, 2016))
    show_code = settings.get('show_code_items', True)
    code_label = "Кодовые вещи: ВКЛ" if show_code else "Кодовые вещи: ВЫКЛ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Диапазон лет: {y1}-{y2}", callback_data="set_years",    icon_custom_emoji_id="5890937706803894250")],
        [InlineKeyboardButton(text="Типы предметов",            callback_data="set_types",    icon_custom_emoji_id="5884479287171485878")],
        [InlineKeyboardButton(text=code_label,                  callback_data="toggle_codes", icon_custom_emoji_id="5940433880585605708")],
        [InlineKeyboardButton(text="Назад",                     callback_data="main_menu",    icon_custom_emoji_id="5893057118545646106")],
    ])

def types_keyboard(current_types: list):
    names = {8: "Шляпы", 41: "Причёски", 18: "Лица", 19: "Гиры", 42: "Аксессуары"}
    rows  = []
    for tid, name in names.items():
        status = "✅" if tid in current_types else "⬜"
        rows.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"toggle_type_{tid}")])
    rows.append([
        InlineKeyboardButton(text="Выбрать всё", callback_data="types_all",  icon_custom_emoji_id="5870633910337015697"),
        InlineKeyboardButton(text="Сбросить",    callback_data="types_none", icon_custom_emoji_id="5870657884844462243"),
    ])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="settings", icon_custom_emoji_id="5893057118545646106")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить админа",  callback_data="add_admin",    icon_custom_emoji_id="5870633910337015697")],
        [InlineKeyboardButton(text="Удалить админа",   callback_data="del_admin",    icon_custom_emoji_id="5870657884844462243")],
        [InlineKeyboardButton(text="Список админов",   callback_data="list_admins",  icon_custom_emoji_id="5870994129244131212")],
        [InlineKeyboardButton(text="Назад",            callback_data="main_menu",    icon_custom_emoji_id="5893057118545646106")],
    ])

def back_to_settings():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к настройкам", callback_data="settings", icon_custom_emoji_id="5893057118545646106")]
    ])

def back_to_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="main_menu", icon_custom_emoji_id="5893057118545646106")]
    ])

# ========== Хелпер настроек ==========
def get_user_settings(uid: int) -> dict:
    if uid not in user_settings:
        user_settings[uid] = {'year_range': (2006, 2016), 'item_types': [8, 41, 18, 19, 42], 'show_code_items': True}
    return user_settings[uid]

# ========== Хендлеры ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    admins = await get_all_admins()
    if message.from_user.id not in admins:
        await message.answer(f"{EM_ERR} Доступ запрещён.", parse_mode=ParseMode.HTML)
        return
    await message.answer(
        f"{EM_HAT} <b>Roblox Account Checker</b>\n\n"
        f"Пришли .ROBLOSECURITY куки (текстом или файлом):\n\n"
        f"{EM_OK} Ник, дата создания, верификация\n"
        f"{EM_HAT} Старые вещи с датами и ссылками\n"
        f"{EM_CODE} Кодовые редкие вещи\n"
        f"{EM_LINK} Прямые ссылки на предметы",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{EM_HAT} <b>Главное меню</b>",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    uid = callback.from_user.id
    get_user_settings(uid)
    await callback.message.edit_text(
        f"{EM_GEAR} <b>Настройки</b>",
        reply_markup=settings_keyboard(uid),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "toggle_codes")
async def cb_toggle_codes(callback: types.CallbackQuery):
    uid = callback.from_user.id
    s   = get_user_settings(uid)
    s['show_code_items'] = not s.get('show_code_items', True)
    status = "включены" if s['show_code_items'] else "выключены"
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(uid))
    try: await callback.answer(f"Кодовые вещи {status}")
    except Exception: pass


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        total = (await (await db.execute('SELECT value FROM stats WHERE key="total_checks"')).fetchone())[0]
        rare  = (await (await db.execute('SELECT value FROM stats WHERE key="rare_finds"')).fetchone())[0]
    admins = await get_all_admins()
    await callback.message.edit_text(
        f"{EM_STATS} <b>Статистика</b>\n\n"
        f"Проверено аккаунтов: <b>{total}</b>\n"
        f"Найдено старых вещей: <b>{rare}</b>\n"
        f"Админов: <b>{len(admins)}</b>",
        reply_markup=back_to_main(),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "set_years")
async def cb_set_years(callback: types.CallbackQuery, state: FSMContext):
    uid     = callback.from_user.id
    y1, y2  = get_user_settings(uid).get('year_range', (2006, 2016))
    await callback.message.edit_text(
        f"{EM_CAL} <b>Диапазон лет</b>\n\n"
        f"Текущий: <b>{y1}–{y2}</b>\n\n"
        f"Введите новый в формате <code>2006-2016</code>:",
        reply_markup=back_to_settings(),
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(Settings.waiting_for_years)
    try: await callback.answer()
    except Exception: pass


@dp.message(Settings.waiting_for_years)
async def process_years(message: types.Message, state: FSMContext):
    admins = await get_all_admins()
    if message.from_user.id not in admins:
        await state.clear(); return
    m = re.match(r'^(\d{4})-(\d{4})$', message.text.strip())
    if not m:
        await message.answer(f"{EM_ERR} Неверный формат. Используйте: <code>2006-2016</code>", parse_mode=ParseMode.HTML)
        return
    y1, y2 = sorted([int(m[1]), int(m[2])])
    get_user_settings(message.from_user.id)['year_range'] = (y1, y2)
    await message.answer(f"{EM_OK} Диапазон установлен: <b>{y1}–{y2}</b>", parse_mode=ParseMode.HTML)
    await state.clear()


@dp.callback_query(F.data == "set_types")
async def cb_set_types(callback: types.CallbackQuery):
    uid     = callback.from_user.id
    current = get_user_settings(uid).get('item_types', [8, 41, 18, 19, 42])
    await callback.message.edit_text(
        f"{EM_HAT} <b>Типы предметов</b>",
        reply_markup=types_keyboard(current),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data.startswith("toggle_type_"))
async def cb_toggle_type(callback: types.CallbackQuery):
    uid     = callback.from_user.id
    tid     = int(callback.data.split("_")[2])
    s       = get_user_settings(uid)
    current = s.get('item_types', [8, 41, 18, 19, 42])
    if tid in current:
        current.remove(tid)
    else:
        current.append(tid)
    s['item_types'] = current
    await callback.message.edit_reply_markup(reply_markup=types_keyboard(current))
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "types_all")
async def cb_types_all(callback: types.CallbackQuery):
    get_user_settings(callback.from_user.id)['item_types'] = [8, 41, 18, 19, 42]
    await callback.message.edit_reply_markup(reply_markup=types_keyboard([8, 41, 18, 19, 42]))
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "types_none")
async def cb_types_none(callback: types.CallbackQuery):
    get_user_settings(callback.from_user.id)['item_types'] = []
    await callback.message.edit_reply_markup(reply_markup=types_keyboard([]))
    try: await callback.answer()
    except Exception: pass


# ========== Управление админами ==========

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: types.CallbackQuery):
    admins = await get_all_admins()
    if callback.from_user.id not in admins:
        try: await callback.answer("Доступ запрещён", show_alert=True)
        except Exception: pass
        return
    await callback.message.edit_text(
        f"{EM_ADMIN} <b>Управление администраторами</b>",
        reply_markup=admin_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "list_admins")
async def cb_list_admins(callback: types.CallbackQuery):
    admins = await get_all_admins()
    text   = f"{EM_ADMIN} <b>Список администраторов</b>\n\n"
    for uid in admins:
        mark = " (владелец)" if uid == OWNER_ID else ""
        text += f"• <code>{uid}</code>{mark}\n"
    await callback.message.edit_text(text, reply_markup=admin_keyboard(), parse_mode=ParseMode.HTML)
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "add_admin")
async def cb_add_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        try: await callback.answer("Только владелец", show_alert=True)
        except Exception: pass
        return
    await callback.message.edit_text(
        f"{EM_ADMIN} Введите Telegram ID нового админа (через запятую для нескольких):\n"
        f"Пример: <code>123456789,987654321</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="admin_panel", icon_custom_emoji_id="5870657884844462243")]
        ]),
        parse_mode=ParseMode.HTML,
    )
    await state.update_data(action="add")
    await state.set_state(Settings.waiting_for_admins)
    try: await callback.answer()
    except Exception: pass


@dp.callback_query(F.data == "del_admin")
async def cb_del_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        try: await callback.answer("Только владелец", show_alert=True)
        except Exception: pass
        return
    await callback.message.edit_text(
        f"{EM_ADMIN} Введите Telegram ID для удаления (через запятую для нескольких):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="admin_panel", icon_custom_emoji_id="5870657884844462243")]
        ]),
        parse_mode=ParseMode.HTML,
    )
    await state.update_data(action="del")
    await state.set_state(Settings.waiting_for_admins)
    try: await callback.answer()
    except Exception: pass


@dp.message(Settings.waiting_for_admins)
async def process_admins(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        await state.clear(); return
    data   = await state.get_data()
    action = data.get("action", "add")
    ids_raw = [s.strip() for s in message.text.split(",")]
    added, removed, errors = [], [], []
    for raw in ids_raw:
        if not raw.isdigit():
            errors.append(raw); continue
        uid = int(raw)
        if action == "add":
            await add_admin(uid); added.append(uid)
        else:
            ok = await remove_admin(uid)
            if ok: removed.append(uid)
            else:  errors.append(f"{uid} (владелец)")
    await state.clear()
    lines = []
    if added:   lines.append(f"{EM_OK} Добавлены: {', '.join(map(str, added))}")
    if removed: lines.append(f"{EM_OK} Удалены: {', '.join(map(str, removed))}")
    if errors:  lines.append(f"{EM_ERR} Ошибки: {', '.join(map(str, errors))}")
    await message.answer('\n'.join(lines) or "Ничего не изменено", parse_mode=ParseMode.HTML)


# ========== Проверка куки ==========

@dp.callback_query(F.data == "check_cookie")
async def cb_check_cookie(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{EM_SEARCH} Отправьте .ROBLOSECURITY куки текстом или .txt файлом.",
        reply_markup=back_to_settings(),
        parse_mode=ParseMode.HTML,
    )
    try: await callback.answer()
    except Exception: pass


@dp.message(F.text)
async def handle_text(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    admins = await get_all_admins()
    if message.from_user.id not in admins:
        return
    text = message.text.strip()
    # Простая проверка — куки обычно длинные и содержат _|WARNING:-DO-NOT-SHARE
    if len(text) < 50 and '_|WARNING' not in text:
        return
    await process_cookie(message, text)


@dp.message(F.document)
async def handle_doc(message: types.Message):
    admins = await get_all_admins()
    if message.from_user.id not in admins:
        return
    file      = await bot.get_file(message.document.file_id)
    file_path = f"temp_{message.document.file_id}.txt"
    await bot.download_file(file.file_path, file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            cookie = f.read().strip()
    finally:
        try: os.remove(file_path)
        except Exception: pass
    await process_cookie(message, cookie)


async def process_cookie(message: types.Message, cookie: str):
    uid      = message.from_user.id
    settings = get_user_settings(uid)

    status = await message.answer(
        f"{EM_LOAD} Проверяю аккаунт...",
        parse_mode=ParseMode.HTML,
    )

    result = await check_account(cookie, settings)

    if result['error']:
        await status.edit_text(f"{EM_ERR} {result['error']}", parse_mode=ParseMode.HTML)
        return

    # ── Обновляем статистику ──
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE stats SET value = value + 1 WHERE key = "total_checks"')
        await db.execute('UPDATE stats SET value = value + ? WHERE key = "rare_finds"', (result['rare_count'],))
        await db.commit()

    # ── Строим отчёт ──
    username = result['username']
    uid_rb   = result['user_id']
    created  = result['created'][:10] if result['created'] else 'Неизвестно'
    age_ver  = 'Да' if result['age_verified'] else 'Нет'

    report  = "=== ROBLOX ACCOUNT REPORT ===\n\n"
    report += f"Ник: {username} (ID: {uid_rb})\n"
    report += f"Создан: {created}\n"
    report += f"Верификация: {age_ver}\n"
    report += f"Профиль: https://www.roblox.com/users/{uid_rb}/profile\n\n"

    # Старые вещи
    if result['items']:
        report += f"СТАРЫЕ ВЕЩИ: {len(result['items'])} шт.\n"
        report += "─" * 40 + "\n"
        for item in result['items']:
            item_date = item['created'][:10] if item['created'] else '?'
            link      = f"https://www.roblox.com/catalog/{item['id']}/"
            report += f"• {item['name']}\n  Дата: {item_date}\n  Ссылка: {link}\n\n"
    else:
        report += "Старых вещей не найдено.\n\n"

    # Кодовые вещи
    if result['code_items']:
        report += f"КОДОВЫЕ ВЕЩИ: {len(result['code_items'])} шт.\n"
        report += "─" * 40 + "\n"
        for item in result['code_items']:
            report += f"• {item['name']}\n"

    # Сохраняем файл
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
        f.write(report)
        tmp = f.name

    # Telegram-сообщение (краткое)
    msg = (
        f"{EM_USER} <b>{username}</b> | ID: <code>{uid_rb}</code>\n"
        f"{EM_CAL} Создан: {created} | Верификация: {age_ver}\n"
        f"{EM_LINK} <a href='https://www.roblox.com/users/{uid_rb}/profile'>Профиль на Roblox</a>\n\n"
    )

    if result['items']:
        msg += f"{EM_HAT} <b>Старых вещей: {len(result['items'])}</b>\n"
        for item in result['items'][:10]:
            d    = item['created'][:7] if item['created'] else '?'
            link = f"https://www.roblox.com/catalog/{item['id']}/"
            msg += f"  • <a href='{link}'>{item['name']}</a> ({d})\n"
        if len(result['items']) > 10:
            msg += f"  <i>...и ещё {len(result['items']) - 10} — смотри файл</i>\n"
    else:
        msg += f"{EM_ERR} Старых вещей не найдено\n"

    if result['code_items']:
        msg += f"\n{EM_CODE} <b>Кодовые вещи: {len(result['code_items'])}</b>\n"
        for item in result['code_items'][:8]:
            msg += f"  • {item['name']}\n"

    await status.edit_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    doc = FSInputFile(tmp, filename=f"{username}_report.txt")
    await message.answer_document(doc)
    try: os.unlink(tmp)
    except Exception: pass


# ========== Запуск ==========
async def main():
    global bot
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await init_db()
    logger.info(f"Бот запущен | Владелец: {OWNER_ID}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
