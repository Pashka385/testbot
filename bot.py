# -*- coding: utf-8 -*-
import telebot
from telebot import types
import configparser
import threading
import schedule
import logging
import random
import datetime
import pytz
import time
import sys

# Логирование
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(filename='bot_log.txt', level=logging.ERROR, format='%(asctime)s [%(levelname)s] %(message)s')

# Конфиг
config = configparser.ConfigParser()
config.read('config.ini')
BOT_TOKEN = config.get('BotConfig', 'BOT_TOKEN')
operators_str = config.get('BotConfig', 'operators')
operators = [int(x) for x in operators_str.split(',')] if operators_str.strip() else []
time_wait_for_send_message = int(config.get('BotConfig', 'time_wait_for_send_message'))

# Состояние
media_group_dict = {}  # { media_group_id: {'items': [InputMedia...], 'timer': Timer, 'caption': str, 'user_id': int, 'sender_info': str, 'last_update': float} }
user_data = {}         # { user_id: {captcha_status, captcha_answer, message_pool_status, last_message_time} }

# Бот
bot = telebot.TeleBot(BOT_TOKEN)

# =============================
# УТИЛИТЫ/СЛУЖЕБНЫЕ ФУНКЦИИ
# =============================

def clear_dicts():
    global media_group_dict, user_data
    media_group_dict = {}
    user_data = {}
    print("[BOT] The dictionaries have been cleared")

def run_clear_dict_scheduler():
    my_scheduler = schedule.Scheduler()
    my_scheduler.every().day.at("03:00").do(clear_dicts)
    while True:
        my_scheduler.run_pending()
        time.sleep(1)

def can_send_message(user_id, current_time):
    """Антифлуд: текст не чаще, чем раз в N секунд."""
    if current_time - user_data[user_id]["last_message_time"] < time_wait_for_send_message:
        send_wait_60_sec(user_id)
        return False
    return True

def is_command(user_input: str) -> bool:
    if not user_input:
        return False
    return user_input.startswith("/") or user_input.startswith(("❗","📖","💬","🔄","◀️"))

def generate_captcha(user_id):
    num1 = random.randint(0, 10)
    num2 = random.randint(0, 10)
    ans = num1 + num2
    user_data[user_id]["captcha_answer"] = ans
    example = f"{num1} + {num2} = ?"
    send_solve_captcha(user_id, example)

def need_captcha(user_id):
    """True если пользователь ещё не прошёл капчу."""
    if user_data.get(user_id):
        return not user_data[user_id]["captcha_status"]
    return True

def new_user(user_id):
    user_data[user_id] = {
        "captcha_status": False,
        "captcha_answer": 12345,
        "message_pool_status": False,
        "last_message_time": 0,
    }

def message_pool(user_id):
    return user_data[user_id]["message_pool_status"]

def telegram_id_check(telegram_id: str) -> bool:
    return telegram_id.isdigit()

def chat_exists(user_id: int) -> bool:
    try:
        bot.get_chat(user_id)
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "chat not found" in str(e):
            return False
        else:
            raise e

def add_operator(user_id, operator_id):
    if not telegram_id_check(operator_id):
        bot.send_message(user_id, "❗Неверный формат Telegram ID (он должен быть числом)")
        return
    operator_id = int(operator_id)
    if not chat_exists(operator_id):
        bot.send_message(user_id, "❗Чата с этим пользователем не существует. Будущий оператор должен сначала написать боту")
        return
    global operators
    if operator_id not in operators:
        operators.append(operator_id)
        config.set('BotConfig', 'operators', ','.join(map(str, operators)))
        with open('config.ini', 'w') as f:
            config.write(f)
        bot.send_message(user_id, f"✅ Добавлен оператор: {operator_id}")
        print(f"[BOT] Operators list has been changed: {operators}")
    else:
        bot.send_message(user_id, "❗Такой оператор уже был добавлен")

def remove_operator(user_id, operator_id):
    if not telegram_id_check(operator_id):
        bot.send_message(user_id, "❗Неверный формат Telegram ID (он должен быть числом)")
        return
    operator_id = int(operator_id)
    global operators
    if operator_id in operators:
        operators.remove(operator_id)
        config.set('BotConfig', 'operators', ','.join(map(str, operators)))
        with open('config.ini', 'w') as f:
            config.write(f)
        bot.send_message(user_id, f"✅ Удалён оператор: {operator_id}")
        print(f"[BOT] Operators list has been changed: {operators}")
    else:
        bot.send_message(user_id, "❗Такого оператора нет")

