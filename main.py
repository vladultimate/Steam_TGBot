import sqlite3
import aiohttp
import asyncio
import re
import telebot
from telebot import types
import threading
from fake_useragent import UserAgent
from send_gmails import send_email, process_email_input


async def get_currency_rate(currency_code='USD'):
    url = 'https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            for currency in data:
                if currency['ccy'] == currency_code:
                    return float(currency['sale'])


async def get_skinprice(link):
    headers = {'User-Agent': user_agent.random}
    async with aiohttp.ClientSession() as session:
        match = re.search(r"market/listings/\d+/(.*?)\?", link)
        if match:
            market_hash_name = match.group(1).rstrip('/')
            price_url = f"https://steamcommunity.com/market/priceoverview/?appid=730&market_hash_name={market_hash_name}"
            async with session.get(price_url, headers=headers) as response:
                data = await response.json()
                if "lowest_price" in data:
                    price = data["lowest_price"]
                    price = float(price.replace("$", ''))
                    exchange_rate = await get_currency_rate('USD')  
                    return round(price * exchange_rate)
TOKEN_INFO = ''
bot = telebot.TeleBot(f"{TOKEN_INFO}")

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

user_agent = UserAgent()


@bot.message_handler(commands=['start'])
def handle_start(message):
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (message.chat.id,))
    user_data = cursor.fetchone()

    referred_by = None
    if len(message.text.split()) > 1 and user_data is None:
        referred_by = message.text.split()[1]
        cursor.execute("SELECT * FROM users WHERE chat_id = ?", (referred_by,))
        referrer = cursor.fetchone()

        if referrer:
            cursor.execute("INSERT INTO users (username, chat_id, referred_by) VALUES (?, ?, ?)", 
                           (message.from_user.username, message.chat.id, referred_by))
            conn.commit()

            cursor.execute("UPDATE users SET referrals = referrals + 1, max_lots = max_lots + 1 WHERE chat_id = ?", 
                           (referred_by,))
            conn.commit()
        else:
            cursor.execute("INSERT INTO users (username, chat_id, referred_by) VALUES (?, ?, ?)", 
                           (message.from_user.username, message.chat.id, None))
            conn.commit()
    elif user_data is None:
        cursor.execute("INSERT INTO users (username, chat_id, referred_by) VALUES (?, ?, ?)", 
                       (message.from_user.username, message.chat.id, None))
        conn.commit()
    
    cursor.execute("SELECT * FROM skins WHERE user_id = ?", (message.chat.id,))
    user_skins = cursor.fetchall()

    welcome_message = (
    f"👋 Ласкаво просимо, <b>@{message.from_user.username}</b>! 🌟\n\n"
    "Я тут, щоб допомогти вам з обміном ваших ігрових скінів 🎮.\n\n"
    "🔄 Ви можете легко додавати скіни для купівлі чи продажу. Просто оберіть потрібну дію нижче ⬇️"
    )

    bot.send_message(message.chat.id, welcome_message, reply_markup=update_keyboard(message), parse_mode='html')


