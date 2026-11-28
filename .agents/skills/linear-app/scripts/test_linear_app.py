#!/usr/bin/env python3
"""Tests for linear_app.py. Standard library only; no network, no keychain.

Run from the clone's root:  python3 .agents/skills/linear-app/scripts/test_linear_app.py
"""

import io
import json
import os
import shlex
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
REAL_READ, REAL_DELETE, REAL_WRITE = la.read_keychain, la.delete_keychain, la.write_keychain

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
                    # check reads ~/.claude.json: never the person's own.
                    "HOME": self.tmp.name,
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


class WriteKeychainOnMacOS(unittest.TestCase):
    """write_keychain against a fake `security`: the value goes on standard input and is read back."""

    def write(self, readback="s3cret\n", add_rc=0, find_rc=0, add_stderr=""):
        def run(cmd, **kwargs):
            if cmd[1] == "add-generic-password":
                return types.SimpleNamespace(returncode=add_rc, stdout="", stderr=add_stderr)
            return types.SimpleNamespace(returncode=find_rc, stdout=readback, stderr="not found")
        run = mock.Mock(side_effect=run)
        try:
            result = la.write_keychain("linear-app", "acme:client-secret", "s3cret", "Linear client secret (acme)",
                                       run=run, which=lambda t: t == "security")
        except la.Failure as e:
            result = e
        return result, run.call_args_list

    def test_security_gets_the_value_twice_on_standard_input_never_as_an_argument(self):
        result, calls = self.write()
        self.assertIsNone(result)
        add = calls[0]
        self.assertEqual(add.args[0],
                         ["security", "add-generic-password", "-U", "-s", "linear-app", "-a", "acme:client-secret", "-w"])
        self.assertEqual(add.kwargs["input"], "s3cret\ns3cret\n")
        for call in calls:
            self.assertNotIn("s3cret", " ".join(call.args[0]))

    def test_security_runs_with_no_terminal_to_prompt_on(self):
        # With a controlling terminal, `security` prompts there and ignores standard input.
        _, calls = self.write()
        self.assertIs(calls[0].kwargs.get("start_new_session"), True)

    def test_the_stored_value_is_read_back(self):
        _, calls = self.write()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[0],
                         ["security", "find-generic-password", "-s", "linear-app", "-a", "acme:client-secret", "-w"])

    def test_an_empty_read_back_fails(self):
        # `security` exits 0 after storing an empty password when the second copy is missing.
        result, _ = self.write(readback="\n")
        self.assertIsInstance(result, la.Failure)
        self.assertIn("does not hold the value entered", str(result))

    def test_a_different_read_back_fails_without_echoing_either_value(self):
        result, _ = self.write(readback="other-secret\n")
        self.assertIsInstance(result, la.Failure)
        self.assertNotIn("s3cret", str(result))
        self.assertNotIn("other-secret", str(result))

    def test_a_failed_read_back_fails(self):
        result, _ = self.write(find_rc=44)
        self.assertIsInstance(result, la.Failure)
        self.assertIn("could not read back", str(result))
        self.assertNotIn("s3cret", str(result))

    def test_a_failed_store_skips_the_read_back_and_drops_the_prompts(self):
        result, calls = self.write(
            add_rc=1, add_stderr="password data for new item: retype password for new item: security: denied\n")
        self.assertIsInstance(result, la.Failure)
        self.assertEqual(str(result), "storing acme:client-secret failed: security: denied")
        self.assertEqual(len(calls), 1)

    def test_store_credentials_stores_both_values_this_way(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd[1] == "add-generic-password":
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            return types.SimpleNamespace(returncode=0, stdout={"acme:client-id": "cid", "acme:client-secret": "sec"}[
                cmd[cmd.index("-a") + 1]] + "\n", stderr="")
        real = la.write_keychain
        write = lambda s, a, v, label: real(s, a, v, label, run=run, which=lambda t: t == "security")
        with mock.patch("builtins.input", return_value="cid"), mock.patch.object(la.getpass, "getpass", return_value="sec"), \
                mock.patch.object(la, "write_keychain", side_effect=write), \
                mock.patch.object(la, "env_overrides_keychain", return_value=False), redirect_stderr(io.StringIO()):
            result = la.cmd_store_credentials(types.SimpleNamespace(identity="acme"), {})
        self.assertTrue(result["stored"])
        adds = [(cmd, kw) for cmd, kw in calls if cmd[1] == "add-generic-password"]
        self.assertEqual([kw["input"] for _, kw in adds], ["cid\ncid\n", "sec\nsec\n"])
        for cmd, _ in calls:
            self.assertNotIn("sec", cmd[cmd.index("-a") + 2:])
            self.assertNotIn("cid", cmd[cmd.index("-a") + 2:])


class Http(unittest.TestCase):
    def test_mint_sends_client_credentials_and_scopes(self):
        opener = mock.Mock(return_value=response({"access_token": "t", "expires_in": 100}))
        self.assertEqual(la.mint("cid", "sec", "read,write", opener), ("t", 100, None))
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
        self.assertEqual(self.token(now=1000 + 14 * DAY)[0], "tok1")
        self.assertEqual(len(self.mints), 1)

    def test_a_token_past_half_its_life_is_replaced(self):
        self.token()
        self.assertEqual(self.token(now=1000 + 16 * DAY)[0], "tok2")

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
                        "renewAt": 1000 + 15 * DAY, "expiresAt": 1000 + 30 * DAY}
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

    def test_the_helper_names_the_installed_skill_when_it_leads_here(self):
        installed = os.path.join(self.tmp.name, ".claude", "skills", "linear-app")
        os.makedirs(os.path.dirname(installed))
        os.symlink(os.path.dirname(os.path.dirname(os.path.abspath(la.__file__))), installed)
        self.assertEqual(la.stable_script(home=self.tmp.name),
                         os.path.join(installed, "scripts", os.path.basename(la.__file__)))

    def test_the_helper_names_the_file_itself_when_no_skill_is_installed(self):
        self.assertEqual(la.stable_script(home=self.tmp.name), os.path.abspath(la.__file__))

    def test_check_warns_when_the_wired_helper_can_no_longer_run(self):
        gone = os.path.join(self.tmp.name, "python@3.14", "bin", "python3.14")
        helper = la.helper_command("default", script=os.path.abspath(la.__file__), python=gone)
        claude = {"mcpServers": {"linear": {"type": "http", "headersHelper": helper}},
                  "projects": {"/p": {"mcpServers": {"other": {"headersHelper": "echo hi"}}}}}
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump(claude, f)
        warnings = la.stale_helpers("default")
        self.assertEqual(len(warnings), 1)
        self.assertIn(gone, warnings[0])
        self.assertEqual(la.stale_helpers("someone-else"), [])

    def test_check_reads_the_config_claude_code_uses_when_claude_config_dir_is_set(self):
        gone = os.path.join(self.tmp.name, "gone", "python3")
        helper = la.helper_command("default", script=os.path.abspath(la.__file__), python=gone)
        config = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(config)
        with open(os.path.join(config, ".claude.json"), "w") as f:
            json.dump({"mcpServers": {"linear": {"headersHelper": helper}}}, f)
        os.environ["CLAUDE_CONFIG_DIR"] = config
        self.assertEqual(len(la.stale_helpers("default")), 1)

    def test_the_warning_names_the_server_and_project_to_rewire(self):
        project = os.path.join(self.tmp.name, "proj")
        os.makedirs(project)
        gone = os.path.join(self.tmp.name, "gone", "python3.13")
        helper = la.helper_command("acme", script=os.path.abspath(la.__file__), python=gone)
        claude = {"mcpServers": {"linear-acme": {"headersHelper": helper}},
                  "projects": {project: {"mcpServers": {"linear": {"headersHelper": helper}}}}}
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump(claude, f)
        warnings = " | ".join(la.stale_helpers("acme"))
        self.assertIn("--name linear-acme", warnings)
        self.assertIn(f"--project {project}", warnings)

    def test_a_server_in_a_deleted_project_folder_is_not_warned_about(self):
        gone = os.path.join(self.tmp.name, "gone", "python3.13")
        helper = la.helper_command("acme", script=os.path.abspath(la.__file__), python=gone)
        claude = {"projects": {os.path.join(self.tmp.name, "deleted-worktree"):
                               {"mcpServers": {"linear": {"headersHelper": helper}}}}}
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump(claude, f)
        self.assertEqual(la.stale_helpers("acme"), [])

    def test_a_malformed_claude_json_never_breaks_check(self):
        for text in ("null", "[]", '{"projects": [1, 2]}', '{"mcpServers": "x"}'):
            with self.subTest(text):
                with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
                    f.write(text)
                self.assertEqual(la.stale_helpers("acme"), [])

    def test_a_hand_written_helper_using_path_and_tilde_is_not_flagged(self):
        script = os.path.join(self.tmp.name, ".agents", "skills", "linear-app", "scripts", "linear_app.py")
        os.makedirs(os.path.dirname(script))
        with open(script, "w") as f:
            f.write("")
        os.makedirs(os.path.join(self.tmp.name, "bin"))
        os.symlink(sys.executable, os.path.join(self.tmp.name, "bin", "python3"))
        os.environ["PATH"] = os.path.join(self.tmp.name, "bin")
        helper = "python3 ~/.agents/skills/linear-app/scripts/linear_app.py --identity acme headers"
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump({"mcpServers": {"linear": {"headersHelper": helper}}}, f)
        self.assertEqual(la.stale_helpers("acme"), [])

    def test_the_suggested_command_can_be_pasted_into_a_shell(self):
        project = os.path.join(self.tmp.name, "my proj")
        os.makedirs(project)
        gone = os.path.join(self.tmp.name, "gone", "python3.13")
        helper = la.helper_command("acme", script=os.path.abspath(la.__file__), python=gone)
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump({"projects": {project: {"mcpServers": {"it's linear": {"headersHelper": helper}}}}}, f)
        [warning] = la.stale_helpers("acme")
        self.assertIn("; run: ", warning)
        words = shlex.split(warning.split("; run: ", 1)[1])
        self.assertTrue(words[1].endswith("linear_app.py"), words)
        self.assertEqual(words[words.index("--name") + 1], "it's linear")
        self.assertEqual(words[words.index("--project") + 1], project)

    def test_a_working_helper_gets_no_warning(self):
        helper = la.helper_command("default", script=os.path.abspath(la.__file__), python=sys.executable)
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump({"mcpServers": {"linear": {"headersHelper": helper}}}, f)
        self.assertEqual(la.stale_helpers("default"), [])


