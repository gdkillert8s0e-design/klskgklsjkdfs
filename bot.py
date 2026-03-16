import asyncio
import aiohttp
import aiosqlite
import logging
import re
import os
import tempfile
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

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
ADMIN_IDS = [5883796026]  # Можно добавлять через запятую
# =================================

# Дефолтные настройки
DEFAULT_SETTINGS = {
    'year_range': (2006, 2016),
    'item_types': [8, 41, 18, 19],
    'show_code_items': True
}

REQUESTS_PER_SECOND = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())
DB_PATH = "roblox_checker.db"
user_settings = {}  # хранилище настроек пользователей

# ----- Список кодовых предметов -----
CODE_ITEMS = {
    189934238: "Fireman",
    4342314393: "Rainbow Squid Unicorn",
    263405835: "Chicken Headrow",
    263405839: "Black Iron Tentacles",
    263405842: "Code Review Specs",
    263405844: "Stickpack",
    263405846: "Shark Fin",
    263405849: "Federation Necklace",
    263405851: "Backup Mr. Robot",
    263405853: "Dark Lord of SQL",
    263405855: "Roblox visor 1",
    263405857: "Silver Bow Tie",
    263405859: "Dodgeball Helmet",
    263405861: "Shoulder Raccoon",
    263405863: "Dued1",
    263405865: "Pauldrons",
    263405867: "Octember Encore",
    263405869: "Umberhorns",
    128540404: "Police Cap",
    128540406: "American Baseball Cap",
    128540408: "Orange Cap",
    218491492: "Navy Queen otn",
    128540410: "Zombie Knit",
    128540412: "Epic Miners Headlamp",
    128540414: "Beast Mode Bandana",
    162295698: "Golden Reingment",
    128540416: "Beast Scythe",
    128540418: "Hare Hoodie",
    128540420: "Diamond Tiara",
    128540422: "Callmehbob",
    128540424: "Sword Cane",
    128540426: "Selfie Stick",
    128540428: "Phantom Forces Combat Knife",
    128540430: "Golden Horns",
    128540432: "The Soup is Dry",
    128540434: "Monster Grumpy Face",
    128540436: "Elegant Evening Face",
    128540438: "Super Pink Make-Up",
    128540440: "Cyanskeleface",
    128540442: "Pizza Face",
    128540444: "Bakonetta",
    128540446: "Isabella",
    128540448: "Mon Cheri",
    128540450: "Rogueish Good Looks",
    128540452: "Mixologist’s Smile",
    128540454: "BiteyMcFace",
    128540456: "Performing Mime",
    128540458: "Rainbow Spirit Face",
    128540460: "Mermaid Mystique",
    128540462: "Starry Eyes Sparkling",
    128540464: "Sparkling Friendly Wink",
    128540466: "Kandi’s Sprinkle Face",
    128540468: "Tears of Sorrow",
    128540470: "Fashion Face",
    128540472: "Princess Alexis",
    128540474: "Otakufaic",
    128540476: "Pop Queen",
    128540478: "Assassin Face",
    128540480: "Sapphire Gaze",
    128540482: "Persephone's E-Girl",
    128540484: "Arachnid Queen",
    128540486: "Rainbow Barf Face",
    128540488: "Star Sorority",
    128540490: "Tsundere Face",
    128540492: "Winning Smile",
}

# ----- Функция получения настроек пользователя -----
def get_user_settings(uid: int) -> dict:
    """Возвращает настройки пользователя, дополняя их дефолтными."""
    settings = user_settings.get(uid, {})
    # Создаём копию дефолтных настроек и обновляем из сохранённых
    result = DEFAULT_SETTINGS.copy()
    result.update(settings)
    return result

