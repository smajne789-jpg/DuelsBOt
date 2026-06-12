from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data="menu:profile")
    builder.button(text="🎮 Играть", callback_data="menu:play")
    builder.button(text="🤝 Рефералы", callback_data="menu:referrals")
    builder.button(text="🎁 Промокод", callback_data="menu:promo")
    if is_admin:
        builder.button(text="🛠 Админ-панель", callback_data="menu:admin")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def profile_menu(auto_deposit_enabled: bool, auto_withdraw_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Пополнить", callback_data="wallet:deposit")
    builder.button(text="💸 Вывести", callback_data="wallet:withdraw")
    builder.button(
        text=f"🔄 Авто-пополнение: {'ON' if auto_deposit_enabled else 'OFF'}",
        callback_data="wallet:toggle_deposit",
    )
    builder.button(
        text=f"🧾 Авто-вывод: {'ON' if auto_withdraw_enabled else 'OFF'}",
        callback_data="wallet:toggle_withdraw",
    )
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


def play_menu(rooms: list[dict], user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать комнату", callback_data="room:create")
    builder.button(text="🔄 Обновить", callback_data="menu:play")
    for room in rooms:
        label = f"Комната #{room['id']} • {room['bet_amount_text']}"
        builder.button(text=label, callback_data=f"room:join:{room['id']}")
        if room["creator_id"] == user_id:
            builder.button(text=f"❌ Отменить #{room['id']}", callback_data=f"room:cancel:{room['id']}")
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


def referrals_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    return builder.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Создать промокод", callback_data="admin:create_promo")
    builder.button(text="🎯 Мин. ставка", callback_data="admin:set_min_room")
    builder.button(text="🤝 Реф. процент", callback_data="admin:set_ref_percent")
    builder.button(text="💳 Мин. пополнение", callback_data="admin:set_min_deposit")
    builder.button(text="💸 Мин. вывод", callback_data="admin:set_min_withdraw")
    builder.button(text="📣 Канал подписки", callback_data="admin:set_channel")
    builder.button(text="👮 Добавить админа", callback_data="admin:add_admin")
    builder.button(text="➕ Выдать баланс", callback_data="admin:add_balance")
    builder.button(text="➖ Списать баланс", callback_data="admin:remove_balance")
    builder.button(text="⬅️ В меню", callback_data="menu:main")
    builder.adjust(2, 2, 2, 2, 1, 1)
    return builder.as_markup()


def join_channel_menu(channel: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if channel and channel.startswith("@"):
        builder.button(text="📣 Подписаться", url=f"https://t.me/{channel[1:]}")
    builder.button(text="✅ Проверить подписку", callback_data="subscription:check")
    builder.adjust(1)
    return builder.as_markup()


def invoice_menu(pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить счет", url=pay_url)
    builder.button(text="👤 В профиль", callback_data="menu:profile")
    builder.adjust(1)
    return builder.as_markup()


def back_to_profile() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 В профиль", callback_data="menu:profile")
    return builder.as_markup()