@bot.message_handler(content_types=['text'])
def handle_action(message):
    user_data = cursor.fetchone()
    if message.text == '🔗 Реферальне посилання':
        referral_code = message.chat.id
        
        cursor.execute("SELECT referrals FROM users WHERE chat_id = ?", (message.chat.id,))
        referrals_count = cursor.fetchone()[0]

        referral_link = f"https://t.me/SteamMarket_FindPricer_bot?start={referral_code}"
        
        if referrals_count and referrals_count > 0:
            referral_message = f"👥 <b>Ви вже запросили:</b> {referrals_count} друзів!"
        else:
            referral_message = (
                "🙁 <b>Ви ще не запросили жодного друга.</b>\n"
                "Але ви можете це виправити! Запросіть друзів та отримайте бонуси!"
            )

        bot.send_message(
            message.chat.id, 
            f"🔗 <b>Ваше реферальне посилання:</b>\n"
            f"📩 <code>{referral_link}</code>\n\n"
            f"{referral_message}\n"
            f"Запросіть друзів за цим посиланням та отримайте бонуси:\n"
            "🎉 Більше запрошених — більше лотів для відслідковування ціни ваших товарів!",
            parse_mode='html'
        )

    if message.text == '🛒 Додати скін':
        
        cursor.execute("SELECT id, max_lots FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        if user_data is None:
            bot.send_message(message.chat.id, "⚠️ Користувача не знайдено. Будь ласка, спробуйте ще раз.")                                                                            
            return
        user_id, max_lots = user_data
        cursor.execute("SELECT COUNT(*) FROM skins WHERE user_id = ?", (user_id,))
        active_skins_count = cursor.fetchone()[0]

        if active_skins_count >= max_lots:
            bot.send_message(message.chat.id, f"❌ Ви досягли максимального ліміту ({max_lots}) активних скінів.")
        else:
            cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
            user_data = cursor.fetchone()
            user_id = user_data[0]
            cursor.execute("UPDATE skins SET paused = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            bot.send_message(message.chat.id, '🔗 Будь ласка, скиньте посилання на ваш товар.')
            bot.register_next_step_handler(message, process_skin_url, user_id)

    if message.text == '🗑 Очистити свої данні':
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("DELETE FROM skins WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, '🗑️ Ваші лоти очищено!', reply_markup=update_keyboard(message))

    if message.text == '🆘 Допомога':
        markup = types.InlineKeyboardMarkup()
        item1 = types.InlineKeyboardButton("Що робить цей бот? Для чого його використовують?", callback_data='whats_doing_this_bot')
        item2 = types.InlineKeyboardButton("Повернутись назад↩️", callback_data='Return_to_default')
        markup.row(item1)
        markup.row(item2)
        bot.send_message(message.chat.id, 'Виберіть питання зі списку: ', reply_markup=markup)

    if message.text == '⚠️ Надіслати проблему': 
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("UPDATE skins SET paused = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, '🔑 Будь ласка, введіть ваш E-mail для зв’язку з вами по поводу вашої проблеми:')
        bot.register_next_step_handler(message, process_email_input)

    if message.text == '⏸️ Призупинити моніторинг':
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("UPDATE skins SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, "⏸️ Моніторинг призупинено для всіх ваших товарів.", reply_markup=update_keyboard(message))

    if message.text == '▶️ Відновити моніторинг':
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("UPDATE skins SET is_active = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, "▶️ Моніторинг відновлено для всіх ваших товарів.", reply_markup=update_keyboard(message))


def process_skin_url(message, user_id):
    if 'https://steamcommunity.com/market/listings/' in message.text:
        cursor.execute("SELECT id FROM users WHERE chat_id = ?", (message.chat.id,))
        user_data = cursor.fetchone()
        user_ids = user_data[0]
        cursor.execute("SELECT is_active FROM skins WHERE user_id = ?", (user_ids,))
        is_active = cursor.fetchall()
        if any(row[0] == 0 for row in is_active):
            cursor.execute("INSERT INTO skins (user_id, skin_url, is_active) VALUES (?, ?, ?)", 
                       (user_id, message.text, 0))
        else:
            cursor.execute("INSERT INTO skins (user_id, skin_url, is_active) VALUES (?, ?, ?)", 
                       (user_id, message.text, 1))
        conn.commit()
        bot.send_message(
            message.chat.id, 
            '🌟<b>Будь ласка, введіть ціну в гривнях:</b>\n'
            '|<i>Зверніть увагу на ціну, яку ви вводите. Якщо ви хочете продати, вводьте ціну, при якій і вище бот надішле повідомлення про збільшення. Для покупки — введіть ціну, за яку і нижче бот надсилатиме повідомлення.</i>|', 
            parse_mode='html'
        )
        bot.register_next_step_handler(message, process_price, user_id)
    else:
        bot.send_message(message.chat.id, '❌ Неправильне посилання. Спробуйте ще раз.')
        bot.register_next_step_handler(message, process_skin_url, user_id)


def process_price(message, user_id):
    if message.text.isdigit():
        price = int(message.text)
        cursor.execute("UPDATE skins SET price = ? WHERE user_id = ? AND price IS NULL", 
                       (price, user_id))
        conn.commit()

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        sell_button = types.KeyboardButton("🛍 Продати вигідніше")
        buy_button = types.KeyboardButton("🛒 Купити вигідніше")
        markup.add(sell_button, buy_button)

        bot.send_message(message.chat.id, '✅ Скін додано! Що хочете зробити далі з вашим товаром?', reply_markup=markup)
        bot.register_next_step_handler(message, process_action, user_id)
    else:
        bot.send_message(message.chat.id, '❌ Будь ласка, введіть коректне число.')
        bot.register_next_step_handler(message, process_price, user_id)


def update_keyboard(message):
    cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
    user_data = cursor.fetchone()
    user_id = user_data[0]
    cursor.execute("SELECT skin_url FROM skins WHERE user_id = ?", (user_id,))
    user_skins = cursor.fetchall()
    cursor.execute("SELECT is_active FROM skins WHERE user_id = ?", (user_id,))

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    try:
        if user_skins[0][0]:
            is_active = cursor.fetchall()[0][0]
            if is_active:
                item_pause = types.KeyboardButton("⏸️ Призупинити моніторинг")
                markup.add(item_pause)
            else:
                item_resume = types.KeyboardButton("▶️ Відновити моніторинг")
                markup.add(item_resume)
    except:
        pass
    item1 = types.KeyboardButton("🛒 Додати скін")
    item2 = types.KeyboardButton("🆘 Допомога")
    item3 = types.KeyboardButton("🔗 Реферальне посилання")
    item4 = types.KeyboardButton("⚠️ Надіслати проблему")
    markup.add(item1, item2)
    markup.add(item3)
    markup.add(item4)
    try:
        if user_skins[0][0]:
            markup.add(types.KeyboardButton("🗑 Очистити свої данні"))
    except:
        pass
        
    return markup


def process_action(message, user_id):
    if message.text == '🛍 Продати вигідніше':
        cursor.execute("UPDATE skins SET action = 'sell' WHERE user_id = ? AND action IS NULL", 
                       (user_id,))
        conn.commit()
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("UPDATE skins SET paused = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, '💸 Ваш скін готовий до продажу!', reply_markup=update_keyboard(message))
    elif message.text == '🛒 Купити вигідніше':
        cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
        user_data = cursor.fetchone()
        user_id = user_data[0]
        cursor.execute("UPDATE skins SET paused = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        cursor.execute("UPDATE skins SET action = 'buy' WHERE user_id = ? AND action IS NULL", 
                       (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, '🛍️ Ваш скін готовий до купівлі!', reply_markup=update_keyboard(message))
    else:
        bot.send_message(message.chat.id, '⚠️ Неправильний вибір. Спробуйте ще раз.')
        bot.register_next_step_handler(message, process_action, user_id)

def process_email_input(message):
    user_email = message.text  
    bot.send_message(message.chat.id, 'Опишіть вашу проблему:')
    bot.register_next_step_handler(message, process_help_request, user_email)

def process_help_request(message, user_email):
    problem = message.text 

    email_thread = threading.Thread(target=send_email, args=("SteamBot Helper", f"Ваше звернення по поводу: ||{problem}|| скоро буде оброблено, і відповідь буде відправлена вам на електронну скриньку", user_email))
    email_thread.start()

    cursor.execute("SELECT id FROM users WHERE username = ?", (message.from_user.username,))
    user_data = cursor.fetchone()
    user_id = user_data[0]
    cursor.execute("UPDATE skins SET paused = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

    bot.send_message(message.chat.id, '📧Ваше повідомлення надіслано! Ми зв’яжемося з вами найближчим часом.', parse_mode='html', reply_markup=update_keyboard(message))

@bot.callback_query_handler(func=lambda call: True)
def questions_answers(call):
    if call.data == 'Return_to_default':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
        welcome_message = (
            f"<i>Виберіть дію нижче⬇️</i>"
        )  
        bot.send_message(call.message.chat.id, welcome_message, reply_markup=update_keyboard(call), parse_mode='html')
        
    if call.data == 'FAQ':
        markup = types.InlineKeyboardMarkup()
        item1 = types.InlineKeyboardButton("Що робить цей бот? Для чого його використовують?", callback_data='whats_doing_this_bot')
        item2 = types.InlineKeyboardButton("Повернутись назад↩️", callback_data='Return_to_default')
        markup.row(item1)
        markup.row(item2)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Виберіть питання зі списку: ", parse_mode='html', reply_markup=markup)

    if call.data == 'whats_doing_this_bot':
        markup = types.InlineKeyboardMarkup()
        item1 = types.InlineKeyboardButton("Повернутись↩️", callback_data='FAQ')
        markup.row(item1)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Цей бот моніторить ціни товарів на Steam маркеті та сповіщає про зміни в ціні в залежності від вашого вибраного критерію<i>(Продати вигідніше, Купити вигідніше).</i>", parse_mode='html', reply_markup=markup)

def main_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("🛒 Додати скін")
    item3 = types.KeyboardButton("🗑️ Очистити свої данні")
    markup.row(item1)
    markup.row(item3)
    return markup

async def custom_checks():
    while True:
        cursor.execute("""
            SELECT u.chat_id, s.skin_url, s.price, s.action, s.last_price_message_id 
            FROM skins s 
            JOIN users u ON s.user_id = u.id 
            WHERE s.action IS NOT NULL AND s.is_active = 1 AND s.paused = 0
        """)
        skins = cursor.fetchall()
        
        for skin in skins:
            chat_id, skin_url, price, action, last_price_message_id = skin
            if skin_url is None:
                bot.send_message(chat_id, "Помилка: не вказано посилання на скін.")
                continue
            try:
                current_price = await get_skinprice(skin_url)
                if current_price is not None:
                    if last_price_message_id:
                        try:
                            bot.delete_message(chat_id, last_price_message_id)
                        except Exception as e:
                            print(f"{e}")
                    if action == 'buy' and price > current_price:
                        print(skin_url)
                        new_message = bot.send_message(chat_id, f"🔻 Зниження ціни! Ваш скін доступний за {current_price}₴! Купуйте тут: [🛒 Відкрити товар]({skin_url})", parse_mode='Markdown')
                    elif action == 'sell' and price < current_price:
                        new_message = bot.send_message(chat_id, f"💸 Ваш скін подорожчав до {current_price}₴! [🖱️ Відкрити товар]({skin_url})", parse_mode='Markdown')
                    cursor.execute("UPDATE skins SET last_price_message_id = ? WHERE skin_url = ?", 
                                   (new_message.message_id, skin_url))
                    conn.commit()
            except Exception as e:
                print(e)
        await asyncio.sleep(20)

def bot_polling():
    bot.polling(none_stop=True)

def main():
    bot_thread = threading.Thread(target=bot_polling)
    bot_thread.daemon = True
    bot_thread.start()

    asyncio.run(custom_checks())

if __name__ == '__main__':
    main()
