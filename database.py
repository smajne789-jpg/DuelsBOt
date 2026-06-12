from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.path = str(Path(path))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def initialize(self, default_settings: dict[str, str]) -> None:
        await asyncio.to_thread(self._initialize_sync, default_settings)

    def _initialize_sync(self, default_settings: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    balance REAL NOT NULL DEFAULT 0,
                    referrer_id INTEGER,
                    total_deposit REAL NOT NULL DEFAULT 0,
                    total_withdraw REAL NOT NULL DEFAULT 0,
                    total_wager REAL NOT NULL DEFAULT 0,
                    total_wins REAL NOT NULL DEFAULT 0,
                    referral_earnings REAL NOT NULL DEFAULT 0,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    auto_deposit_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_withdraw_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(referrer_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    opponent_id INTEGER,
                    bet_amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    creator_roll INTEGER,
                    opponent_roll INTEGER,
                    winner_id INTEGER,
                    prize_amount REAL NOT NULL DEFAULT 0,
                    commission_amount REAL NOT NULL DEFAULT 0,
                    referral_reward REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY(creator_id) REFERENCES users(user_id),
                    FOREIGN KEY(opponent_id) REFERENCES users(user_id),
                    FOREIGN KEY(winner_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS promocodes (
                    code TEXT PRIMARY KEY,
                    amount REAL NOT NULL,
                    activations_limit INTEGER NOT NULL,
                    activations_used INTEGER NOT NULL DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS promocode_activations (
                    code TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    activated_at TEXT NOT NULL,
                    PRIMARY KEY(code, user_id),
                    FOREIGN KEY(code) REFERENCES promocodes(code)
                );

                CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    asset TEXT NOT NULL,
                    pay_url TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS withdrawals (
                    check_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    asset TEXT NOT NULL,
                    check_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                """
            )

            for key, value in default_settings.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                    (key, value),
                )
            conn.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str,
        referrer_id: int | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_user_sync, user_id, username, first_name, referrer_id)

    def _upsert_user_sync(
        self,
        user_id: int,
        username: str | None,
        first_name: str,
        referrer_id: int | None,
    ) -> dict[str, Any]:
        now = utc_now()
        username_value = (username or "").lower() or None
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO users(
                        user_id, username, first_name, referrer_id, created_at, last_seen_at
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username_value, first_name, referrer_id, now, now),
                )
            else:
                if existing["referrer_id"] is None and referrer_id and referrer_id != user_id:
                    conn.execute(
                        """
                        UPDATE users
                        SET username = ?, first_name = ?, referrer_id = ?, last_seen_at = ?
                        WHERE user_id = ?
                        """,
                        (username_value, first_name, referrer_id, now, user_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE users
                        SET username = ?, first_name = ?, last_seen_at = ?
                        WHERE user_id = ?
                        """,
                        (username_value, first_name, now, user_id),
                    )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(user)

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_user_sync, user_id)

    def _get_user_sync(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_user_by_username_sync, username)

    def _get_user_by_username_sync(self, username: str) -> dict[str, Any] | None:
        normalized = username.strip().lstrip("@").lower()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
            return dict(row) if row else None

    async def set_admin(self, user_id: int, is_admin: bool) -> None:
        await asyncio.to_thread(self._set_admin_sync, user_id, is_admin)

    def _set_admin_sync(self, user_id: int, is_admin: bool) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, username, first_name, is_admin, created_at, last_seen_at)
                VALUES(?, NULL, 'Admin', ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET is_admin = excluded.is_admin, last_seen_at = excluded.last_seen_at
                """,
                (user_id, int(is_admin), now, now),
            )
            conn.commit()

    async def get_admin_ids(self, env_admin_ids: set[int]) -> set[int]:
        return await asyncio.to_thread(self._get_admin_ids_sync, env_admin_ids)

    def _get_admin_ids_sync(self, env_admin_ids: set[int]) -> set[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id FROM users WHERE is_admin = 1").fetchall()
            return set(env_admin_ids) | {row["user_id"] for row in rows}

    async def get_setting(self, key: str, default: str = "") -> str:
        return await asyncio.to_thread(self._get_setting_sync, key, default)

    def _get_setting_sync(self, key: str, default: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._set_setting_sync, key, value)

    def _set_setting_sync(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    async def toggle_auto_flag(self, user_id: int, field: str) -> int:
        return await asyncio.to_thread(self._toggle_auto_flag_sync, user_id, field)

    def _toggle_auto_flag_sync(self, user_id: int, field: str) -> int:
        if field not in {"auto_deposit_enabled", "auto_withdraw_enabled"}:
            raise ValueError("Unsupported flag")
        with self._connect() as conn:
            conn.execute(f"UPDATE users SET {field} = CASE {field} WHEN 1 THEN 0 ELSE 1 END WHERE user_id = ?", (user_id,))
            conn.commit()
            row = conn.execute(f"SELECT {field} FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return int(row[field])

    async def list_open_rooms(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_open_rooms_sync)

    def _list_open_rooms_sync(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rooms.*, users.username
                FROM rooms
                LEFT JOIN users ON users.user_id = rooms.creator_id
                WHERE rooms.status = 'open'
                ORDER BY rooms.id DESC
                LIMIT 20
                """
            ).fetchall()
            return [dict(row) for row in rows]

    async def create_room(self, creator_id: int, bet_amount: float) -> dict[str, Any]:
        return await asyncio.to_thread(self._create_room_sync, creator_id, bet_amount)

    def _create_room_sync(self, creator_id: int, bet_amount: float) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT balance FROM users WHERE user_id = ?", (creator_id,)).fetchone()
            if user is None:
                raise ValueError("Пользователь не найден")
            if user["balance"] < bet_amount:
                raise ValueError("Недостаточно средств для создания комнаты")

            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet_amount, creator_id))
            cursor = conn.execute(
                """
                INSERT INTO rooms(creator_id, bet_amount, status, created_at)
                VALUES(?, ?, 'open', ?)
                """,
                (creator_id, bet_amount, now),
            )
            room_id = cursor.lastrowid
            conn.commit()
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            return dict(room)

    async def cancel_room(self, room_id: int, creator_id: int) -> bool:
        return await asyncio.to_thread(self._cancel_room_sync, room_id, creator_id)

    def _cancel_room_sync(self, room_id: int, creator_id: int) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if room is None or room["creator_id"] != creator_id or room["status"] != "open":
                return False
            conn.execute("UPDATE rooms SET status = 'cancelled', finished_at = ? WHERE id = ?", (utc_now(), room_id))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (room["bet_amount"], creator_id))
            conn.commit()
            return True

    async def join_room(self, room_id: int, opponent_id: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._join_room_sync, room_id, opponent_id)

    def _join_room_sync(self, room_id: int, opponent_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if room is None:
                raise ValueError("Комната не найдена")
            if room["status"] != "open":
                raise ValueError("Комната уже недоступна")
            if room["creator_id"] == opponent_id:
                raise ValueError("Нельзя зайти в свою комнату")

            user = conn.execute("SELECT balance FROM users WHERE user_id = ?", (opponent_id,)).fetchone()
            if user is None:
                raise ValueError("Пользователь не найден")
            if user["balance"] < room["bet_amount"]:
                raise ValueError("Недостаточно средств для входа в комнату")

            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (room["bet_amount"], opponent_id))
            conn.execute(
                "UPDATE rooms SET opponent_id = ?, status = 'in_progress' WHERE id = ?",
                (opponent_id, room_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            return dict(updated)

    async def finish_room(
        self,
        room_id: int,
        creator_roll: int,
        opponent_roll: int,
        winner_id: int,
        prize_amount: float,
        commission_amount: float,
        referral_reward: float,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._finish_room_sync,
            room_id,
            creator_roll,
            opponent_roll,
            winner_id,
            prize_amount,
            commission_amount,
            referral_reward,
        )

    def _finish_room_sync(
        self,
        room_id: int,
        creator_roll: int,
        opponent_roll: int,
        winner_id: int,
        prize_amount: float,
        commission_amount: float,
        referral_reward: float,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if room is None:
                raise ValueError("Комната не найдена")
            loser_id = room["opponent_id"] if winner_id == room["creator_id"] else room["creator_id"]
            referrer = conn.execute("SELECT referrer_id FROM users WHERE user_id = ?", (loser_id,)).fetchone()
            referrer_id = referrer["referrer_id"] if referrer and referrer["referrer_id"] else None
            if referrer_id:
                conn.execute(
                    """
                    UPDATE users
                    SET balance = balance + ?, referral_earnings = referral_earnings + ?
                    WHERE user_id = ?
                    """,
                    (referral_reward, referral_reward, referrer_id),
                )
            else:
                referral_reward = 0

            conn.execute(
                "UPDATE users SET balance = balance + ?, total_wins = total_wins + ? WHERE user_id = ?",
                (prize_amount, prize_amount, winner_id),
            )
            conn.execute(
                "UPDATE users SET total_wager = total_wager + ? WHERE user_id IN (?, ?)",
                (room["bet_amount"], room["creator_id"], room["opponent_id"]),
            )
            conn.execute(
                """
                UPDATE rooms
                SET status = 'finished',
                    creator_roll = ?,
                    opponent_roll = ?,
                    winner_id = ?,
                    prize_amount = ?,
                    commission_amount = ?,
                    referral_reward = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    creator_roll,
                    opponent_roll,
                    winner_id,
                    prize_amount,
                    commission_amount,
                    referral_reward,
                    utc_now(),
                    room_id,
                ),
            )
            conn.commit()
            result = conn.execute(
                """
                SELECT rooms.*, creator.username AS creator_username, opponent.username AS opponent_username
                FROM rooms
                LEFT JOIN users AS creator ON creator.user_id = rooms.creator_id
                LEFT JOIN users AS opponent ON opponent.user_id = rooms.opponent_id
                WHERE rooms.id = ?
                """,
                (room_id,),
            ).fetchone()
            return dict(result)

    async def create_invoice(
        self,
        invoice_id: int,
        user_id: int,
        amount: float,
        asset: str,
        pay_url: str,
        payload: str,
    ) -> None:
        await asyncio.to_thread(self._create_invoice_sync, invoice_id, user_id, amount, asset, pay_url, payload)

    def _create_invoice_sync(
        self,
        invoice_id: int,
        user_id: int,
        amount: float,
        asset: str,
        pay_url: str,
        payload: str,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO invoices(invoice_id, user_id, amount, asset, pay_url, payload, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (invoice_id, user_id, amount, asset, pay_url, payload, now, now),
            )
            conn.commit()

    async def list_pending_invoices(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_pending_invoices_sync)

    def _list_pending_invoices_sync(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM invoices WHERE status = 'pending' ORDER BY created_at ASC").fetchall()
            return [dict(row) for row in rows]

    async def mark_invoice_paid(self, invoice_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._mark_invoice_paid_sync, invoice_id)

    def _mark_invoice_paid_sync(self, invoice_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            invoice = conn.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
            if invoice is None or invoice["status"] == "paid":
                return None
            conn.execute(
                "UPDATE invoices SET status = 'paid', updated_at = ? WHERE invoice_id = ?",
                (utc_now(), invoice_id),
            )
            conn.execute(
                """
                UPDATE users
                SET balance = balance + ?, total_deposit = total_deposit + ?
                WHERE user_id = ?
                """,
                (invoice["amount"], invoice["amount"], invoice["user_id"]),
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (invoice["user_id"],)).fetchone()
            result = dict(invoice)
            result["user"] = dict(user) if user else None
            return result

    async def register_withdrawal(self, check_id: int, user_id: int, amount: float, asset: str, check_url: str) -> None:
        await asyncio.to_thread(self._register_withdrawal_sync, check_id, user_id, amount, asset, check_url)

    def _register_withdrawal_sync(self, check_id: int, user_id: int, amount: float, asset: str, check_url: str) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if user is None:
                raise ValueError("Пользователь не найден")
            if user["balance"] < amount:
                raise ValueError("Недостаточно средств")
            conn.execute("UPDATE users SET balance = balance - ?, total_withdraw = total_withdraw + ? WHERE user_id = ?", (amount, amount, user_id))
            conn.execute(
                """
                INSERT INTO withdrawals(check_id, user_id, amount, asset, check_url, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (check_id, user_id, amount, asset, check_url, utc_now()),
            )
            conn.commit()

    async def create_promocode(self, code: str, amount: float, activations_limit: int, created_by: int) -> None:
        await asyncio.to_thread(self._create_promocode_sync, code, amount, activations_limit, created_by)

    def _create_promocode_sync(self, code: str, amount: float, activations_limit: int, created_by: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO promocodes(code, amount, activations_limit, created_by, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (code.upper(), amount, activations_limit, created_by, utc_now()),
            )
            conn.commit()

    async def activate_promocode(self, code: str, user_id: int) -> float:
        return await asyncio.to_thread(self._activate_promocode_sync, code, user_id)

    def _activate_promocode_sync(self, code: str, user_id: int) -> float:
        normalized = code.strip().upper()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            promo = conn.execute("SELECT * FROM promocodes WHERE code = ?", (normalized,)).fetchone()
            if promo is None:
                raise ValueError("Промокод не найден")
            if promo["activations_used"] >= promo["activations_limit"]:
                raise ValueError("Лимит активаций исчерпан")
            exists = conn.execute(
                "SELECT 1 FROM promocode_activations WHERE code = ? AND user_id = ?",
                (normalized, user_id),
            ).fetchone()
            if exists:
                raise ValueError("Вы уже активировали этот промокод")

            conn.execute(
                "INSERT INTO promocode_activations(code, user_id, activated_at) VALUES(?, ?, ?)",
                (normalized, user_id, utc_now()),
            )
            conn.execute(
                "UPDATE promocodes SET activations_used = activations_used + 1 WHERE code = ?",
                (normalized,),
            )
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo["amount"], user_id))
            conn.commit()
            return float(promo["amount"])

    async def get_referral_summary(self, user_id: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_referral_summary_sync, user_id)

    def _get_referral_summary_sync(self, user_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            total_refs = conn.execute("SELECT COUNT(*) AS count FROM users WHERE referrer_id = ?", (user_id,)).fetchone()
            user = conn.execute("SELECT referral_earnings FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return {
                "count": int(total_refs["count"]) if total_refs else 0,
                "earnings": float(user["referral_earnings"]) if user else 0.0,
            }

    async def adjust_balance(self, user_id: int, amount: float) -> float:
        return await asyncio.to_thread(self._adjust_balance_sync, user_id, amount)

    def _adjust_balance_sync(self, user_id: int, amount: float) -> float:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if user is None:
                raise ValueError("Пользователь не найден")
            if amount < 0 and user["balance"] < abs(amount):
                raise ValueError("Недостаточно средств на балансе пользователя")
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return float(row["balance"])