class Forget(Env):
    def test_forget_removes_the_cached_token(self):
        la.current_token("default", {}, now=1000.0, opener=self.opener())
        with mock.patch.object(la, "delete_keychain") as delete:
            la.cmd_forget(types.SimpleNamespace(identity="default"), {})
        self.assertFalse(os.path.exists(la.cache_path("default")))
        self.assertEqual(delete.call_count, 3)
        self.assertEqual(delete.call_args_list[-1].args, ("linear-app", "default:token"))


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
        minted = iter([("tok1", 30 * DAY, None), ("tok2", 30 * DAY, None)])
        with mock.patch.object(la, "mint", side_effect=lambda *a, **k: next(minted)) as mint:
            la.current_token("default", {})
            real_graphql = la.graphql

            def graphql(token, query, opener=None, variables=None):
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
        # Only linear-app's own cached-token entry is deleted, never the other tool's.
        self.assertEqual([c.args for c in delete.call_args_list], [("linear-app", "default:token")])

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
        minted = iter([("tok1", 30 * DAY, None), ("tok2", 30 * DAY, None), ("tok3", 30 * DAY, None)])
        with mock.patch.object(la, "mint", side_effect=lambda *a, **k: next(minted)) as mint:
            la.current_token("default", {})
            real_graphql = la.graphql

            def graphql(token, query, opener=None, variables=None):
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


