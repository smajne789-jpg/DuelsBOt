from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .database import Database
from .keyboards import (
    admin_menu,
    back_to_profile,
    invoice_menu,
    join_channel_menu,
    main_menu,
    play_menu,
    profile_menu,
    referrals_menu,
)
from .services.cryptobot import CryptoBotError, CryptoBotService
from .states import AdminStates, RoomStates, WalletStates


router = Router()


def money(value: float) -> str:
    text = f"{value:.4f}"
    return text.rstrip("0").rstrip(".")


async def is_admin(db: Database, settings: Settings, user_id: int) -> bool:
    return user_id in await db.get_admin_ids(settings.admin_ids)


async def ensure_subscription(bot: Bot, db: Database, user_id: int) -> tuple[bool, str | None]:
    required_channel = await db.get_setting("required_channel", "")
    if not required_channel:
        return True, None
    try:
        member = await bot.get_chat_member(required_channel, user_id)
    except Exception:
        return True, required_channel

    allowed = {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    }
    return member.status in allowed, required_channel


async def require_subscription_message(message: Message, bot: Bot, db: Database) -> bool:
    subscribed, channel = await ensure_subscription(bot, db, message.from_user.id)
    if subscribed:
        return True
    await message.answer(
        "Чтобы пользоваться ботом, сначала подпишись на обязательный канал.",
        reply_markup=join_channel_menu(channel),
    )
    return False


async def require_subscription_callback(callback: CallbackQuery, bot: Bot, db: Database) -> bool:
    subscribed, channel = await ensure_subscription(bot, db, callback.from_user.id)
    if subscribed:
        return True
    await callback.answer("Сначала подпишись на канал", show_alert=True)
    if callback.message:
        await callback.message.answer(
            "Пока подписка не подтверждена, доступ к функциям закрыт.",
            reply_markup=join_channel_menu(channel),
        )
    return False


async def send_log(bot: Bot, settings: Settings, text: str) -> None:
    if not settings.log_chat_id:
        return
    try:
        await bot.send_message(settings.log_chat_id, text)
    except Exception:
        return


async def show_main(message: Message, db: Database, settings: Settings) -> None:
    admin = await is_admin(db, settings, message.from_user.id)
    await message.answer(
        (
            "🎲 <b>Dice Duel Bot</b>\n\n"
            "Выбирай действие ниже: профиль, игра, промокоды или рефералы."
        ),
        reply_markup=main_menu(admin),
    )


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup: Any) -> None:
    if callback.message:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    else:
        await callback.answer(text, show_alert=True)


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, db: Database, settings: Settings, bot: Bot) -> None:
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
        if referrer_id == message.from_user.id:
            referrer_id = None

    await db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        referrer_id=referrer_id,
    )

    if not await require_subscription_message(message, bot, db):
        return

    await show_main(message, db, settings)


