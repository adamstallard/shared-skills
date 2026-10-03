#!/usr/bin/env python3
"""Tests for linear_app.py. Standard library only; no network, no keychain.

Run from the clone's root:  python3 .agents/skills/linear-app/scripts/test_linear_app.py
"""

import io
import json
import os
import stat
import sys
import tempfile
import types
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import linear_app as la  # noqa: E402

# The real keychain functions, kept before each test replaces them with stubs.
REAL_READ, REAL_DELETE = la.read_keychain, la.delete_keychain

DAY = 24 * 3600


def response(payload):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    return resp


def http_error(code, payload):
    return urllib.error.HTTPError("u", code, "reason", {}, io.BytesIO(json.dumps(payload).encode()))


class Env(unittest.TestCase):
    """Each test gets its own XDG folders and fake credentials."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"XDG_CONFIG_HOME": os.path.join(self.tmp.name, "config"),
                    "XDG_STATE_HOME": os.path.join(self.tmp.name, "state"),
                    "LINEAR_CLIENT_ID": "cid", "LINEAR_CLIENT_SECRET": "secret"}
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Never reach the real keychain from a test.
        for name in ("read_keychain", "write_keychain", "delete_keychain"):
            stub = mock.patch.object(la, name, return_value=None)
            stub.start()
            self.addCleanup(stub.stop)
        self.addCleanup(self.tmp.cleanup)
        self.mints = []

    def opener(self, expires_in=30 * DAY):
        def open_(req, timeout=None):
            if req.full_url == la.TOKEN_URL:
                self.mints.append(dict(x.split("=", 1) for x in req.data.decode().split("&")))
                return response({"access_token": f"tok{len(self.mints)}", "expires_in": expires_in})
            raise AssertionError(req.full_url)
        return open_

    def write_config(self, identity, config):
        os.makedirs(os.path.join(self.env["XDG_CONFIG_HOME"], "linear-app"), exist_ok=True)
        with open(os.path.join(self.env["XDG_CONFIG_HOME"], "linear-app", identity + ".json"), "w") as f:
            json.dump(config, f)


class Identity(unittest.TestCase):
    def test_argument_then_environment_then_default(self):
        self.assertEqual(la.resolve_identity("milton", {"LINEAR_APP_IDENTITY": "x"}), "milton")
        self.assertEqual(la.resolve_identity(None, {"LINEAR_APP_IDENTITY": "x"}), "x")
        self.assertEqual(la.resolve_identity(None, {}), "default")

    def test_identity_cannot_reach_outside_its_folder(self):
        with self.assertRaises(la.Failure):
            la.resolve_identity("../x", {})


class Scopes(unittest.TestCase):
    def test_default_includes_the_delegate_scopes(self):
        self.assertEqual(la.scopes_for({}), "read,write,app:assignable,app:mentionable")

    def test_order_is_kept_because_a_new_string_revokes_tokens(self):
        self.assertEqual(la.scopes_for({"scopes": "write, read"}), "write,read")
        self.assertEqual(la.scopes_for({"scopes": ["write", "read"]}), "write,read")


class Credentials(unittest.TestCase):
    def test_environment_wins(self):
        read = mock.Mock()
        self.assertEqual(la.client_credentials("default", {}, {"LINEAR_CLIENT_ID": "a", "LINEAR_CLIENT_SECRET": "b"}, read),
                         ("a", "b"))
        read.assert_not_called()

    def test_keychain_entries_are_named_by_identity(self):
        read = mock.Mock(side_effect=lambda s, a: {"milton:client-id": "a", "milton:client-secret": "b"}[a])
        self.assertEqual(la.client_credentials("milton", {}, {}, read), ("a", "b"))
        self.assertEqual({c.args[0] for c in read.call_args_list}, {"linear-app"})

    def test_config_can_point_at_existing_keychain_entries(self):
        config = {"keychain": {"service": "old", "clientIdAccount": "id", "clientSecretAccount": "sec"}}
        read = mock.Mock(side_effect=lambda s, a: {("old", "id"): "a", ("old", "sec"): "b"}[(s, a)])
        self.assertEqual(la.client_credentials("me", config, {}, read), ("a", "b"))

    def test_missing_credentials_say_how_to_provide_them(self):
        with self.assertRaisesRegex(la.Failure, "LINEAR_CLIENT_SECRET.*store-credentials"):
            la.client_credentials("x", {}, {}, lambda s, a: None)

    def test_no_keychain_tool_reads_nothing(self):
        self.assertIsNone(la.read_keychain("s", "a", run=None, which=lambda t: None))

    def test_linux_uses_secret_tool(self):
        run = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout="v\n"))
        self.assertEqual(la.read_keychain("s", "a", run=run, which=lambda t: t == "secret-tool"), "v")
        self.assertEqual(run.call_args[0][0][:2], ["secret-tool", "lookup"])


class Http(unittest.TestCase):
    def test_mint_sends_client_credentials_and_scopes(self):
        opener = mock.Mock(return_value=response({"access_token": "t", "expires_in": 100}))
        self.assertEqual(la.mint("cid", "sec", "read,write", opener), ("t", 100))
        req = opener.call_args[0][0]
        self.assertEqual(req.full_url, la.TOKEN_URL)
        sent = dict(x.split("=", 1) for x in req.data.decode().split("&"))
        self.assertEqual(sent["grant_type"], "client_credentials")
        self.assertEqual(sent["scope"], "read%2Cwrite")

    def test_mint_without_a_token_is_an_error(self):
        with self.assertRaisesRegex(la.Failure, "no access token"):
            la.mint("c", "s", "read", mock.Mock(return_value=response({})))

    def test_oauth_error_is_reported_with_its_description(self):
        opener = mock.Mock(side_effect=http_error(401, {"error": "invalid_client", "error_description": "bad secret"}))
        with self.assertRaisesRegex(la.Failure, "401: bad secret"):
            la.mint("c", "s", "read", opener)

    def test_error_body_that_is_not_json_still_reports_the_status(self):
        err = urllib.error.HTTPError("u", 503, "Unavailable", {}, io.BytesIO(b"<html>"))
        with self.assertRaisesRegex(la.Failure, "503"):
            la.post("https://example.test", b"", {}, mock.Mock(side_effect=err))

    def test_connection_errors_are_reported(self):
        for exc in (urllib.error.URLError("dns"), TimeoutError("read timed out"), ConnectionResetError(54, "reset")):
            with self.assertRaisesRegex(la.Failure, "cannot reach Linear"):
                la.post("https://example.test", b"", {}, mock.Mock(side_effect=exc))

    def test_graphql_errors_are_reported(self):
        opener = mock.Mock(return_value=response({"errors": [{"message": "nope"}]}))
        with self.assertRaisesRegex(la.Failure, "nope"):
            la.graphql("t", "{ viewer { id } }", opener)


class Cache(Env):
    def token(self, identity="default", config=None, now=1000.0, expires_in=30 * DAY):
        return la.current_token(identity, config or {}, now=now, opener=self.opener(expires_in))

    def test_a_fresh_token_is_reused(self):
        self.assertEqual(self.token()[0], "tok1")
        self.assertEqual(self.token(now=1000 + 20 * DAY)[0], "tok1")
        self.assertEqual(len(self.mints), 1)

    def test_a_token_near_expiry_is_replaced(self):
        self.token()
        self.assertEqual(self.token(now=1000 + 26 * DAY)[0], "tok2")

    def test_changed_scopes_mint_a_new_token(self):
        self.token()
        self.token(config={"scopes": "read"})
        self.assertEqual(len(self.mints), 2)
        self.assertEqual(self.mints[1]["scope"], "read")

    def test_a_different_app_mints_a_new_token(self):
        self.token()
        os.environ["LINEAR_CLIENT_ID"] = "other"
        self.token()
        self.assertEqual(len(self.mints), 2)

    def test_identities_have_separate_tokens(self):
        os.environ["LINEAR_APP_IDENTITY"] = "a"
        self.token("a")
        os.environ["LINEAR_APP_IDENTITY"] = "b"
        self.token("b")
        self.assertEqual(len(self.mints), 2)

    def test_cache_file_is_private(self):
        self.token()
        path = la.cache_path("default")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_a_token_minted_while_waiting_for_the_lock_is_used(self):
        path = la.cache_path("default")
        real_read = la.read_cache
        calls = []

        def read(p):
            calls.append(p)
            if len(calls) == 2:  # the re-read under the lock sees another process's token
                return {"token": "theirs", "scopes": la.DEFAULT_SCOPES,
                        "credential": la.fingerprint("cid", "secret", la.DEFAULT_SCOPES),
                        "expiresAt": 1000 + 30 * DAY}
            return real_read(p)

        with mock.patch.object(la, "read_cache", side_effect=read):
            token, _ = self.token()
        self.assertEqual(token, "theirs")
        self.assertEqual(self.mints, [])
        self.assertEqual(calls, [path, path])

    def test_unreadable_cache_is_treated_as_empty(self):
        os.makedirs(os.path.dirname(la.cache_path("default")), exist_ok=True)
        with open(la.cache_path("default"), "w") as f:
            f.write("not json")
        self.assertEqual(self.token()[0], "tok1")


class Commands(Env):
    def run_main(self, argv, token="tok", data=None):
        cached = {"token": token, "scopes": la.DEFAULT_SCOPES, "expiresAt": 10 ** 12}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(la, "current_token", return_value=(token, cached)), \
                mock.patch.object(la, "graphql", return_value=data or {}), \
                redirect_stdout(out), redirect_stderr(err):
            code = la.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_token_prints_only_the_token(self):
        self.assertEqual(self.run_main(["token"])[:2], (0, "tok\n"))

    def test_headers_prints_an_authorization_header(self):
        code, out, _ = self.run_main(["headers"])
        self.assertEqual(json.loads(out), {"Authorization": "Bearer tok"})

    def test_raw_command_failure_goes_to_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(la, "current_token", side_effect=la.Failure("no client credentials")), \
                redirect_stdout(out), redirect_stderr(err):
            code = la.main(["token"])
        self.assertEqual((code, out.getvalue()), (1, ""))
        self.assertIn("no client credentials", err.getvalue())

    def test_check_reports_identity_workspace_and_delegate_ability(self):
        data = {"viewer": {"id": "u", "name": "agent-bot"}, "organization": {"name": "Acme", "urlKey": "acme"}}
        code, out, _ = self.run_main(["check"], data=data)
        result = json.loads(out)
        self.assertEqual((code, result["user"], result["workspace"]["urlKey"]), (0, "agent-bot", "acme"))
        self.assertTrue(result["canBeDelegate"])

    def test_check_refuses_the_wrong_workspace(self):
        self.write_config("default", {"workspace": "other"})
        data = {"viewer": {"name": "bot"}, "organization": {"name": "Acme", "urlKey": "acme"}}
        code, out, _ = self.run_main(["check"], data=data)
        self.assertEqual(code, 1)
        self.assertIn("expects 'other'", json.loads(out)["error"])

    def test_unexpected_error_still_answers_in_json(self):
        out = io.StringIO()
        with mock.patch.object(la, "cmd_check", side_effect=KeyError("x")), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = la.main(["check"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.getvalue())["ok"])


class Wire(Env):
    def args(self, project=None):
        return types.SimpleNamespace(identity="milton", project=project, name="linear")

    def wire(self, project=None, add_rc=0):
        calls = []

        def run(cmd, cwd=None, **kw):
            calls.append((cmd, cwd))
            return types.SimpleNamespace(returncode=add_rc if cmd[2] == "add-json" else 0, stdout="", stderr="boom")

        with mock.patch.object(la, "current_token", return_value=("t", {})):
            result = la.cmd_wire(self.args(project), {}, run=run, which=lambda t: "/bin/claude")
        return result, calls

    def test_user_scope_uses_a_headers_helper_not_the_token(self):
        result, calls = self.wire()
        add = calls[-1][0]
        self.assertEqual(add[:5], ["claude", "mcp", "add-json", "--scope", "user"])
        server = json.loads(add[-1])
        self.assertEqual(server["url"], la.MCP_URL)
        self.assertNotIn("headers", server)
        self.assertIn("--identity milton headers", server["headersHelper"])
        self.assertTrue(result["restartNeeded"])

    def test_project_scope_runs_in_that_folder(self):
        result, calls = self.wire(project=self.tmp.name)
        self.assertEqual(calls[-1][0][4], "local")
        self.assertEqual(calls[-1][1], os.path.abspath(self.tmp.name))

    def test_missing_project_folder_is_refused(self):
        with self.assertRaisesRegex(la.Failure, "not a folder"):
            self.wire(project=os.path.join(self.tmp.name, "nope"))

    def test_add_failure_is_reported(self):
        with self.assertRaisesRegex(la.Failure, "boom"):
            self.wire(add_rc=1)

    def test_without_claude_wiring_is_refused(self):
        with self.assertRaisesRegex(la.Failure, "not on PATH"):
            la.cmd_wire(self.args(), {}, run=None, which=lambda t: None)

    def test_helper_command_quotes_paths_with_spaces(self):
        cmd = la.helper_command("me", script="/a b/linear_app.py", python="/usr/bin/python3")
        self.assertEqual(cmd, "/usr/bin/python3 '/a b/linear_app.py' --identity me headers")


class Forget(Env):
    def test_forget_removes_the_cached_token(self):
        la.current_token("default", {}, now=1000.0, opener=self.opener())
        with mock.patch.object(la, "delete_keychain") as delete:
            la.cmd_forget(types.SimpleNamespace(identity="default"), {})
        self.assertFalse(os.path.exists(la.cache_path("default")))
        self.assertEqual(delete.call_count, 2)


class Regressions(Env):
    """Bugs found by bug-hunter; each test failed before its fix."""

    def test_a_new_secret_mints_a_new_token(self):
        la.current_token("default", {}, now=1000.0, opener=self.opener())
        os.environ["LINEAR_CLIENT_SECRET"] = "rotated"
        token, _ = la.current_token("default", {}, now=1000.0, opener=self.opener())
        self.assertEqual(token, "tok2")

    def test_wire_keeps_the_old_server_when_the_new_one_cannot_be_added(self):
        calls = []

        def run(cmd, cwd=None, **kw):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=1 if cmd[2] == "add-json" else 0, stdout="", stderr="unknown option")

        args = types.SimpleNamespace(identity="default", project=None, name="linear")
        with mock.patch.object(la, "current_token", return_value=("t", {})):
            with self.assertRaises(la.Failure):
                la.cmd_wire(args, {}, run=run, which=lambda t: "/bin/claude")
        self.assertNotIn(["claude", "mcp", "remove", "--scope", "user", "linear"], calls)

    def test_environment_credentials_belong_only_to_their_identity(self):
        env = {"LINEAR_APP_IDENTITY": "reviewer", "LINEAR_CLIENT_ID": "cid-r", "LINEAR_CLIENT_SECRET": "sec-r"}
        read = lambda s, a: {"acme:client-id": "cid-a", "acme:client-secret": "sec-a"}.get(a)
        self.assertEqual(la.client_credentials("acme", {}, env, read), ("cid-a", "sec-a"))
        self.assertEqual(la.client_credentials("reviewer", {}, env, read), ("cid-r", "sec-r"))

    def test_half_the_credentials_in_the_environment_is_an_error(self):
        read = lambda s, a: "from-keychain"
        with self.assertRaisesRegex(la.Failure, "both"):
            la.client_credentials("default", {}, {"LINEAR_CLIENT_ID": "cid"}, read)

    def test_store_credentials_prints_only_json(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=lambda prompt="": (sys.stdout.write(prompt), "cid")[1]), \
                mock.patch.object(la.getpass, "getpass", return_value="sec"), \
                mock.patch.object(la, "write_keychain"), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = la.main(["store-credentials"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])

    def test_empty_or_malformed_scopes_are_refused(self):
        for bad in (None, "", [], " , "):
            with self.assertRaises(la.Failure, msg=repr(bad)):
                la.scopes_for({"scopes": bad})

    def test_a_short_lived_token_is_still_reused(self):
        la.current_token("default", {}, now=1000.0, opener=self.opener(expires_in=3 * DAY))
        token, _ = la.current_token("default", {}, now=1000.0 + 3600, opener=self.opener(expires_in=3 * DAY))
        self.assertEqual(token, "tok1")


    def test_check_replaces_a_token_linear_has_revoked(self):
        minted = iter([("tok1", 30 * DAY), ("tok2", 30 * DAY)])
        with mock.patch.object(la, "mint", side_effect=lambda *a, **k: next(minted)) as mint:
            la.current_token("default", {})
            real_graphql = la.graphql

            def graphql(token, query, opener=None):
                if token == "tok1":
                    return real_graphql(token, query, mock.Mock(side_effect=http_error(
                        401, {"errors": [{"message": "Authentication required"}]})))
                return {"viewer": {"name": "bot"}, "organization": {"name": "A", "urlKey": "a"}}

            out = io.StringIO()
            with mock.patch.object(la, "graphql", side_effect=graphql), redirect_stdout(out), \
                    redirect_stderr(io.StringIO()):
                code = la.main(["check"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(mint.call_count, 2)
        self.assertEqual(la.read_cache(la.cache_path("default"))["token"], "tok2")

    def test_env_credentials_for_another_identity_are_named_in_the_error(self):
        with self.assertRaisesRegex(la.Failure, "LINEAR_APP_IDENTITY"):
            la.client_credentials("svc", {}, {"LINEAR_CLIENT_ID": "x", "LINEAR_CLIENT_SECRET": "y"},
                                  lambda s, a: None)

    def test_forget_leaves_keychain_entries_it_does_not_own(self):
        config = {"keychain": {"service": "aura-linear-agent", "clientIdAccount": "linear-client-id",
                               "clientSecretAccount": "linear-client-secret"}}
        with mock.patch.object(la, "delete_keychain") as delete:
            la.cmd_forget(types.SimpleNamespace(identity="default"), config)
        delete.assert_not_called()

    def test_store_credentials_without_a_terminal_says_so(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=EOFError), redirect_stdout(out), \
                redirect_stderr(io.StringIO()):
            code = la.main(["store-credentials"])
        self.assertEqual(code, 1)
        self.assertIn("terminal", json.loads(out.getvalue())["error"])


    def test_store_credentials_warns_when_the_environment_overrides_it(self):
        out = io.StringIO()
        with mock.patch("builtins.input", return_value="cid"), \
                mock.patch.object(la.getpass, "getpass", return_value="new-secret"), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = la.main(["store-credentials"])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("LINEAR_CLIENT_SECRET", " ".join(result.get("warnings", [])))

    def test_check_reuses_a_token_another_process_already_replaced(self):
        minted = iter([("tok1", 30 * DAY), ("tok2", 30 * DAY), ("tok3", 30 * DAY)])
        with mock.patch.object(la, "mint", side_effect=lambda *a, **k: next(minted)) as mint:
            la.current_token("default", {})
            real_graphql = la.graphql

            def graphql(token, query, opener=None):
                if token == "tok1":
                    # Another session already saw tok1 refused and replaced it with tok2.
                    la.current_token("default", {}, refused="tok1")
                    return real_graphql(token, query, mock.Mock(side_effect=http_error(
                        401, {"errors": [{"message": "Authentication required"}]})))
                return {"viewer": {"name": "bot"}, "organization": {"name": "A", "urlKey": "a"}}

            out = io.StringIO()
            with mock.patch.object(la, "graphql", side_effect=graphql), redirect_stdout(out), \
                    redirect_stderr(io.StringIO()):
                code = la.main(["check"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(mint.call_count, 2)
        self.assertEqual(la.read_cache(la.cache_path("default"))["token"], "tok2")

    def test_forget_says_the_environment_still_holds_credentials(self):
        result = la.cmd_forget(types.SimpleNamespace(identity="default"), {})
        warning = " ".join(result["warnings"])
        self.assertIn("still", warning)
        self.assertNotIn("take effect", warning)


    def test_forget_with_half_a_pair_does_not_claim_the_identity_works(self):
        os.environ.pop("LINEAR_CLIENT_SECRET")
        result = la.cmd_forget(types.SimpleNamespace(identity="default"), {})
        self.assertNotIn("keeps working", " ".join(result.get("warnings", [])))

    def test_forget_with_kept_keychain_entries_does_not_say_unsetting_stops_it(self):
        config = {"keychain": {"service": "other"}}
        la.read_keychain.return_value = "kept"
        result = la.cmd_forget(types.SimpleNamespace(identity="default"), config)
        self.assertIn("keptKeychain", result)
        self.assertNotIn("until they are unset", " ".join(result.get("warnings", [])))


    def test_forget_warns_when_its_own_entries_could_not_be_deleted(self):
        os.environ.pop("LINEAR_CLIENT_ID")
        os.environ.pop("LINEAR_CLIENT_SECRET")
        la.read_keychain.return_value = "still-there"  # the delete silently did nothing
        result = la.cmd_forget(types.SimpleNamespace(identity="default"), {})
        self.assertIn("warnings", result)

    def test_forget_with_half_a_pair_names_the_kept_entries_that_take_over(self):
        os.environ.pop("LINEAR_CLIENT_SECRET")
        la.read_keychain.return_value = "kept"
        result = la.cmd_forget(types.SimpleNamespace(identity="default"), {"keychain": {"service": "x"}})
        self.assertIn("'x'", " ".join(result.get("warnings", [])))


    def test_the_keychain_stub_reaches_credential_lookup(self):
        os.environ.pop("LINEAR_CLIENT_ID")
        os.environ.pop("LINEAR_CLIENT_SECRET")
        la.read_keychain.return_value = "from-stub"
        self.assertEqual(la.client_credentials("default", {}), ("from-stub", "from-stub"))


class ForgetAgainstAKeychain(Env):
    """forget run against a fake `security`, through the real keychain functions."""

    def keychain(self, entries, locked=False, undeletable=()):
        store = dict(entries)

        def run(cmd, capture_output=True, text=False, input=None):
            account = cmd[cmd.index("-a") + 1]
            key = (cmd[cmd.index("-s") + 1], account)
            if locked:
                return types.SimpleNamespace(returncode=36, stdout="", stderr="User interaction is not allowed.")
            if key not in store:
                return types.SimpleNamespace(returncode=44, stdout="", stderr="could not be found")
            if cmd[1] == "delete-generic-password":
                if account in undeletable:
                    return types.SimpleNamespace(returncode=1, stdout="", stderr="denied")
                del store[key]
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            return types.SimpleNamespace(returncode=0, stdout=store[key] + "\n", stderr="")

        which = lambda tool: tool == "security"
        la.read_keychain.side_effect = lambda s, a: REAL_READ(s, a, run=run, which=which)
        la.delete_keychain.side_effect = lambda s, a: REAL_DELETE(s, a, run=run, which=which)
        return store

    def forget(self, identity, config):
        os.environ.pop("LINEAR_CLIENT_ID")
        os.environ.pop("LINEAR_CLIENT_SECRET")
        return la.cmd_forget(types.SimpleNamespace(identity=identity), config)

    def test_a_locked_keychain_is_not_reported_as_a_clean_forget(self):
        self.keychain({("linear-app", "default:client-id"): "cid",
                       ("linear-app", "default:client-secret"): "sek"}, locked=True)
        result = self.forget("default", {})
        self.assertIn("warnings", result)

    def test_a_secret_that_survives_the_delete_is_named(self):
        store = self.keychain({("linear-app", "default:client-id"): "cid",
                               ("linear-app", "default:client-secret"): "sek"},
                              undeletable=("default:client-secret",))
        result = self.forget("default", {})
        self.assertIn(("linear-app", "default:client-secret"), store)
        self.assertIn("default:client-secret", " ".join(result.get("warnings", [])))

    def test_nothing_stored_on_linux_is_a_clean_forget(self):
        # `secret-tool clear` exits 1, printing nothing, when no item matches.
        quiet_miss = lambda cmd, capture_output=True, text=False, input=None: types.SimpleNamespace(
            returncode=1, stdout="", stderr="")
        which = lambda tool: tool == "secret-tool"
        la.read_keychain.side_effect = lambda s, a: REAL_READ(s, a, run=quiet_miss, which=which)
        la.delete_keychain.side_effect = lambda s, a: REAL_DELETE(s, a, run=quiet_miss, which=which)
        self.assertNotIn("warnings", self.forget("default", {}))

    def test_an_unreadable_keychain_is_not_said_to_keep_working(self):
        self.keychain({("linear-app", "default:client-id"): "cid",
                       ("linear-app", "default:client-secret"): "sek"}, locked=True)
        warnings = " ".join(self.forget("default", {})["warnings"])
        self.assertNotIn("keeps working", warnings)

    def test_no_secret_service_on_a_server_is_a_clean_forget(self):
        no_service = lambda cmd, capture_output=True, text=False, input=None: types.SimpleNamespace(
            returncode=1, stdout=b"", stderr=b"secret-tool: Cannot autolaunch D-Bus without X11 $DISPLAY\n")
        which = lambda tool: tool == "secret-tool"
        la.read_keychain.side_effect = lambda s, a: REAL_READ(s, a, run=no_service, which=which)
        la.delete_keychain.side_effect = lambda s, a: REAL_DELETE(s, a, run=no_service, which=which)
        self.assertNotIn("warnings", self.forget("default", {}))


if __name__ == "__main__":
    unittest.main()
