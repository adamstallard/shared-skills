#!/usr/bin/env python3
"""Tests for discord_bot.py. Standard library only; no network, no keychain.

Run from the clone's root:  python3 .agents/skills/discord-bot/scripts/test_discord_bot.py
"""

import io
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_bot as d  # noqa: E402

GUILD = "100"
BOT = "900"


class FakeApi:
    """Answers Discord API paths from a table and records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, path, body=None, query=None):
        self.calls.append((method, path, body, query))
        answer = self.routes.get((method, path))
        if answer is None:
            raise AssertionError(f"unexpected call {method} {path}")
        if isinstance(answer, d.Failure):
            raise answer
        return answer(body, query) if callable(answer) else answer


def channel(cid, name, ctype=0, overwrites=None):
    return {"id": cid, "name": name, "type": ctype, "guild_id": GUILD, "permission_overwrites": overwrites or []}


def member(uid, username, nick=None, global_name=None):
    return {"user": {"id": uid, "username": username, "global_name": global_name}, "nick": nick}


def guild_routes(members=None, search=None):
    routes = {
        ("GET", "/users/@me/guilds"): [{"id": GUILD, "name": "Team"}],
        ("GET", f"/guilds/{GUILD}/channels"): [
            channel("1", "general"),
            channel("2", "agents"),
            channel("3", "voice", ctype=2),
        ],
        ("GET", f"/guilds/{GUILD}/members/search"): search
        if search is not None
        else (lambda body, query: [m for m in members or [] if m["user"]["username"].startswith(query["query"].lower())]),
    }
    return routes


def args(**kw):
    base = dict(identity="default", channel=None, thread=None, agent=None, session=None, project=None,
                message=None, limit=20, before=None, message_id=None, name=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


class Header(unittest.TestCase):
    def test_all_three_parts_in_order(self):
        self.assertEqual(d.header("Scout", "pr-review", "repo#47"), "👤 Scout  🎯 pr-review  📦 repo#47")

    def test_no_parts_means_no_header(self):
        self.assertEqual(d.header(None, None, None), "")

    def test_missing_parts_are_skipped(self):
        self.assertEqual(d.header("Scout", None, "repo"), "👤 Scout  📦 repo")


class Mentions(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi(guild_routes(members=[member("7", "adamstallard"), member("8", "adam")]))
        self.channels = {"agents": "2"}

    def convert(self, text):
        return d.convert_mentions(self.api, GUILD, text, self.channels)

    def test_shortest_matching_name_wins(self):
        text, ids, warnings = self.convert("ping @adam please")
        self.assertEqual(text, "ping <@8> please")
        self.assertEqual(ids, ["8"])
        self.assertEqual(warnings, [])

    def test_trailing_punctuation_is_not_part_of_the_name(self):
        text, _, _ = self.convert("thanks @adamstallard, done")
        self.assertEqual(text, "thanks <@7>, done")

    def test_email_address_is_left_alone(self):
        text, ids, _ = self.convert("mail adam@example.com")
        self.assertEqual(text, "mail adam@example.com")
        self.assertEqual(ids, [])

    def test_everyone_and_here_are_never_converted(self):
        text, ids, _ = self.convert("@everyone and @here")
        self.assertEqual(text, "@everyone and @here")
        self.assertEqual(ids, [])
        self.assertFalse(any("members/search" in c[1] for c in self.api.calls))

    def test_unknown_name_stays_text_with_a_warning(self):
        text, ids, warnings = self.convert("hi @nobody")
        self.assertEqual(text, "hi @nobody")
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("@nobody", warnings[0])

    def test_a_name_is_searched_once(self):
        self.convert("@adam and @adam again")
        searches = [c for c in self.api.calls if c[1].endswith("members/search")]
        self.assertEqual(len(searches), 1)

    def test_refused_search_warns_once_and_keeps_text(self):
        api = FakeApi(guild_routes(search=d.Failure("Missing Access", status=403, code=50001)))
        text, ids, warnings = d.convert_mentions(api, GUILD, "@a1 and @b2", {})
        self.assertEqual(text, "@a1 and @b2")
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)
        searches = [c for c in api.calls if c[1].endswith("members/search")]
        self.assertEqual(len(searches), 1)

    def test_other_search_failures_are_raised(self):
        api = FakeApi(guild_routes(search=d.Failure("server error", status=500)))
        with self.assertRaises(d.Failure):
            d.convert_mentions(api, GUILD, "@someone", {})

    def test_channel_name_becomes_a_link(self):
        text, _, _ = self.convert("see #agents")
        self.assertEqual(text, "see <#2>")

    def test_issue_reference_is_not_a_channel(self):
        text, _, _ = self.convert("fixed in repo#agents and #47")
        self.assertEqual(text, "fixed in repo#agents and #47")


class Channels(unittest.TestCase):
    def test_finds_text_channel_by_name(self):
        api = FakeApi(guild_routes())
        found, guild_id = d.find_channel(api, {}, "#agents")
        self.assertEqual((found["id"], guild_id), ("2", GUILD))

    def test_non_text_channel_is_not_found(self):
        api = FakeApi(guild_routes())
        with self.assertRaisesRegex(d.Failure, "no text channel #voice"):
            d.find_channel(api, {}, "voice")

    def test_numeric_name_is_fetched_as_an_id(self):
        cid = "123456789012345678"
        api = FakeApi({("GET", f"/channels/{cid}"): channel(cid, "x")})
        found, guild_id = d.find_channel(api, {}, cid)
        self.assertEqual((found["id"], guild_id), (cid, GUILD))

    def test_same_name_in_two_servers_is_ambiguous(self):
        api = FakeApi({
            ("GET", "/users/@me/guilds"): [{"id": "100", "name": "A"}, {"id": "200", "name": "B"}],
            ("GET", "/guilds/100/channels"): [channel("1", "general")],
            ("GET", "/guilds/200/channels"): [channel("5", "general")],
        })
        with self.assertRaisesRegex(d.Failure, "more than one server"):
            d.find_channel(api, {}, "general")
        found, _ = d.find_channel(api, {"server": "B"}, "general")
        self.assertEqual(found["id"], "5")

    def test_unknown_server_in_config_is_reported(self):
        api = FakeApi(guild_routes())
        with self.assertRaisesRegex(d.Failure, "not in a server"):
            d.find_channel(api, {"server": "Elsewhere"}, "general")

    def test_thread_must_be_a_thread(self):
        api = FakeApi({("GET", "/channels/2"): channel("2", "agents")})
        with self.assertRaisesRegex(d.Failure, "not a thread"):
            d.find_thread(api, "2")

    def test_missing_thread_is_not_found(self):
        api = FakeApi({("GET", "/channels/9"): d.Failure("Unknown Channel", status=404, code=10003)})
        with self.assertRaisesRegex(d.Failure, "thread 9 not found"):
            d.find_thread(api, "9")

    def test_no_channel_anywhere_is_an_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(d.Failure, "no channel given"):
                d.target(FakeApi({}), {}, args())

    def test_default_channel_comes_from_config(self):
        api = FakeApi(guild_routes())
        with mock.patch.dict(os.environ, {}, clear=True):
            found, _ = d.target(api, {"defaultChannel": "general"}, args())
        self.assertEqual(found["id"], "1")


class Post(unittest.TestCase):
    def routes(self, sent):
        routes = guild_routes(members=[member("7", "adam")])
        routes[("POST", "/channels/2/messages")] = lambda body, query: sent.append(body) or {"id": "55"}
        return routes

    def test_posts_header_and_converted_text(self):
        sent = []
        api = FakeApi(self.routes(sent))
        result = d.cmd_post(api, {}, args(channel="agents", message="hi @adam", agent="Scout", session="s", project="p"))
        self.assertEqual(sent[0]["content"], "👤 Scout  🎯 s  📦 p\nhi <@7>")
        self.assertEqual(sent[0]["allowed_mentions"], {"parse": [], "users": ["7"]})
        self.assertEqual(result["messageId"], "55")
        self.assertEqual(result["url"], f"https://discord.com/channels/{GUILD}/2/55")

    def test_without_header_fields_posts_the_text_alone(self):
        sent = []
        d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="plain"))
        self.assertEqual(sent[0]["content"], "plain")

    def test_channel_list_is_fetched_only_for_a_hash(self):
        api = FakeApi(self.routes([]))
        d.cmd_post(api, {}, args(channel="agents", message="no channels here"))
        lookups = [c for c in api.calls if c[1].endswith("/channels")]
        self.assertEqual(len(lookups), 1)  # finding --channel itself
        d.cmd_post(api, {}, args(channel="agents", message="see #general"))
        lookups = [c for c in api.calls if c[1].endswith("/channels")]
        self.assertEqual(len(lookups), 3)

    def test_too_long_is_refused_not_truncated(self):
        sent = []
        with self.assertRaisesRegex(d.Failure, "limit is 2000"):
            d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="x" * 2001))
        self.assertEqual(sent, [])

    def test_empty_message_is_refused(self):
        with self.assertRaisesRegex(d.Failure, "empty"):
            d.cmd_post(FakeApi(self.routes([])), {}, args(channel="agents", message="   "))

    def test_message_dash_reads_standard_input(self):
        sent = []
        with mock.patch.object(sys, "stdin", io.StringIO("from stdin\nline two")):
            d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="-"))
        self.assertEqual(sent[0]["content"], "from stdin\nline two")


class Edit(unittest.TestCase):
    def run_edit(self, old_content):
        sent = []
        routes = guild_routes()
        routes[("GET", "/channels/2/messages/55")] = {"id": "55", "content": old_content}
        routes[("PATCH", "/channels/2/messages/55")] = lambda body, query: sent.append(body) or {}
        d.cmd_edit(FakeApi(routes), {}, args(channel="agents", message_id="55", message="new text"))
        return sent[0]["content"]

    def test_keeps_the_original_header(self):
        self.assertEqual(self.run_edit("👤 Scout  🎯 s  📦 p\nold text"), "👤 Scout  🎯 s  📦 p\nnew text")

    def test_without_a_header_replaces_everything(self):
        self.assertEqual(self.run_edit("old text"), "new text")


class Read(unittest.TestCase):
    def test_keeps_readable_messages_and_their_threads(self):
        routes = guild_routes()
        routes[("GET", "/channels/2/messages")] = [
            {"id": "3", "type": 0, "timestamp": "t3", "author": {"username": "a"}, "content": "hi", "thread": {"id": "77"}},
            {"id": "2", "type": 7, "timestamp": "t2", "author": {"username": "b"}, "content": "joined"},
            {"id": "1", "type": 0, "timestamp": "t1", "author": {"username": "c"}, "content": "",
             "attachments": [{"url": "https://cdn/x.png"}]},
            {"id": "0", "type": 0, "timestamp": "t0", "author": {"username": "d"}, "content": " "},
        ]
        api = FakeApi(routes)
        result = d.cmd_read(api, {}, args(channel="agents", limit=10, before="9"))
        self.assertEqual([m["messageId"] for m in result["messages"]], ["3", "1"])
        self.assertEqual(result["messages"][0]["threadId"], "77")
        self.assertEqual(result["messages"][1]["attachments"], ["https://cdn/x.png"])
        self.assertEqual(api.calls[-1][3], {"limit": 10, "before": "9"})

    def test_limit_out_of_range_is_refused(self):
        with self.assertRaisesRegex(d.Failure, "between 1 and 100"):
            d.cmd_read(FakeApi(guild_routes()), {}, args(channel="agents", limit=101))


class Thread(unittest.TestCase):
    def test_existing_thread_is_a_conflict(self):
        routes = guild_routes()
        routes[("POST", "/channels/2/messages/55/threads")] = d.Failure("exists", status=400, code=160004)
        with self.assertRaises(d.Failure) as e:
            d.cmd_thread(FakeApi(routes), {}, args(channel="agents", message_id="55", name="notes"))
        self.assertEqual(e.exception.status, 409)

    def test_long_name_is_cut_to_the_limit(self):
        sent = []
        routes = guild_routes()
        routes[("POST", "/channels/2/messages/55/threads")] = lambda body, query: sent.append(body) or {"id": "77", "name": body["name"]}
        d.cmd_thread(FakeApi(routes), {}, args(channel="agents", message_id="55", name="n" * 150))
        self.assertEqual(len(sent[0]["name"]), 100)


class Permissions(unittest.TestCase):
    SEND = str(d.PERMISSIONS["sendMessages"])
    VIEW = d.PERMISSIONS["viewChannel"]

    def guild(self, everyone=0, bot_role=0, owner="1"):
        return {"id": GUILD, "owner_id": owner, "roles": [
            {"id": GUILD, "permissions": str(everyone)},
            {"id": "r1", "permissions": str(bot_role)},
        ]}

    def test_roles_add_up(self):
        perms = d.compute_permissions(self.guild(everyone=self.VIEW, bot_role=int(self.SEND)), ["r1"], BOT, [])
        self.assertTrue(perms & self.VIEW and perms & int(self.SEND))

    def test_role_overwrite_denies(self):
        overwrites = [{"id": "r1", "type": 0, "allow": "0", "deny": self.SEND}]
        perms = d.compute_permissions(self.guild(bot_role=int(self.SEND)), ["r1"], BOT, overwrites)
        self.assertFalse(perms & int(self.SEND))

    def test_member_overwrite_beats_role_overwrite(self):
        overwrites = [
            {"id": "r1", "type": 0, "allow": "0", "deny": self.SEND},
            {"id": BOT, "type": 1, "allow": self.SEND, "deny": "0"},
        ]
        perms = d.compute_permissions(self.guild(everyone=self.VIEW, bot_role=int(self.SEND)), ["r1"], BOT, overwrites)
        self.assertTrue(perms & int(self.SEND))

    def test_administrator_ignores_overwrites(self):
        overwrites = [{"id": GUILD, "type": 0, "allow": "0", "deny": self.SEND}]
        perms = d.compute_permissions(self.guild(bot_role=d.ADMINISTRATOR), ["r1"], BOT, overwrites)
        self.assertEqual(perms, d.ALL_PERMISSIONS)


class Identity(unittest.TestCase):
    def test_argument_then_environment_then_default(self):
        self.assertEqual(d.resolve_identity("reviewer", {"DISCORD_BOT_IDENTITY": "x"}), "reviewer")
        self.assertEqual(d.resolve_identity(None, {"DISCORD_BOT_IDENTITY": "x"}), "x")
        self.assertEqual(d.resolve_identity(None, {}), "default")

    def test_identity_cannot_reach_outside_the_config_folder(self):
        with self.assertRaises(d.Failure):
            d.resolve_identity("../secrets", {})

    def test_config_is_read_from_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "discord-bot"))
            with open(os.path.join(tmp, "discord-bot", "reviewer.json"), "w") as f:
                json.dump({"defaultChannel": "agents"}, f)
            config, path = d.load_config("reviewer", {"XDG_CONFIG_HOME": tmp})
        self.assertEqual(config, {"defaultChannel": "agents"})
        self.assertTrue(path.endswith("reviewer.json"))

    def test_missing_config_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(d.load_config("nobody", {"XDG_CONFIG_HOME": tmp}), ({}, None))

    def test_config_that_is_not_an_object_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "discord-bot"))
            with open(os.path.join(tmp, "discord-bot", "x.json"), "w") as f:
                f.write("[]")
            with self.assertRaisesRegex(d.Failure, "JSON object"):
                d.load_config("x", {"XDG_CONFIG_HOME": tmp})


class Token(unittest.TestCase):
    def test_environment_wins_over_keychain(self):
        read = mock.Mock(return_value="from-keychain")
        self.assertEqual(d.resolve_token("x", {}, {"DISCORD_BOT_TOKEN": "from-env"}, read), "from-env")
        read.assert_not_called()

    def test_keychain_entry_defaults_to_the_identity(self):
        read = mock.Mock(return_value="tok")
        d.resolve_token("reviewer", {}, {}, read)
        read.assert_called_once_with("discord-bot", "reviewer")

    def test_config_can_name_an_existing_keychain_entry(self):
        read = mock.Mock(return_value="tok")
        d.resolve_token("me", {"keychain": {"service": "old-bridge", "account": "bot"}}, {}, read)
        read.assert_called_once_with("old-bridge", "bot")

    def test_no_token_says_how_to_provide_one(self):
        with self.assertRaisesRegex(d.Failure, "DISCORD_BOT_TOKEN"):
            d.resolve_token("x", {}, {}, lambda s, a: None)

    def test_macos_keychain_is_preferred_and_failures_are_none(self):
        run = mock.Mock(return_value=types.SimpleNamespace(returncode=44, stdout=""))
        self.assertIsNone(d.read_keychain("s", "a", run=run, which=lambda t: t == "security"))
        self.assertEqual(run.call_args[0][0][:2], ["security", "find-generic-password"])

    def test_linux_secret_tool_is_used_without_security(self):
        run = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout="tok\n"))
        self.assertEqual(d.read_keychain("s", "a", run=run, which=lambda t: t == "secret-tool"), "tok")

    def test_no_keychain_tool_means_none(self):
        self.assertIsNone(d.read_keychain("s", "a", run=None, which=lambda t: None))


class Http(unittest.TestCase):
    def response(self, payload):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        return resp

    def http_error(self, code, payload):
        return urllib.error.HTTPError("u", code, "reason", {}, io.BytesIO(json.dumps(payload).encode()))

    def test_rate_limit_waits_and_retries(self):
        sleeps = []
        opener = mock.Mock(side_effect=[self.http_error(429, {"retry_after": 0.5}), self.response({"ok": 1})])
        api = d.Api("t", opener=opener, sleep=sleeps.append)
        self.assertEqual(api.request("GET", "/x"), {"ok": 1})
        self.assertEqual(sleeps, [0.5])

    def test_persistent_rate_limit_gives_up(self):
        opener = mock.Mock(side_effect=lambda *a, **k: (_ for _ in ()).throw(self.http_error(429, {"retry_after": 0})))
        with self.assertRaisesRegex(d.Failure, "rate limited"):
            d.Api("t", opener=opener, sleep=lambda s: None).request("GET", "/x")

    def test_discord_error_carries_status_and_code(self):
        opener = mock.Mock(side_effect=self.http_error(403, {"message": "Missing Access", "code": 50001}))
        with self.assertRaises(d.Failure) as e:
            d.Api("t", opener=opener).request("GET", "/x")
        self.assertEqual((e.exception.status, e.exception.code), (403, 50001))
        self.assertTrue(e.exception.no_access())

    def test_token_and_body_are_sent(self):
        opener = mock.Mock(return_value=self.response({}))
        d.Api("secret", opener=opener).request("POST", "/m", body={"a": 1}, query={"limit": 2})
        req = opener.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bot secret")
        self.assertEqual(req.full_url, d.API + "/m?limit=2")
        self.assertEqual(json.loads(req.data), {"a": 1})


class Main(unittest.TestCase):
    def test_failure_prints_json_and_exits_1(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tempfile.gettempdir()}, clear=True), \
                mock.patch.object(d, "read_keychain", return_value=None), redirect_stdout(out):
            code = d.main(["--identity", "nobody-here", "read", "--channel", "x"])
        self.assertEqual(code, 1)
        result = json.loads(out.getvalue())
        self.assertFalse(result["ok"])
        self.assertIn("no bot token", result["error"])


class Regressions(unittest.TestCase):
    """Bugs found by bug-hunter; each test failed before its fix."""

    def mentions(self, text, members):
        api = FakeApi(guild_routes(members=members))
        return d.convert_mentions(api, GUILD, text, {"agents": "2"}), api

    def test_network_error_after_connect_is_reported_as_json(self):
        for exc in (TimeoutError("The read operation timed out"), ConnectionResetError(54, "reset")):
            out = io.StringIO()
            api = d.Api("t", opener=mock.Mock(side_effect=exc))
            with mock.patch.object(d, "load_config", return_value=({}, None)), \
                    mock.patch.object(d, "resolve_token", return_value="t"), \
                    mock.patch.object(d, "Api", return_value=api), redirect_stdout(out):
                code = d.main(["read", "--channel", "123"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out.getvalue())["ok"])

    def test_numeric_server_in_config_is_treated_as_an_id(self):
        api = FakeApi(guild_routes())
        found, _ = d.find_channel(api, {"server": int(GUILD)}, "agents")
        self.assertEqual(found["id"], "2")

    def test_numeric_default_channel_in_config_is_treated_as_an_id(self):
        cid = 123456789012345678
        api = FakeApi({("GET", f"/channels/{cid}"): channel(str(cid), "x")})
        with mock.patch.dict(os.environ, {}, clear=True):
            found, _ = d.target(api, {"defaultChannel": cid}, args())
        self.assertEqual(found["id"], str(cid))

    def test_hyphenated_handle_is_matched_whole(self):
        (text, ids, _), api = self.mentions("ping @acme-reviewer please",
                                            [member("9", "acme"), member("10", "acme-reviewer")])
        self.assertEqual(text, "ping <@10> please")
        self.assertEqual(ids, ["10"])

    def test_sentence_ending_period_is_not_part_of_the_handle(self):
        (text, ids, warnings), _ = self.mentions("Thanks @adam.", [member("8", "adam")])
        self.assertEqual(text, "Thanks <@8>.")
        self.assertEqual(warnings, [])

    def test_code_and_urls_are_left_alone(self):
        text_in = "see https://medium.com/@adam/post and `git log --author=@adam #agents`\n```\n@adam #agents\n```"
        (text, ids, _), _ = self.mentions(text_in, [member("8", "adam")])
        self.assertEqual(text, text_in)
        self.assertEqual(ids, [])

    def test_edit_keeps_a_header_without_an_agent(self):
        sent = []
        routes = guild_routes()
        routes[("GET", "/channels/2/messages/55")] = {"id": "55", "content": "🎯 pr-review  📦 repo#47\nold text"}
        routes[("PATCH", "/channels/2/messages/55")] = lambda body, query: sent.append(body) or {}
        d.cmd_edit(FakeApi(routes), {}, args(channel="agents", message_id="55", message="new text"))
        self.assertEqual(sent[0]["content"], "🎯 pr-review  📦 repo#47\nnew text")

    def test_no_view_channel_means_no_other_channel_permission(self):
        view, send = d.PERMISSIONS["viewChannel"], d.PERMISSIONS["sendMessages"]
        guild = {"id": GUILD, "owner_id": "1", "roles": [{"id": GUILD, "permissions": str(view | send)}]}
        overwrites = [{"id": GUILD, "type": 0, "allow": "0", "deny": str(view)}]
        self.assertEqual(d.compute_permissions(guild, [], BOT, overwrites), 0)

    def test_channel_named_with_digits_is_found_by_name(self):
        routes = guild_routes()
        routes[("GET", f"/guilds/{GUILD}/channels")] = [channel("1", "general"), channel("7", "2024")]
        found, _ = d.find_channel(FakeApi(routes), {}, "2024")
        self.assertEqual(found["id"], "7")


    def test_double_backtick_code_is_left_alone(self):
        (text, ids, _), _ = self.mentions("see ``@adam`` here", [member("8", "adam")])
        self.assertEqual(text, "see ``@adam`` here")
        self.assertEqual(ids, [])

    def test_an_unmatched_backtick_does_not_hide_later_mentions(self):
        for text_in, expected in (
            ("Press the ` key, then @adam please review", "Press the ` key, then <@8> please review"),
            ("Use `` ` `` to quote; @adam please review", "Use `` ` `` to quote; <@8> please review"),
        ):
            (text, ids, _), _ = self.mentions(text_in, [member("8", "adam")])
            self.assertEqual(text, expected)
            self.assertEqual(ids, ["8"])

    def test_same_channel_name_twice_in_one_server_says_to_use_the_id(self):
        routes = guild_routes()
        routes[("GET", f"/guilds/{GUILD}/channels")] = [channel("1", "agents"), channel("2", "agents")]
        with self.assertRaisesRegex(d.Failure, "channel id"):
            d.find_channel(FakeApi(routes), {"server": GUILD}, "agents")

    def test_mention_in_underscore_emphasis_is_converted(self):
        for text_in, expected in (("_@adam_ please look", "_<@8>_ please look"),
                                  ("__@adam__ please look", "__<@8>__ please look")):
            (text, ids, _), _ = self.mentions(text_in, [member("8", "adam")])
            self.assertEqual(text, expected)
            self.assertEqual(ids, ["8"])

    def test_http_error_with_unreadable_body_keeps_its_status(self):
        fp = mock.Mock()
        fp.read.side_effect = ConnectionResetError(54, "reset")
        err = urllib.error.HTTPError("u", 503, "Service Unavailable", {}, fp)
        with self.assertRaises(d.Failure) as e:
            d.Api("t", opener=mock.Mock(side_effect=err)).request("GET", "/x")
        self.assertEqual(e.exception.status, 503)


    def test_non_ascii_name_never_pings_a_prefix_match(self):
        (text, ids, warnings), _ = self.mentions("thanks @José for the review",
                                                 [member("1", "josh"), member("2", "jose")])
        self.assertEqual(ids, [])
        self.assertEqual(text, "thanks @José for the review")
        self.assertEqual(len(warnings), 1)

    def test_underscore_emphasis_prefers_the_exact_name(self):
        (text, ids, _), _ = self.mentions("_@adam_ please look",
                                          [member("8", "adam"), member("9", "adam_smith")])
        self.assertEqual(text, "_<@8>_ please look")
        self.assertEqual(ids, ["8"])

    def test_output_is_ascii_so_any_stdout_encoding_can_print_it(self):
        routes = guild_routes()
        routes[("GET", "/channels/2/messages")] = [
            {"id": "3", "type": 0, "timestamp": "t", "author": {"username": "a"}, "content": "ship it 🚀"}]
        out = io.StringIO()
        with mock.patch.object(d, "load_config", return_value=({}, None)), \
                mock.patch.object(d, "resolve_token", return_value="t"), \
                mock.patch.object(d, "Api", return_value=FakeApi(routes)), redirect_stdout(out):
            code = d.main(["read", "--channel", "agents"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().isascii())
        self.assertEqual(json.loads(out.getvalue())["messages"][0]["content"], "ship it 🚀")

    def test_mention_after_cjk_text_is_not_silently_skipped(self):
        (text, ids, warnings), _ = self.mentions("请@adam 看看", [member("8", "adam")])
        self.assertEqual(text, "请<@8> 看看")
        self.assertEqual(ids, ["8"])

    def test_an_unknown_name_is_warned_about_once(self):
        (_, _, warnings), _ = self.mentions("@nobody and @nobody", [])
        self.assertEqual(len(warnings), 1)


    def test_a_name_shared_by_two_members_pings_neither(self):
        members = [member("8", "adam"), member("9", "bob", nick="Adam")]
        api = FakeApi(guild_routes(search=members))
        text, ids, warnings = d.convert_mentions(api, GUILD, "hi @adam", {})
        self.assertEqual(text, "hi @adam")
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)


class Check(unittest.TestCase):
    def run_check(self, search):
        routes = guild_routes(search=search)
        routes[("GET", "/users/@me")] = {"id": BOT, "username": "helper-bot"}
        routes[("GET", f"/guilds/{GUILD}")] = {"id": GUILD, "owner_id": "1", "roles": [
            {"id": GUILD, "permissions": str(d.PERMISSIONS["viewChannel"] | d.PERMISSIONS["sendMessages"])}]}
        routes[("GET", f"/guilds/{GUILD}/members/{BOT}")] = {"roles": []}
        with mock.patch.dict(os.environ, {}, clear=True):
            return d.cmd_check(FakeApi(routes), {"defaultChannel": "agents"}, args())

    def test_member_search_counts_when_the_bot_is_found(self):
        self.assertTrue(self.run_check([member(BOT, "helper-bot")])["memberSearch"])

    def test_a_search_that_returns_nobody_is_not_working(self):
        self.assertFalse(self.run_check([])["memberSearch"])

    def test_a_refused_search_is_not_working(self):
        self.assertFalse(self.run_check(d.Failure("Missing Access", status=403, code=50001))["memberSearch"])

    def test_a_crowded_name_still_counts_as_working(self):
        others = [member(str(i), f"helper-bot{i}") for i in range(100)]
        self.assertTrue(self.run_check(others)["memberSearch"])

    def test_a_search_outage_keeps_the_rest_of_the_report(self):
        result = self.run_check(d.Failure("Internal", status=500))
        self.assertIsNone(result["memberSearch"])
        self.assertIn("Internal", result["memberSearchError"])
        self.assertIn("permissions", result["defaultChannel"])

    def test_check_reports_the_default_channel_permissions(self):
        perms = self.run_check([member(BOT, "helper-bot")])["defaultChannel"]["permissions"]
        self.assertTrue(perms["viewChannel"] and perms["sendMessages"])
        self.assertFalse(perms["createPublicThreads"])


if __name__ == "__main__":
    unittest.main()
