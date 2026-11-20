import asyncio
import json
import math
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import dotenv_values

from .interaction import ToolError

TRAIN = "XUNJI_TRAIN_KEY"
FOOD = "XUNJI_FOOD_KEY"
FOOD_SEARCH = "XUNJI_FOOD_SEARCH_KEY"
BODY = "XUNJI_BODY_KEY"
TEMPLATE = "XUNJI_AGENT_TEMPLATE_KEY"
KEY_NAMES = (TRAIN, FOOD, FOOD_SEARCH, BODY, TEMPLATE)

TRAIN_URL = "https://trains.xunjiapp.cn"
FOOD_URL = "https://eatings.xunjiapp.cn"
API_URL = "https://api.xunjiapp.cn"


@dataclass(frozen=True)
class Route:
    key: str
    url: str
    rate: float = 15


ROUTES = {
    "training_read": Route(TRAIN, f"{TRAIN_URL}/api_trains_for_llm_v2"),
    "training_write": Route(TRAIN, f"{TRAIN_URL}/api_upsert_trains_for_llm_v2", 45),
    "plan": Route(TRAIN, f"{API_URL}/open/plan/query_gzip"),
    "food_query": Route(FOOD, f"{FOOD_URL}/open/food/query_gzip"),
    "food_write": Route(FOOD, f"{FOOD_URL}/open/food/upsert_gzip"),
    "food_custom": Route(FOOD, f"{FOOD_URL}/open/food/custom/upsert_gzip"),
    "food_search": Route(FOOD_SEARCH, f"{API_URL}/open_agent/food/search_gzip"),
    "body_query": Route(BODY, f"{API_URL}/open/body/query_gzip"),
    "body_write": Route(BODY, f"{API_URL}/open/body/upsert_gzip"),
    "template_sync": Route(TEMPLATE, f"{TRAIN_URL}/api_agent_templates_sync_for_llm_v2", 0),
    "template_mutate": Route(TEMPLATE, f"{TRAIN_URL}/api_agent_templates_mutate_for_llm_v1", 0),
}