# --- relay identities, post, edit and delete (linear-app spec) -----------------------

REAL_POST = la.post
RELAY_KEYCHAIN = {("linear-app", "answers-bot:client-id"): "relay-cid",
                  ("linear-app", "answers-bot:client-secret"): "relay-sec"}


class FakeLinear:
    """Linear's token endpoint and GraphQL API, holding comments in memory."""

    def __init__(self):
        self.mints = 0
        self.requests = []  # (token, payload) of each GraphQL request
        self.comments = {}
        self.revoked = set()
        self.revoke_every_token = False
        self.refusal = None  # (status, body) for every mutation
        self.teams = ["ENG"]
        self.team_pages = None  # lists of keys, served one per request
        self.teams_after = []  # the `after` of each teams request
        self.teams_refused = False
        self.scope = "read write"

    def __call__(self, req, timeout=None):
        if req.full_url == la.TOKEN_URL:
            self.mints += 1
            return response({"access_token": f"tok{self.mints}", "expires_in": 30 * DAY, "scope": self.scope})
        token = req.get_header("Authorization")[len("Bearer "):]
        payload = json.loads(req.data)
        self.requests.append((token, payload))
        if self.revoke_every_token or token in self.revoked:
            raise http_error(401, {"errors": [{"message": "Authentication required"}]})
        query, variables = payload["query"], payload.get("variables") or {}
        if self.refusal and query.startswith("mutation"):
            raise http_error(*self.refusal)
        if "viewer" in query:
            return response({"data": {"viewer": {"id": "user-1", "name": "answers-bot"},
                                      "organization": {"name": "Acme", "urlKey": "acme"}}})
        if "teams" in query:
            if self.teams_refused:
                raise http_error(400, {"errors": [{"message": "Forbidden"}]})
            self.teams_after.append(variables.get("after"))
            pages = self.team_pages or [self.teams]
            index = int(variables["after"][1:]) if variables.get("after") else 0
            return response({"data": {"teams": {"nodes": [{"key": k} for k in pages[index]], "pageInfo": {
                "hasNextPage": index + 1 < len(pages), "endCursor": f"p{index + 1}"}}}})
        if "commentCreate" in query:
            comment_id = f"c{len(self.comments) + 1}"
            self.comments[comment_id] = dict(variables["input"])
            return response({"data": {"commentCreate": {"success": True, "comment": {
                "id": comment_id, "url": f"https://linear.app/acme/issue/x#comment-{comment_id}"}}}})
        if "commentUpdate" in query:
            self.comments[variables["id"]]["body"] = variables["input"]["body"]
            return response({"data": {"commentUpdate": {"success": True, "comment": {
                "id": variables["id"], "url": f"https://linear.app/acme/issue/x#comment-{variables['id']}"}}}})
        if "commentDelete" in query:
            del self.comments[variables["id"]]
            return response({"data": {"commentDelete": {"success": True}}})
        raise AssertionError(query)

    def mutations(self):
        return [p for _, p in self.requests if p["query"].startswith("mutation")]