def list_operator():
    return operators

# =============================
# ТЕКСТЫ
# =============================

BTN_INST = "📖 Инструкция"
BTN_SEND = "💬 Отправить сообщение"
BTN_BACK = "◀️ Назад"
BTN_NEW = "🔄 Новый пример"
BTN_OP_HELP = "📖 Инструкция оператора"

def send_instruction(user_id):
    message_instruction = (
        "🔘 Важно! Ваше сообщение отправляется анонимно. Если вам нужна обратная связь, "
        "пожалуйста, укажите в сообщении свои контактные данные (номер телефона, ссылка на соцсеть или юзернейм в Telegram).\n\n"
        "🔘 Пишите подробно и развернуто. Вы можете прикреплять к своему сообщению видеозаписи, фотографии, голосовые сообщения – всё это будет доставлено нам.\n\n"
        "🔘 Чтобы отправить сообщение, нажмите кнопку «Отправить сообщение» и напишите его после уведомления от бота.\n\n"
        "🔘 Вы получите уведомление о статусе доставки Вашего сообщения, как только оно будет получено нами."
    )
    bot.send_message(user_id, message_instruction, reply_markup=get_main_keyboard())

def send_bottask_message(user_id):
    bot.send_message(user_id, "❗Решите небольшое задание.\nЭто помогает нам отсеять ботов.", reply_markup=get_keyboard_captcha())

def send_wait_60_sec(user_id):
    bot.send_message(user_id, "❗Подождите 60 секунд перед отправкой следующего сообщения.", reply_markup=get_keyboard_message_pool())

def send_solve_captcha(user_id, example):
    bot.send_message(user_id, "❓Решите пример: " + str(example), reply_markup=get_keyboard_captcha())

def send_you_operator(user_id):
    bot.send_message(user_id, f"🔹 Вы оператор с Telegram ID: {user_id}", reply_markup=get_operator_keyboard())

def send_incorrect_unswer_captcha(user_id):
    bot.send_message(user_id, "❗Вы написали неверный ответ\nПожалуйста, будьте внимательнее!", reply_markup=get_keyboard_captcha())

def send_passed_captcha(user_id):
    bot.send_message(user_id, "✅ Проверка завершена!", reply_markup=get_main_keyboard())

def send_description(user_id):
    description = (
        "🇷🇺 *Присоединяйтесь к движению \"Свободная Россия!\"*\n\n"
        "🔘 Если вы хотите внести свой вклад в освобождение России и помочь нашей стране, присоединяйтесь к нашему народному движению. "
        "Вместе мы можем сделать нашу страну свободной от преступного, кровавого режима и построить будущее, которое она заслуживает.\n\n"
        "🔘 Вступайте в наши ряды и поддержите борьбу за справедливость. За вашу поддержку и участие в сопротивлении путинскому режиму предусмотрена зарплата и социальная защита.\n\n"
        "🔘 Свяжитесь с нами прямо сейчас, нажав кнопку \"💬 Отправить сообщение\". Также обязательно ознакомьтесь с инструкцией.\n\n"
        "🔘 Будущее России зависит от каждого из нас!"
    )
    bot.send_message(user_id, description, reply_markup=get_main_keyboard(), parse_mode="Markdown")

def send_warn_message_length(user_id):
    bot.send_message(user_id, "❗Длина сообщения должна превышать 8 символов, пожалуйста, старайтесь писать понятнее.", reply_markup=get_keyboard_message_pool())

def send_warn_you_cant_send_stickers(user_id):
    bot.send_message(user_id, "❗Вы не можете отправлять боту стикеры!\nПопробуйте передать информацию текстом, голосовым, фото или видео.", reply_markup=get_keyboard_message_pool())

def send_unknown_file_type(user_id):
    bot.send_message(user_id, "❗Такой тип файла нам неизвестен. Попробуйте другой способ (текст, голосовое, фото, видео).", reply_markup=get_keyboard_message_pool())

