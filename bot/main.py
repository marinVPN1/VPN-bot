import os
import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
import json

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
API_URL = os.getenv("API_URL", "http://backend:8000")

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# States
class PaymentState(StatesGroup):
    waiting_for_tariff = State()

class ExtendState(StatesGroup):
    waiting_for_days = State()

# Helper functions
async def api_request(method: str, endpoint: str, data: dict = None):
    url = f"{API_URL}{endpoint}"
    async with httpx.AsyncClient() as client:
        if method.upper() == 'GET':
            response = await client.get(url)
        elif method.upper() == 'POST':
            response = await client.post(url, json=data)
        elif method.upper() == 'PUT':
            response = await client.put(url, json=data)
        elif method.upper() == 'DELETE':
            response = await client.delete(url)
        return response.json() if response.status_code == 200 else None

async def get_tariffs():
    return await api_request('GET', '/tariffs')

async def create_payment(tariff_id: int, telegram_id: str):
    return await api_request('POST', '/payments/create', {
        "tariff_id": tariff_id,
        "telegram_id": telegram_id
    })

async def get_user_info(telegram_id: str):
    # This would need a new API endpoint
    return await api_request('GET', f'/users/by-telegram/{telegram_id}')

# Handlers
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Купить подписку")],
            [KeyboardButton(text="📅 Проверить статус")],
            [KeyboardButton(text="🔄 Продлить подписку")],
            [KeyboardButton(text="⚙️ Личный кабинет")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "👋 Добро пожаловать в VPN Bot!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

@dp.message(lambda message: message.text == "🛒 Купить подписку")
async def buy_subscription(message: types.Message, state: FSMContext):
    tariffs = await get_tariffs()
    if not tariffs:
        await message.answer("❌ Тарифы недоступны. Попробуйте позже.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for tariff in tariffs:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{tariff['name']} - {tariff['price']}₽ ({tariff['duration_days']} дней)",
                callback_data=f"tariff_{tariff['id']}"
            )
        ])

    await message.answer("Выберите тариф:", reply_markup=keyboard)
    await state.set_state(PaymentState.waiting_for_tariff)

@dp.callback_query(lambda c: c.data.startswith("tariff_"))
async def process_tariff_selection(callback_query: types.CallbackQuery, state: FSMContext):
    tariff_id = int(callback_query.data.split("_")[1])

    # Create payment
    payment_data = await create_payment(tariff_id, str(callback_query.from_user.id))

    if payment_data:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_data["confirmation_url"])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_payment_{payment_data['payment_id']}")]
        ])

        await callback_query.message.edit_text(
            f"💰 Оплата: {payment_data['amount']}₽\n\n"
            f"Нажмите 'Оплатить' для перехода к платежу.\n"
            f"После оплаты нажмите 'Проверить оплату'.",
            reply_markup=keyboard
        )
    else:
        await callback_query.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")

    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith("check_payment_"))
async def check_payment(callback_query: types.CallbackQuery):
    payment_id = callback_query.data.split("_")[2]

    # In a real implementation, you'd check payment status via API
    await callback_query.message.edit_text(
        "✅ Оплата проверяется...\n\n"
        "Если оплата прошла успешно, доступы будут отправлены автоматически."
    )
    await callback_query.answer()

@dp.message(lambda message: message.text == "📅 Проверить статус")
async def check_status(message: types.Message):
    user_info = await get_user_info(str(message.from_user.id))

    if user_info:
        status_text = f"📊 Ваш статус:\n\n"
        status_text += f"Статус подписки: {'✅ Активна' if user_info['subscription_active'] else '❌ Неактивна'}\n"

        if user_info['subscription_end_date']:
            status_text += f"Действует до: {user_info['subscription_end_date'][:10]}\n"

        status_text += f"Всего покупок: {user_info['total_purchases']}₽\n"
        status_text += f"Количество продлений: {user_info['renewal_count']}\n"

        if user_info['config_links']:
            try:
                configs = json.loads(user_info['config_links'])
                status_text += f"\n🔗 Конфигурации: {len(configs.get('results', []))} inbound(s)"
            except:
                pass

        await message.answer(status_text)
    else:
        await message.answer("❌ Информация о пользователе не найдена.")

@dp.message(lambda message: message.text == "🔄 Продлить подписку")
async def extend_subscription(message: types.Message, state: FSMContext):
    await message.answer("Введите количество дней для продления (1-365):")
    await state.set_state(ExtendState.waiting_for_days)

