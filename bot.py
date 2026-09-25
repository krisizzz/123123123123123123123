import json
import os
import requests
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================== CONFIGURATION ==================
TELEGRAM_TOKEN = "8996725656:AAGVkpKzTuDtXkVmd15KIJucgCY-tsxkBUs"

ADMIN_ID = 8961457975
SUBSCRIBERS_FILE = "subscribers.json"

# --- OpenWeatherMap ---
OPENWEATHER_API_KEY = "ad20dbbdbcbc4ab10217df049c9150fa"
CITY = "Могилёв"
TIMEZONE = "Europe/Minsk"

# ==== WEEKLY SCHEDULE (9 "Б", first term 2026/2027) ====
LESSON_TIMES = {
    2: "10:00–10:45",
    3: "11:00–11:45",
    4: "12:00–12:45",
    5: "13:00–13:45",
    6: "14:00–14:45",
    7: "15:00–15:45",
    8: "16:00–16:45",
}

WEEKLY_SCHEDULE = {
    0: {2: "Русский язык", 3: "Английский язык", 4: "Русская литература",
        5: "География", 6: "Математика", 7: "Классный час"},
    1: {2: "Физика", 3: "Химия", 4: "Английский язык",
        5: "Всемирная история", 6: "Математика"},
    2: {2: "История Беларуси", 3: "Математика", 4: "Биология",
        5: "Белорусский язык", 6: "Белорусская литература", 7: "Факультатив по истории"},
    3: {2: "Русский язык", 3: "Физика", 4: "География",
        5: "Информатика / Английский язык", 6: "Английский язык / Информатика",
        7: "Русская литература", 8: "Информационный час"},
    4: {2: "Физика", 3: "Математика", 4: "Химия",
        5: "Обществоведение", 6: "Белорусский язык", 7: "Искусство"},
}

WEEKDAY_NAMES = {0: "Понедельник", 1: "Вторник", 2: "Среда",
                 3: "Четверг", 4: "Пятница"}
# ===================================================

application: Application = None


def load_subscribers() -> set:
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_subscribers(subs: set):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(subs), f, ensure_ascii=False, indent=2)


subscribers: set = load_subscribers()


def build_report() -> str:
    """Build the daily report text (schedule + weather)."""
    now = datetime.now()
    weekday = now.weekday()

    if weekday > 4:
        return ""

    today_name = WEEKDAY_NAMES[weekday]
    lessons = WEEKLY_SCHEDULE.get(weekday, {})

    if lessons:
        lessons_text = "\n".join(
            f"  • {LESSON_TIMES[num]} — {subject}"
            for num, subject in sorted(lessons.items())
        )
    else:
        lessons_text = "  🎉 Сегодня уроков нет!"

    weather_info = "Не удалось получить данные о погоде."
    advice = ""

    try:
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": CITY,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric",
            "lang": "ru",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if str(data.get("cod")) == "200":
            temp = round(data["main"]["temp"])
            feels_like = round(data["main"]["feels_like"])
            humidity = data["main"]["humidity"]
            wind = data["wind"]["speed"]
            desc = data["weather"][0]["description"].capitalize()

            weather_info = (
                f"🌡 Температура: {temp}°C (ощущается как {feels_like}°C)\n"
                f"☁️ Состояние: {desc}\n"
                f"💧 Влажность: {humidity}%\n"
                f"💨 Ветер: {wind} м/с"
            )

            if temp <= 0:
                advice = "🥶 Очень холодно. Надень тёплую куртку, шапку и перчатки."
            elif temp <= 10:
                advice = "🧥 Прохладно. Рекомендуется куртка или свитер."
            elif temp <= 20:
                advice = "👕 Комфортно. Лёгкая куртка или рубашка с длинным рукавом."
            elif temp <= 30:
                advice = "☀️ Тепло. Лёгкая одежда и солнцезащитный крем."
            else:
                advice = "🔥 Жарко. Пей больше воды, избегай долгого пребывания на улице."

            desc_lower = desc.lower()
            if any(w in desc_lower for w in ["дождь", "морось", "ливень"]):
                advice += "\n☔ Ожидается дождь — возьми зонт!"
            if "снег" in desc_lower:
                advice += "\n❄️ Ожидается снег — одевайся теплее и смотри под ноги."
            if wind > 10:
                advice += "\n🌬 Сильный ветер — держи шапку!"
        else:
            error_msg = data.get("message", "неизвестная ошибка")
            weather_info = f"Ошибка запроса погоды: {error_msg}"
    except Exception as e:
        weather_info = f"Ошибка запроса погоды: {e}"

    return (
        f"☀️ Доброе утро! {now.strftime('%d.%m.%Y')} ({today_name})\n"
        f"{'=' * 30}\n"
        f"📚 Расписание на сегодня:\n"
        f"{lessons_text}\n"
        f"{'=' * 30}\n"
        f"🌤 Погода в Могилёве:\n"
        f"{weather_info}\n"
        f"{'=' * 30}\n"
        f"💡 Совет:\n"
        f"{advice}\n"
        f"{'=' * 30}\n"
        f"Хорошего дня! 😊"
    )