def send_message_sent_to_operator(user_id):
    bot.send_message(user_id, "✅ Спасибо! Ваше сообщение доставлено операторам.", reply_markup=get_keyboard_message_pool())

def send_you_in_message_pool(user_id):
    text = (
        "✉️ Напишите сообщение оператору здесь!\n\n"
        "❗Вы можете делиться любой важной информацией: видеозаписями и фотографиями воинских частей, координатами штабов и местонахождения российских сил, "
        "планами или другой ценной информацией. Всё это поможет нам в нашей работе.\n\n"
        "❗Хотите помочь разведывательной или иной деятельностью против режима? Пишите! Поможем материально и гарантируем соцзащиту.\n\n"
        "❗Ваше общение с чат-ботом остаётся анонимным. Если вы хотите получить ответ, укажите контакты.\n\n"
        "◀️ Изменили решение? Нажмите кнопку \"Назад\"."
    )
    bot.send_message(user_id, text, reply_markup=get_keyboard_message_pool())

def send_you_in_main_menu(user_id):
    bot.send_message(user_id, "🔘 Вы снова в главном меню!\n\n▶️ Выберите интересующую вас операцию на клавиатуре.", reply_markup=get_main_keyboard())

def send_warn_characters_forbidden(user_id):
    bot.send_message(user_id, "❗Сообщение не было доставлено. Символы '<', '>' и '\\\\' запрещены!", reply_markup=get_keyboard_message_pool())

# =============================
# КЛАВЫ
# =============================

def get_main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_SEND))
    kb.add(types.KeyboardButton(BTN_INST))
    return kb

def get_operator_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_OP_HELP))
    return kb

def get_keyboard_message_pool():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_BACK))
    return kb

def get_keyboard_captcha():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(BTN_NEW))
    return kb

# =============================
# МЕДИАГРУППЫ
# =============================

def _flush_media_group(group_id):
    """Отправка накопленной медиагруппы всем операторам одной пачкой."""
    grp = media_group_dict.pop(group_id, None)
    if not grp:
        return

    # Антифлуд
    uid = grp['user_id']
    now = time.time()
    if not can_send_message(uid, now):
        return
    user_data[uid]["last_message_time"] = now

    
    items = grp['items']
    if not items:
        return
    
    if grp['caption']:
        if isinstance(items[0], telebot.types.InputMediaPhoto):
            items[0].caption = grp['sender_info'] + "<b>Прикреплённый текст:</b>\n" + grp['caption']
            items[0].parse_mode = 'HTML'
        elif isinstance(items[0], telebot.types.InputMediaVideo):
            items[0].caption = grp['sender_info'] + "<b>Прикреплённый текст:</b>\n" + grp['caption']
            items[0].parse_mode = 'HTML'
    else:
        if isinstance(items[0], (telebot.types.InputMediaPhoto, telebot.types.InputMediaVideo)):
            items[0].caption = grp['sender_info']
            items[0].parse_mode = 'HTML'

    for operator_id in operators:
        try:
            bot.send_media_group(operator_id, items)
        except Exception as e:
            logging.error(f"send_media_group error to {operator_id}: {e}")
    send_message_sent_to_operator(uid)

def _schedule_group_flush(group_id, delay=1.2):
    """Запускаем/перезапускаем таймер для группового отправления."""
    grp = media_group_dict.get(group_id)
    if not grp:
        return
    timer = grp.get('timer')
    if timer and timer.is_alive():
        try:
            timer.cancel()
        except Exception:
            pass
    t = threading.Timer(delay, _flush_media_group, args=[group_id])
    grp['timer'] = t
    t.start()

def _append_media_group_item(message, sender_info):
    """Кладём элемент в группу."""
    gid = message.media_group_id
    if gid not in media_group_dict:
        media_group_dict[gid] = {
            'items': [],
            'timer': None,
            'caption': message.caption or "",
            'user_id': message.from_user.id,
            'sender_info': sender_info,
            'last_update': time.time()
        }
    grp = media_group_dict[gid]

    if message.photo:
        file_id = message.photo[-1].file_id
        grp['items'].append(telebot.types.InputMediaPhoto(media=file_id))
    elif message.video:
        file_id = message.video.file_id
        grp['items'].append(telebot.types.InputMediaVideo(media=file_id))

    grp['last_update'] = time.time()
    _schedule_group_flush(gid)

