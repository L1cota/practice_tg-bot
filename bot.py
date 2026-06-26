import asyncio
import sys

# Полностью убираем сбойную политику циклов для 3.14
# if sys.platform == 'win32':
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import sqlite3
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, html
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# ИМПОРТИРУЕМ СЕССИЮ С НАСТРОЙКОЙ СЛУЖБЫ АДРЕСОВ
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO)

TOKEN = "BOT_TOKEN"

session = AiohttpSession(
    timeout=ClientTimeout(total=30, connect=15)
)

# Возвращаем стандартный стабильный Bot (благодаря фиксу выше он больше не упадет)
bot = Bot(token=TOKEN)
dp = Dispatcher()

GROUPS = [f"Группа {i}" for i in range(1, 13)]

# --- БЛОК 1: БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            selected_group TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_user_group(user_id: int) -> str:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT selected_group FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def update_user(user_id: int, username: str, group_name: str = None):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    safe_username = username if username else "Не указан"
    if group_name:
        cursor.execute("""
            INSERT INTO users (user_id, username, selected_group) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id) DO UPDATE SET 
                username = excluded.username, 
                selected_group = excluded.selected_group
        """, (user_id, safe_username, group_name))
    else:
        cursor.execute("""
            INSERT INTO users (user_id, username) 
            VALUES (?, ?) 
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, safe_username))
    conn.commit()
    conn.close()

# --- БЛОК 2: СТАТУС ПАРЫ ---
def get_lesson_status(date_str: str, time_slot: str) -> str:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    if date_str < today_str:
        return "⚫ Пара закончилась"
    elif date_str > today_str:
        return "⚪ Пара еще не началась"
        
    try:
        time_clean = time_slot.replace(" ", "").replace("–", "-")
        time_parts = time_clean.split("-")
        start_str, end_str = time_parts[0], time_parts[1]
        
        if ":" not in start_str:
            start_str = f"{start_str[:-2].zfill(2)}:{start_str[-2:]}"
        if ":" not in end_str:
            end_str = f"{end_str[:-2].zfill(2)}:{end_str[-2:]}"

        start_time = datetime.strptime(f"{today_str} {start_str}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{today_str} {end_str}", "%Y-%m-%d %H:%M")
        
        if now < start_time:
            return "⚪ Занятие еще не началось"
        elif start_time <= now <= end_time:
            return "🟢 Идет занятие"
        else:
            return "⚫ Занятие закончилось"
    except Exception:
        return "🔹 Занятие"

# --- БЛОК 3: ТЕКСТ РАСПИСАНИЯ ---
def load_schedule(group: str, date_str: str) -> str:
    try:
        with open("schedule.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return "⚠️ Ошибка: Файл schedule.json не найден."

    if group not in data:
        return f"Расписание для группы {html.quote(group)} не найдено."

    group_data = data[group]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    pretty_date = date_obj.strftime("%d.%m.%Y")

    text = f"<b>Расписание группы {html.quote(group)[-1]} на {pretty_date}</b>\n\n"

    if date_str not in group_data or not group_data[date_str]["lessons"]:
        text += "В этот день занятий нет."
        return text

    for lesson in group_data[date_str]["lessons"]:
        status = get_lesson_status(date_str, lesson["time"])
        
        safe_subject = html.quote(lesson['subject'])
        safe_classroom = html.quote(lesson['classroom'])
        safe_teacher = html.quote(lesson['teacher'])
        safe_time = html.quote(lesson['time'])
        
        text += f"{status}\n"
        text += f"{safe_time}\n"
        text += f"{safe_subject} {safe_classroom}\n"
        text += f"({safe_teacher})\n\n"
        
    return text.strip()

# --- БЛОК 4: КЛАВИАТУРЫ ---
def get_schedule_keyboard(current_date_str: str) -> InlineKeyboardMarkup:
    current_date = datetime.strptime(current_date_str, "%Y-%m-%d")
    start_of_week = current_date - timedelta(days=current_date.weekday())
    
    builder = InlineKeyboardBuilder()
    
    week_days = [
        ("Пн", 0), ("Вт", 1), ("Ср", 2), 
        ("Чт", 3), ("Пт", 4)
    ]
    
    for name, day_offset in week_days:
        day_date = start_of_week + timedelta(days=day_offset)
        day_date_str = day_date.strftime("%Y-%m-%d")
        
        btn_text = f"[{name}]" if day_date_str == current_date_str else name
        builder.button(text=btn_text, callback_data=f"show_date:{day_date_str}")
        
    builder.adjust(3, 2)
    
    prev_week_date = (current_date - timedelta(weeks=1)).strftime("%Y-%m-%d")
    next_week_date = (current_date + timedelta(weeks=1)).strftime("%Y-%m-%d")
    
    end_of_week = start_of_week + timedelta(days=4)
    week_range_text = f"{start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m')}"
    
    row_buttons = [
        InlineKeyboardButton(text="<<", callback_data=f"show_date:{prev_week_date}"),
        InlineKeyboardButton(text=week_range_text, callback_data="current_week_ignore"),
        InlineKeyboardButton(text=">>", callback_data=f"show_date:{next_week_date}")
    ]
    
    builder.row(*row_buttons)
    return builder.as_markup()

def get_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="ℹ️ Информация"), KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_groups_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in GROUPS:
        builder.button(text=group, callback_data=f"set_group:{group}")
    builder.adjust(2)
    return builder.as_markup()

# --- БЛОК 5: ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    username = message.from_user.username or message.from_user.first_name
    update_user(message.from_user.id, username)
    
    await message.answer(
        "Привет! Я бот для просмотра расписания летней практики 2026.\n"
        "Пожалуйста, выбери свою учебную группу:",
        reply_markup=get_groups_keyboard()
    )

@dp.callback_query(F.data.startswith("set_group:"))
async def callback_set_group(callback: CallbackQuery):
    group_name = callback.data.split(":")[1]
    username = callback.from_user.username or callback.from_user.first_name
    
    update_user(callback.from_user.id, username, group_name)
    
    await callback.answer(f"{group_name} выбрана.")
    await callback.message.answer(
        f"{group_name} закреплена за вашим профилем.",
        reply_markup=get_main_menu()
    )
    await callback.message.delete()

@dp.message(F.text == "📅 Расписание")
async def show_today_schedule(message: Message):
    group = get_user_group(message.from_user.id)
    if not group:
        await message.answer("Сначала выберите группу с помощью команды /start")
        return

    username = message.from_user.username or message.from_user.first_name
    update_user(message.from_user.id, username)

    today_str = datetime.now().strftime("%Y-%m-%d")
    text = load_schedule(group, today_str)
    
    await message.answer(
        text=text, 
        reply_markup=get_schedule_keyboard(today_str), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("show_date:"))
async def change_schedule_date(callback: CallbackQuery):
    group = get_user_group(callback.from_user.id)
    if not group:
        await callback.answer("Группа не выбрана. Введите /start", show_alert=True)
        return

    username = callback.from_user.username or callback.from_user.first_name
    update_user(callback.from_user.id, username)

    target_date_str = callback.data.split(":")[1]
    new_text = load_schedule(group, target_date_str)

    if callback.message.text != new_text:
        try:
            await callback.message.edit_text(
                text=new_text,
                reply_markup=get_schedule_keyboard(target_date_str),
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass
    await callback.answer()

@dp.callback_query(F.data == "current_week_ignore")
async def week_stub_callback(callback: CallbackQuery):
    await callback.answer()

@dp.message(F.text == "ℹ️ Информация")
async def show_info(message: Message):
    text = (
        "<b>Информация о практике 2026</b>\n\n"
        "Руководители:\n"
        "— Кузин В.В. (ауд. 303)\n"
        "— Хрушкова Е.А. (ауд. 203)\n\n"
        "Все отчеты сдаются строго в установленные сроки."
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    group = get_user_group(message.from_user.id) or "Не выбрана"
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить группу", callback_data="change_group")]
    ])
    await message.answer(
        f"Ваша текущая группа: <b>{group}</b>",
        reply_markup=inline_kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "change_group")
async def process_change_group(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите учебную группу:",
        reply_markup=get_groups_keyboard()
    )
    await callback.answer()

# --- СТАРТ ---
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())