@dp.message(ExtendState.waiting_for_days)
async def process_extend_days(message: types.Message, state: FSMContext):
    try:
        days = int(message.text)
        if days < 1 or days > 365:
            raise ValueError

        # Get current tariffs for pricing
        tariffs = await get_tariffs()
        if tariffs:
            # Use first tariff as base price per day
            price_per_day = tariffs[0]['price'] / tariffs[0]['duration_days']
            total_price = price_per_day * days

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💳 Оплатить {total_price:.0f}₽", callback_data=f"extend_{days}_{total_price:.0f}")]            ])

            await message.answer(
                f"Продление на {days} дней будет стоить {total_price:.0f}₽\n\n"
                f"Нажмите кнопку для оплаты:",
                reply_markup=keyboard
            )
        else:
            await message.answer("❌ Тарифы недоступны.")

    except ValueError:
        await message.answer("❌ Введите корректное количество дней (1-365).")

    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("extend_"))
async def process_extend_payment(callback_query: types.CallbackQuery):
    _, days, price = callback_query.data.split("_")
    days = int(days)
    price = float(price)

    # Create custom payment for extension
    # This would need a custom API endpoint
    await callback_query.message.edit_text(f"Функция продления в разработке. Стоимость: {price}₽ за {days} дней.")
    await callback_query.answer()

@dp.message(lambda message: message.text == "⚙️ Личный кабинет")
async def personal_cabinet(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить конфиги", callback_data="get_configs")],
        [InlineKeyboardButton(text="🔄 Регенерировать ссылки", callback_data="regen_links")],
        [InlineKeyboardButton(text="📞 Поддержка", callback_data="support")]
    ])

    await message.answer("Личный кабинет:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "get_configs")
async def get_configs(callback_query: types.CallbackQuery):
    user_info = await get_user_info(str(callback_query.from_user.id))

    if user_info and user_info['config_links']:
        try:
            configs = json.loads(user_info['config_links'])
            config_text = "🔗 Ваши конфигурации:\n\n"

            for result in configs.get('results', []):
                if result['status'] == 'created' or result['status'] == 'updated':
                    config_text += f"Inbound {result['inbound_id']}: ✅\n"

            config_text += "\nПолучите конфигурации в 3X-UI панели."
            await callback_query.message.edit_text(config_text)
        except:
            await callback_query.message.edit_text("❌ Ошибка получения конфигураций.")
    else:
        await callback_query.message.edit_text("❌ Конфигурации не найдены.")

    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "regen_links")
async def regen_links(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("🔄 Функция регенерации ссылок в разработке.")
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "support")
async def support(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "📞 Поддержка:\n\n"
        "Если у вас возникли проблемы, обратитесь к администратору."
    )
    await callback_query.answer()

# Admin handlers
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if str(message.from_user.id) != ADMIN_TELEGRAM_ID:
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="💸 Платежи")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📢 Рассылка")]
        ],
        resize_keyboard=True
    )

    await message.answer("Админ панель:", reply_markup=keyboard)

@dp.message(lambda message: message.text == "👥 Пользователи" and str(message.from_user.id) == ADMIN_TELEGRAM_ID)
async def admin_users(message: types.Message):
    # Get users count
    users_count = await api_request('GET', '/users?limit=1')  # This would need modification
    await message.answer(f"👥 Всего пользователей: {len(users_count) if users_count else 0}")

@dp.message(lambda message: message.text == "💸 Платежи" and str(message.from_user.id) == ADMIN_TELEGRAM_ID)
async def admin_payments(message: types.Message):
    payments = await api_request('GET', '/payments?limit=10')
    if payments:
        text = "💸 Последние платежи:\n\n"
        for payment in payments[:5]:
            text += f"ID: {payment['id']}, Сумма: {payment['amount']}₽, Статус: {payment['status']}\n"
        await message.answer(text)
    else:
        await message.answer("❌ Ошибка получения платежей.")

@dp.message(lambda message: message.text == "📊 Статистика" and str(message.from_user.id) == ADMIN_TELEGRAM_ID)
async def admin_stats(message: types.Message):
    stats = await api_request('GET', '/dashboard/stats')
    if stats:
        text = "📊 Статистика:\n\n"
        text += f"Выручка сегодня: {stats['today_revenue']}₽\n"
        text += f"Активных пользователей: {stats['active_users']}\n"
        text += f"Всего платежей: {stats['total_payments']}\n"
        await message.answer(text)
    else:
        await message.answer("❌ Ошибка получения статистики.")

@dp.message(lambda message: message.text == "📢 Рассылка" and str(message.from_user.id) == ADMIN_TELEGRAM_ID)
async def admin_broadcast(message: types.Message):
    await message.answer("Функция рассылки в разработке.")

async def main():
    logger.info("Starting VPN Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())