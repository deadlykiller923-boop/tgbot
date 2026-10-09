import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Загружаем токен из файла .env (если он есть), иначе из переменных окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.getenv("BOT_TOKEN")

router = Router()


class SendFlow(StatesGroup):
    waiting_for_id = State()


def choice_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Отправить копию мне (от бота)", callback_data="copy_here")
    kb.button(text="👤 Отправить другому человеку", callback_data="send_other")
    kb.button(text="❌ Отмена", callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Отправь мне любое сообщение (текст, фото, стикер, голосовое), "
        "а затем выбери, кому его отправить."
    )


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


# Ждём ID получателя (этот обработчик стоит выше общего)
@router.message(SendFlow.waiting_for_id, F.text)
async def receive_target_id(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("Нужен числовой ID, например 123456789. Или /cancel для отмены.")
        return

    data = await state.get_data()
    try:
        await bot.copy_message(
            chat_id=int(text),
            from_chat_id=data["src_chat"],
            message_id=data["src_msg"],
        )
        await message.answer("✅ Отправлено.")
    except TelegramForbiddenError:
        await message.answer(
            "❌ Бот не может написать этому человеку: он должен сначала нажать /start у бота."
        )
    except TelegramBadRequest as e:
        await message.answer(f"❌ Не удалось отправить: {e.message}")
    finally:
        await state.clear()


# Любое новое сообщение: сохраняем его и показываем кнопки
@router.message(StateFilter(None))
async def got_message(message: Message, state: FSMContext):
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await message.answer("Что сделать с этим сообщением?", reply_markup=choice_keyboard())


@router.callback_query(F.data == "copy_here")
async def copy_here(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data:
        await call.answer("Сообщение не найдено, отправь его заново.", show_alert=True)
        return
    try:
        await bot.copy_message(
            chat_id=call.from_user.id,
            from_chat_id=data["src_chat"],
            message_id=data["src_msg"],
        )
        await call.message.edit_text("✅ Копия отправлена от имени бота.")
    except TelegramBadRequest as e:
        await call.message.edit_text(f"❌ Не удалось: {e.message}")
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "send_other")
async def send_other(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await call.answer("Сообщение не найдено, отправь его заново.", show_alert=True)
        return
    await state.set_state(SendFlow.waiting_for_id)
    await call.message.edit_text(
        "Введи числовой ID получателя (узнать можно у @userinfobot).\n"
        "Для отмены: /cancel"
    )
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Отменено.")
    await call.answer()


async def main():
    if not TOKEN:
        raise RuntimeError("Не задана переменная BOT_TOKEN (укажи её в файле .env)")

    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(token=TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
