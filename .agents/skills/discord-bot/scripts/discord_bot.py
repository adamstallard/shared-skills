#!/usr/bin/env python3
"""Post to, read and manage Discord channels as a bot, one call at a time.

Each command makes its Discord API calls, prints one JSON object, and exits;
nothing keeps running between calls. Standard library only.

Why it is built this way, and what was tried and rejected: ../DECISIONS.md.
"""

import argparse
import getpass
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/adamstallard/shared-skills, 1)"
KEYCHAIN_SERVICE = "discord-bot"
MAX_CONTENT = 2000
MAX_THREAD_NAME = 100
MAX_READ = 100
# Header parts for agent, session and project; edit keeps a first line starting with one.
HEADER_PREFIXES = ("👤 ", "🎯 ", "📦 ")
IDENTITY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

TEXT_CHANNEL_TYPES = {0, 5}  # text, announcement
THREAD_TYPES = {10, 11, 12}  # announcement thread, public thread, private thread
READABLE_MESSAGE_TYPES = {0, 19, 21}  # default, reply, thread starter

PERMISSIONS = {
    "viewChannel": 1 << 10,
    "sendMessages": 1 << 11,
    "readMessageHistory": 1 << 16,
    "createPublicThreads": 1 << 35,
    "sendMessagesInThreads": 1 << 38,
}
CHANNEL_BITS = sum(PERMISSIONS.values())
ADMINISTRATOR = 1 << 3
ALL_PERMISSIONS = (1 << 64) - 1

# Discord error codes that mean the bot lacks access or a permission.
NO_ACCESS = {50001, 50013}

# User and channel mentions, matched in one pass so both lookbehinds see the
# original text: in "@adam#agents" the "#" follows "m", so it isn't a channel.
#
# "@name" is not a mention after:
# - an ASCII letter or digit, or one of them and then "._-": an email address
#   ("adam@x.com", "adam_@gmail.com"). is_email() checks other letters.
# - "/": a path ("youtube.com/@adam").
# - a backslash: an escape, as in Discord.
# So "_@adam_" (emphasis) and "请@adam" (Chinese and Japanese use no spaces)
# are mentions. The name takes word characters and combining accents, so
# "@José" is read whole however the accent is typed. It has no length cap, so
# a long word is never cut down to a shorter member's name.
#
# "#channel" must start a word, so "repo#47" is left alone.
MENTION_RE = re.compile(
    r"(?<![A-Za-z0-9@<\\/])(?<![A-Za-z0-9][._-])@(?P<user>[\w.\u0300-\u036f-]{2,})"
    r"|(?<![\w<#\\])#(?P<channel>[a-z0-9_-]{1,100})"
)
# After a name, "/" and a word character make it a package scope ("@types/node").
SCOPE_RE = re.compile(r"/\w")
# Trailing characters that may be punctuation or emphasis rather than part of a name.
NAME_TAIL = "._-"
# Scripts that space their words, so a letter of theirs right before "@" makes an email address.
# "EXTENDED ARABIC" covers the Persian and Urdu digits ("EXTENDED ARABIC-INDIC DIGIT ONE").
SPACED_SCRIPTS = ("LATIN", "GREEK", "CYRILLIC", "ARMENIAN", "GEORGIAN", "HEBREW", "ARABIC",
                  "EXTENDED ARABIC")
MAX_NAME = 32  # Discord's longest username or nickname
MEMBER_SEARCH_LIMIT = 100
NEVER_MENTION = {"everyone", "here"}
# Code and links, which mention conversion leaves untouched. Code follows
# CommonMark's code-span rule, which also covers ``` fences: a run of N
# backticks opens a span that the next run of exactly N backticks closes, and a
# run that nothing closes is plain text.
VERBATIM_RE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)|https?://\S+", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def is_id(value):
    """Whether a channel or server reference is a Discord id (a 17-20 digit snowflake), not a name."""
    return value.isdigit() and 17 <= len(value) <= 20


class Failure(Exception):
    """An error to report to the caller, with Discord's status and code when known."""

    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code

    def no_access(self):
        return self.status == 403 or self.code in NO_ACCESS


# --- identity, config and token ---------------------------------------------


def config_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "discord-bot")


def resolve_identity(arg, env=None):
    env = os.environ if env is None else env
    identity = arg or env.get("DISCORD_BOT_IDENTITY") or "default"
    if not IDENTITY_RE.match(identity):
        raise Failure(f"identity {identity!r} may use only letters, digits, '_', '.' and '-'")
    return identity


