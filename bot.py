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
BOT_TOKEN = "8035442503:AAG-gdNAKMFhnyyaHGfjeMdh48-sa-Jd55A"
OWNER_ID = 5883796026
ADMIN_IDS = [OWNER_ID]
# =================================

# Лимиты запросов к API
REQUESTS_PER_SECOND = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----- Создаём диспетчер -----
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "roblox_checker.db"

# ----- Хранилище настроек пользователя -----
user_settings = {}

# ----- Инициализация БД -----
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items_cache (
                asset_id INTEGER PRIMARY KEY,
                name TEXT,
                type INTEGER,
                created TEXT,
                rap INTEGER,
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

# ----- Вспомогательные функции для работы с Roblox API -----
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
    """Получает UserId и ник по куки."""
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
        'description': data.get('description', '')
    }

async def get_inventory(user_id: int, session: aiohttp.ClientSession, cookie: str = None):
    """Получает инвентарь через API с кукой (для приватных инвентарей)."""
    headers = {}
    if cookie:
        headers['Cookie'] = f'.ROBLOSECURITY={cookie}'
    
    base_url = f'https://inventory.roblox.com/v2/users/{user_id}/inventory?limit=100'
    items = []
    cursor = ''
    
    logger.info(f"Запрашиваем инвентарь для пользователя {user_id}")
    
    while True:
        url = base_url + (f'&cursor={cursor}' if cursor else '')
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    page_items = data.get('data', [])
                    items.extend(page_items)
                    
                    # Логируем первые предметы для отладки
                    if len(items) <= 10 and page_items:
                        for item in page_items[:3]:
                            logger.info(f"Найден предмет: {item.get('name', 'Unknown')} (ID: {item.get('assetId')})")
                    
                    cursor = data.get('nextPageCursor')
                    if not cursor:
                        break
                elif resp.status == 403:
                    logger.warning(f"Доступ запрещён (403). Инвентарь пользователя {user_id} приватный.")
                    # Пробуем с прокси-сервером
                    proxy_url = f'https://inventory.roproxy.com/v2/users/{user_id}/inventory?limit=100'
                    proxy_url += (f'&cursor={cursor}' if cursor else '')
                    async with session.get(proxy_url, headers=headers, timeout=10) as proxy_resp:
                        if proxy_resp.status == 200:
                            proxy_data = await proxy_resp.json()
                            proxy_items = proxy_data.get('data', [])
                            items.extend(proxy_items)
                            cursor = proxy_data.get('nextPageCursor')
                            if not cursor:
                                break
                        else:
                            logger.error(f"Не удалось получить инвентарь даже через прокси: {proxy_resp.status}")
                            break
                else:
                    logger.warning(f"Не удалось получить инвентарь: HTTP {resp.status}")
                    break
        except Exception as e:
            logger.error(f"Ошибка при запросе инвентаря: {e}")
            break
    
    logger.info(f"Всего найдено предметов: {len(items)}")
    return items

async def get_item_details(asset_id: int, session: aiohttp.ClientSession) -> dict | None:
    """Получает детали предмета (название, тип, дата создания)."""
    # Проверяем кэш
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT name, type, created FROM items_cache WHERE asset_id = ?', (asset_id,))
        row = await cursor.fetchone()
        if row:
            return {'name': row[0], 'type': row[1], 'created': row[2]}

    # Запрос к economy API
    url = f'https://economy.roblox.com/v2/assets/{asset_id}/details'
    data = await fetch_json(session, url)
    if not data:
        return None

    item = {
        'name': data.get('Name', 'Unknown'),
        'type': data.get('AssetTypeId'),
        'created': data.get('Created')  # Это дата создания предмета
    }

    # Сохраняем в кэш
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
        'rare_count': 0
    }

    async with aiohttp.ClientSession() as session:
        # 1. Получаем UserId и ник
        user_id, username = await get_user_id_from_cookie(cookie)
        if not user_id:
            result['error'] = 'Недействительные куки'
            return result
        result['user_id'] = user_id
        result['username'] = username
        logger.info(f"Проверяем аккаунт: {username} (ID: {user_id})")

        # 2. Информация о пользователе
        user_info = await get_user_info(user_id, session)
        result['created'] = user_info.get('created', '')
        result['age_verified'] = user_info.get('age_verified', False)

        # 3. Инвентарь (теперь с кукой!)
        inventory = await get_inventory(user_id, session, cookie)

        # 4. Фильтруем по типам и годам
        target_types = settings.get('item_types', [8, 41, 18, 19])
        year_range = settings.get('year_range', (2006, 2016))
        
        logger.info(f"Ищем предметы типов {target_types} за {year_range[0]}-{year_range[1]} годы")

        sem = asyncio.Semaphore(REQUESTS_PER_SECOND)

        async def process_item(item):
            async with sem:
                asset_id = item.get('assetId')
                if not asset_id:
                    return
                
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
                            logger.info(f"✅ Найден старый предмет: {details['name']} ({year})")
                    except:
                        pass

        tasks = [process_item(item) for item in inventory if item.get('assetId')]
        await asyncio.gather(*tasks)

        result['items'].sort(key=lambda x: x['created'])
        result['rare_count'] = len(result['items'])
        
        logger.info(f"Найдено старых предметов: {result['rare_count']}")

        return result

