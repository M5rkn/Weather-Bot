import asyncio
import logging
import os
from datetime import datetime
from typing import List, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Константы
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Курс валют по умолчанию (обновляется при запуске)
EXCHANGE_RATES = {"EUR": 1.0, "UAH": 44.5}

# Список городов (название, широта, долгота)
CITIES: List[Tuple[str, float, float]] = [
    ("Кёльн", 50.9375, 6.9603),
    ("Линц-ам-Райн", 50.5667, 7.3167),
    ("Нюмбрехт", 50.9167, 7.6333),
    ("Гуммерсбах", 51.0236, 7.5628),
    ("Виль", 50.9167, 7.5333),
    ("Диренхаузен", 50.8833, 7.6167),
    ("Вальдбрель", 50.9333, 7.7167),
]


async def get_exchange_rates() -> dict:
    """Получает актуальные курсы валют от ПриватБанк API."""
    import aiohttp
    
    url = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    rates = {"EUR": 1.0, "UAH": 44.5}
                    for item in data:
                        if item.get("ccy") == "EUR":
                            rates["EUR"] = float(item.get("sale", "44.5"))
                            rates["UAH"] = 1.0
                    return rates
                else:
                    logging.error(f"API курсов валют: {response.status}")
                    return EXCHANGE_RATES
        except Exception as e:
            logging.error(f"Ошибка получения курсов: {e}")
            return EXCHANGE_RATES


def convert_currency(amount: float, from_currency: str, to_currency: str, rates: dict) -> tuple:
    """Конвертирует сумму из одной валюты в другую."""
    if from_currency == to_currency:
        return amount, rates.get(from_currency, 1.0)
    
    # Конвертируем через базовую валюту
    if from_currency == "EUR":
        result = amount * rates.get("EUR", 1.0)
        rate = rates.get("EUR", 1.0)
    else:  # UAH
        result = amount / rates.get("EUR", 1.0)
        rate = 1.0 / rates.get("EUR", 1.0)
    
    return result, rate


def get_currency_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для конвертера валют."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="€ EUR → ₴ UAH", callback_data="conv_eur_uah"),
            InlineKeyboardButton(text="₴ UAH → € EUR", callback_data="conv_uah_eur"),
        ],
        [InlineKeyboardButton(text="🔄 Обновить курс", callback_data="currency_rates")],
    ])


async def get_weather(city_name: str, lat: float, lon: float) -> dict | None:
    """Получает данные о погоде от OpenWeatherMap API."""
    import aiohttp

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                # Заменяем название города на наше
                data["name"] = city_name
                return data
            else:
                error_text = await response.text()
                logging.error(f"Ошибка API: {response.status} - {error_text}")
                return None


async def get_forecast(city_name: str, lat: float, lon: float) -> List[dict] | None:
    """Получает прогноз погоды на 3 дня от OpenWeatherMap API."""
    import aiohttp

    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                # Группируем по дням (берём данные на 12:00 для каждого дня)
                forecast_list = data.get("list", [])
                daily_forecast = {}
                
                for item in forecast_list:
                    dt_txt = item.get("dt_txt", "")
                    if "12:00:00" in dt_txt:
                        date = dt_txt.split(" ")[0]
                        daily_forecast[date] = {
                            "date": date,
                            "temp": item["main"]["temp"],
                            "feels_like": item["main"]["feels_like"],
                            "description": item["weather"][0]["description"],
                            "icon": item["weather"][0]["icon"],
                            "humidity": item["main"]["humidity"],
                            "wind": item["wind"]["speed"],
                        }
                
                return list(daily_forecast.values())[:3]  # Первые 3 дня
            else:
                error_text = await response.text()
                logging.error(f"Ошибка API прогноза: {response.status} - {error_text}")
                return None