def load_config(identity, env=None):
    path = os.path.join(config_dir(env), identity + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as e:
        raise Failure(f"cannot read {path}: {e}")
    if not isinstance(config, dict):
        raise Failure(f"{path} must hold a JSON object")
    return config, path


def keychain_entry(identity, config):
    entry = config.get("keychain") or {}
    return entry.get("service", KEYCHAIN_SERVICE), entry.get("account", identity)


def read_keychain(service, account, run=subprocess.run, which=shutil.which):
    """The stored token, or None when no keychain tool is available or nothing is stored."""
    if which("security"):
        cmd = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
    elif which("secret-tool"):
        cmd = ["secret-tool", "lookup", "service", service, "account", account]
    else:
        return None
    result = run(cmd, capture_output=True, text=True)
    token = result.stdout.strip() if result.returncode == 0 else ""
    return token or None


def resolve_token(identity, config, env=None, read=read_keychain):
    env = os.environ if env is None else env
    token = env.get("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    service, account = keychain_entry(identity, config)
    token = read(service, account)
    if token:
        return token
    raise Failure(
        f"no bot token for identity {identity!r}: set DISCORD_BOT_TOKEN, or run "
        f"'discord_bot.py store-token --identity {identity}' to keep it in the keychain "
        f"(service {service!r}, account {account!r})"
    )


# --- Discord API ---------------------------------------------------------------


class Api:
    def __init__(self, token, opener=urllib.request.urlopen, sleep=time.sleep):
        self.token = token
        self.opener = opener
        self.sleep = sleep

    def request(self, method, path, body=None, query=None):
        url = API + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": "Bot " + self.token, "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = "application/json"
        # Discord answers 429 with how long to wait; retrying a few times
        # covers ordinary bursts without hiding a sustained rate limit.
        for _ in range(4):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with self.opener(req, timeout=30) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                try:
                    payload = _json_or_empty(e.read())
                except (OSError, http.client.HTTPException):
                    payload = {}  # the status alone still says what went wrong
                if e.code == 429:
                    self.sleep(min(float(payload.get("retry_after", 1)), 30))
                    continue
                raise Failure(payload.get("message") or e.reason, status=e.code, code=payload.get("code"))
            except urllib.error.URLError as e:
                raise Failure(f"cannot reach Discord: {e.reason}")
            except (OSError, http.client.HTTPException) as e:
                # urlopen wraps only connection errors; a timeout or a dropped
                # connection while waiting for or reading the answer arrives raw.
                raise Failure(f"lost the connection to Discord: {e!r}")
        raise Failure("rate limited by Discord; try again shortly", status=429)


def _json_or_empty(raw):
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


# --- servers, channels and threads ----------------------------------------------


def servers(api, config):
    guilds = api.request("GET", "/users/@me/guilds")
    wanted = str(config.get("server") or "").strip()
    if wanted:
        guilds = [g for g in guilds if wanted in (g["id"], g["name"])]
        if not guilds:
            raise Failure(f"the bot is not in a server named or numbered {wanted!r}")
    if not guilds:
        raise Failure("the bot is not in any server; invite it first")
    return guilds


def find_channel(api, config, name):
    """The text channel called `name` (or with that id), and the id of its server."""
    name = str(name).lstrip("#")
    if is_id(name):
        channel = api.request("GET", f"/channels/{name}")
        return channel, channel.get("guild_id")
    matches = []
    for guild in servers(api, config):
        for channel in api.request("GET", f"/guilds/{guild['id']}/channels"):
            if channel.get("type") in TEXT_CHANNEL_TYPES and channel.get("name") == name:
                matches.append((channel, guild["id"]))
    if not matches:
        raise Failure(f"no text channel #{name} that the bot can see")
    if len({guild_id for _, guild_id in matches}) > 1:
        raise Failure(f"#{name} exists in more than one server; set \"server\" in the identity's config")
    if len(matches) > 1:
        ids = ", ".join(channel["id"] for channel, _ in matches)
        raise Failure(f"one server has several channels named #{name} ({ids}); pass the channel id instead")
    return matches[0]


def find_thread(api, thread_id):
    try:
        thread = api.request("GET", f"/channels/{thread_id}")
    except Failure as e:
        if e.status in (400, 404):
            raise Failure(f"thread {thread_id} not found", status=404)
        raise
    if thread.get("type") not in THREAD_TYPES:
        raise Failure(f"{thread_id} is a channel, not a thread", status=404)
    return thread, thread.get("guild_id")


def target(api, config, args):
    """The channel or thread a command acts on, and its server's id."""
    if getattr(args, "thread", None):
        return find_thread(api, args.thread)
    name = str(args.channel or os.environ.get("DISCORD_BOT_CHANNEL") or config.get("defaultChannel") or "")
    if not name:
        raise Failure("no channel given: pass --channel, or set \"defaultChannel\" in the identity's config")
    return find_channel(api, config, name)


# --- message text ------------------------------------------------------------------


def header(agent, session, project):
    """The line naming who posts, from which session, about what; empty if none given."""
    values = (agent, session, project)
    return "  ".join(prefix + v for prefix, v in zip(HEADER_PREFIXES, values) if v)


def folded(name):
    """A name as mentions compare it: accents composed (NFC), case ignored."""
    return unicodedata.normalize("NFC", name).lower()


def is_email(text, at):
    """Whether the "@" at `at` follows a letter or digit of a script that spaces its words ("josé@x.com").

    The regex already skips ASCII letters and digits; this catches the rest.
    Other scripts, such as Chinese, Japanese, Korean and Thai, use no spaces,
    so "请@adam", "ขอบคุณ@adam" and "質問１@adam" (a fullwidth digit) are
    still mentions.
    """
    i = at
    while i > 0 and unicodedata.category(text[i - 1]).startswith("M"):
        i -= 1  # a combining accent belongs to the letter before it
    if i == 0:
        return False
    c = text[i - 1]
    return (c.isalpha() or c.isdecimal()) and unicodedata.name(c, "").startswith(SPACED_SCRIPTS)


def member_names(member):
    user = member.get("user") or {}
    return [folded(n) for n in (user.get("username"), user.get("global_name"), member.get("nick")) if n]


def exact_members(handle, members):
    """Ids of the members whose username, global name or nickname is `handle`, ignoring case."""
    handle = folded(handle)
    ids = []
    for member in members:
        user_id = (member.get("user") or {}).get("id")
        if handle in member_names(member) and user_id not in ids:
            ids.append(user_id)
    return ids


def convert_mentions(api, guild_id, text, channels):
    """Turn @name and #channel into Discord mentions.

    Returns the text, the ids of users it mentions, and warnings for names that
    stayed as plain text.
    """
    warnings, warned, user_ids, found = [], set(), [], {}
    search_refused = False

    def note(key, warning):
        """Warn once per key, which is a name and ignores case."""
        if folded(key) not in warned:
            warned.add(folded(key))
            warnings.append(warning)

    def search(handle):
        """The members a search for `handle` returns; empty if search is refused."""
        nonlocal search_refused
        query, key = unicodedata.normalize("NFC", handle), folded(handle)
        # A name longer than Discord allows belongs to nobody, so it isn't searched.
        if key not in found and not search_refused and len(query) <= MAX_NAME:
            try:
                found[key] = api.request(
                    "GET", f"/guilds/{guild_id}/members/search",
                    query={"query": query, "limit": MEMBER_SEARCH_LIMIT},
                ) or []
            except Failure as e:
                if not e.no_access():
                    raise
                search_refused = True
                note("@", "Discord refused member search, so @names stay plain text; "
                          "see the README's 'Mentions' section")
        return found.get(key, [])

    def verdict(handle, rest):
        """The id of the one member `handle` can only mean, or None and a warning.

        `rest` is the text from the start of the name. Search returns members
        whose names start with `handle`, so it also shows when the text goes on
        to spell a longer name ("@Adam Smith", "@Jo'Anne"). That name stops the
        ping but is never picked: the writer may mean neither.
        """
        members = search(handle)
        if len(members) >= MEMBER_SEARCH_LIMIT:
            # The page is full, so another member with this exact name may be missing from it.
            return None, f"too many members' names start with @{handle} to be sure; left as plain text"
        ids = exact_members(handle, members)
        if len(ids) > 1:
            return None, f"several members are named @{handle}; left as plain text"
        # Both sides folded, since folding can change a name's length ("İ" lowercases to two).
        name, rest = folded(handle), folded(rest)
        longer = next((n for m in members for n in member_names(m)
                       if len(n) > len(name) and rest.startswith(n)), None)
        if ids and longer:
            return None, f"@{handle} could be the start of @{longer}; left as plain text"
        return (ids[0] if ids else None), None

    def user(match):
        name = match.group("user")
        if SCOPE_RE.match(match.string, match.end("user")):
            return match.group(0)  # a package scope, checked here because a lookahead would backtrack
        if is_email(match.string, match.start()):
            return match.group(0)
        if name.rstrip(NAME_TAIL).lower() in NEVER_MENTION:
            return match.group(0)  # "@everyone." and "_@here_" too, never a member named with the tail
        # The whole name first; then without a trailing "._-", which may be
        # punctuation ("Thanks @adam.") or emphasis ("_@adam_") and is put back.
        handles = [h for h in dict.fromkeys((name, name.rstrip(NAME_TAIL)))
                   if len(unicodedata.normalize("NFC", h)) >= 2]
        if not handles or not guild_id:
            return match.group(0)
        why = None  # the first handle's reason for not pinging, if it had one
        for handle in handles:
            user_id, reason = verdict(handle, match.string[match.start("user"):])
            if user_id:
                break
            why = why or (reason and (handle, reason))
        else:
            if not search_refused:
                note(*(why or (handles[-1], f"no member is named @{handles[-1]}; left as plain text")))
            return match.group(0)
        if user_id not in user_ids:
            user_ids.append(user_id)
        return f"<@{user_id}>{name[len(handle):]}"

    def mention(match):
        if match.group("user"):
            return user(match)
        channel_id = channels.get(match.group("channel"))
        return f"<#{channel_id}>" if channel_id else match.group(0)

    verbatim = []

    def hide(match):
        verbatim.append(match.group(0))
        return f"\x00{len(verbatim) - 1}\x00"

    text = VERBATIM_RE.sub(hide, text.replace("\x00", ""))  # no NUL can pose as a placeholder
    text = MENTION_RE.sub(mention, text)
    text = PLACEHOLDER_RE.sub(lambda m: verbatim[int(m.group(1))], text)
    return text, user_ids, warnings


def channel_ids(api, guild_id, text):
    """Channel names to ids, fetched only when the text could mention a channel."""
    if not guild_id or "#" not in text:
        return {}
    return {
        c["name"]: c["id"]
        for c in api.request("GET", f"/guilds/{guild_id}/channels")
        if c.get("type") in TEXT_CHANNEL_TYPES
    }


def fit(content):
    if len(content) > MAX_CONTENT:
        raise Failure(
            f"message is {len(content)} characters with its header; Discord's limit is {MAX_CONTENT}. "
            "Shorten it, or post it in parts."
        )
    return content


def message_text(value):
    """The --message value, or standard input when it is '-'."""
    text = sys.stdin.read() if value == "-" else value
    if not text or not text.strip():
        raise Failure("the message is empty")
    return text


# --- permissions -----------------------------------------------------------------


def compute_permissions(guild, member_role_ids, user_id, overwrites):
    """The bot's effective permissions in a channel, following Discord's documented order."""
    if guild.get("owner_id") == user_id:
        return ALL_PERMISSIONS
    roles = {r["id"]: int(r["permissions"]) for r in guild.get("roles", [])}
    perms = roles.get(guild["id"], 0)
    for role_id in member_role_ids:
        perms |= roles.get(role_id, 0)
    if perms & ADMINISTRATOR:
        return ALL_PERMISSIONS
    by_id = {o["id"]: o for o in overwrites or []}
    everyone = by_id.get(guild["id"])
    if everyone:
        perms = (perms & ~int(everyone["deny"])) | int(everyone["allow"])
    allow = deny = 0
    for role_id in member_role_ids:
        o = by_id.get(role_id)
        if o:
            allow |= int(o["allow"])
            deny |= int(o["deny"])
    perms = (perms & ~deny) | allow
    own = by_id.get(user_id)
    if own and own.get("type") == 1:
        perms = (perms & ~int(own["deny"])) | int(own["allow"])
    # Without View Channel, Discord denies every other permission in the channel.
    if not perms & PERMISSIONS["viewChannel"]:
        perms &= ~CHANNEL_BITS
    return perms


def channel_permissions(api, guild_id, channel, bot_id):
    guild = api.request("GET", f"/guilds/{guild_id}")
    member = api.request("GET", f"/guilds/{guild_id}/members/{bot_id}")
    perms = compute_permissions(guild, member.get("roles", []), bot_id, channel.get("permission_overwrites"))
    return {name: bool(perms & bit) for name, bit in PERMISSIONS.items()}


# --- commands ---------------------------------------------------------------------


def cmd_post(api, config, args):
    where, guild_id = target(api, config, args)
    text = message_text(args.message)
    body, user_ids, warnings = convert_mentions(api, guild_id, text, channel_ids(api, guild_id, text))
    top = header(args.agent, args.session, args.project)
    content = fit(f"{top}\n{body}" if top else body)
    sent = api.request(
        "POST",
        f"/channels/{where['id']}/messages",
        body={"content": content, "allowed_mentions": {"parse": [], "users": user_ids}},
    )
    result = {"messageId": sent["id"], "channelId": where["id"], "url": message_url(guild_id, where["id"], sent["id"])}
    if args.thread:
        result["threadId"] = where["id"]
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_read(api, config, args):
    where, _ = target(api, config, args)
    if not 1 <= args.limit <= MAX_READ:
        raise Failure(f"--limit must be between 1 and {MAX_READ}")
    query = {"limit": args.limit}
    if args.before:
        query["before"] = args.before
    messages = []
    for m in api.request("GET", f"/channels/{where['id']}/messages", query=query):
        if m.get("type") not in READABLE_MESSAGE_TYPES:
            continue
        attachments = [a["url"] for a in m.get("attachments", [])]
        if not (m.get("content") or "").strip() and not attachments:
            continue
        item = {
            "messageId": m["id"],
            "timestamp": m["timestamp"],
            "author": (m.get("author") or {}).get("username", "unknown"),
            "content": m.get("content", ""),
        }
        if attachments:
            item["attachments"] = attachments
        if m.get("thread"):
            item["threadId"] = m["thread"]["id"]
        messages.append(item)
    result = {"channel": "#" + where.get("name", ""), "messages": messages}
    if args.thread:
        result["threadId"] = where["id"]
    return result


def cmd_edit(api, config, args):
    where, guild_id = target(api, config, args)
    old = api.request("GET", f"/channels/{where['id']}/messages/{args.message_id}")
    text = message_text(args.message)
    body, user_ids, warnings = convert_mentions(api, guild_id, text, channel_ids(api, guild_id, text))
    first = (old.get("content") or "").split("\n", 1)[0]
    content = fit(f"{first}\n{body}" if first.startswith(HEADER_PREFIXES) else body)
    api.request(
        "PATCH",
        f"/channels/{where['id']}/messages/{args.message_id}",
        body={"content": content, "allowed_mentions": {"parse": [], "users": user_ids}},
    )
    result = {"messageId": args.message_id, "edited": True}
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_delete(api, config, args):
    where, _ = target(api, config, args)
    api.request("DELETE", f"/channels/{where['id']}/messages/{args.message_id}")
    return {"messageId": args.message_id, "deleted": True}


def cmd_thread(api, config, args):
    where, _ = target(api, config, args)
    name = args.name.strip()
    if not name:
        raise Failure("the thread name is empty")
    try:
        thread = api.request(
            "POST",
            f"/channels/{where['id']}/messages/{args.message_id}/threads",
            body={"name": name[:MAX_THREAD_NAME]},
        )
    except Failure as e:
        if e.code == 160004:
            raise Failure("that message already has a thread", status=409, code=e.code)
        raise
    return {"threadId": thread["id"], "threadName": thread["name"], "messageId": args.message_id, "channelId": where["id"]}


def cmd_check(api, config, args):
    """Report who the bot is, where it can post, and what it may do there."""
    me = api.request("GET", "/users/@me")
    result = {
        "identity": args.identity,
        "bot": me.get("username"),
        "servers": [g["name"] for g in servers(api, config)],
    }
    for key in ("channels", "people"):
        if config.get(key):
            result[key] = config[key]
    try:
        channel, guild_id = target(api, config, args)
    except Failure as e:
        result["defaultChannel"] = {"ok": False, "error": str(e)}
        return result
    entry = {"name": "#" + channel.get("name", ""), "id": channel["id"]}
    try:
        entry["permissions"] = channel_permissions(api, guild_id, channel, me["id"])
    except Failure as e:
        entry["permissions"] = {"ok": False, "error": str(e)}
    result["defaultChannel"] = entry
    # Discord can accept a search and still return nobody; a search for the bot's
    # own name always has a match, so an empty answer means search is not working.
    try:
        found = api.request(
            "GET", f"/guilds/{guild_id}/members/search",
            query={"query": me["username"], "limit": MEMBER_SEARCH_LIMIT},
        )
        result["memberSearch"] = bool(found)
    except Failure as e:
        if e.no_access():
            result["memberSearch"] = False
        else:
            result["memberSearch"] = None
            result["memberSearchError"] = str(e)
    return result


def cmd_store_token(args, env=None, run=subprocess.run, which=shutil.which):
    config, _ = load_config(args.identity, env)
    service, account = keychain_entry(args.identity, config)
    token = getpass.getpass(f"Bot token for {args.identity!r} (input hidden): ").strip()
    if not token:
        raise Failure("no token entered")
    if which("security"):
        # `security` takes the secret only as an argument, so it is briefly
        # visible to other processes of this user; see DECISIONS.md.
        cmd = ["security", "add-generic-password", "-U", "-s", service, "-a", account, "-w", token]
        result = run(cmd, capture_output=True, text=True)
    elif which("secret-tool"):
        cmd = ["secret-tool", "store", "--label", f"Discord bot token ({account})", "service", service, "account", account]
        result = run(cmd, input=token, capture_output=True, text=True)
    else:
        raise Failure("no keychain tool found (macOS 'security' or Linux 'secret-tool'); use DISCORD_BOT_TOKEN instead")
    if result.returncode != 0:
        raise Failure(f"storing the token failed: {result.stderr.strip()}")
    return {"identity": args.identity, "stored": True, "service": service, "account": account}


def message_url(guild_id, channel_id, message_id):
    return f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}"


# --- command line -----------------------------------------------------------------


def parser():
    p = argparse.ArgumentParser(prog="discord_bot.py", description="Use Discord as a bot, one call at a time.")
    p.add_argument("--identity", help="which bot to act as (default: $DISCORD_BOT_IDENTITY, else 'default')")
    sub = p.add_subparsers(dest="command", required=True)

    def where(cmd, threads=True):
        cmd.add_argument("--channel", help="channel name or id (default: the identity's defaultChannel)")
        if threads:
            cmd.add_argument("--thread", help="thread id; takes precedence over --channel")

    c = sub.add_parser("post", help="post a message")
    where(c)
    c.add_argument("--message", required=True, help="the text, or '-' to read it from standard input")
    c.add_argument("--agent", help="header: who is posting")
    c.add_argument("--session", help="header: which session the post comes from")
    c.add_argument("--project", help="header: what the work is about")

    c = sub.add_parser("read", help="read recent messages, newest first")
    where(c)
    c.add_argument("--limit", type=int, default=20, help=f"how many, 1 to {MAX_READ} (default 20)")
    c.add_argument("--before", help="only messages older than this message id, to page back")

    c = sub.add_parser("edit", help="replace a message's text, keeping its header")
    where(c)
    c.add_argument("--message-id", required=True)
    c.add_argument("--message", required=True, help="the new text, or '-' to read it from standard input")

    c = sub.add_parser("delete", help="delete a message")
    where(c)
    c.add_argument("--message-id", required=True)

    c = sub.add_parser("thread", help="start a thread on a message")
    where(c, threads=False)
    c.add_argument("--message-id", required=True)
    c.add_argument("--name", required=True, help=f"thread title, cut to {MAX_THREAD_NAME} characters")

    c = sub.add_parser("check", help="show who the bot is and what it may do")
    where(c, threads=False)

    sub.add_parser("store-token", help="save this identity's bot token in the keychain")
    return p


COMMANDS = {
    "post": cmd_post,
    "read": cmd_read,
    "edit": cmd_edit,
    "delete": cmd_delete,
    "thread": cmd_thread,
    "check": cmd_check,
}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        args.identity = resolve_identity(args.identity)
        if args.command == "store-token":
            result = cmd_store_token(args)
        else:
            config, _ = load_config(args.identity)
            api = Api(resolve_token(args.identity, config))
            result = COMMANDS[args.command](api, config, args)
    except Failure as e:
        error = {"ok": False, "error": str(e)}
        if e.status:
            error["status"] = e.status
        if e.code:
            error["code"] = e.code
        print(json.dumps(error))
        return 1
    except Exception as e:
        # Callers parse stdout, so even a bug answers in JSON; the traceback goes to stderr.
        traceback.print_exc()
        print(json.dumps({"ok": False, "error": f"unexpected error: {e!r}"}))
        return 1
    # ASCII-only JSON, so any stdout encoding (a Windows pipe, say) can print it.
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
