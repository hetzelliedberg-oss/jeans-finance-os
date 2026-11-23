"""Meta Graph API & Marketing API client for Jeans Around Page (359833590537243)."""

import os
import time
import asyncio
import requests
from typing import Any, Dict, List, Optional, Tuple

GRAPH_BASE = "https://graph.facebook.com/v21.0"


class MetaClient:
    def __init__(self) -> None:
        self.page_id = os.getenv("FB_PAGE_ID", "359833590537243")
        self.ad_account_id = os.getenv("AD_ACCOUNT_ID", "act_703804833399837")
        self._user_token = os.getenv("FB_ACCESS_TOKEN", "")
        self._page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
        self._page_token_fetched_at = 0.0

    def reload_env(self) -> None:
        self.page_id = os.getenv("FB_PAGE_ID", self.page_id)
        self.ad_account_id = os.getenv("AD_ACCOUNT_ID", self.ad_account_id)
        self._user_token = os.getenv("FB_ACCESS_TOKEN", self._user_token)
        if os.getenv("FB_PAGE_ACCESS_TOKEN"):
            self._page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")

    def get_user_token(self) -> str:
        return self._user_token or os.getenv("FB_ACCESS_TOKEN", "")

    def get_page_token(self) -> str:
        if self._page_token and (time.time() - self._page_token_fetched_at < 3600):
            return self._page_token
        if os.getenv("FB_PAGE_ACCESS_TOKEN"):
            self._page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
            return self._page_token

        ut = self.get_user_token()
        if not ut:
            return ""
        try:
            r = requests.get(
                f"{GRAPH_BASE}/{self.page_id}",
                params={"fields": "access_token,name", "access_token": ut},
                timeout=12,
            )
            data = r.json()
            if data.get("access_token"):
                self._page_token = data["access_token"]
                self._page_token_fetched_at = time.time()
                return self._page_token
        except Exception as e:
            print(f"[MetaClient] Error resolving page token: {e}")
        return ut

    def fetch_conversations(self, limit: int = 35, msg_limit: int = 20, max_total: Optional[int] = None) -> List[Dict[str, Any]]:
        token = self.get_page_token()
        if not token:
            return []
        target_total = max_total or limit
        page_limit = min(50, target_total)
        results: List[Dict[str, Any]] = []
        url: Optional[str] = f"{GRAPH_BASE}/{self.page_id}/conversations"
        params: Optional[Dict[str, Any]] = {
            "fields": (
                f"id,updated_time,unread_count,participants,"
                f"messages.limit({msg_limit}){{id,message,from,created_time,tags,attachments{{mime_type,name,image_data}}}}"
            ),
            "limit": page_limit,
            "access_token": token,
        }
        try:
            while url and len(results) < target_total:
                r = requests.get(url, params=params, timeout=25)
                data = r.json()
                if "error" in data:
                    print(f"[MetaClient] conversations error: {data['error']}")
                    break
                batch = data.get("data", [])
                if not batch:
                    break
                results.extend(batch)
                url = (data.get("paging") or {}).get("next")
                params = None
            return results[:target_total]
        except Exception as e:
            print(f"[MetaClient] fetch_conversations exception: {e}")
            return results

    def fetch_ads_metadata(self, limit: int = 400) -> List[Dict[str, Any]]:
        ut = self.get_user_token()
        if not ut:
            return []
        fields = (
            "id,name,status,effective_status,campaign{id,name},"
            "adset{id,name,targeting},"
            "creative{id,title,body,effective_object_story_id,object_story_spec}"
        )
        results: List[Dict[str, Any]] = []
        url: Optional[str] = f"{GRAPH_BASE}/{self.ad_account_id}/ads"
        params: Optional[Dict[str, Any]] = {"fields": fields, "limit": min(100, limit), "access_token": ut}
        try:
            while url and len(results) < limit:
                r = requests.get(url, params=params, timeout=20)
                data = r.json()
                if "error" in data:
                    print(f"[MetaClient] ads error: {data['error']}")
                    break
                batch = data.get("data", [])
                if not batch:
                    break
                results.extend(batch)
                url = (data.get("paging") or {}).get("next")
                params = None
            return results[:limit]
        except Exception as e:
            print(f"[MetaClient] fetch_ads_metadata exception: {e}")
            return results

    def fetch_ad_by_id(self, ad_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single Ad's campaign/adset/creative metadata on-demand by ad_id (cached)."""
        aid = (ad_id or "").strip()
        if not aid:
            return None
        cache = getattr(self, "_ad_cache", None)
        if cache is None:
            cache = {}
            self._ad_cache = cache
        if aid in cache:
            return cache[aid]
        ut = self.get_user_token()
        if not ut:
            return None
        try:
            fields = "id,name,effective_status,campaign{id,name},adset{id,name,targeting},creative{id,title,body,effective_object_story_id,object_story_spec}"
            r = requests.get(f"{GRAPH_BASE}/{aid}", params={"fields": fields, "access_token": ut}, timeout=12)
            if r.status_code == 200:
                d = r.json()
                if "error" not in d and d.get("id"):
                    cache[aid] = d
                    return d
        except Exception as e:
            print(f"[MetaClient] fetch_ad_by_id exception: {e}")
        return None

    def get_ad_post_text(self, ad_id: str) -> str:
        """Return full ad post caption/title/body for an ad_id so replies match exact post price/product."""
        ad = self.fetch_ad_by_id(ad_id)
        if not ad:
            return ""
        cr = ad.get("creative") or {}
        parts = []
        for k in ("title", "body"):
            v = (cr.get(k) or "").strip()
            if v and v not in parts:
                parts.append(v)
        oss = cr.get("object_story_spec") or {}
        for sub_k in ("link_data", "video_data", "photo_data"):
            sub = oss.get(sub_k) or {}
            for fld in ("name", "title", "message", "caption"):
                v = (sub.get(fld) or "").strip()
                if v and v not in parts:
                    parts.append(v)
        if not parts and cr.get("effective_object_story_id"):
            msg = self.fetch_post_message(cr["effective_object_story_id"])
            if msg:
                parts.append(msg.strip())
        return " | ".join(parts)[:600]

    def fetch_post_message(self, post_or_reel_id: str) -> str:
        """Fetch caption/message from a Page Post, Photo, or Reel ID via Meta Graph API (cached)."""
        obj_id = (post_or_reel_id or "").strip()
        if not obj_id:
            return ""
        cache = getattr(self, "_post_cache", None)
        if cache is None:
            cache = {}
            self._post_cache = cache
        if obj_id in cache:
            return cache[obj_id]
        tokens = [t for t in [self.get_page_token(), self.get_user_token()] if t]
        candidates = [obj_id]
        if "_" not in obj_id and obj_id.isdigit() and self.page_id:
            candidates.append(f"{self.page_id}_{obj_id}")
        for tok in tokens:
            for cid in candidates:
                try:
                    r = requests.get(
                        f"{GRAPH_BASE}/{cid}",
                        params={"fields": "message,description,story", "access_token": tok},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        txt = " ".join(
                            str(d.get(k) or "").strip()
                            for k in ("message", "description", "story")
                            if d.get(k)
                        ).strip()
                        if txt:
                            cache[obj_id] = txt
                            return txt
                except Exception:
                    pass
        cache[obj_id] = ""
        return ""

    def _send_typing(self, psid: str, token: str) -> None:
        try:
            requests.post(
                f"{GRAPH_BASE}/me/messages",
                params={"access_token": token},
                json={"recipient": {"id": psid}, "sender_action": "typing_on"},
                timeout=8,
            )
        except Exception:
            pass

    def send_single_text(self, psid: str, text: str) -> Tuple[bool, str]:
        token = self.get_page_token()
        if not token:
            return False, "Missing FB_ACCESS_TOKEN / FB_PAGE_ACCESS_TOKEN"
        try:
            r = requests.post(
                f"{GRAPH_BASE}/me/messages",
                params={"access_token": token},
                json={
                    "recipient": {"id": psid},
                    "messaging_type": "RESPONSE",
                    "message": {"text": text},
                },
                timeout=15,
            )
            res = r.json()
            if r.status_code == 200 and res.get("message_id"):
                return True, res["message_id"]
            return False, str(res.get("error", res))
        except Exception as e:
            return False, str(e)

    def send_image_url(self, psid: str, image_url: str) -> Tuple[bool, str]:
        token = self.get_page_token()
        if not token or not image_url:
            return False, "Missing token or image_url"
        try:
            ref = image_url.strip()
            if ref.startswith("attachment_id:"):
                att_id = ref.split("attachment_id:", 1)[1].strip()
                payload = {"attachment_id": att_id}
            else:
                payload = {"url": ref, "is_reusable": True}

            r = requests.post(
                f"{GRAPH_BASE}/me/messages",
                params={"access_token": token},
                json={
                    "recipient": {"id": psid},
                    "messaging_type": "RESPONSE",
                    "message": {
                        "attachment": {
                            "type": "image",
                            "payload": payload,
                        }
                    },
                },
                timeout=15,
            )
            res = r.json()
            if r.status_code == 200 and res.get("message_id"):
                return True, res["message_id"]

            # Fallback: if direct Meta URL fails (e.g., CDN signature expiry), stream bytes via filedata
            if ref.startswith("http"):
                img_resp = requests.get(ref, timeout=15)
                if img_resp.status_code == 200 and img_resp.content:
                    mime = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
                    up = requests.post(
                        f"{GRAPH_BASE}/me/messages",
                        params={"access_token": token},
                        data={
                            "recipient": json.dumps({"id": psid}),
                            "messaging_type": "RESPONSE",
                            "message": json.dumps({"attachment": {"type": "image", "payload": {"is_reusable": True}}}),
                        },
                        files={"filedata": ("product.jpg", img_resp.content, mime)},
                        timeout=25,
                    )
                    up_res = up.json()
                    if up.status_code == 200 and up_res.get("message_id"):
                        return True, up_res["message_id"]
                    return False, str(up_res.get("error", up_res))

            return False, str(res.get("error", res))
        except Exception as e:
            return False, str(e)

    async def send_3enter_sequence(
        self,
        psid: str,
        bubbles: List[str],
        dry_run: bool = True,
        delay_sec: float = 0.5,
        image_url: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        clean_bubbles = [b.strip() for b in bubbles if b and b.strip()]
        imgs: List[str] = []
        for u in ([image_url] if image_url else []) + list(image_urls or []):
            u_clean = (u or "").strip()
            if u_clean and u_clean not in imgs:
                imgs.append(u_clean)

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "sent_count": len(clean_bubbles),
                "msg_ids": [],
                "image_sent": bool(imgs),
                "image_count": len(imgs),
                "errors": [],
            }

        token = self.get_page_token()
        if not token:
            return {"ok": False, "dry_run": False, "sent_count": 0, "msg_ids": [], "errors": ["Missing Page Token"]}

        msg_ids = []
        errors = []
        for idx, text in enumerate(clean_bubbles):
            if idx == 0:
                self._send_typing(psid, token)
            await asyncio.sleep(0.2 if idx == 0 else delay_sec)
            ok, info = await asyncio.to_thread(self.send_single_text, psid, text)
            if ok:
                msg_ids.append(info)
            else:
                errors.append(info)
                break

        image_count = 0
        if imgs and not errors:
            for img_ref in imgs:
                await asyncio.sleep(0.3)
                ok_img, info_img = await asyncio.to_thread(self.send_image_url, psid, img_ref)
                if ok_img:
                    msg_ids.append(info_img)
                    image_count += 1

        return {
            "ok": len(errors) == 0 and len(msg_ids) > 0,
            "dry_run": False,
            "sent_count": len(msg_ids),
            "msg_ids": msg_ids,
            "image_sent": image_count > 0,
            "image_count": image_count,
            "errors": errors,
        }


meta_client = MetaClient()