def format_forecast(city_name: str, forecast_list: List[dict]) -> str:
    """Форматирует прогноз погоды на 3 дня."""
    weather_emojis = {
        "01d": "☀️", "02d": "⛅", "03d": "☁️", "04d": "☁️",
        "09d": "🌧️", "10d": "🌦️", "11d": "⛈️", "13d": "❄️", "50d": "🌫️",
        "01n": "🌙", "02n": "⛅", "03n": "☁️", "04n": "☁️",
        "09n": "🌧️", "10n": "🌦️", "11n": "⛈️", "13n": "❄️", "50n": "🌫️",
    }
    
    days_ru = {
        "Mon": "Пн", "Tue": "Вт", "Wed": "Ср", "Thu": "Чт",
        "Fri": "Пт", "Sat": "Сб", "Sun": "Вс"
    }
    
    result = f"📅 **Прогноз на 3 дня: {city_name}**\n\n"
    
    for day in forecast_list:
        date = day["date"]
        day_name = date.split("-")
        if len(day_name) >= 3:
            from datetime import datetime
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                day_short = days_ru.get(dt.strftime("%a"), date)
            except:
                day_short = date[5:]  # MM-DD
        else:
            day_short = date
        
        icon = day["icon"]
        emoji = weather_emojis.get(icon, "🌡️")
        temp = round(day["temp"])
        feels = round(day["feels_like"])
        desc = day["description"].capitalize()
        humidity = day["humidity"]
        wind = day["wind"]
        
        result += (
            f"**{day_short}** {emoji}\n"
            f"🌡️ {temp}°C (ощущается как {feels}°C)\n"
            f"📝 {desc}\n"
            f"💧 {humidity}% | 💨 {wind} м/с\n\n"
        )
    
    return result.strip()