async def send_daily_report():
    """Send report to all subscribers. Runs Mon–Fri at 6:50."""
    now = datetime.now()
    if now.weekday() > 4:
        return
    text = build_report()
    if not text:
        return

    dead = set()
    for uid in list(subscribers):
        try:
            await application.bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            print(f"⚠️ Не удалось отправить {uid}: {e}")
            dead.add(uid)

    if dead:
        subscribers.difference_update(dead)
        save_subscribers(subscribers)


async def start_handler(update, context):
    uid = update.effective_chat.id
    if uid not in subscribers:
        subscribers.add(uid)
        save_subscribers(subscribers)
        added = True
    else:
        added = False

    await update.message.reply_text(
        f"🤖 Привет! Ты подписан на ежедневную рассылку расписания и погоды.\n"
        f"Каждый день в 06:50 (Пн–Пт) буду присылать отчёт.\n\n"
        f"Твой ID: {uid}\n"
        f"{'✅ Ты добавлен в список.' if added else 'ℹ️ Ты уже в списке.'}"
    )


async def stop_handler(update, context):
    uid = update.effective_chat.id
    if uid in subscribers:
        subscribers.discard(uid)
        save_subscribers(subscribers)
        await update.message.reply_text("❌ Ты отписан от рассылки.")
    else:
        await update.message.reply_text("Ты и так не подписан.")


async def test_handler(update, context):
    await update.message.reply_text("Отправляю тестовый отчёт...")
    text = build_report()
    if not text:
        await update.message.reply_text("Сегодня выходной — отчёта нет.")
        return
    await update.message.reply_text(text)


async def stats_handler(update, context):
    uid = update.effective_chat.id
    if uid != ADMIN_ID:
        await update.message.reply_text("Команда только для администратора.")
        return
    await update.message.reply_text(
        f"📊 Подписчиков: {len(subscribers)}\n"
        f"ID: {sorted(subscribers)}"
    )


async def broadcast_handler(update, context):
    uid = update.effective_chat.id
    if uid != ADMIN_ID:
        await update.message.reply_text("Команда только для администратора.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Использование: /broadcast текст")
        return
    sent = 0
    for sid in list(subscribers):
        try:
            await application.bot.send_message(chat_id=sid, text=text)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} получателям.")


async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        send_daily_report,
        "cron",
        hour=6,
        minute=50,
        day_of_week="mon-fri",
    )
    scheduler.start()


def main():
    global application
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("stop", stop_handler))
    application.add_handler(CommandHandler("test", test_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))

    print(f"🤖 Бот запущен. Подписчиков: {len(subscribers)}")
    application.run_polling()


if __name__ == "__main__":
    main()
