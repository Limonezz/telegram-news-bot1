import asyncio
import sqlite3
import os
from datetime import datetime
import pytz
from telethon import TelegramClient, events
import logging

# ===== НАСТРОЙКИ =====
API_ID = os.getenv('24826804')
API_HASH = os.getenv('048e59c243cce6ff788a7da214bf8119')
BOT_TOKEN = os.getenv('7597923417:AAHW1LyqzOIY7os9iHlYISqlGlyaG_5bU0c')

# Список каналов для парсинга
CHANNELS = [
    'gubernator_46',
    'kursk_info46',
    'Alekhin_Telega',
    'rian_ru',
    'kursk_ak46',
    'zhest_kursk_146',
    'novosti_efir',
    'kursk_tipich',
    'seymkursk',
    'kursk_smi',
    'kursk_russia',
    'belgorod01',
    'kurskadm',
    'Avtokadr46',
    'kurskbomond',
    'prigranichie_radar1',
    'grohot_pgr',
    'kursk_nasv',
    'mchs_46',
    'patriot046',
    'kursk_now',
    'Hinshtein',
    'incidentkursk',
    'zhest_belgorod',
    'Pogoda_Kursk',
    'pb_032',
    'tipicl32',
    'bryansk_smi',

]
# Файл для хранения подписчиков
SUBSCRIBERS_FILE = 'subscribers.txt'
# ======================

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Функции для работы с подписчиками
def load_subscribers():
    """Загружаем список подписчиков из файла"""
    try:
        with open(SUBSCRIBERS_FILE, 'r') as f:
            return [int(line.strip()) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_subscribers(subscribers):
    """Сохраняем список подписчиков в файл"""
    with open(SUBSCRIBERS_FILE, 'w') as f:
        for user_id in subscribers:
            f.write(f"{user_id}\n")

def add_subscriber(user_id):
    """Добавляем нового подписчика"""
    subscribers = load_subscribers()
    if user_id not in subscribers:
        subscribers.append(user_id)
        save_subscribers(subscribers)
        logger.info(f"✅ Новый подписчик: {user_id}")
    return subscribers

def remove_subscriber(user_id):
    """Удаляем подписчика"""
    subscribers = load_subscribers()
    if user_id in subscribers:
        subscribers.remove(user_id)
        save_subscribers(subscribers)
        logger.info(f"❌ Отписался: {user_id}")
    return subscribers

# Функции для парсинга новостей
def init_db():
    """Создаем временную базу для避免 дубликатов"""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parsed_posts (
            post_id TEXT PRIMARY KEY,
            channel TEXT,
            text TEXT
        )
    ''')
    return conn

def is_post_sent(conn, post_id):
    """Проверяем, отправляли ли уже пост"""
    cursor = conn.cursor()
    cursor.execute("SELECT post_id FROM parsed_posts WHERE post_id = ?", (post_id,))
    return cursor.fetchone() is not None

def mark_post_as_sent(conn, post_id, channel, text):
    """Помечаем пост как отправленный"""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO parsed_posts (post_id, channel, text) VALUES (?, ?, ?)",
        (post_id, channel, text)
    )
    conn.commit()

def generate_post_id(channel_name, message_id):
    """Генерируем уникальный ID поста"""
    return f"{channel_name}_{message_id}"

async def parse_channel(client, channel_name, conn):
    """Парсим один канал и возвращаем новые посты"""
    try:
        logger.info(f"🔍 Парсим канал: {channel_name}")
        
        # Получаем последние 5 сообщений
        messages = await client.get_messages(channel_name, limit=5)
        new_posts = []
        posts_count = 0
        
        for message in messages:
            # Пропускаем пустые сообщения
            if not message.text or not message.text.strip():
                continue
            
            # Создаем уникальный ID
            post_id = generate_post_id(channel_name, message.id)
            
            # Проверяем, не отправляли ли уже этот пост
            if not is_post_sent(conn, post_id):
                # Форматируем текст
                post_text = message.text.strip()
                if len(post_text) > 1000:
                    post_text = post_text[:1000] + "..."
                
                # Форматируем для отправки
                formatted_post = f"📢 **{channel_name}**\n\n{post_text}\n\n🕒 *Время публикации:* {message.date.astimezone(pytz.timezone('Europe/Moscow')).strftime('%H:%M %d.%m.%Y')}"
                
                new_posts.append({
                    'text': formatted_post,
                    'post_id': post_id,
                    'channel': channel_name
                })
                
                # Помечаем как отправленный
                mark_post_as_sent(conn, post_id, channel_name, message.text)
                posts_count += 1
                
                # Останавливаемся после 2 постов
                if posts_count >= 2:
                    break
        
        return new_posts
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга {channel_name}: {e}")
        return []

async def send_news_to_user(client, user_id, posts):
    """Отправляем новости конкретному пользователю"""
    if not posts:
        await client.send_message(
            user_id, 
            "📭 Свежих новостей за последнее время нет!\nПопробуйте позже."
        )
        return
    
    moscow_time = datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M %d.%m.%Y')
    
    # Отправляем заголовок
    await client.send_message(
        user_id,
        f"📊 **СВЕЖИЕ НОВОСТИ**\n"
        f"🕒 *Актуально на:* {moscow_time} (МСК)\n"
        f"📈 *Всего новостей:* {len(posts)}\n"
        f"────────────────"
    )
    
    # Отправляем посты
    for post in posts:
        try:
            await client.send_message(user_id, post['text'], parse_mode='md')
            await asyncio.sleep(1)  # Пауза между сообщениями
        except Exception as e:
            logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")

async def send_news_to_all_subscribers(client):
    """Отправляем новости всем подписчикам"""
    subscribers = load_subscribers()
    if not subscribers:
        logger.info("📭 Нет подписчиков для отправки")
        return
    
    logger.info(f"📨 Начинаем отправку для {len(subscribers)} подписчиков")
    
    # Парсим новости один раз для всех
    db_conn = init_db()
    all_news = []
    
    for channel in CHANNELS:
        try:
            channel_news = await parse_channel(client, channel, db_conn)
            all_news.extend(channel_news)
            await asyncio.sleep(1)  # Пауза между каналами
        except Exception as e:
            logger.error(f"❌ Ошибка канала {channel}: {e}")
    
    # Отправляем каждому подписчику
    for user_id in subscribers:
        try:
            await send_news_to_user(client, user_id, all_news)
            logger.info(f"✅ Отправили пользователю {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки пользователю {user_id}: {e}")
    
    logger.info(f"✅ Отправка завершена для {len(subscribers)} подписчиков")

async def main():
    """Основная функция бота"""
    client = TelegramClient('news_bot_session', API_ID, API_HASH)
    
    # Обработчики команд
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        user_id = event.chat_id
        add_subscriber(user_id)
        await event.reply(
            "🎉 **Добро пожаловать!**\n\n"
            "Вы подписались на свежие новости Курска и области!\n\n"
            "📰 *Что вы будете получать:*\n"
            "• Актуальные новости 2 раза в день\n"
            "• Самые свежие посты из 15+ каналов\n"
            "• Время по МСК\n\n"
            "⏰ *Время отправки:* 09:00, 13:00, 16:00 (МСК)\n\n"
            "❌ Чтобы отписаться: /stop"
        )
    
    @client.on(events.NewMessage(pattern='/subscribe'))
    async def subscribe_handler(event):
        user_id = event.chat_id
        add_subscriber(user_id)
        await event.reply(
            "✅ **Вы подписались на новости!**\n\n"
            "Теперь вы будете получать свежие новости "
            "Курска и области в 09:00, 13:00 и 16:00 по МСК."
        )
    
    @client.on(events.NewMessage(pattern='/stop'))
    async def stop_handler(event):
        user_id = event.chat_id
        remove_subscriber(user_id)
        await event.reply(
            "❌ **Вы отписались от новостей.**\n\n"
            "Больше вы не будете получать уведомления.\n"
            "Чтобы снова подписаться: /start"
        )
    
    @client.on(events.NewMessage(pattern='/stats'))
    async def stats_handler(event):
        subscribers = load_subscribers()
        await event.reply(
            f"📊 **Статистика бота:**\n\n"
            f"• Подписчиков: {len(subscribers)}\n"
            f"• Отслеживаемых каналов: {len(CHANNELS)}\n"
            f"• Время по МСК: {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M %d.%m.%Y')}"
        )
    
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Бот запущен и авторизован")
        
        # Отправляем новости всем подписчикам
        await send_news_to_all_subscribers(client)
        
        # Бот продолжает работать для обработки команд
        logger.info("🤖 Бот готов к приему команд /start, /subscribe")
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