def get_cities_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопками городов."""
    keyboard = []
    for i, city in enumerate(CITIES):
        if i % 2 == 0:  # Новая строка
            keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(text=city[0], callback_data=f"weather_{city[0]}"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_forecast_keyboard(city_name: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с прогнозом для города."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Прогноз на 3 дня", callback_data=f"forecast_{city_name}")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"weather_{city_name}")],
    ])


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Создаёт основную клавиатуру бота."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌤️ Погода во всех городах", callback_data="weather_all")],
        [InlineKeyboardButton(text="📅 Прогноз на 3 дня", callback_data="forecast_all")],
        [InlineKeyboardButton(text="💱 Конвертер валют", callback_data="currency")],
        [InlineKeyboardButton(text="📍 Список городов", callback_data="list_cities")],
    ])


def format_weather(data: dict) -> str:
    """Форматирует данные о погоде для вывода."""
    city = data["name"]
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    pressure = data["main"]["pressure"]
    wind_speed = data["wind"]["speed"]
    description = data["weather"][0]["description"]
    icon = data["weather"][0]["icon"]

    # Получаем эмодзи для погоды
    weather_emojis = {
        "01d": "☀️",
        "01n": "🌙",
        "02d": "⛅",
        "02n": "⛅",
        "03d": "☁️",
        "03n": "☁️",
        "04d": "☁️",
        "04n": "☁️",
        "09d": "🌧️",
        "09n": "🌧️",
        "10d": "🌦️",
        "10n": "🌦️",
        "11d": "⛈️",
        "11n": "⛈️",
        "13d": "❄️",
        "13n": "❄️",
        "50d": "🌫️",
        "50n": "🌫️",
    }
    emoji = weather_emojis.get(icon, "🌡️")

    return (
        f"{emoji} **Погода в городе {city}**\n\n"
        f"🌡️ Температура: {temp}°C (ощущается как {feels_like}°C)\n"
        f"📝 Описание: {description.capitalize()}\n"
        f"💧 Влажность: {humidity}%\n"
        f"🔽 Давление: {pressure} гПа\n"
        f"💨 Ветер: {wind_speed} м/с\n"
        f"🕒 Обновлено: {datetime.fromtimestamp(data['dt']).strftime('%H:%M')}"
    )


async def cmd_start(message: types.Message):
    """Обработчик команды /start."""
    await message.answer(
        "👋 Привет! Я бот для показа погоды и конвертации валют.\n\n"
        f"📍 Города: {', '.join([c[0] for c in CITIES])}\n\n"
        "**Команды:**\n"
        "/weather - погода во всех городах\n"
        "/forecast - прогноз на 3 дня\n"
        "/currency - конвертер валют (EUR ↔ UAH)\n"
        "/city <название> - погода в городе\n"
        "/help - справка\n\n"
        "Или используйте кнопки ниже:",
        reply_markup=get_main_keyboard(),
    )


async def cmd_help(message: types.Message):
    """Обработчик команды /help."""
    cities_list = "\n".join([f"• {city[0]}" for city in CITIES])

    await message.answer(
        f"📖 **Справка**\n\n"
        "Этот бот показывает погоду, прогноз и конвертирует валюты.\n\n"
        f"**Города ({len(CITIES)} шт.):**\n"
        f"{cities_list}\n\n"
        "**Команды:**\n"
        "/weather - погода во всех городах\n"
        "/forecast - прогноз на 3 дня для всех городов\n"
        "/currency - конвертер валют (EUR ↔ UAH)\n"
        "/city <название> - погода в конкретном городе\n"
        "/near - список городов\n\n"
        "Или используйте кнопки под сообщениями.",
        reply_markup=get_main_keyboard(),
    )


async def cmd_weather(message: types.Message):
    """Обработчик команды /weather - показывает погоду во всех городах."""
    await message.answer(f"🔄 Загружаю погоду для {len(CITIES)} городов...")

    for city_name, lat, lon in CITIES:
        weather_data = await get_weather(city_name, lat, lon)
        if weather_data:
            text = format_weather(weather_data)
            await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer(f"❌ Не удалось получить погоду для города {city_name}")


async def cmd_city(message: types.Message):
    """Обработчик команды /city <название>."""
    from aiogram.filters import CommandObject
    
    # Получаем аргументы команды
    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2:
        await message.answer(
            "❌ Укажите название города.\nПример: /city Кёльн"
        )
        return

    city_query = cmd[1].lower()

    # Ищем город в списке
    found_city = None
    for city_name, lat, lon in CITIES:
        if city_query in city_name.lower() or city_name.lower() in city_query:
            found_city = (city_name, lat, lon)
            break

    if not found_city:
        await message.answer(
            f"❌ Город '{cmd[1]}' не найден.\n"
            "Используйте команду /near чтобы увидеть список доступных городов."
        )
        return

    weather_data = await get_weather(*found_city)
    if weather_data:
        text = format_weather(weather_data)
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer(f"❌ Не удалось получить погоду для города {found_city[0]}")


async def cmd_near(message: types.Message):
    """Обработчик команды /near - показывает список городов."""
    cities_text = "\n".join(
        [f"{i+1}. {city[0]}" for i, city in enumerate(CITIES)]
    )

    await message.answer(
        f"📍 **Доступные города:**\n\n"
        f"{cities_text}\n\n"
        f"Всего: {len(CITIES)} города",
        parse_mode="Markdown",
        reply_markup=get_cities_keyboard(),
    )


async def cmd_forecast(message: types.Message):
    """Обработчик команды /forecast - прогноз на 3 дня для всех городов."""
    await message.answer(f"🔄 Загружаю прогноз на 3 дня для {len(CITIES)} городов...")

    for city_name, lat, lon in CITIES:
        forecast_data = await get_forecast(city_name, lat, lon)
        if forecast_data:
            text = format_forecast(city_name, forecast_data)
            await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer(f"❌ Не удалось получить прогноз для города {city_name}")


async def cmd_currency(message: types.Message):
    """Обработчик команды /currency - конвертер валют."""
    # Парсим команду: /currency 100 EUR или /currency 1000 UAH
    parts = message.text.split()
    
    if len(parts) < 2:
        # Показать текущие курсы
        rates = await get_exchange_rates()
        eur_rate = rates.get("EUR", 1.0)
        
        await message.answer(
            f"💱 **Курс валют (ПриватБанк)**\n\n"
            f"🇪🇺 1 EUR = {eur_rate:.2f} ₴ UAH\n"
            f"🇺🇦 1 UAH = {1/eur_rate:.4f} € EUR\n\n"
            f"**Примеры:**\n"
            f"/currency 100 EUR - конвертировать 100 евро в гривны\n"
            f"/currency 1000 UAH - конвертировать 1000 гривен в евро\n\n"
            f"Или используйте кнопки ниже:",
            reply_markup=get_currency_keyboard(),
            parse_mode="Markdown",
        )
        return
    
    # Получаем сумму и валюту
    amount_str = parts[1].replace(",", ".")
    currency = parts[2].upper() if len(parts) > 2 else None
    
    try:
        amount = float(amount_str)
    except ValueError:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Примеры:\n"
            "/currency 100 EUR\n"
            "/currency 1000 UAH"
        )
        return
    
    # Если валюта не указана, определяем автоматически
    if currency is None:
        if amount >= 100:  # Если сумма >= 100, считаем что это UAH
            currency = "UAH"
        else:  # Если < 100, считаем что это EUR
            currency = "EUR"
    
    if currency not in ["EUR", "UAH"]:
        await message.answer(
            "❌ Поддерживаются только EUR и UAH.\n\n"
            "Примеры:\n"
            "/currency 100 EUR\n"
            "/currency 1000 UAH"
        )
        return
    
    rates = await get_exchange_rates()
    
    if currency == "EUR":
        converted, rate = convert_currency(amount, "EUR", "UAH", rates)
        await message.answer(
            f"💱 **Конвертация**\n\n"
            f"{amount:.2f} € EUR = {converted:.2f} ₴ UAH\n\n"
            f"Курс: 1 EUR = {rate:.2f} UAH",
            parse_mode="Markdown",
        )
    else:
        converted, rate = convert_currency(amount, "UAH", "EUR", rates)
        await message.answer(
            f"💱 **Конвертация**\n\n"
            f"{amount:.2f} ₴ UAH = {converted:.2f} € EUR\n\n"
            f"Курс: 1 UAH = {rate:.4f} EUR",
            parse_mode="Markdown",
        )


async def process_callback(call: types.CallbackQuery):
    """Обработчик нажатий на кнопки."""
    action = call.data
    
    if action == "weather_all":
        await call.message.edit_text(
            f"🔄 Загружаю погоду для {len(CITIES)} городов...",
            reply_markup=get_main_keyboard(),
        )
        for city_name, lat, lon in CITIES:
            weather_data = await get_weather(city_name, lat, lon)
            if weather_data:
                text = format_weather(weather_data)
                keyboard = get_forecast_keyboard(city_name)
                await call.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await call.message.answer(f"❌ Не удалось получить погоду для города {city_name}")
        await call.answer()
    
    elif action == "forecast_all":
        await call.message.edit_text(
            f"🔄 Загружаю прогноз на 3 дня для {len(CITIES)} городов...",
            reply_markup=get_main_keyboard(),
        )
        for city_name, lat, lon in CITIES:
            forecast_data = await get_forecast(city_name, lat, lon)
            if forecast_data:
                text = format_forecast(city_name, forecast_data)
                await call.message.answer(text, parse_mode="Markdown")
            else:
                await call.message.answer(f"❌ Не удалось получить прогноз для города {city_name}")
        await call.answer()
    
    elif action == "list_cities":
        cities_text = "\n".join([f"{i+1}. {city[0]}" for i, city in enumerate(CITIES)])
        await call.message.edit_text(
            f"📍 **Доступные города:**\n\n{cities_text}\n\nВсего: {len(CITIES)} города",
            parse_mode="Markdown",
            reply_markup=get_cities_keyboard(),
        )
        await call.answer()
    
    elif action.startswith("weather_"):
        city_name = action.replace("weather_", "")
        await call.message.answer(f"🔄 Загружаю погоду для города {city_name}...")
        
        # Ищем город
        for c_name, lat, lon in CITIES:
            if c_name == city_name:
                weather_data = await get_weather(c_name, lat, lon)
                if weather_data:
                    text = format_weather(weather_data)
                    keyboard = get_forecast_keyboard(city_name)
                    await call.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
                else:
                    await call.message.answer(f"❌ Не удалось получить погоду для города {city_name}")
                break
        await call.answer()
    
    elif action.startswith("forecast_"):
        city_name = action.replace("forecast_", "")
        await call.message.answer(f"🔄 Загружаю прогноз на 3 дня для города {city_name}...")

        # Ищем город
        for c_name, lat, lon in CITIES:
            if c_name == city_name:
                forecast_data = await get_forecast(c_name, lat, lon)
                if forecast_data:
                    text = format_forecast(c_name, forecast_data)
                    await call.message.answer(text, parse_mode="Markdown")
                else:
                    await call.message.answer(f"❌ Не удалось получить прогноз для города {city_name}")
                break
        await call.answer()

    elif action == "currency":
        rates = await get_exchange_rates()
        eur_rate = rates.get("EUR", 1.0)
        await call.message.answer(
            f"💱 **Курс валют (ПриватБанк)**\n\n"
            f"🇪🇺 1 EUR = {eur_rate:.2f} ₴ UAH\n"
            f"🇺🇦 1 UAH = {1/eur_rate:.4f} € EUR\n\n"
            f"**Примеры:**\n"
            f"/currency 100 EUR\n"
            f"/currency 1000 UAH",
            parse_mode="Markdown",
            reply_markup=get_currency_keyboard(),
        )
        await call.answer()

    elif action == "currency_rates":
        rates = await get_exchange_rates()
        eur_rate = rates.get("EUR", 1.0)
        await call.message.edit_text(
            f"💱 **Курс валют (ПриватБанк)**\n\n"
            f"🇪🇺 1 EUR = {eur_rate:.2f} ₴ UAH\n"
            f"🇺🇦 1 UAH = {1/eur_rate:.4f} € EUR\n\n"
            f"_Обновлено: {datetime.now().strftime('%H:%M')}_",
            parse_mode="Markdown",
            reply_markup=get_currency_keyboard(),
        )
        await call.answer()

    elif action == "conv_eur_uah":
        await call.message.answer(
            "💱 **EUR → UAH**\n\n"
            f"Введите сумму в евро:\n"
            f"Пример: `/currency 100 EUR`",
            parse_mode="Markdown",
        )
        await call.answer()

    elif action == "conv_uah_eur":
        await call.message.answer(
            "💱 **UAH → EUR**\n\n"
            f"Введите сумму в гривнах:\n"
            f"Пример: `/currency 1000 UAH`",
            parse_mode="Markdown",
        )
        await call.answer()


async def main():
    """Основная функция запуска бота."""
    if not BOT_TOKEN:
        logging.error("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
        return

    if not OPENWEATHER_API_KEY:
        logging.error("❌ OPENWEATHER_API_KEY не найден в переменных окружения!")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрация обработчиков сообщений
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_weather, Command("weather"))
    dp.message.register(cmd_forecast, Command("forecast"))
    dp.message.register(cmd_currency, Command("currency"))
    dp.message.register(cmd_near, Command("near"))
    dp.message.register(cmd_city, lambda msg: msg.text and msg.text.startswith("/city"))
    
    # Регистрация обработчика callback query (кнопки)
    dp.callback_query.register(process_callback)

    logging.info("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