@router.callback_query(F.data == "subscription:check")
async def subscription_check(callback: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    await callback.answer("Подписка подтверждена")
    if callback.message:
        await callback.message.answer("Доступ открыт.", reply_markup=main_menu(await is_admin(db, settings, callback.from_user.id)))


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    admin = await is_admin(db, settings, callback.from_user.id)
    await edit_or_send(
        callback,
        "🎲 <b>Главное меню</b>\n\nВыбирай нужный раздел.",
        main_menu(admin),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def menu_profile(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    text = (
        "👤 <b>Профиль</b>\n\n"
        f"Баланс: <b>{money(float(user['balance']))}</b>\n"
        f"Пополнено: {money(float(user['total_deposit']))}\n"
        f"Выведено: {money(float(user['total_withdraw']))}\n"
        f"Ставок: {money(float(user['total_wager']))}\n"
        f"Выигрышей: {money(float(user['total_wins']))}\n\n"
        f"Авто-пополнение: {'ON' if user['auto_deposit_enabled'] else 'OFF'}\n"
        f"Авто-вывод: {'ON' if user['auto_withdraw_enabled'] else 'OFF'}"
    )
    await edit_or_send(
        callback,
        text,
        profile_menu(bool(user["auto_deposit_enabled"]), bool(user["auto_withdraw_enabled"])),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:referrals")
async def menu_referrals(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    summary = await db.get_referral_summary(callback.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    ref_percent = await db.get_setting("referral_percent", "0.01")
    await edit_or_send(
        callback,
        (
            "🤝 <b>Реферальная система</b>\n\n"
            f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
            f"Приглашено: <b>{summary['count']}</b>\n"
            f"Заработано: <b>{money(summary['earnings'])}</b>\n"
            f"Процент с проигрышной ставки: <b>{ref_percent}%</b>"
        ),
        referrals_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:promo")
async def menu_promo(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    await state.set_state(WalletStates.waiting_for_promocode)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи промокод одним сообщением.", reply_markup=back_to_profile())


@router.message(WalletStates.waiting_for_promocode)
async def apply_promo(message: Message, state: FSMContext, db: Database) -> None:
    try:
        reward = await db.activate_promocode(message.text or "", message.from_user.id)
    except ValueError as error:
        await message.answer(str(error), reply_markup=back_to_profile())
    else:
        await message.answer(
            f"Промокод активирован. На баланс зачислено {money(reward)}.",
            reply_markup=back_to_profile(),
        )
    finally:
        await state.clear()


@router.callback_query(F.data == "wallet:toggle_deposit")
async def toggle_deposit(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    new_value = await db.toggle_auto_flag(callback.from_user.id, "auto_deposit_enabled")
    user = await db.get_user(callback.from_user.id)
    if callback.message and user:
        await callback.message.edit_text(
            (
                "👤 <b>Профиль</b>\n\n"
                f"Баланс: <b>{money(float(user['balance']))}</b>\n"
                f"Пополнено: {money(float(user['total_deposit']))}\n"
                f"Выведено: {money(float(user['total_withdraw']))}\n"
                f"Ставок: {money(float(user['total_wager']))}\n"
                f"Выигрышей: {money(float(user['total_wins']))}\n\n"
                f"Авто-пополнение: {'ON' if user['auto_deposit_enabled'] else 'OFF'}\n"
                f"Авто-вывод: {'ON' if user['auto_withdraw_enabled'] else 'OFF'}"
            ),
            reply_markup=profile_menu(bool(user["auto_deposit_enabled"]), bool(user["auto_withdraw_enabled"])),
        )
    await callback.answer(f"Авто-пополнение {'включено' if new_value else 'выключено'}")


@router.callback_query(F.data == "wallet:toggle_withdraw")
async def toggle_withdraw(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    new_value = await db.toggle_auto_flag(callback.from_user.id, "auto_withdraw_enabled")
    user = await db.get_user(callback.from_user.id)
    if callback.message and user:
        await callback.message.edit_text(
            (
                "👤 <b>Профиль</b>\n\n"
                f"Баланс: <b>{money(float(user['balance']))}</b>\n"
                f"Пополнено: {money(float(user['total_deposit']))}\n"
                f"Выведено: {money(float(user['total_withdraw']))}\n"
                f"Ставок: {money(float(user['total_wager']))}\n"
                f"Выигрышей: {money(float(user['total_wins']))}\n\n"
                f"Авто-пополнение: {'ON' if user['auto_deposit_enabled'] else 'OFF'}\n"
                f"Авто-вывод: {'ON' if user['auto_withdraw_enabled'] else 'OFF'}"
            ),
            reply_markup=profile_menu(bool(user["auto_deposit_enabled"]), bool(user["auto_withdraw_enabled"])),
        )
    await callback.answer(f"Авто-вывод {'включен' if new_value else 'выключен'}")


@router.callback_query(F.data == "wallet:deposit")
async def wallet_deposit(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    user = await db.get_user(callback.from_user.id)
    if user and not user["auto_deposit_enabled"]:
        await callback.answer("Сначала включи авто-пополнение в профиле", show_alert=True)
        return
    min_deposit = await db.get_setting("min_deposit", "0.05")
    await state.set_state(WalletStates.waiting_for_deposit_amount)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Введи сумму пополнения. Минимум: {min_deposit}",
            reply_markup=back_to_profile(),
        )


@router.message(WalletStates.waiting_for_deposit_amount)
async def process_deposit_amount(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    cryptobot: CryptoBotService,
    bot: Bot,
) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Нужна числовая сумма.", reply_markup=back_to_profile())
        return

    min_deposit = float(await db.get_setting("min_deposit", str(settings.min_deposit)))
    if amount < min_deposit:
        await message.answer(f"Минимум для пополнения: {money(min_deposit)}", reply_markup=back_to_profile())
        return
    if not cryptobot.enabled:
        await message.answer("CryptoBot не настроен. Добавь CRYPTOBOT_TOKEN.", reply_markup=back_to_profile())
        await state.clear()
        return

    payload = f"deposit:{message.from_user.id}:{int(asyncio.get_running_loop().time())}"
    try:
        invoice = await cryptobot.create_invoice(
            amount=amount,
            asset=settings.cryptobot_asset,
            description=f"Пополнение баланса для {message.from_user.id}",
            payload=payload,
        )
        await db.create_invoice(
            invoice_id=int(invoice["invoice_id"]),
            user_id=message.from_user.id,
            amount=amount,
            asset=settings.cryptobot_asset,
            pay_url=invoice["pay_url"],
            payload=payload,
        )
    except CryptoBotError as error:
        await message.answer(f"Ошибка CryptoBot: {error}", reply_markup=back_to_profile())
    else:
        await message.answer(
            (
                "💳 <b>Счет создан</b>\n\n"
                f"Сумма: <b>{money(amount)} {settings.cryptobot_asset}</b>\n"
                "После оплаты баланс зачислится автоматически."
            ),
            reply_markup=invoice_menu(invoice["pay_url"]),
        )
        await send_log(
            bot,
            settings,
            f"💳 Создан инвойс\nUser: {message.from_user.id}\nСумма: {money(amount)} {settings.cryptobot_asset}",
        )
    finally:
        await state.clear()


@router.callback_query(F.data == "wallet:withdraw")
async def wallet_withdraw(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    user = await db.get_user(callback.from_user.id)
    if user and not user["auto_withdraw_enabled"]:
        await callback.answer("Сначала включи авто-вывод в профиле", show_alert=True)
        return
    min_withdraw = await db.get_setting("min_withdraw", "0.05")
    await state.set_state(WalletStates.waiting_for_withdraw_amount)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Введи сумму вывода. Минимум: {min_withdraw}",
            reply_markup=back_to_profile(),
        )


@router.message(WalletStates.waiting_for_withdraw_amount)
async def process_withdraw_amount(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    cryptobot: CryptoBotService,
    bot: Bot,
) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Нужна числовая сумма.", reply_markup=back_to_profile())
        return

    min_withdraw = float(await db.get_setting("min_withdraw", str(settings.min_withdraw)))
    if amount < min_withdraw:
        await message.answer(f"Минимум для вывода: {money(min_withdraw)}", reply_markup=back_to_profile())
        return
    if not cryptobot.enabled:
        await message.answer("CryptoBot не настроен. Добавь CRYPTOBOT_TOKEN.", reply_markup=back_to_profile())
        await state.clear()
        return

    try:
        check = await cryptobot.create_check(amount=amount, asset=settings.cryptobot_asset)
        await db.register_withdrawal(
            check_id=int(check["check_id"]),
            user_id=message.from_user.id,
            amount=amount,
            asset=settings.cryptobot_asset,
            check_url=check["bot_check_url"],
        )
    except (CryptoBotError, ValueError) as error:
        await message.answer(f"Не удалось вывести: {error}", reply_markup=back_to_profile())
    else:
        await message.answer(
            (
                "💸 <b>Вывод создан</b>\n\n"
                f"Сумма: <b>{money(amount)} {settings.cryptobot_asset}</b>\n"
                f"Чек: {check['bot_check_url']}"
            ),
            reply_markup=back_to_profile(),
        )
        await send_log(
            bot,
            settings,
            f"💸 Вывод\nUser: {message.from_user.id}\nСумма: {money(amount)} {settings.cryptobot_asset}",
        )
    finally:
        await state.clear()


@router.callback_query(F.data == "menu:play")
async def menu_play(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    rooms = await db.list_open_rooms()
    display_rooms = []
    for room in rooms:
        room["bet_amount_text"] = money(float(room["bet_amount"]))
        display_rooms.append(room)
    text_lines = [
        "🎮 <b>Игровые комнаты</b>",
        "",
        "Создавай комнату или заходи в открытую из списка.",
    ]
    if display_rooms:
        text_lines.extend(["", "Открытые комнаты:"])
        text_lines.extend(
            f"• #{room['id']} — {room['bet_amount_text']} (создатель: @{room['username'] or room['creator_id']})"
            for room in display_rooms
        )
    else:
        text_lines.extend(["", "Пока нет открытых комнат. Создай первую."])
    await edit_or_send(callback, "\n".join(text_lines), play_menu(display_rooms, callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "room:create")
async def room_create(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    minimum = await db.get_setting("room_min_bet", "0.05")
    await state.set_state(RoomStates.waiting_for_bet)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Введи сумму комнаты. Минимум: {minimum}",
            reply_markup=back_to_profile(),
        )


@router.message(RoomStates.waiting_for_bet)
async def room_create_amount(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    try:
        amount = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Нужна числовая сумма ставки.", reply_markup=back_to_profile())
        return

    minimum = float(await db.get_setting("room_min_bet", str(settings.room_min_bet)))
    if amount < minimum:
        await message.answer(f"Минимальная ставка: {money(minimum)}", reply_markup=back_to_profile())
        return

    try:
        room = await db.create_room(message.from_user.id, amount)
    except ValueError as error:
        await message.answer(str(error), reply_markup=back_to_profile())
    else:
        await message.answer(
            (
                "✅ <b>Комната создана</b>\n\n"
                f"Комната #{room['id']}\n"
                f"Ставка: <b>{money(amount)}</b>\n"
                "Она уже доступна в списке комнат."
            ),
            reply_markup=back_to_profile(),
        )
        await send_log(
            bot,
            settings,
            f"🎮 Создана комната #{room['id']}\nUser: {message.from_user.id}\nСтавка: {money(amount)}",
        )
    finally:
        await state.clear()


async def run_duel(bot: Bot, db: Database, settings: Settings, room: dict[str, Any]) -> dict[str, Any]:
    creator_id = int(room["creator_id"])
    opponent_id = int(room["opponent_id"])

    creator_roll = opponent_roll = 0
    while creator_roll == opponent_roll:
        creator_dice = await bot.send_dice(creator_id, emoji="🎲")
        opponent_dice = await bot.send_dice(opponent_id, emoji="🎲")
        creator_roll = creator_dice.dice.value
        opponent_roll = opponent_dice.dice.value
        if creator_roll == opponent_roll:
            await bot.send_message(creator_id, "Ничья. Перебрасываем кубики.")
            await bot.send_message(opponent_id, "Ничья. Перебрасываем кубики.")
            await asyncio.sleep(1)

    winner_id = creator_id if creator_roll > opponent_roll else opponent_id
    bet_amount = float(room["bet_amount"])
    pot = bet_amount * 2
    commission_percent = float(await db.get_setting("house_fee_percent", str(settings.house_fee_percent)))
    referral_percent = float(await db.get_setting("referral_percent", str(settings.referral_percent)))
    commission_amount = round(pot * commission_percent / 100, 8)
    referral_reward = round(bet_amount * referral_percent / 100, 8)
    prize_amount = round(pot - commission_amount, 8)

    result = await db.finish_room(
        room_id=int(room["id"]),
        creator_roll=creator_roll,
        opponent_roll=opponent_roll,
        winner_id=winner_id,
        prize_amount=prize_amount,
        commission_amount=commission_amount,
        referral_reward=referral_reward,
    )

    winner_text = "создатель" if winner_id == creator_id else "вошедший игрок"
    summary = (
        f"🎲 Дуэль комнаты #{room['id']} завершена\n\n"
        f"Создатель: {creator_roll}\n"
        f"Соперник: {opponent_roll}\n"
        f"Победитель: <b>{winner_text}</b>\n"
        f"Выигрыш: <b>{money(prize_amount)}</b>\n"
        f"Комиссия: {money(commission_amount)}"
    )
    await bot.send_message(creator_id, summary)
    await bot.send_message(opponent_id, summary)
    await send_log(
        bot,
        settings,
        (
            f"🏆 Дуэль #{room['id']}\n"
            f"Creator: {creator_id} ({creator_roll})\n"
            f"Opponent: {opponent_id} ({opponent_roll})\n"
            f"Winner: {winner_id}\n"
            f"Prize: {money(prize_amount)}\n"
            f"Fee: {money(commission_amount)}\n"
            f"Referral: {money(referral_reward)}"
        ),
    )
    return result


@router.callback_query(F.data.startswith("room:join:"))
async def room_join(callback: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    room_id = int(callback.data.split(":")[-1])
    try:
        room = await db.join_room(room_id, callback.from_user.id)
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await callback.answer("Соперник найден, кидаем кубики")
    await bot.send_message(room["creator_id"], f"В твою комнату #{room_id} зашел соперник. Начинаем дуэль.")
    await bot.send_message(callback.from_user.id, f"Ты вошел в комнату #{room_id}. Начинаем дуэль.")
    await run_duel(bot, db, settings, room)


@router.callback_query(F.data.startswith("room:cancel:"))
async def room_cancel(callback: CallbackQuery, db: Database) -> None:
    room_id = int(callback.data.split(":")[-1])
    cancelled = await db.cancel_room(room_id, callback.from_user.id)
    if not cancelled:
        await callback.answer("Комнату нельзя отменить", show_alert=True)
        return
    await callback.answer("Комната отменена")
    if callback.message:
        await callback.message.answer(f"Комната #{room_id} отменена, ставка возвращена.")


@router.callback_query(F.data == "menu:admin")
async def menu_admin(callback: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_subscription_callback(callback, bot, db):
        return
    if not await is_admin(db, settings, callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    settings_text = (
        "🛠 <b>Админ-панель</b>\n\n"
        f"Мин. ставка: {await db.get_setting('room_min_bet', str(settings.room_min_bet))}\n"
        f"Реф. процент: {await db.get_setting('referral_percent', str(settings.referral_percent))}%\n"
        f"Мин. пополнение: {await db.get_setting('min_deposit', str(settings.min_deposit))}\n"
        f"Мин. вывод: {await db.get_setting('min_withdraw', str(settings.min_withdraw))}\n"
        f"Канал: {await db.get_setting('required_channel', settings.required_channel or 'не задан')}"
    )
    await edit_or_send(callback, settings_text, admin_menu())
    await callback.answer()


async def require_admin(callback: CallbackQuery, db: Database, settings: Settings, bot: Bot) -> bool:
    if not await require_subscription_callback(callback, bot, db):
        return False
    if not await is_admin(db, settings, callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return False
    return True


@router.callback_query(F.data == "admin:create_promo")
async def admin_create_promo(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_promocode)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Формат: CODE 10 50\nГде 10 — сумма, 50 — число активаций.")


@router.message(AdminStates.waiting_for_promocode)
async def admin_create_promo_done(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Нужен формат: CODE 10 50")
        return
    code, amount_raw, limit_raw = parts
    try:
        amount = float(amount_raw.replace(",", "."))
        limit = int(limit_raw)
        await db.create_promocode(code, amount, limit, message.from_user.id)
    except (ValueError, sqlite3.IntegrityError):  # type: ignore[name-defined]
        await message.answer("Не удалось создать промокод. Проверь формат и уникальность.")
    else:
        await message.answer(f"Промокод {code.upper()} создан.")
        await send_log(bot, settings, f"🎁 Промокод {code.upper()} создан админом {message.from_user.id}")
        await state.clear()


async def set_numeric_setting(
    message: Message,
    state: FSMContext,
    db: Database,
    setting_name: str,
    label: str,
) -> None:
    try:
        value = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Нужно число.")
        return
    await db.set_setting(setting_name, str(value))
    await message.answer(f"{label} обновлено: {money(value)}")
    await state.clear()


@router.callback_query(F.data == "admin:set_min_room")
async def admin_set_min_room(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_min_room)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи новую минимальную ставку комнаты.")


@router.message(AdminStates.waiting_for_min_room)
async def admin_set_min_room_done(message: Message, state: FSMContext, db: Database) -> None:
    await set_numeric_setting(message, state, db, "room_min_bet", "Минимальная ставка")


@router.callback_query(F.data == "admin:set_ref_percent")
async def admin_set_ref_percent(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_referral_percent)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи новый реферальный процент.")


@router.message(AdminStates.waiting_for_referral_percent)
async def admin_set_ref_percent_done(message: Message, state: FSMContext, db: Database) -> None:
    await set_numeric_setting(message, state, db, "referral_percent", "Реферальный процент")


@router.callback_query(F.data == "admin:set_min_deposit")
async def admin_set_min_deposit(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_min_deposit)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи новый минимум пополнения.")


@router.message(AdminStates.waiting_for_min_deposit)
async def admin_set_min_deposit_done(message: Message, state: FSMContext, db: Database) -> None:
    await set_numeric_setting(message, state, db, "min_deposit", "Минимум пополнения")


@router.callback_query(F.data == "admin:set_min_withdraw")
async def admin_set_min_withdraw(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_min_withdraw)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи новый минимум вывода.")


@router.message(AdminStates.waiting_for_min_withdraw)
async def admin_set_min_withdraw_done(message: Message, state: FSMContext, db: Database) -> None:
    await set_numeric_setting(message, state, db, "min_withdraw", "Минимум вывода")


@router.callback_query(F.data == "admin:set_channel")
async def admin_set_channel(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_required_channel)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи новый канал для обязательной подписки, например @mychannel")


@router.message(AdminStates.waiting_for_required_channel)
async def admin_set_channel_done(message: Message, state: FSMContext, db: Database) -> None:
    channel = (message.text or "").strip()
    await db.set_setting("required_channel", channel)
    await message.answer(f"Канал обновлен: {channel}")
    await state.clear()


@router.callback_query(F.data == "admin:add_admin")
async def admin_add_admin(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_admin)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Введи Telegram ID или @username пользователя для выдачи прав админа.")


@router.message(AdminStates.waiting_for_admin)
async def admin_add_admin_done(message: Message, state: FSMContext, db: Database) -> None:
    target = (message.text or "").strip()
    if target.isdigit():
        user_id = int(target)
    else:
        user = await db.get_user_by_username(target)
        if not user:
            await message.answer("Пользователь с таким username не найден в базе.")
            return
        user_id = int(user["user_id"])
    await db.set_admin(user_id, True)
    await message.answer(f"Пользователь {target} теперь админ.")
    await state.clear()


@router.callback_query(F.data == "admin:add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_balance_add)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Формат: @username 10.5")


@router.callback_query(F.data == "admin:remove_balance")
async def admin_remove_balance(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    if not await require_admin(callback, db, settings, bot):
        return
    await state.set_state(AdminStates.waiting_for_balance_remove)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Формат: @username 10.5")


async def handle_balance_change(message: Message, state: FSMContext, db: Database, sign: int) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Нужен формат: @username 10.5")
        return
    username, amount_raw = parts
    user = await db.get_user_by_username(username)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    try:
        amount = float(amount_raw.replace(",", ".")) * sign
        new_balance = await db.adjust_balance(int(user["user_id"]), amount)
    except ValueError as error:
        await message.answer(str(error))
    else:
        await message.answer(f"Баланс обновлен. Новый баланс: {money(new_balance)}")
        await state.clear()


@router.message(AdminStates.waiting_for_balance_add)
async def admin_add_balance_done(message: Message, state: FSMContext, db: Database) -> None:
    await handle_balance_change(message, state, db, 1)


@router.message(AdminStates.waiting_for_balance_remove)
async def admin_remove_balance_done(message: Message, state: FSMContext, db: Database) -> None:
    await handle_balance_change(message, state, db, -1)