class RelayEnv(Env):
    """A fake keychain, a fake Linear, and an inquisitor.json naming answers-bot as the Linear relay."""

    def setUp(self):
        super().setUp()
        self.keychain = dict(RELAY_KEYCHAIN)
        la.read_keychain.side_effect = lambda s, a, *rest: self.keychain.get((s, a))
        la.write_keychain.side_effect = lambda s, a, v, label, *rest: self.keychain.__setitem__((s, a), v)
        la.delete_keychain.side_effect = lambda s, a, *rest: self.keychain.pop((s, a), None) is not None or True
        self.tool = "security"
        tool = mock.patch.object(la, "keychain_tool", side_effect=lambda which=None: self.tool)
        tool.start()
        self.addCleanup(tool.stop)
        self.linear = FakeLinear()
        net = mock.patch.object(la, "post", side_effect=lambda url, data, headers, opener=None:
                                REAL_POST(url, data, headers, self.linear))
        net.start()
        self.addCleanup(net.stop)
        self.write_inquisitor({"answer_service": {"linear": {"relay": "answers-bot"}}})
        self.body = os.path.join(self.tmp.name, "c.md")
        self.write_body("User says: yes")

    def write_inquisitor(self, config, raw=None):
        folder = os.path.join(self.tmp.name, ".config", "shared-skills")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "inquisitor.json"), "w") as f:
            f.write(raw if raw is not None else json.dumps(config))

    def write_body(self, text):
        with open(self.body, "w", encoding="utf-8") as f:
            f.write(text)

    def run_main(self, argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            code = la.main(argv)
        return code, out.getvalue(), err.getvalue()

    def relay(self, identity, config=None):
        return la.relay_status(identity, config or {})

    def state_files(self):
        folder = os.path.join(self.env["XDG_STATE_HOME"], "linear-app")
        found = {}
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                found[name] = f.read()
        return found


class RelayIdentities(RelayEnv):
    def test_the_named_identity_is_a_relay_identity(self):
        # @scenario linear-app: The identity the configuration names is a relay identity
        self.assertTrue(self.relay("answers-bot").relay)

    def test_without_a_linear_relay_no_identity_is_one(self):
        # @scenario linear-app: Without a Linear relay no identity is one
        for config in ({}, {"answer_service": {}}, {"answer_service": {"linear": {}}}):
            with self.subTest(config):
                self.write_inquisitor(config)
                self.assertFalse(self.relay("answers-bot").relay)
        os.remove(la.inquisitor_config_path())
        self.assertFalse(self.relay("answers-bot").relay)

    def test_an_unreadable_configuration_makes_every_identity_a_relay(self):
        # @scenario linear-app: An unreadable configuration refuses token commands for every identity
        self.write_inquisitor(None, raw="not json")
        code, out, err = self.run_main(["--identity", "worker", "token"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("inquisitor.json", err)
        # The environment's credentials are ignored for `default`, too.
        code, out, _ = self.run_main(["post", "--issue", "ENG-5", "--body-file", self.body])
        self.assertEqual(code, 1)
        self.assertIn("no client credentials", json.loads(out)["error"])
        self.assertEqual(self.linear.mints, 0)
        # And a token the state folder held for `worker` is deleted.
        la.write_cache(la.cache_path("worker"), {"token": "old"})
        self.run_main(["--identity", "worker", "check"])
        self.assertFalse(os.path.exists(la.cache_path("worker")))

    def test_a_relay_that_is_not_a_string_makes_every_identity_a_relay(self):
        self.write_inquisitor({"answer_service": {"linear": {"relay": 5}}})
        self.assertIn("not a string", self.relay("worker").why)

    def test_an_identity_holding_the_relays_client_id_is_a_relay_identity(self):
        # @scenario linear-app: Another identity with the relay's client ID is a relay identity
        self.write_config("worker", {"keychain": {"clientIdAccount": "answers-bot:client-id",
                                                  "clientSecretAccount": "answers-bot:client-secret"}})
        code, out, err = self.run_main(["--identity", "worker", "token"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("client ID of the Linear relay", err)
        os.environ["LINEAR_CLIENT_ID"] = "relay-cid"
        code, out, err = self.run_main(["token"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("'default'", err)
        os.environ["LINEAR_CLIENT_ID"] = "cid"
        del self.keychain[("linear-app", "answers-bot:client-id")]
        code, out, err = self.run_main(["--identity", "other", "token"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no client ID for the Linear relay 'answers-bot'", err)
        self.assertEqual(self.linear.mints, 0)

    def test_token_and_headers_refuse_a_relay_identity(self):
        # @scenario linear-app: token and headers refuse a relay identity
        for command in ("token", "headers"):
            with self.subTest(command):
                code, out, err = self.run_main(["--identity", "answers-bot", command])
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                for word in ("post", "edit", "delete"):
                    self.assertIn(word, err)
        self.assertEqual(self.linear.mints, 0)

    def test_other_identities_keep_token_and_headers(self):
        # @scenario linear-app: Other identities keep token and headers
        self.assertEqual(self.run_main(["token"])[:2], (0, "tok1\n"))
        code, out, _ = self.run_main(["headers"])
        self.assertEqual((code, json.loads(out)), (0, {"Authorization": "Bearer tok1"}))

    def test_wire_refuses_a_relay_identity(self):
        # @scenario linear-app: wire refuses a relay identity
        run = mock.Mock()
        args = types.SimpleNamespace(identity="answers-bot", project=None, name="linear",
                                     relay=self.relay("answers-bot"))
        with self.assertRaisesRegex(la.Failure, "post, edit and delete.*no MCP server was changed"):
            la.cmd_wire(args, {}, run=run, which=lambda t: "/bin/claude")
        run.assert_not_called()
        code, out, _ = self.run_main(["--identity", "answers-bot", "wire"])
        self.assertEqual(code, 1)
        self.assertIn("post, edit and delete", json.loads(out)["error"])

    def test_check_warns_of_a_server_wired_to_a_relay_identity(self):
        # @scenario linear-app: check warns of a server wired to a relay identity
        helper = la.helper_command("answers-bot", script=os.path.abspath(la.__file__), python=sys.executable)
        with open(os.path.join(self.tmp.name, ".claude.json"), "w") as f:
            json.dump({"mcpServers": {"linear": {"type": "http", "headersHelper": helper}}}, f)
        code, out, _ = self.run_main(["--identity", "answers-bot", "check"])
        warnings = " | ".join(json.loads(out)["warnings"])
        self.assertEqual(code, 0)
        self.assertIn("'linear' MCP server", warnings)
        self.assertIn("relay identity 'answers-bot', whose headers refuses", warnings)

    def test_a_relay_identity_ignores_credentials_in_the_environment(self):
        # @scenario linear-app: A relay identity ignores credentials in the environment
        self.keychain.clear()
        os.environ["LINEAR_APP_IDENTITY"] = "answers-bot"
        code, out, _ = self.run_main(["post", "--issue", "ENG-5", "--body-file", self.body])
        self.assertEqual(code, 1)
        self.assertIn("no client credentials", json.loads(out)["error"])
        # A relay identity is never told to use the environment it ignores.
        self.assertNotIn("set LINEAR_CLIENT_ID", json.loads(out)["error"])
        self.assertEqual(self.linear.mints, 0)

    def test_a_host_with_no_keychain_tool_refuses_a_relay_identity(self):
        # @scenario linear-app: A host with no keychain tool refuses a relay identity
        self.tool = None
        self.keychain.clear()  # nothing can be read without a tool
        for argv in (["--identity", "answers-bot", "post", "--issue", "ENG-5", "--body-file", self.body],
                     ["post", "--issue", "ENG-5", "--body-file", self.body]):
            with self.subTest(argv):
                code, out, _ = self.run_main(argv)
                error = json.loads(out)["error"]
                self.assertEqual(code, 1)
                self.assertIn("'security'", error)
                self.assertIn("'secret-tool'", error)
        self.assertEqual(self.linear.mints, 0)
        self.assertNotIn("tok", "".join(self.state_files().values()))
        code, out, _ = self.run_main(["--identity", "answers-bot", "forget"])
        self.assertEqual((code, json.loads(out)["forgotten"]), (0, True))


class RelayTokenCache(RelayEnv):
    def test_a_relay_identitys_token_is_cached_in_the_keychain(self):
        # @scenario linear-app: A relay identity's token is cached in the keychain
        self.assertEqual(self.run_main(["--identity", "answers-bot", "post", "--issue", "ENG-5",
                                        "--body-file", self.body])[0], 0)
        self.write_body("User says: no")
        self.assertEqual(self.run_main(["--identity", "answers-bot", "edit", "--comment", "c1",
                                        "--body-file", self.body])[0], 0)
        cached = json.loads(self.keychain[("linear-app", "answers-bot:token")])
        self.assertEqual(cached["token"], "tok1")
        self.assertEqual(self.linear.mints, 1)
        self.assertEqual([t for t, _ in self.linear.requests], ["tok1", "tok1"])
        self.assertNotIn("tok1", "".join(self.state_files().values()))

    def test_the_keychain_cache_ignores_the_configs_credential_service(self):
        self.keychain[("old", "id")] = "relay-cid"
        self.keychain[("old", "sec")] = "relay-sec"
        self.write_config("answers-bot", {"keychain": {"service": "old", "clientIdAccount": "id",
                                                       "clientSecretAccount": "sec"}})
        self.run_main(["--identity", "answers-bot", "post", "--issue", "ENG-5", "--body-file", self.body])
        self.assertIn(("linear-app", "answers-bot:token"), self.keychain)

    def test_a_token_cached_before_the_identity_became_a_relay_is_deleted(self):
        # @scenario linear-app: A token cached before the identity became a relay identity is deleted
        la.write_cache(la.cache_path("answers-bot"), {"token": "old"})
        self.run_main(["--identity", "answers-bot", "check"])
        self.assertFalse(os.path.exists(la.cache_path("answers-bot")))

    def test_forget_deletes_a_relay_identitys_cached_token(self):
        # @scenario linear-app: forget deletes a relay identity's cached token
        self.run_main(["--identity", "answers-bot", "check"])
        self.assertIn(("linear-app", "answers-bot:token"), self.keychain)
        self.assertEqual(self.run_main(["--identity", "answers-bot", "forget"])[0], 0)
        self.assertNotIn(("linear-app", "answers-bot:token"), self.keychain)


class PostEditDelete(RelayEnv):
    def post(self, *extra, identity="answers-bot"):
        return self.run_main(["--identity", identity, "post", "--issue", "ENG-5", "--body-file", self.body, *extra])

    def test_a_post_prints_the_comments_id_and_url(self):
        # @scenario linear-app: A post prints the comment's id and URL
        code, out, _ = self.post()
        result = json.loads(out)
        self.assertEqual((code, result["ok"], result["id"]), (0, True, "c1"))
        self.assertIn("comment-c1", result["url"])
        self.assertEqual(self.linear.comments["c1"], {"issueId": "ENG-5", "body": "User says: yes"})
        self.assertNotIn("tok1", out)

    def test_a_reply_goes_into_its_comments_thread(self):
        # @scenario linear-app: A reply goes into its comment's thread
        self.assertEqual(self.post("--parent", "c9")[0], 0)
        self.assertEqual(self.linear.comments["c1"]["parentId"], "c9")

    def test_edit_and_delete_change_the_identitys_own_comment(self):
        # @scenario linear-app: edit and delete change the identity's own comment
        self.post()
        self.write_body("User says: no")
        code, out, _ = self.run_main(["--identity", "answers-bot", "edit", "--comment", "c1",
                                      "--body-file", self.body])
        result = json.loads(out)
        self.assertEqual((code, result["id"], len(self.linear.comments)), (0, "c1", 1))
        self.assertIn("comment-c1", result["url"])
        self.assertEqual(self.linear.comments["c1"]["body"], "User says: no")
        code, out, _ = self.run_main(["--identity", "answers-bot", "delete", "--comment", "c1"])
        self.assertEqual((code, json.loads(out)), (0, {"ok": True, "identity": "answers-bot", "id": "c1"}))
        self.assertEqual(self.linear.comments, {})

    def test_post_edit_and_delete_work_for_any_identity(self):
        code, out, _ = self.post(identity="default")
        self.assertEqual((code, json.loads(out)["id"]), (0, "c1"))

    def test_a_revoked_token_is_replaced_once(self):
        # @scenario linear-app: A revoked token is replaced once
        self.run_main(["--identity", "answers-bot", "check"])
        self.linear.revoked.add("tok1")
        self.assertEqual(self.post()[0], 0)
        self.assertEqual(self.linear.mints, 2)
        self.assertEqual(len(self.linear.mutations()), 2)  # the refused try and the one post
        self.assertEqual(len(self.linear.comments), 1)
        self.linear.revoke_every_token = True
        code, out, _ = self.post()
        result = json.loads(out)
        self.assertEqual((code, result["ok"], result["status"]), (1, False, 401))
        self.assertEqual(self.linear.mints, 3)

    def test_a_refusal_for_lack_of_permission_is_passed_on(self):
        # @scenario linear-app: A refusal for lack of permission is passed on
        errors = [{"message": "Forbidden", "extensions": {"code": "FORBIDDEN", "userPresentableMessage":
                                                          "You don't have access to this team"}}]
        self.linear.refusal = (403, {"errors": errors})
        code, out, _ = self.post()
        result = json.loads(out)
        self.assertEqual((code, result["ok"], result["status"], result["errors"]), (1, False, 403, errors))
        self.assertNotIn("tok1", out)

    def test_text_on_stdin_or_an_abbreviated_option_is_refused(self):
        # @scenario linear-app: Text on standard input or an abbreviated option is refused
        other = os.path.join(self.tmp.name, "b.md")
        with open(other, "w") as f:
            f.write("User says: no")
        base = ["--identity", "answers-bot", "post", "--issue", "ENG-5"]
        for extra in ([], ["--body-file", "/dev/stdin"], ["--body-file", "-"], ["--body", self.body],
                      ["--body-file", self.body, "--body-file", other], ["--body-f=" + self.body]):
            with self.subTest(extra):
                code, out, _ = self.run_main(base + extra, stdin="User says: yes")
                self.assertEqual(code, 1)
                self.assertIn("--body-file", json.loads(out)["error"])
        self.assertEqual(self.linear.mutations(), [])

    def test_text_cannot_change_the_request(self):
        # @scenario linear-app: Text cannot change the request
        text = '"}) { id } } mutation {\n$(rm -rf ~)\n`whoami`'
        self.write_body(text)
        self.assertEqual(self.post()[0], 0)
        self.assertEqual(self.linear.comments["c1"]["body"], text)
        self.assertEqual(self.linear.mutations()[0]["query"], la.COMMENT_CREATE)


class CheckReportsWhatLinearGrants(RelayEnv):
    def test_check_prints_the_user_id_scopes_and_teams(self):
        # @scenario linear-app: check prints the user id, scopes and teams
        code, out, _ = self.run_main(["--identity", "answers-bot", "check"])
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((result["user"], result["userId"]), ("answers-bot", "user-1"))
        self.assertTrue({"read", "write"} <= set(result["grantedScopes"]))
        self.assertEqual(result["visibleTeams"], ["ENG"])
        self.assertNotIn("tok1", out)
        la.delete_keychain("linear-app", "answers-bot:token")
        self.linear.teams_refused = True
        code, out, _ = self.run_main(["--identity", "answers-bot", "check"])
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertNotIn("visibleTeams", result)
        self.assertIn("could not read the teams", result["visibleTeamsError"])

    def test_teams_listed_in_the_config_are_not_visible_teams(self):
        # @scenario linear-app: Teams listed in the config are not visible teams
        self.write_config("default", {"teams": ["OPS"]})
        code, out, _ = self.run_main(["check"])
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertNotIn("OPS", result["visibleTeams"])
        self.assertEqual(result["teams"], ["OPS"])


class RelayRegressions(RelayEnv):
    """Bugs found by bug-hunter in the relay rules; each test failed before its fix."""

    def test_body_file_naming_standard_input_is_refused_when_stdin_is_a_file(self):
        # A redirect or a zsh heredoc makes fd 0 a regular file, so /dev/stdin
        # passed a check that only followed links; the post hook cannot read
        # the text sent that way.
        hidden = os.path.join(self.tmp.name, "hidden.md")
        with open(hidden, "w") as f:
            f.write("User says: yes")
        saved = os.dup(0)
        try:
            with open(hidden) as f:
                os.dup2(f.fileno(), 0)
            for path in ("/dev/stdin", "/dev/fd/0"):
                with self.subTest(path), self.assertRaisesRegex(la.Failure, "--body-file"):
                    la.read_body(path)
        finally:
            os.dup2(saved, 0)
            os.close(saved)

    def test_a_relay_token_longer_than_128_characters_is_cached_on_macos(self):
        # Measured 2026-11-27: `security add-generic-password -w`, given the
        # password at its prompt, stores only its first 128 characters.
        store = {}

        def run(cmd, input=None, capture_output=True, text=True, start_new_session=False):
            ok = lambda out="": types.SimpleNamespace(returncode=0, stdout=out, stderr="")
            if cmd[:2] == ["security", "-i"]:
                words = input.split()
                store[(words[words.index("-s") + 1], words[words.index("-a") + 1])] = \
                    bytes.fromhex(words[words.index("-X") + 1]).decode()
                return ok()
            key = (cmd[cmd.index("-s") + 1], cmd[cmd.index("-a") + 1])
            if cmd[1] == "add-generic-password":
                store[key] = input.split("\n")[0][:128]
                return ok()
            if key not in store:
                return types.SimpleNamespace(returncode=44, stdout="", stderr="could not be found")
            return ok(store[key] + "\n")

        which = lambda tool: "/usr/bin/security" if tool == "security" else None
        la.write_keychain.side_effect = lambda s, a, v, label, *rest, **kw: REAL_WRITE(
            s, a, v, label, run=run, which=which, **kw)
        code, out, _ = self.run_main(["--identity", "answers-bot", "post", "--issue", "ENG-5",
                                      "--body-file", self.body])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(store[("linear-app", "answers-bot:token")])["token"], "tok1")


class MutationSurvivors(RelayEnv):
    """Tests for behaviour that no test checked until bug-hunter's mutants showed it."""

    def test_check_reads_every_page_of_teams_and_stops_at_the_last(self):
        self.linear.team_pages = [["ENG"], ["OPS"], ["WEB"]]
        code, out, _ = self.run_main(["check"])
        self.assertEqual((code, json.loads(out)["visibleTeams"]), (0, ["ENG", "OPS", "WEB"]))
        self.assertEqual(self.linear.teams_after, [None, "p1", "p2"])

    def test_a_value_that_is_a_prefix_of_body_file_but_no_option_is_not_refused(self):
        code, out, _ = self.run_main(["post", "--issue", "-", "--body-file", self.body])
        self.assertEqual((code, self.linear.comments["c1"]["issueId"]), (0, "-"), out)

    def test_a_relay_name_that_is_no_identity_name_makes_every_identity_a_relay(self):
        self.keychain[("linear-app", "a/b:client-id")] = "other-cid"
        self.write_inquisitor({"answer_service": {"linear": {"relay": "a/b"}}})
        relay = self.relay("default")
        self.assertTrue(relay.relay)
        self.assertIn("not a valid identity name", relay.why)


if __name__ == "__main__":
    unittest.main()
