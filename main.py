from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import build_default_settings_map, load_settings
from .database import Database
from .handlers import router, send_log
from .services.cryptobot import CryptoBotError, CryptoBotService


async def invoice_worker(bot: Bot, db: Database, settings, cryptobot: CryptoBotService) -> None:
    while True:
        try:
            pending = await db.list_pending_invoices()
            if cryptobot.enabled and pending:
                remote_items = await cryptobot.get_invoices([int(item["invoice_id"]) for item in pending])
                remote_by_id = {int(item["invoice_id"]): item for item in remote_items}
                for invoice in pending:
                    remote = remote_by_id.get(int(invoice["invoice_id"]))
                    if not remote:
                        continue
                    if remote.get("status") in {"paid", "confirmed", "completed"}:
                        paid_invoice = await db.mark_invoice_paid(int(invoice["invoice_id"]))
                        if paid_invoice:
                            user = paid_invoice["user"]
                            await bot.send_message(
                                paid_invoice["user_id"],
                                (
                                    "✅ <b>Пополнение зачислено</b>\n\n"
                                    f"Сумма: <b>{paid_invoice['amount']}</b> {paid_invoice['asset']}\n"
                                    f"Новый баланс: <b>{user['balance']}</b>"
                                ),
                            )
                            await send_log(
                                bot,
                                settings,
                                f"💰 Пополнение подтверждено\nUser: {paid_invoice['user_id']}\nСумма: {paid_invoice['amount']} {paid_invoice['asset']}",
                            )
        except CryptoBotError as error:
            await send_log(bot, settings, f"⚠️ Ошибка фоновой проверки инвойсов: {error}")
        except Exception as error:
            await send_log(bot, settings, f"⚠️ Неожиданная ошибка invoice worker: {error}")

        await asyncio.sleep(settings.invoice_poll_interval)


async def main() -> None:
    settings = load_settings()
    db = Database(settings.database_path)
    await db.initialize(build_default_settings_map(settings))

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    cryptobot = CryptoBotService(settings.cryptobot_token, settings.cryptobot_base_url)

    dispatcher["db"] = db
    dispatcher["settings"] = settings
    dispatcher["cryptobot"] = cryptobot
    dispatcher.include_router(router)

    worker_task = asyncio.create_task(invoice_worker(bot, db, settings, cryptobot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await cryptobot.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