# =============================
# ОБРАБОТКА СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯ
# =============================

def user_message_handler(user_id, message):
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    message_timestamp = message.date
    message_text = message.text
    current_time = time.time()

    if message_text:
        if '\\\\' in message_text or '<' in message_text or '>' in message_text:
            send_warn_characters_forbidden(user_id)
            return

    moscow_timezone = pytz.timezone('Europe/Moscow')
    message_time = datetime.datetime.fromtimestamp(message_timestamp, tz=pytz.utc).astimezone(moscow_timezone)

    sender_info = f'<b>Telegram ID пользователя:</b> {user_id}\n'
    if username:
        sender_info += f'<b>Юзернейм:</b> @{username}\n'
    if first_name:
        sender_info += f'<b>Имя:</b> {first_name}\n'
    if last_name:
        sender_info += f'<b>Фамилия:</b> {last_name}\n'
    sender_info += f'<b>Дата/время [МСК]:</b> {message_time.strftime("%Y-%m-%d %H:%M:%S")}\n'

    # ТЕКСТ
    if message.text and not message.media_group_id:
        if len(message.text) <= 8:
            send_warn_message_length(user_id)
            return
        if not can_send_message(user_id, current_time):
            return
        for operator_id in operators:
            bot.send_message(operator_id, sender_info + f'<b>Сообщение:</b>\\n{message_text}', parse_mode='HTML')
        user_data[user_id]["last_message_time"] = current_time
        send_message_sent_to_operator(user_id)
        return

    # МЕДИА (включая caption и смешанную медиагруппу)
    if message.media_group_id:
        _append_media_group_item(message, sender_info)
        return

    # Одиночные медиа/файлы вне группы
    if message.photo:
        file_id = message.photo[-1].file_id
        if message.caption:
            for operator_id in operators:
                bot.send_photo(operator_id, file_id, caption=sender_info + f'<b>Прикреплённый текст:</b>\\n{message.caption}', parse_mode='HTML')
        else:
            for operator_id in operators:
                bot.send_photo(operator_id, file_id, caption=sender_info, parse_mode='HTML')
        send_message_sent_to_operator(user_id)
        return

    if message.video:
        file_id = message.video.file_id
        if message.caption:
            for operator_id in operators:
                bot.send_video(operator_id, file_id, caption=sender_info + f'<b>Прикреплённый текст:</b>\\n{message.caption}', parse_mode='HTML')
        else:
            for operator_id in operators:
                bot.send_video(operator_id, file_id, caption=sender_info, parse_mode='HTML')
        send_message_sent_to_operator(user_id)
        return

    if message.voice:
        file_id = message.voice.file_id
        if message.caption:
            for operator_id in operators:
                bot.send_voice(operator_id, file_id, caption=sender_info + f'<b>Прикреплённый текст:</b>\\n{message.caption}', parse_mode='HTML')
        else:
            for operator_id in operators:
                bot.send_voice(operator_id, file_id, caption=sender_info, parse_mode='HTML')
        send_message_sent_to_operator(user_id)
        return

    if message.location:
        latitude = message.location.latitude
        longitude = message.location.longitude
        for operator_id in operators:
            bot.send_message(operator_id, sender_info + f'<b>Прикреплена локация:</b>', parse_mode='HTML')
            bot.send_location(operator_id, latitude, longitude)
        send_message_sent_to_operator(user_id)
        return

    if message.document:
        file_id = message.document.file_id
        if message.caption:
            for operator_id in operators:
                bot.send_document(operator_id, file_id, caption=sender_info + f'<b>Прикреплённый текст:</b>\\n{message.caption}', parse_mode='HTML')
        else:
            for operator_id in operators:
                bot.send_document(operator_id, file_id, caption=sender_info, parse_mode='HTML')
        send_message_sent_to_operator(user_id)
        return

    if message.sticker:
        send_warn_you_cant_send_stickers(user_id)
        return

    send_unknown_file_type(user_id)

# =============================
# ОБРАБОТЧИКИ
# =============================