# ----- Инициализация БД -----
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items_cache (
                asset_id INTEGER PRIMARY KEY,
                name TEXT,
                type INTEGER,
                created TEXT,
                last_updated TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        ''')
        await db.execute('INSERT OR IGNORE INTO stats (key, value) VALUES ("total_checks", 0)')
        await db.execute('INSERT OR IGNORE INTO stats (key, value) VALUES ("rare_finds", 0)')
        await db.commit()
    logger.info("База данных инициализирована")

# ----- API функции -----
async def fetch_json(session, url, headers=None):
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.warning(f"HTTP {resp.status} for {url}")
                return None
    except Exception as e:
        logger.error(f"Request error: {e}")
        return None

async def get_user_id_from_cookie(cookie: str) -> tuple[int | None, str | None]:
    headers = {'Cookie': f'.ROBLOSECURITY={cookie}'}
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, 'https://users.roblox.com/v1/users/authenticated', headers)
        if data and 'id' in data and 'name' in data:
            return data['id'], data['name']
    return None, None

async def get_user_info(user_id: int, session: aiohttp.ClientSession) -> dict:
    url = f'https://users.roblox.com/v1/users/{user_id}'
    data = await fetch_json(session, url)
    if not data:
        return {}
    return {
        'created': data.get('created', ''),
        'age_verified': data.get('hasVerifiedBadge', False),
    }

async def get_inventory(user_id: int, session: aiohttp.ClientSession, cookie: str = None):
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    if cookie:
        headers['Cookie'] = f'.ROBLOSECURITY={cookie}'
    base_url = f'https://inventory.roblox.com/v2/users/{user_id}/inventory?limit=100'
    items = []
    cursor = ''
    logger.info(f"Запрашиваем инвентарь для пользователя {user_id}")
    page_num = 0
    while True:
        page_num += 1
        url = base_url + (f'&cursor={cursor}' if cursor else '')
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Логируем количество элементов на странице
                    page_items = data.get('data', [])
                    logger.info(f"Страница {page_num}: получено {len(page_items)} предметов")
                    # Для отладки покажем первые 3 предмета
                    if page_items:
                        for i, item in enumerate(page_items[:3]):
                            logger.info(f"  Пример {i+1}: {item.get('name')} (ID: {item.get('assetId')}) collectibleItemId={item.get('collectibleItemId')}")
                    # Фильтруем по наличию collectibleItemId (коллекционные предметы)
                    for item in page_items:
                        if item.get('collectibleItemId'):
                            items.append(item)
                    cursor = data.get('nextPageCursor')
                    if not cursor:
                        break
                else:
                    logger.warning(f"Не удалось получить инвентарь: HTTP {resp.status}")
                    break
        except Exception as e:
            logger.error(f"Ошибка при запросе инвентаря: {e}")
            break
    logger.info(f"Найдено коллекционных предметов: {len(items)}")
    return items

async def get_item_details(asset_id: int, session: aiohttp.ClientSession) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT name, type, created FROM items_cache WHERE asset_id = ?', (asset_id,))
        row = await cursor.fetchone()
        if row:
            return {'name': row[0], 'type': row[1], 'created': row[2]}
    url = f'https://economy.roblox.com/v2/assets/{asset_id}/details'
    data = await fetch_json(session, url)
    if not data:
        return None
    item = {
        'name': data.get('Name', 'Unknown'),
        'type': data.get('AssetTypeId'),
        'created': data.get('Created')
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
        'error': None,
        'user_id': None,
        'username': None,
        'created': None,
        'age_verified': False,
        'items': [],
        'code_items': [],
        'rare_count': 0,
        'code_count': 0
    }
    async with aiohttp.ClientSession() as session:
        user_id, username = await get_user_id_from_cookie(cookie)
        if not user_id:
            result['error'] = 'Недействительные куки'
            return result
        result['user_id'] = user_id
        result['username'] = username
        logger.info(f"Проверяем аккаунт: {username} (ID: {user_id})")
        user_info = await get_user_info(user_id, session)
        result['created'] = user_info.get('created', '')
        result['age_verified'] = user_info.get('age_verified', False)
        inventory = await get_inventory(user_id, session, cookie)
        target_types = settings.get('item_types', [8, 41, 18, 19])
        year_range = settings.get('year_range', (2006, 2016))
        show_code_items = settings.get('show_code_items', True)
        logger.info(f"Ищем предметы типов {target_types} за {year_range[0]}-{year_range[1]} годы")
        sem = asyncio.Semaphore(REQUESTS_PER_SECOND)
        async def process_item(item):
            async with sem:
                asset_id = item.get('assetId')
                if not asset_id:
                    return
                if show_code_items and asset_id in CODE_ITEMS:
                    result['code_items'].append({
                        'id': asset_id,
                        'name': CODE_ITEMS[asset_id],
                        'type': 'code'
                    })
                    result['code_count'] += 1
                    logger.info(f"🔨 Найден кодовый предмет: {CODE_ITEMS[asset_id]}")
                details = await get_item_details(asset_id, session)
                if not details:
                    return
                if details['type'] not in target_types:
                    return
                if details['created']:
                    try:
                        year = int(details['created'][:4])
                        if year_range[0] <= year <= year_range[1]:
                            result['items'].append({
                                'id': asset_id,
                                'name': details['name'],
                                'type': details['type'],
                                'created': details['created']
                            })
                            result['rare_count'] += 1
                            logger.info(f"✅ Найден старый предмет: {details['name']} ({year})")
                    except:
                        pass
        tasks = [process_item(item) for item in inventory if item.get('assetId')]
        await asyncio.gather(*tasks)
        result['items'].sort(key=lambda x: x['created'])
        logger.info(f"Найдено старых предметов: {result['rare_count']}")
        logger.info(f"Найдено кодовых предметов: {result['code_count']}")
        return result

# ----- FSM -----
class Settings(StatesGroup):
    waiting_for_years = State()
    waiting_for_item_types = State()

# ----- Клавиатуры -----
def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Проверить куки", callback_data="check_cookie")
    builder.button(text="⚙️ Настройки", callback_data="settings")
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.adjust(1)
    return builder.as_markup()

def settings_keyboard(uid):
    s = get_user_settings(uid)
    code_status = s.get('show_code_items', True)
    code_text = f"{'✅' if code_status else '⬜'} Кодовые предметы"
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Диапазон лет", callback_data="set_years")
    builder.button(text="🎩 Типы предметов", callback_data="set_types")
    builder.button(text=code_text, callback_data="toggle_code")
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()

def years_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад к настройкам", callback_data="settings")
    builder.adjust(1)
    return builder.as_markup()

def types_keyboard(current_types):
    type_names = {8: "🎩 Шляпы", 41: "💇 Причёски", 18: "😐 Лица", 19: "⚙️ Гиры"}
    builder = InlineKeyboardBuilder()
    for tid, name in type_names.items():
        status = "✅" if tid in current_types else "⬜"
        builder.button(text=f"{status} {name}", callback_data=f"toggle_type_{tid}")
    builder.button(text="✅ Выбрать всё", callback_data="types_all")
    builder.button(text="⬜ Сбросить всё", callback_data="types_none")
    builder.button(text="◀️ Назад", callback_data="settings")
    builder.adjust(1)
    return builder.as_markup()

# ----- Обработчики -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "👋 <b>Roblox Offsale Checker</b>\n\n"
        "🔍 Пришли мне .ROBLOSECURITY куки, и я покажу все оффсейл предметы на аккаунте\n"
        "💎 <i>Ищем только limited/limitedU предметы</i>\n\n"
        "⚙️ В настройках можно:\n"
        "• Выбрать диапазон лет\n"
        "• Выбрать типы предметов\n"
        "• Включить/выключить поиск кодовых предметов",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=settings_keyboard(uid),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def stats_menu(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT value FROM stats WHERE key = "total_checks"')
        total = (await cursor.fetchone())[0]
        cursor = await db.execute('SELECT value FROM stats WHERE key = "rare_finds"')
        rare = (await cursor.fetchone())[0]
    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"Всего проверено аккаунтов: {total}\n"
        f"Найдено редких предметов: {rare}",
        reply_markup=settings_keyboard(callback.from_user.id),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "toggle_code")
async def toggle_code(callback: types.CallbackQuery):
    uid = callback.from_user.id
    current = get_user_settings(uid)['show_code_items']
    user_settings[uid] = user_settings.get(uid, {})
    user_settings[uid]['show_code_items'] = not current
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(uid))
    await callback.answer(f"Поиск кодовых предметов: {'включён' if not current else 'выключен'}")

@dp.callback_query(F.data == "set_years")
async def set_years_start(callback: types.CallbackQuery, state: FSMContext):
    current = get_user_settings(callback.from_user.id)['year_range']
    await callback.message.edit_text(
        f"📅 <b>Текущий диапазон:</b> {current[0]}–{current[1]}\n\n"
        "Введите новый диапазон в формате <code>2006-2016</code>:",
        reply_markup=years_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(Settings.waiting_for_years)
    await callback.answer()

@dp.message(Settings.waiting_for_years)
async def process_years(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    text = message.text.strip()
    match = re.match(r'^(\d{4})-(\d{4})$', text)
    if not match:
        await message.answer("❌ Неверный формат. Используйте 2006-2016")
        return
    y1, y2 = int(match[1]), int(match[2])
    if y1 > y2:
        y1, y2 = y2, y1
    uid = message.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {}
    user_settings[uid]['year_range'] = (y1, y2)
    await message.answer(f"✅ Диапазон установлен: {y1}–{y2}")
    await state.clear()

@dp.callback_query(F.data == "set_types")
async def set_types_start(callback: types.CallbackQuery):
    uid = callback.from_user.id
    current = get_user_settings(uid)['item_types']
    await callback.message.edit_text(
        "🎩 <b>Выберите типы предметов для поиска</b>",
        reply_markup=types_keyboard(current),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_type_"))
async def toggle_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    type_id = int(callback.data.split("_")[2])
    if uid not in user_settings:
        user_settings[uid] = {}
    current = user_settings[uid].get('item_types', [8, 41, 18, 19])
    if type_id in current:
        current.remove(type_id)
    else:
        current.append(type_id)
    user_settings[uid]['item_types'] = current
    await callback.message.edit_reply_markup(reply_markup=types_keyboard(current))
    await callback.answer()

@dp.callback_query(F.data == "types_all")
async def types_all(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {}
    user_settings[uid]['item_types'] = [8, 41, 18, 19]
    await callback.message.edit_reply_markup(reply_markup=types_keyboard([8, 41, 18, 19]))
    await callback.answer()

@dp.callback_query(F.data == "types_none")
async def types_none(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {}
    user_settings[uid]['item_types'] = []
    await callback.message.edit_reply_markup(reply_markup=types_keyboard([]))
    await callback.answer()

@dp.callback_query(F.data == "check_cookie")
async def check_cookie_prompt(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🔍 Отправьте .ROBLOSECURITY куки (текстом) или .txt файл с куки.",
        reply_markup=settings_keyboard(callback.from_user.id),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.message(F.text)
async def handle_cookie_text(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await process_cookie(message, message.text.strip())

@dp.message(F.document)
async def handle_cookie_file(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    file = await bot.get_file(message.document.file_id)
    file_path = f"temp_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            cookie = f.read().strip()
        await process_cookie(message, cookie)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def process_cookie(message: types.Message, cookie: str):
    status_msg = await message.answer("🔄 Проверяю аккаунт...")
    uid = message.from_user.id
    settings = get_user_settings(uid)

    result = await check_account(cookie, settings)

    if result['error']:
        await status_msg.edit_text(f"❌ {result['error']}")
        return

    # Формируем отчёт
    report_lines = []
    report_lines.append("=== ROBLOX OFFSALE REPORT ===\n")
    report_lines.append(f"👤 Ник: {result['username']} (ID: {result['user_id']})")
    report_lines.append(f"📅 Создан аккаунт: {result['created'][:10] if result['created'] else 'Неизвестно'}")
    report_lines.append(f"✅ Верификация возраста: {'Да' if result['age_verified'] else 'Нет'}\n")

    if result['code_count'] > 0 and settings.get('show_code_items', True):
        report_lines.append(f"\n🔨 КОДОВЫЕ ПРЕДМЕТЫ: {result['code_count']}")
        report_lines.append("─" * 40)
        for item in result['code_items']:
            report_lines.append(f"• {item['name']}")
            report_lines.append(f"  Ссылка: https://www.roblox.com/catalog/{item['id']}\n")

    if result['rare_count'] > 0:
        report_lines.append(f"\n💎 ОФФСЕЙЛ ПРЕДМЕТЫ ЗА {settings['year_range'][0]}-{settings['year_range'][1]}: {result['rare_count']}")
        report_lines.append("─" * 40)
        for item in result['items']:
            item_date = item['created'][:4] if item['created'] else 'Неизвестно'
            item_type = {8: "🎩", 41: "💇", 18: "😐", 19: "⚙️"}.get(item['type'], "📦")
            report_lines.append(f"{item_type} {item['name']} ({item_date})")
            report_lines.append(f"  Ссылка: https://www.roblox.com/catalog/{item['id']}\n")
    else:
        report_lines.append(f"\n❌ Оффсейл предметов за {settings['year_range'][0]}-{settings['year_range'][1]} не найдено.")

    report = "\n".join(report_lines)

    # Создаём временный файл с безопасным именем
    safe_username = re.sub(r'[^\w\-_\. ]', '_', result['username'])
    fd, temp_path = tempfile.mkstemp(suffix='.txt', prefix=f'{safe_username}_', text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(report)

    # Обновляем статистику
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE stats SET value = value + 1 WHERE key = "total_checks"')
        await db.execute('UPDATE stats SET value = value + ? WHERE key = "rare_finds"', (result['rare_count'],))
        await db.commit()

    # Отправляем результат
    total_items = result['rare_count'] + result['code_count']
    await status_msg.edit_text(
        f"✅ <b>Готово!</b>\n\n"
        f"Аккаунт: {result['username']}\n"
        f"Найдено предметов: {total_items}",
        parse_mode=ParseMode.HTML
    )

    # Отправляем файл с полным отчётом
    doc = FSInputFile(temp_path, filename=f"{safe_username}_report.txt")
    await message.answer_document(doc, caption="📊 Полный отчёт")

    # Удаляем временный файл
    os.unlink(temp_path)

# ----- Запуск -----
async def main():
    logger.info("Запуск бота...")
    global bot
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logger.info(f"Бот запускается с токеном: {BOT_TOKEN[:10]}...")
    logger.info(f"Админы: {ADMIN_IDS}")
    await init_db()
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