class UpstreamError(ToolError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def load_keys(env_file: Path) -> dict[str, str]:
    file_values = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    return {
        name: (os.environ.get(name, file_values.get(name)) or "").strip()
        for name in KEY_NAMES
    }


def retry_seconds(payloads: tuple[dict, ...], response: httpx.Response) -> float:
    hints = [payload.get("retry_after_ms") for payload in payloads]
    if response.headers.get("Retry-After"):
        try:
            hints.append(float(response.headers["Retry-After"]) * 1000)
        except ValueError:
            pass
    return max(
        (hint / 1000 for hint in hints if type(hint) in (int, float) and 0 < hint <= 2_147_483_647),
        default=0,
    )


class ApiClient:
    def __init__(self, keys: dict[str, str], transport: httpx.AsyncBaseTransport | None = None):
        self._keys = keys.copy()
        self._transport = transport
        self._cache: dict[tuple[str, str], tuple[float, object]] = {}
        self._next_call: dict[tuple[str, str], float] = {}
        self._cache_version: dict[str, int] = {}

    def _rate_error(self, wait: float) -> UpstreamError:
        return UpstreamError("rate_limited", f"训记接口限频，请在 {math.ceil(wait)} 秒后重试。")

    async def wait_for_rate_limit(self, route: str, rate_scope: str = "") -> None:
        wait = self._next_call.get((route, rate_scope), 0) - time.monotonic()
        if wait > ROUTES[route].rate:
            raise self._rate_error(wait)
        if wait > 0:
            await asyncio.sleep(wait)

    async def call(
        self,
        route: str,
        body: dict,
        *,
        cache_ttl: float = 0,
        rate_scope: str = "",
        rate_seconds: float | None = None,
        invalidate: tuple[str, ...] = (),
    ):
        endpoint = ROUTES[route]
        key = self._keys.get(endpoint.key)
        if not key:
            raise UpstreamError("key_missing", f"请配置 {endpoint.key} 后重启 MCP。")
        if not key.isascii() or not key.isprintable() or any(char.isspace() for char in key):
            raise UpstreamError("key_invalid", f"{endpoint.key} 格式无效，请从训记 App 复制 Key 后重启 MCP。")

        now = time.monotonic()
        self._cache = {item: entry for item, entry in self._cache.items() if entry[0] > now}
        cache_key = (route, json.dumps(body, sort_keys=True)) if cache_ttl else None
        if cache_key in self._cache:
            return deepcopy(self._cache[cache_key][1])
        cache_version = self._cache_version.get(route, 0)

        self._next_call = {bucket: until for bucket, until in self._next_call.items() if until > now}
        bucket = (route, rate_scope)
        wait = self._next_call.get(bucket, 0) - now
        if wait > 0:
            raise self._rate_error(wait)
        period = endpoint.rate if rate_seconds is None else rate_seconds
        self._next_call[bucket] = now + period

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=self._transport) as client:
                response = await client.post(
                    endpoint.url,
                    headers={"Authorization": f"Bearer {key}", "Accept-Encoding": "gzip"},
                    json=body,
                )
        except httpx.HTTPError:
            raise UpstreamError("connection", "无法连接训记或读取响应。请检查网络后重试。") from None

        try:
            payload = response.json()
            if not isinstance(payload, dict):
                payload = {}
        except ValueError:
            payload = {}

        error_fields = (payload, *(
            nested for field in ("error", "res") if isinstance(nested := payload.get(field), dict)
        ))
        result = payload.get("res")
        implicit_success = route in {"training_read", "training_write", "plan", "template_sync", "template_mutate"}
        if route == "template_sync" and result is None and "folder" in payload and "template_versions" in payload:
            result = payload
        if route == "template_mutate" and result is None and "applied" in payload:
            result = payload
        if not response.is_success or result is None or (
            payload.get("success") is not True and (not implicit_success or "success" in payload)
        ):
            error_text = " ".join(
                value.lower() for fields in error_fields for field in ("error", "msg", "message", "code", "detail")
                if isinstance(value := fields.get(field), str)
            )
            if response.status_code == 429 or "too frequent" in error_text:
                wait = max(retry_seconds(error_fields, response), self._next_call.get(bucket, 0) - time.monotonic(), 1)
                self._next_call[bucket] = time.monotonic() + wait
                raise self._rate_error(wait)
            if "仅vip可用" in error_text:
                raise UpstreamError("vip_required", "此训记接口需要 VIP 权限。")
            if response.status_code in (401, 403) or any(
                phrase in error_text for phrase in ("apikey missing", "apikey invalid", "api key missing", "api key invalid")
            ):
                raise UpstreamError("key_invalid", f"训记拒绝了 {endpoint.key}，请更新该 Key 后重启 MCP。")
            if response.status_code == 409 or "version conflict" in error_text:
                raise UpstreamError("version_conflict", "训记版本冲突（version conflict），请重新读取数据。")
            if "user confirmation required" in error_text:
                raise UpstreamError("confirmation_required", "训记要求重新确认，请重新发起操作。")
            if "content safety rejected" in error_text:
                raise UpstreamError("content_rejected", "训记未接受模板文本，请用户提供新的文案。")
            if "template limit exceeded" in error_text:
                raise UpstreamError("template_limit", "训记模板已满，请重新同步后选择要替换的模板。")
            raise UpstreamError("rejected", f"训记未接受请求或响应格式异常（HTTP {response.status_code}）。")

        if invalidate:
            self._cache = {item: entry for item, entry in self._cache.items() if item[0] not in invalidate}
            for name in invalidate:
                self._cache_version[name] = self._cache_version.get(name, 0) + 1
        if cache_key is not None and cache_version == self._cache_version.get(route, 0):
            self._cache[cache_key] = (time.monotonic() + cache_ttl, deepcopy(result))
        return result