@bot.message_handler(func=lambda message: message, content_types=['audio','photo','voice','video','document','text','location','contact','sticker'])
def handle_message(message):
    user_id = message.from_user.id
    message_text = message.text or ""

    # ОПЕРАТОРЫ
    if user_id in operators:
        if is_command(message_text) and message_text.startswith("/add_operator"):
            args = message_text.split(' ')
            if len(args) >= 2:
                add_operator(user_id, args[1])
            else:
                bot.send_message(user_id, "❗Укажите Telegram ID оператора после команды", reply_markup=get_operator_keyboard())
            return

        if is_command(message_text) and message_text.startswith("/remove_operator"):
            args = message_text.split(' ')
            if len(args) >= 2:
                remove_operator(user_id, args[1])
            else:
                bot.send_message(user_id, "❗Укажите Telegram ID оператора после команды", reply_markup=get_operator_keyboard())
            return

        if is_command(message_text) and message_text.startswith("/list_operator"):
            bot.send_message(user_id, f"🔘 Операторы системы: {list_operator()}", reply_markup=get_operator_keyboard())
            return

        if is_command(message_text) and message_text.startswith("/send_answer"):
            parts = message_text.split(' ', 2)
            if len(parts) < 3:
                bot.send_message(user_id, "❗Использование: /send_answer <telegram_id> <текст>", reply_markup=get_operator_keyboard())
                return
            target_id_str, answer_text = parts[1], parts[2].strip()
            if not telegram_id_check(target_id_str):
                bot.send_message(user_id, "❗Неверный Telegram ID", reply_markup=get_operator_keyboard())
                return
            target_id = int(target_id_str)
            try:
                bot.send_message(target_id, f"📩 Ответ оператора:\n\n{answer_text}")
                bot.send_message(user_id, f"✅ Ответ отправлен пользователю {target_id}")
            except Exception as e:
                bot.send_message(user_id, f"❗Не удалось отправить сообщение: {e}")
            return

        if is_command(message_text) and message_text == BTN_OP_HELP:
            bot.send_message(user_id,
                "📖 Команды оператора:\n"
                "🔘 /list_operator — список операторов\n"
                "🔘 /add_operator [telegram_id] — добавить оператора\n"
                "🔘 /remove_operator [telegram_id] — удалить оператора\n"
                "🔘 /send_answer [telegram_id] [текст] — ответ пользователю",
                reply_markup=get_operator_keyboard()
            )
            return

        #Прочее
        send_you_operator(user_id)
        return

    # ЮЗЕРЫ
    if (not user_data.get(user_id)) or (message_text == "/start"):
        new_user(user_id)
        send_bottask_message(user_id)
        generate_captcha(user_id)
        return

    # Кнопки и команды
    if not need_captcha(user_id):
        if is_command(message_text) and message_text == BTN_INST:
            send_instruction(user_id)
            return
        elif is_command(message_text) and message_text == BTN_SEND:
            user_data[user_id]["message_pool_status"] = True
            send_you_in_message_pool(user_id)
            return
        elif not is_command(message_text) and message_pool(user_id):
            user_message_handler(user_id, message)
            return
        elif is_command(message_text) and message_text == BTN_BACK:
            user_data[user_id]["message_pool_status"] = False
            send_you_in_main_menu(user_id)
            return
        elif is_command(message_text) and message_text == "/get_telegram_id":
            bot.send_message(user_id, f"Твой Telegram ID: {user_id}")
            return

    if is_command(message_text) and message_text == BTN_NEW:
        generate_captcha(user_id)
        return

    # Проверка капчи
    if str(user_data[user_id]["captcha_answer"]) == message_text:
        user_data[user_id]["captcha_status"] = True
        send_passed_captcha(user_id)
        send_description(user_id)
    else:
        send_incorrect_unswer_captcha(user_id)
        generate_captcha(user_id)



def run_bot():
    while True:
        try:
            print("[BOT] Start!")
            print(f"[BOT] Operators: {operators}")
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            error_message = f"[BOT] ERROR: {str(e)}"
            print(error_message)
            logging.error(error_message)
            print("[BOT] Retry connecting after 10 seconds...")
            time.sleep(10)

clear_dict_thread = threading.Thread(target=run_clear_dict_scheduler, daemon=True)
bot_thread = threading.Thread(target=run_bot, daemon=True)

clear_dict_thread.start()
bot_thread.start()

clear_dict_thread.join()
bot_thread.join()
