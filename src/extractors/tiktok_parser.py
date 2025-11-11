thonimport json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

from extractors.utils_pagination import (
    get_has_more_flag,
    get_next_cursor,
    should_continue_pagination,
)

class TikTokUserScraper:
    """
    Scrapes TikTok user search results into structured Python dictionaries.

    This implementation uses TikTok's public search endpoint. TikTok may change
    their internals at any time, so this code is written to be defensive:
    - Network and parsing errors are logged and result in graceful degradation.
    - Unexpected response shapes simply produce fewer or no records,
      without raising fatal exceptions.
    """

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: int = 10,
        sleep_between_requests: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.sleep_between_requests = sleep_between_requests
        self.logger = logger or logging.getLogger(__name__)
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        return session

    def _fetch_search_page(
        self,
        keyword: str,
        cursor: int | None,
        count: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a single HTTP request to TikTok's search API.

        The actual parameters used by TikTok may evolve; this function aims
        to be reasonably compatible while remaining robust to failures.
        """
        params: Dict[str, Any] = {
            "keyword": keyword,
            "count": count,
            "cursor": cursor or 0,
            "source": "discover",
            "lang": "en",
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            self.logger.warning("HTTP error while querying TikTok for '%s': %s", keyword, exc)
            return None

        if not response.ok:
            self.logger.warning(
                "Received non-OK status %s from TikTok for keyword '%s'",
                response.status_code,
                keyword,
            )
            return None

        try:
            payload: Dict[str, Any] = response.json()
        except json.JSONDecodeError as exc:
            self.logger.warning("Failed to decode TikTok response as JSON: %s", exc)
            return None

        return payload

    def _parse_users_from_response(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extracts user profiles from a TikTok search response payload.

        The structure TikTok typically uses:
        {
            "status_code": 0,
            "data": {
                "user_list": [
                    {
                        "user_info": {...},
                        "stats": {...},
                        "follow_status": 0,
                        "platform_sync_info": {...}
                    },
                    ...
                ],
                "cursor": 30,
                "has_more": 1
            }
        }

        This method is defensive and will tolerate missing keys.
        """
        data = payload.get("data") or payload.get("data", {})
        if isinstance(data, dict):
            user_list = data.get("user_list", [])
        else:
            user_list = []

        if not isinstance(user_list, list):
            self.logger.debug("No user_list array found in payload.")
            return []

        parsed: List[Dict[str, Any]] = []

        for entry in user_list:
            if not isinstance(entry, dict):
                continue

            user_info = entry.get("user_info") or entry.get("user") or {}
            if not isinstance(user_info, dict):
                user_info = {}

            stats = entry.get("stats") or {}
            if not isinstance(stats, dict):
                stats = {}

            uid = user_info.get("uid")
            sec_uid = user_info.get("sec_uid")
            unique_id = user_info.get("unique_id") or user_info.get("short_id")
            nickname = user_info.get("nickname")
            signature = user_info.get("signature") or ""
            avatar_thumb = user_info.get("avatar_thumb") or user_info.get("avatarThumb") or {}
            follower_count = (
                stats.get("follower_count")
                or stats.get("followerCount")
                or stats.get("followerCountStr")
            )
            custom_verify = user_info.get("custom_verify") or user_info.get(
                "enterprise_verify_reason"
            )
            follow_status = entry.get("follow_status")
            platform_sync_info = entry.get("platform_sync_info")

            # Skip records that are clearly invalid
            if not uid and not unique_id and not sec_uid:
                continue

            record: Dict[str, Any] = {
                "uid": uid,
                "nickname": nickname,
                "signature": signature,
                "avatar_thumb": avatar_thumb,
                "follower_count": follower_count,
                "custom_verify": custom_verify,
                "unique_id": unique_id,
                "sec_uid": sec_uid,
                "follow_status": follow_status,
                "platform_sync_info": platform_sync_info,
            }

            parsed.append(record)

        return parsed

    def search_users(self, keyword: str, max_items: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch up to `max_items` TikTok users for the given keyword, following pagination.
        """
        collected: List[Dict[str, Any]] = []
        cursor: Optional[int] = 0
        has_more: bool = True

        # TikTok often returns 20-30 records per page; we ask for a bit more
        page_size = min(max_items, 30)

        while should_continue_pagination(len(collected), max_items, has_more):
            payload = self._fetch_search_page(keyword=keyword, cursor=cursor, count=page_size)
            if payload is None:
                self.logger.info(
                    "Stopping pagination for '%s' due to missing/invalid payload.", keyword
                )
                break

            users = self._parse_users_from_response(payload)
            if not users:
                self.logger.info(
                    "No users parsed from response for '%s'; stopping pagination.", keyword
                )
                break

            for user in users:
                if len(collected) >= max_items:
                    break
                collected.append(user)

            has_more = get_has_more_flag(payload)
            cursor = get_next_cursor(payload)

            self.logger.debug(
                "Pagination state for '%s': collected=%d, has_more=%s, next_cursor=%s",
                keyword,
                len(collected),
                has_more,
                cursor,
            )

            if not should_continue_pagination(len(collected), max_items, has_more):
                break

            if cursor is None:
                self.logger.info(
                    "No cursor returned for '%s'; assuming no more pages.", keyword
                )
                break

            time.sleep(self.sleep_between_requests)

        self.logger.info(
            "Finished search for '%s': collected %d user records.",
            keyword,
            len(collected),
        )
        return collected