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
                message=None, limit=20, before=None, message_id=None, name=None, reply_to=None)
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


class ReplyTo(unittest.TestCase):
    MSG = "123456789012345678"

    def routes(self, sent, target=None):
        routes = guild_routes(members=[member("7", "adam")])
        routes[("GET", f"/channels/2/messages/{self.MSG}")] = target if target is not None else {"id": self.MSG}
        routes[("POST", "/channels/2/messages")] = lambda body, query: sent.append(body) or {"id": "55"}
        return routes

    def test_reply_references_the_message_in_this_channel(self):
        sent = []
        result = d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="agreed", reply_to=self.MSG))
        self.assertEqual(sent[0]["message_reference"],
                         {"message_id": self.MSG, "channel_id": "2", "fail_if_not_exists": True})
        self.assertEqual(result["replyTo"], self.MSG)

    def test_reply_does_not_ping_the_author_unless_mentioned(self):
        sent = []
        d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="agreed", reply_to=self.MSG))
        self.assertEqual(sent[0]["allowed_mentions"], {"parse": [], "users": [], "replied_user": False})
        d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="@adam agreed", reply_to=self.MSG))
        self.assertEqual(sent[1]["allowed_mentions"], {"parse": [], "users": ["7"], "replied_user": False})
        self.assertEqual(sent[1]["content"], "<@7> agreed")

    def test_a_message_elsewhere_or_deleted_fails_before_posting(self):
        sent = []
        missing = d.Failure("Unknown Message", status=404, code=10008)
        with self.assertRaisesRegex(d.Failure, "not in this channel or thread, or was deleted") as e:
            d.cmd_post(FakeApi(self.routes(sent, missing)), {}, args(channel="agents", message="hi", reply_to=self.MSG))
        self.assertEqual(sent, [])
        self.assertEqual(e.exception.status, 404)

    def test_other_lookup_failures_are_raised_as_they_are(self):
        outage = d.Failure("Internal", status=500)
        with self.assertRaisesRegex(d.Failure, "^Internal$"):
            d.cmd_post(FakeApi(self.routes([], outage)), {}, args(channel="agents", message="hi", reply_to=self.MSG))

    def test_reply_to_must_be_a_message_id(self):
        sent = []
        with self.assertRaisesRegex(d.Failure, "message id"):
            d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="hi", reply_to="../55"))
        self.assertEqual(sent, [])

    def test_reply_to_in_non_ascii_digits_is_not_a_message_id(self):
        for digits in ("\uff11" * 18, "\u0661" * 18):
            with self.assertRaisesRegex(d.Failure, "message id"):
                d.cmd_post(FakeApi(self.routes([])), {}, args(channel="agents", message="hi", reply_to=digits))

    def test_a_reply_refused_at_posting_says_so(self):
        routes = self.routes([])
        routes[("POST", "/channels/2/messages")] = d.Failure("Invalid Form Body", status=400, code=50035)
        with self.assertRaisesRegex(d.Failure, "refused the reply"):
            d.cmd_post(FakeApi(routes), {}, args(channel="agents", message="hi", reply_to=self.MSG))

    def test_a_reply_in_a_thread_references_the_thread(self):
        sent = []
        routes = {("GET", "/channels/77"): channel("77", "notes", ctype=11),
                  ("GET", f"/channels/77/messages/{self.MSG}"): {"id": self.MSG},
                  ("POST", "/channels/77/messages"): lambda body, query: sent.append(body) or {"id": "56"}}
        d.cmd_post(FakeApi(routes), {}, args(thread="77", message="done", reply_to=self.MSG))
        self.assertEqual(sent[0]["message_reference"]["channel_id"], "77")

    def test_without_reply_to_nothing_changes(self):
        sent = []
        result = d.cmd_post(FakeApi(self.routes(sent)), {}, args(channel="agents", message="hi"))
        self.assertNotIn("message_reference", sent[0])
        self.assertEqual(sent[0]["allowed_mentions"], {"parse": [], "users": []})
        self.assertNotIn("replyTo", result)

    def test_the_command_line_takes_reply_to(self):
        self.assertEqual(d.parser().parse_args(["post", "--message", "x", "--reply-to", self.MSG]).reply_to, self.MSG)


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
        self.assertEqual(d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN": "from-env"}, read), "from-env")
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


class EnvironmentToken(unittest.TestCase):
    """The environment's token belongs to DISCORD_BOT_IDENTITY's bot only (DECISIONS.md)."""

    def token_file(self, content):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "token")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_another_identity_ignores_the_environment_token(self):
        read = mock.Mock(return_value="reviewer-token")
        env = {"DISCORD_BOT_TOKEN": "acme-token", "DISCORD_BOT_IDENTITY": "acme"}
        self.assertEqual(d.resolve_token("reviewer", {}, env, read), "reviewer-token")
        read.assert_called_once_with("discord-bot", "reviewer")

    def test_another_identity_ignores_the_default_identitys_token(self):
        read = mock.Mock(return_value="reviewer-token")
        self.assertEqual(d.resolve_token("reviewer", {}, {"DISCORD_BOT_TOKEN": "default-token"}, read),
                         "reviewer-token")

    def test_the_environment_token_applies_to_discord_bot_identity(self):
        read = mock.Mock(return_value="from-keychain")
        env = {"DISCORD_BOT_TOKEN": "acme-token", "DISCORD_BOT_IDENTITY": "acme"}
        self.assertEqual(d.resolve_token("acme", {}, env, read), "acme-token")
        read.assert_not_called()

    def test_the_environment_token_applies_to_default_when_no_identity_is_named(self):
        read = mock.Mock(return_value="from-keychain")
        self.assertEqual(d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN": "t"}, read), "t")
        read.assert_not_called()

    def test_a_borrowed_token_is_refused_with_the_reason(self):
        env = {"DISCORD_BOT_TOKEN": "acme-token", "DISCORD_BOT_IDENTITY": "acme"}
        with self.assertRaisesRegex(d.Failure, "belongs to identity 'acme'.*never lent"):
            d.resolve_token("reviewer", {}, env, lambda s, a: None)

    def test_the_advice_puts_identity_before_the_command(self):
        with self.assertRaisesRegex(d.Failure, "--identity x store-token"):
            d.resolve_token("x", {}, {}, lambda s, a: None)
        self.assertEqual(d.parser().parse_args(["--identity", "x", "store-token"]).command, "store-token")

    def test_token_file_is_read_and_stripped(self):
        path = self.token_file("  file-token\n\n")
        read = mock.Mock()
        self.assertEqual(d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": path}, read), "file-token")
        read.assert_not_called()

    def test_token_file_belongs_to_one_identity_too(self):
        path = self.token_file("acme-token\n")
        read = mock.Mock(return_value="reviewer-token")
        env = {"DISCORD_BOT_TOKEN_FILE": path, "DISCORD_BOT_IDENTITY": "acme"}
        self.assertEqual(d.resolve_token("acme", {}, env, read), "acme-token")
        self.assertEqual(d.resolve_token("reviewer", {}, env, read), "reviewer-token")

    def test_a_missing_token_file_fails_without_falling_back(self):
        read = mock.Mock(return_value="from-keychain")
        env = {"DISCORD_BOT_TOKEN_FILE": os.path.join(tempfile.gettempdir(), "no-such-discord-token")}
        with self.assertRaisesRegex(d.Failure, "cannot read DISCORD_BOT_TOKEN_FILE"):
            d.resolve_token("default", {}, env, read)
        read.assert_not_called()

    def test_an_unreadable_token_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(d.Failure, "cannot read DISCORD_BOT_TOKEN_FILE"):
                d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": tmp}, lambda s, a: "k")

    def test_an_empty_token_file_fails(self):
        with self.assertRaisesRegex(d.Failure, "is empty"):
            d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": self.token_file(" \n")}, lambda s, a: "k")

    def test_a_token_file_with_more_than_the_token_fails(self):
        path = self.token_file("DISCORD_BOT_TOKEN=a\nother=b\n")
        with self.assertRaisesRegex(d.Failure, "only the token"):
            d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": path}, lambda s, a: "k")

    def test_a_binary_token_file_fails(self):
        path = self.token_file("")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
        with self.assertRaisesRegex(d.Failure, "not a text file"):
            d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": path}, lambda s, a: "k")

    def test_both_token_variables_are_refused(self):
        env = {"DISCORD_BOT_TOKEN": "a", "DISCORD_BOT_TOKEN_FILE": self.token_file("b")}
        with self.assertRaisesRegex(d.Failure, "not both"):
            d.resolve_token("default", {}, env, lambda s, a: "k")

    def test_blank_variables_count_as_unset(self):
        env = {"DISCORD_BOT_TOKEN": "  ", "DISCORD_BOT_TOKEN_FILE": ""}
        self.assertEqual(d.resolve_token("default", {}, env, lambda s, a: "k"), "k")


    def test_a_byte_order_mark_is_not_part_of_the_token(self):
        path = self.token_file("\ufeffabc.def\n")
        self.assertEqual(d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN_FILE": path}, lambda s, a: "k"), "abc.def")

    def test_a_non_ascii_token_fails_without_echoing_it(self):
        path = self.token_file("abc\u200bsecret\n")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tempfile.gettempdir(),
                                          "DISCORD_BOT_TOKEN_FILE": path}, clear=True), \
                mock.patch.object(d, "read_keychain", return_value=None), \
                mock.patch.object(sys, "stderr", io.StringIO()), redirect_stdout(out):
            code = d.main(["read", "--channel", "x"])
        self.assertEqual(code, 1)
        self.assertNotIn("secret", out.getvalue())
        self.assertNotIn("unexpected", out.getvalue())

    def test_an_inline_token_with_a_line_break_fails_without_echoing_it(self):
        with self.assertRaises(d.Failure) as e:
            d.resolve_token("default", {}, {"DISCORD_BOT_TOKEN": "abc\nsecret"}, lambda s, a: "k")
        self.assertNotIn("secret", str(e.exception))

    def test_advice_for_another_identity_names_discord_bot_identity(self):
        with self.assertRaisesRegex(d.Failure, "DISCORD_BOT_IDENTITY=reviewer"):
            d.resolve_token("reviewer", {}, {}, lambda s, a: None)

class StoreToken(unittest.TestCase):
    def store(self, identity, env):
        run = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stderr=""))
        args = types.SimpleNamespace(identity=identity)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(d.getpass, "getpass", return_value="tok"):
            result = d.cmd_store_token(args, {"XDG_CONFIG_HOME": tmp, **env}, run=run,
                                       which=lambda t: t == "secret-tool")
        self.assertEqual(run.call_args[0][0][:2], ["secret-tool", "store"])
        return result

    def test_warns_when_the_environment_token_overrides_this_identity(self):
        result = self.store("acme", {"DISCORD_BOT_TOKEN": "t", "DISCORD_BOT_IDENTITY": "acme"})
        self.assertIn("overrides the stored token", result["warnings"][0])
        self.assertIn("DISCORD_BOT_TOKEN", result["warnings"][0])

    def test_warns_for_default_and_a_token_file(self):
        result = self.store("default", {"DISCORD_BOT_TOKEN_FILE": "/x"})
        self.assertIn("DISCORD_BOT_TOKEN_FILE", result["warnings"][0])

    def test_no_warning_for_another_identity(self):
        result = self.store("reviewer", {"DISCORD_BOT_TOKEN": "t", "DISCORD_BOT_IDENTITY": "acme"})
        self.assertNotIn("warnings", result)

    def test_no_warning_without_an_environment_token(self):
        self.assertNotIn("warnings", self.store("acme", {}))

    def test_no_keychain_tool_advice_names_the_identity(self):
        args = types.SimpleNamespace(identity="reviewer")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(d.getpass, "getpass", return_value="tok"), \
                self.assertRaisesRegex(d.Failure, "DISCORD_BOT_IDENTITY=reviewer"):
            d.cmd_store_token(args, {"XDG_CONFIG_HOME": tmp}, run=None, which=lambda t: None)


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


    def by_any_name(self, members):
        """A member search that, like Discord's, matches the start of any of a member's names."""
        def search(body, query):
            q = query["query"].lower()
            return [m for m in members if any(n and n.lower().startswith(q) for n in
                                              (m["user"]["username"], m["user"]["global_name"], m["nick"]))]
        return FakeApi(guild_routes(search=search))

    def test_decomposed_accent_does_not_cut_the_name(self):
        api = self.by_any_name([member("1", "jose"), member("2", "x", nick="Jos\u00e9")])
        text, ids, warnings = d.convert_mentions(api, GUILD, "@Jose\u0301 hi", {})
        self.assertEqual(ids, ["2"])

    def test_a_longer_name_the_text_spells_out_is_not_cut_short(self):
        for text_in, longer in (("@Adam Smith please review", member("2", "x", global_name="Adam Smith")),
                                ("@Jo'Anne hi", member("2", "x", nick="Jo'Anne")),
                                ("@Jo\U0001f3b8 hi", member("2", "x", nick="Jo\U0001f3b8"))):
            short = member("1", text_in[1:3].lower() if text_in.startswith("@Jo") else "adam")
            api = self.by_any_name([short, longer])
            text, ids, warnings = d.convert_mentions(api, GUILD, text_in, {})
            self.assertEqual(ids, [], text_in)
            self.assertEqual(text, text_in)
            self.assertEqual(len(warnings), 1)

    def test_a_possessive_still_pings(self):
        (text, ids, _), _ = self.mentions("@adam's review", [member("8", "adam")])
        self.assertEqual(text, "<@8>'s review")

    def test_a_name_longer_than_discord_allows_is_not_cut_to_a_member(self):
        name = "a" * 16 + "b" * 16
        (text, ids, warnings), _ = self.mentions(f"@{name}cdefghij is a token", [member("1", name)])
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)

    def test_a_full_page_of_search_results_pings_nobody(self):
        crowd = [member(str(100 + i), f"jo{i:03}") for i in range(d.MEMBER_SEARCH_LIMIT - 1)]
        api = FakeApi(guild_routes(search=[member("1", "jo")] + crowd))
        text, ids, warnings = d.convert_mentions(api, GUILD, "@jo hi", {})
        self.assertEqual(ids, [])
        self.assertEqual(len(warnings), 1)

    def test_escaped_mentions_are_left_alone(self):
        (text, ids, _), _ = self.mentions(r"use \@adam, see \#agents", [member("8", "adam")])
        self.assertEqual(text, r"use \@adam, see \#agents")
        self.assertEqual(ids, [])

    def test_a_hash_right_after_a_mention_is_not_a_channel(self):
        (text, _, _), _ = self.mentions("@adam#agents", [member("8", "adam")])
        self.assertEqual(text, "<@8>#agents")

    def test_the_ambiguity_warning_names_the_ambiguous_name(self):
        api = FakeApi(guild_routes(search=[member("1", "adam."), member("2", "x", nick="adam.")]))
        _, _, warnings = d.convert_mentions(api, GUILD, "@adam. hi", {})
        self.assertEqual(warnings, ["several members are named @adam.; left as plain text"])

    def test_one_name_in_two_cases_is_searched_and_warned_about_once(self):
        api = FakeApi(guild_routes(members=[]))
        _, _, warnings = d.convert_mentions(api, GUILD, "@Bob and @bob", {})
        self.assertEqual(len(warnings), 1)
        self.assertEqual(len([c for c in api.calls if c[1].endswith("members/search")]), 1)

    def test_a_link_without_a_scheme_is_not_a_mention(self):
        for text_in in ("see youtube.com/@adam for that", "my post at medium.com/@adam/why-x"):
            (text, ids, _), _ = self.mentions(text_in, [member("8", "adam")])
            self.assertEqual((text, ids), (text_in, []))

    def test_an_email_address_with_punctuation_before_the_at_is_not_a_mention(self):
        (text, ids, _), _ = self.mentions("mail adam_@gmail.com", [member("1", "gmail.com")])
        self.assertEqual((text, ids), ("mail adam_@gmail.com", []))

    def test_a_package_scope_is_not_a_mention(self):
        (text, ids, _), _ = self.mentions("install @types/node first", [member("1", "types")])
        self.assertEqual((text, ids), ("install @types/node first", []))

    def test_a_dotted_capital_i_does_not_veto_its_own_member(self):
        api = self.by_any_name([member("1", "izzy_t", nick="\u0130zzy")])
        text, ids, warnings = d.convert_mentions(api, GUILD, "thanks @\u0130zzy", {})
        self.assertEqual((text, ids, warnings), ("thanks <@1>", ["1"], []))

    def test_text_without_a_mention_keeps_its_exact_characters(self):
        text_in = "\u212b and \uf900 and \u2126, @Jose\u0301 hi"
        api = self.by_any_name([member("2", "x", nick="Jos\u00e9")])
        text, ids, _ = d.convert_mentions(api, GUILD, text_in, {})
        self.assertEqual(text, "\u212b and \uf900 and \u2126, <@2> hi")
        self.assertEqual(ids, ["2"])

    def test_an_email_address_ending_in_an_accented_letter_is_not_a_mention(self):
        (text, ids, warnings), _ = self.mentions("mail jos\u00e9@adam or zo\u00eb@gmail.com", [member("1", "adam")])
        self.assertEqual((text, ids, warnings), ("mail jos\u00e9@adam or zo\u00eb@gmail.com", [], []))

    def test_a_mention_after_halfwidth_katakana_still_pings(self):
        (text, ids, _), _ = self.mentions("\uff71@adam \u898b\u3066", [member("8", "adam")])
        self.assertEqual((text, ids), ("\uff71<@8> \u898b\u3066", ["8"]))

    def test_a_one_letter_name_is_too_short_however_its_accent_is_typed(self):
        api = self.by_any_name([member("1", "\u00e9")])
        text, ids, _ = d.convert_mentions(api, GUILD, "hi @e\u0301 there", {})
        self.assertEqual((text, ids), ("hi @e\u0301 there", []))

    def test_a_mention_after_thai_or_another_unspaced_script_still_pings(self):
        for before in ("\u0e02\u0e2d\u0e1a\u0e04\u0e38\u0e13", "\u0eaa\u0eb0\u0e9a\u0eb2\u0e8d\u0e94\u0eb5",
                       "\u179f\u17bd\u179f\u17d2\u178f\u17b8", "\u1019\u1004\u103a\u1039\u1002\u101c\u102c\u1015\u102b"):
            (text, ids, _), _ = self.mentions(before + "@adam hi", [member("8", "adam")])
            self.assertEqual((text, ids), (before + "<@8> hi", ["8"]), ascii(before))

    def test_a_dotted_capital_i_alone_is_too_short(self):
        api = self.by_any_name([member("4", "zz", nick="\u0130")])
        text, ids, _ = d.convert_mentions(api, GUILD, "@\u0130. hi", {})
        self.assertEqual((text, ids), ("@\u0130. hi", []))

    def test_an_email_address_ending_in_a_persian_digit_is_not_a_mention(self):
        (text, ids, warnings), _ = self.mentions("\u06f1\u06f2\u06f3@gmail.com", [member("5", "gmail.com")])
        self.assertEqual((text, ids, warnings), ("\u06f1\u06f2\u06f3@gmail.com", [], []))

    def test_an_email_address_ending_in_a_non_ascii_digit_is_not_a_mention(self):
        (text, ids, warnings), _ = self.mentions("\u0661\u0662\u0663@gmail.com", [member("5", "gmail.com")])
        self.assertEqual((text, ids, warnings), ("\u0661\u0662\u0663@gmail.com", [], []))

    def test_a_mention_after_a_fullwidth_or_thai_digit_still_pings(self):
        for before in ("\u8cea\u554f\uff11", "\u0e02\u0e2d\u0e1a\u0e04\u0e38\u0e13\u0e51"):
            (text, ids, _), _ = self.mentions(before + "@adam hi", [member("8", "adam")])
            self.assertEqual((text, ids), (before + "<@8> hi", ["8"]), ascii(before))

    def test_everyone_or_here_with_a_tail_never_pings(self):
        for text_in in ("Hey @everyone. ready?", "_@here_ please"):
            api = FakeApi(guild_routes(search=[member("2", "x", nick="everyone."), member("3", "here_")]))
            text, ids, _ = d.convert_mentions(api, GUILD, text_in, {})
            self.assertEqual((text, ids), (text_in, []), text_in)


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
