"""Simulated phones for the campus acceptance tests (fictional data only).

``SimulatedDevice`` is a tiny model of the mobile client protocol and doubles as
its living documentation:

* The SERVER is authoritative. A device keeps a small in-memory cache
  (``party_id``, ``version``, ``state``) that may be stale or wiped at any time.
* Sockets are only an accelerator. After a restart, a missed push or a lost HTTP
  response, ``reconcile()`` converges the cache using two plain REST reads:
  ``GET /parties/active`` and ``GET /events?after_version=<cached or 0>``.
* A destructive action (cancel) is written to a small durable journal BEFORE it is
  sent, together with its idempotency key. The device shows "CANCEL_PENDING" until
  the server confirms, so a lost reply can be retried with the SAME key (the server
  replays the stored result and never records a second event). The journal survives
  ``restart()``; the in-memory cache does not.

Every call can be recorded by a shared ``Transcript`` that renders sanitized
Markdown (no tokens or Authorization headers, no filesystem paths).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

API = "/api/campus"

HEADER_LINE = (
    "Recorded from the automated acceptance test with a fake clock "
    "and a fake routing provider (no live provider)"
)


# --------------------------------------------------------------------------
# Transcript (sanitized, deterministic Markdown)
# --------------------------------------------------------------------------
_SECRET_KEYS = {"token", "access_token", "authorization", "password", "hashed_password"}
_MAX_STR = 90
_MAX_LIST = 4


def abridge(value: Any) -> Any:
    """Shorten long strings and lists so a transcript stays readable."""
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if k.lower() in _SECRET_KEYS else abridge(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        head = [abridge(v) for v in value[:_MAX_LIST]]
        if len(value) > _MAX_LIST:
            head.append(f"... (+{len(value) - _MAX_LIST} more)")
        return head
    if isinstance(value, str) and len(value) > _MAX_STR:
        return value[: _MAX_STR - 3] + "..."
    return value


class Transcript:
    """Collects request/response pairs and renders them as Markdown.

    ``now`` is a callable returning the fake clock's current instant, so every
    entry is stamped with deterministic time.
    """

    def __init__(self, now, title="TripSync campus scheduling: demo transcript", compact=False):
        self._now = now
        self.compact = compact
        self.title = title
        self.items: List[tuple] = []
        self._step = 0

    def section(self, text: str) -> None:
        self.items.append(("section", text))

    def note(self, text: str) -> None:
        """A one-line italic annotation for steps that are not API calls."""
        self.items.append(("note", text))

    def record(self, who, method, path, request_json, status, response_json, note=None,
               headers=None):
        self._step += 1
        stamp = self._now().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.items.append(
            ("call", self._step, stamp, who, method, path, request_json, status,
             response_json, note, headers or {})
        )

    @staticmethod
    def _compact(value: Any, indent: int = 0, width: int = 160) -> str:
        """Pretty JSON that keeps any object/array fitting in ``width`` on one line."""
        flat = json.dumps(value, ensure_ascii=True)
        if not isinstance(value, (dict, list)) or len(flat) + indent <= width or not value:
            return flat
        pad, inner = " " * indent, " " * (indent + 2)
        if isinstance(value, dict):
            parts = [f"{inner}{json.dumps(k)}: {Transcript._compact(v, indent + 2, width)}"
                     for k, v in value.items()]
            return "{\n" + ",\n".join(parts) + f"\n{pad}}}"
        parts = [inner + Transcript._compact(v, indent + 2, width) for v in value]
        return "[\n" + ",\n".join(parts) + f"\n{pad}]"

    def _block(self, label: str, payload: Any) -> List[str]:
        if self.compact:
            body = self._compact(abridge(payload))
        else:
            body = json.dumps(abridge(payload), indent=2, ensure_ascii=True)
        return [f"{label}", "```json", body, "```", ""]

    def render(self) -> str:
        lines = [f"# {self.title}", "", f"> {HEADER_LINE}", "",
                 "Users are fictional. Times come from the test's fake clock, so the "
                 "transcript is identical on every run.", ""]
        for item in self.items:
            if item[0] == "section":
                lines += [f"## {item[1]}", ""]
                continue
            if item[0] == "note":
                lines += [f"_{item[1]}_", ""]
                continue
            _, step, stamp, who, method, path, req, status, resp, note, headers = item
            lines.append(f"### {step}. {who}: `{method} {path}` -> {status}")
            lines.append(f"_clock {stamp}_" + (f" - {note}" if note else ""))
            lines.append("")
            if req is not None:
                lines += self._block("Request body:", req)
            for name, value in headers.items():
                lines += [f"Response header: `{name}: {value}`", ""]
            if resp is not None:
                lines += self._block("Response body:", resp)
        return "\n".join(lines).rstrip() + "\n"

    def assert_sanitized(self, *forbidden: str) -> None:
        """No credentials, filesystem paths or real-time stamps in the output."""
        text = self.render()
        for needle in ("Bearer", "eyJ", "Authorization", "authorization", "/Users/",
                       "/private/", "/tmp/", "/var/", "C:\\", *forbidden):
            assert needle not in text, f"transcript leaks {needle!r}"
        for stamp in re.findall(r"\b(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}", text):
            assert stamp.startswith("2026-03-"), f"real-time stamp in transcript: {stamp}"


# --------------------------------------------------------------------------
# The simulated phone
# --------------------------------------------------------------------------
@dataclass
class LocalCache:
    """What the phone believes about its party. In memory only: wiped by restart()."""

    party_id: Optional[int] = None
    version: Optional[int] = None
    state: Optional[str] = None
    departure: Optional[str] = None        # agreed departure, UTC ISO
    pending_change: Optional[dict] = None
    event_types: List[str] = field(default_factory=list)


@dataclass
class PendingCancel:
    """Durable journal entry written BEFORE the cancel request is sent."""

    party_id: int
    key: str


class SimulatedDevice:
    def __init__(self, name, client, headers, user_id=None, transcript=None):
        self.name = name
        self.client = client
        self.headers = dict(headers)
        self.user_id = user_id
        self.transcript = transcript
        self.cache = LocalCache()
        self.pending_cancel: Optional[PendingCancel] = None   # durable journal
        self.cancel_resolution: Optional[str] = None
        self._keys = 0

    # ------------------------------------------------------------ transport
    def call(self, method, path, json=None, note=None, drop_response=False):
        """One HTTP call. With ``drop_response`` the server still executes the call
        but the device never sees the reply (returns None), like a lost response."""
        url = path if path.startswith("/api") else API + path
        resp = self.client.request(method, url, headers=self.headers, json=json)
        if self.transcript is not None:
            try:
                body = resp.json()
            except ValueError:
                body = None
            shown = "(response lost before reaching the device)" if drop_response else resp.status_code
            replay = resp.headers.get("Idempotent-Replay")
            self.transcript.record(self.name, method, url, json, shown,
                                   None if drop_response else body, note,
                                   {"Idempotent-Replay": replay} if replay and not drop_response else None)
        return None if drop_response else resp

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.call("POST", path, json=json, **kw)

    def _key(self, label):
        self._keys += 1
        return f"{self.name}-{label}-{self._keys}"

    # ------------------------------------------------------------ protocol
    def create_request(self, body, **kw):
        return self.post("/requests", body, **kw)

    def search(self, request_id, **kw):
        return self.get(f"/requests/{request_id}/suggestions", **kw)

    def propose(self, suggestion_id, acknowledge_warnings=False, **kw):
        return self.post(f"/suggestions/{suggestion_id}/connections",
                         {"acknowledge_warnings": acknowledge_warnings}, **kw)

    def accept(self, connection_id, expected_version, key=None, **kw):
        key = key or self._key("accept")
        resp = self.post(f"/connections/{connection_id}/accept",
                         {"expected_version": expected_version, "idempotency_key": key}, **kw)
        if resp is not None and resp.status_code == 200:
            self._adopt(resp.json()["party"])
        return resp

    def cancel(self, party_id, drop_response=False, key=None, **kw):
        """Record the pending state first, then send. A lost reply leaves it pending."""
        key = key or self._key("cancel")
        self.pending_cancel = PendingCancel(party_id, key)
        resp = self.post(f"/parties/{party_id}/cancel", {"idempotency_key": key},
                         drop_response=drop_response, **kw)
        self._settle_cancel(resp)
        return resp

    def retry_cancel(self, **kw):
        """Resend the pending cancel with the SAME idempotency key."""
        assert self.pending_cancel is not None, "nothing pending"
        p = self.pending_cancel
        resp = self.post(f"/parties/{p.party_id}/cancel", {"idempotency_key": p.key}, **kw)
        self._settle_cancel(resp)
        return resp

    def _settle_cancel(self, resp):
        if resp is None:
            return                          # lost reply: stay pending until the server confirms
        if resp.status_code == 200:
            self._adopt(resp.json())
            self.pending_cancel, self.cancel_resolution = None, "confirmed_by_response"
        elif resp.status_code in (404, 409, 422):
            self.pending_cancel, self.cancel_resolution = None, f"rejected_{resp.status_code}"

    def _adopt(self, party_view):
        c = self.cache
        c.party_id, c.version = party_view["id"], party_view["version"]
        c.state, c.pending_change = party_view["state"], party_view.get("pending_change")
        c.departure = party_view["agreed_departure"]["utc"]

    @property
    def shows(self) -> str:
        """What the screen shows: a pending cancel wins over the cached state."""
        if self.pending_cancel is not None:
            return "CANCEL_PENDING"
        return self.cache.state or "NO_PARTY"

    def restart(self):
        """App restart: the in-memory cache is gone; the durable journal is not."""
        self.cache = LocalCache()

    def reconcile(self):
        """Converge on the server's version and state using REST only."""
        active = self.get("/parties/active").json()
        party = active["party"] or active["recently_ended"]
        if party is None:
            self.cache = LocalCache()
            return self.cache
        if self.cache.party_id != party["id"]:
            self.cache = LocalCache(party_id=party["id"])
        after = self.cache.version or 0
        feed = self.get(f"/events?after_version={after}&party_id={party['id']}").json()
        self.cache.event_types += [e["event_type"] for e in feed["events"]]
        self._adopt(feed["party"])
        self.cache.version = feed["latest_version"]
        # A pending cancel resolves ONLY once the server shows the party is over.
        p = self.pending_cancel
        if p is not None and p.party_id == self.cache.party_id and self.cache.state != "AGREED":
            self.pending_cancel = None
            self.cancel_resolution = f"confirmed_by_server_{self.cache.state}"
        return self.cache