# ----- Состояния FSM -----
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

def settings_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Диапазон лет", callback_data="set_years")
    builder.button(text="🎩 Типы предметов", callback_data="set_types")
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

# ----- Обработчики команд -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "👋 <b>Roblox Account Checker</b>\n\n"
        "Пришли мне .ROBLOSECURITY куки (текстом или файлом), и я покажу:\n"
        "• Ник, дату создания, верификацию\n"
        "• Все старые шляпы/гиры/лица с датами\n\n"
        "Результат можно скачать в .txt файле.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>",
        reply_markup=main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=settings_keyboard()
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
        reply_markup=settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "set_years")
async def set_years_start(callback: types.CallbackQuery, state: FSMContext):
    current = user_settings.get(callback.from_user.id, {}).get('year_range', (2006, 2016))
    await callback.message.edit_text(
        f"📅 Текущий диапазон: {current[0]}–{current[1]}\n\n"
        "Введите новый диапазон в формате <code>2006-2016</code>:",
        reply_markup=years_keyboard()
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
    current = user_settings.get(uid, {}).get('item_types', [8, 41, 18, 19])
    await callback.message.edit_text(
        "🎩 <b>Выберите типы предметов для поиска</b>",
        reply_markup=types_keyboard(current)
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
        "📤 Отправьте .ROBLOSECURITY куки (текстом) или .txt файл с куки.",
        reply_markup=settings_keyboard()
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
    with open(file_path, 'r', encoding='utf-8') as f:
        cookie = f.read().strip()
    os.remove(file_path)
    await process_cookie(message, cookie)

async def process_cookie(message: types.Message, cookie: str):
    status_msg = await message.answer("🔄 Проверяю аккаунт...")
    uid = message.from_user.id
    settings = user_settings.get(uid, {
        'year_range': (2006, 2016),
        'item_types': [8, 41, 18, 19]
    })

    result = await check_account(cookie, settings)

    if result['error']:
        await status_msg.edit_text(f"❌ {result['error']}")
        return

    # Формируем отчёт
    report = f"=== ROBLOX ACCOUNT REPORT ===\n\n"
    report += f"👤 Ник: {result['username']} (ID: {result['user_id']})\n"
    report += f"📅 Создан аккаунт: {result['created'][:10] if result['created'] else 'Неизвестно'}\n"
    report += f"✅ Верификация возраста: {'Да' if result['age_verified'] else 'Нет'}\n\n"

    if result['rare_count'] > 0:
        report += f"🎩 НАЙДЕНО СТАРЫХ ПРЕДМЕТОВ: {result['rare_count']}\n"
        report += "─" * 40 + "\n"
        for item in result['items']:
            item_date = item['created'][:10] if item['created'] else 'Неизвестно'
            report += f"• {item['name']}\n"
            report += f"  ID: {item['id']}\n"
            report += f"  Тип предмета: {item['type']}\n"
            report += f"  Дата создания предмета: {item_date}\n\n"
    else:
        report += "😕 Старых предметов не найдено.\n"

    # Сохраняем в файл
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
        f.write(report)
        temp_path = f.name

    # Обновляем статистику
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE stats SET value = value + 1 WHERE key = "total_checks"')
        await db.execute('UPDATE stats SET value = value + ? WHERE key = "rare_finds"', (result['rare_count'],))
        await db.commit()

    # Отправляем результат
    await status_msg.edit_text(
        f"✅ <b>Готово!</b>\n\n"
        f"Аккаунт: {result['username']}\n"
        f"Найдено предметов: {result['rare_count']}",
        parse_mode=ParseMode.HTML
    )

    # Отправляем файл с полным отчётом
    doc = FSInputFile(temp_path, filename=f"{result['username']}_report.txt")
    await message.answer_document(doc)

    # Удаляем временный файл
    os.unlink(temp_path)

# ----- Запуск -----
async def main():
    logger.info("Запуск бота...")
    
    # Создаём бота
    global bot
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    logger.info(f"Бот запускается с токеном: {BOT_TOKEN[:10]}...")
    logger.info(f"Владелец: {OWNER_ID}")
    
    await init_db()
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
