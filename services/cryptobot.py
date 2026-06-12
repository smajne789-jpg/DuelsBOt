from __future__ import annotations

from typing import Any

import aiohttp


class CryptoBotError(RuntimeError):
    """Raised when CryptoBot API returns an error."""


class CryptoBotService:
    def __init__(self, token: str, base_url: str) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Crypto-Pay-API-Token": self._token,
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.enabled:
            raise CryptoBotError("CryptoBot token is not configured")

        session = await self._get_session()
        async with session.request(method, f"{self._base_url}/{endpoint.lstrip('/')}", json=payload) as response:
            data = await response.json(content_type=None)

        if not data.get("ok"):
            raise CryptoBotError(data.get("error", {}).get("name", "Unknown CryptoBot error"))
        return data.get("result")

    async def create_invoice(self, amount: float, asset: str, description: str, payload: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "createInvoice",
            {
                "amount": f"{amount:.8f}",
                "asset": asset,
                "description": description,
                "payload": payload,
            },
        )

    async def get_invoices(self, invoice_ids: list[int]) -> list[dict[str, Any]]:
        if not invoice_ids:
            return []
        result = await self._request(
            "POST",
            "getInvoices",
            {"invoice_ids": ",".join(str(invoice_id) for invoice_id in invoice_ids)},
        )
        return result.get("items", [])

    async def create_check(self, amount: float, asset: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "createCheck",
            {
                "amount": f"{amount:.8f}",
                "asset": asset,
            },
        )
