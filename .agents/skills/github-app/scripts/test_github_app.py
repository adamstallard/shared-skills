#!/usr/bin/env python3
"""Tests for github_app.py. Standard library only; no network. One test runs the real openssl.

Run from the clone's root:  python3 .agents/skills/github-app/scripts/test_github_app.py
"""

import base64
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import github_app as ga  # noqa: E402

HOUR = 3600
NOW = 1_700_000_000.0


def stamp(t):
    return ga.datetime.datetime.fromtimestamp(t, ga.datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fake_signer(key, data):
    return b"sig:" + key[:4]


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGitHub:
    """Answers GitHub API calls from a table of (method, path) and records each one."""

    def __init__(self, installations=None, expires_in=HOUR, permissions=None, repos=None):
        self.calls = []
        self.minted = 0
        self.installations = installations if installations is not None else [{"id": 7, "account": {"login": "acme"}}]
        self.expires_in = expires_in
        self.permissions = permissions if permissions is not None else {"contents": "write", "pull_requests": "write",
                                                                        "metadata": "read"}
        self.repos = repos if repos is not None else ["acme/web", "acme/api"]
        self.now = NOW

    def __call__(self, req, timeout=None):
        path = req.full_url.replace(ga.API, "")
        self.calls.append((req.get_method(), path, req.headers.get("Authorization")))
        if path.startswith("/app/installations?"):
            return Response(json.dumps(self.installations).encode())
        if path.endswith("/access_tokens"):
            self.minted += 1
            return Response(json.dumps({"token": f"ghs_{self.minted}", "expires_at": stamp(self.now + self.expires_in),
                                        "permissions": self.permissions}).encode())
        if path == "/app":
            return Response(json.dumps({"slug": "acme-agent", "name": "acme agent"}).encode())
        if path.startswith("/users/acme-agent%5Bbot%5D"):
            return Response(json.dumps({"id": 41, "login": "acme-agent[bot]"}).encode())
        if path.startswith("/installation/repositories"):
            return Response(json.dumps({"total_count": len(self.repos),
                                        "repositories": [{"full_name": r} for r in self.repos]}).encode())
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message": "Not Found"}'))


class Env(unittest.TestCase):
    """Each test gets its own XDG folders, a key file and an App ID."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"XDG_CONFIG_HOME": os.path.join(self.tmp.name, "config"),
                    "XDG_STATE_HOME": os.path.join(self.tmp.name, "state"),
                    "PATH": os.environ.get("PATH", ""),
                    # git in these tests must not read the person's own global or system config.
                    "HOME": self.tmp.name, "GIT_CONFIG_NOSYSTEM": "1"}
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = {"appId": "123", "owner": "acme"}
        os.makedirs(ga.xdg_dir("config"), exist_ok=True)
        with open(ga.default_key_path("default"), "wb") as f:
            f.write(b"KEY1-----")
        self.github = FakeGitHub()

    def token(self, identity="default", config=None, now=NOW, **kw):
        return ga.current_token(identity, self.config if config is None else config, now=now,
                                opener=self.github, signer=fake_signer, **kw)


class Minting(Env):
    def test_a_token_is_minted_for_the_owners_installation(self):
        token, cached = self.token()
        self.assertEqual(token, "ghs_1")
        self.assertEqual(cached["installationId"], "7")
        self.assertIn(("POST", "/app/installations/7/access_tokens"), [c[:2] for c in self.github.calls])

    def test_the_token_is_reused_until_half_its_life(self):
        self.token()
        self.assertEqual(self.token(now=NOW + 29 * 60)[0], "ghs_1")
        self.assertEqual(self.token(now=NOW + 31 * 60)[0], "ghs_2")

    def test_the_installation_is_looked_up_once_per_credential(self):
        self.token()
        self.token(now=NOW + 31 * 60)
        lookups = [c for c in self.github.calls if c[1].startswith("/app/installations?")]
        self.assertEqual(len(lookups), 1)

    def test_a_configured_installation_id_skips_the_lookup(self):
        self.token(config={"appId": "123", "installationId": "99"})
        self.assertEqual([c[1] for c in self.github.calls], ["/app/installations/99/access_tokens"])

    def test_the_only_installation_is_used_without_an_owner(self):
        self.assertEqual(self.token(config={"appId": "123"})[1]["installationId"], "7")

    def test_several_installations_and_no_owner_names_them(self):
        self.github.installations = [{"id": 1, "account": {"login": "a"}}, {"id": 2, "account": {"login": "b"}}]
        with self.assertRaisesRegex(ga.Failure, "several accounts .*a, b"):
            self.token(config={"appId": "123"})

    def test_an_owner_without_the_app_installed_says_where_it_is(self):
        with self.assertRaisesRegex(ga.Failure, "not installed on 'other'.*acme"):
            self.token(config={"appId": "123", "owner": "other"})

    def test_owner_matches_ignoring_case(self):
        self.assertEqual(self.token(config={"appId": "123", "owner": "ACME"})[1]["installationId"], "7")

    def test_a_new_key_mints_a_new_token(self):
        self.token()
        with open(ga.default_key_path("default"), "wb") as f:
            f.write(b"KEY2-----")
        self.assertEqual(self.token()[0], "ghs_2")

    def test_the_cache_is_private_and_holds_no_key(self):
        self.token()
        path = ga.cache_path("default")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path) as f:
            self.assertNotIn("KEY1", f.read())

    def test_a_refused_token_is_replaced(self):
        self.token()
        self.assertEqual(self.token(refused="ghs_1")[0], "ghs_2")

    def test_the_jwt_is_sent_to_mint_and_the_token_to_the_api(self):
        self.token()
        mint = [c for c in self.github.calls if c[1].endswith("/access_tokens")][0]
        self.assertTrue(mint[2].startswith("Bearer ey"))


class Credentials(Env):
    def test_no_app_id_names_the_config(self):
        with self.assertRaisesRegex(ga.Failure, "appId"):
            self.token(config={})

    def test_no_key_file_names_it(self):
        os.remove(ga.default_key_path("default"))
        with self.assertRaisesRegex(ga.Failure, "default.pem"):
            self.token()

    def test_environment_credentials_win_for_their_identity(self):
        os.environ.update({"GITHUB_APP_ID": "555", "GITHUB_APP_PRIVATE_KEY": "ENVKEY"})
        app_id, key = ga.app_credentials("default", self.config)
        self.assertEqual((app_id, key), ("555", b"ENVKEY"))

    def test_environment_credentials_are_not_borrowed_by_another_identity(self):
        os.environ.update({"GITHUB_APP_ID": "555", "GITHUB_APP_PRIVATE_KEY": "ENVKEY"})
        with self.assertRaisesRegex(ga.Failure, "belongs to identity 'default'"):
            ga.app_credentials("reviewer", {})

    def test_an_app_id_without_a_key_in_the_environment_is_an_error(self):
        os.environ["GITHUB_APP_ID"] = "555"
        with self.assertRaisesRegex(ga.Failure, "one of GITHUB_APP_PRIVATE_KEY"):
            ga.app_credentials("default", self.config)

    def test_a_key_file_from_the_environment_is_read(self):
        path = os.path.join(self.tmp.name, "k.pem")
        with open(path, "wb") as f:
            f.write(b"FILEKEY")
        os.environ.update({"GITHUB_APP_ID": "555", "GITHUB_APP_PRIVATE_KEY_FILE": path})
        self.assertEqual(ga.app_credentials("default", {})[1], b"FILEKEY")

    def test_a_configured_key_file_is_used(self):
        path = os.path.join(self.tmp.name, "elsewhere.pem")
        with open(path, "wb") as f:
            f.write(b"ELSEWHERE")
        self.assertEqual(ga.app_credentials("x", {"appId": "1", "keyFile": path})[1], b"ELSEWHERE")


class Jwt(unittest.TestCase):
    def test_claims_allow_for_clock_skew_and_github_limit(self):
        token = ga.app_jwt("123", b"k", NOW, fake_signer)
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        self.assertEqual(claims, {"iat": int(NOW) - 60, "exp": int(NOW) + 540, "iss": "123"})

    @unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
    def test_openssl_signs_a_jwt_that_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            key, pub, sig, data = (os.path.join(d, n) for n in ("k.pem", "p.pem", "s.bin", "d.txt"))
            subprocess.run(["openssl", "genrsa", "-out", key, "2048"], check=True, capture_output=True)
            subprocess.run(["openssl", "rsa", "-in", key, "-pubout", "-out", pub], check=True, capture_output=True)
            with open(key, "rb") as f:
                token = ga.app_jwt("123", f.read(), NOW)
            header, claims, signature = token.split(".")
            with open(data, "wb") as f:
                f.write(f"{header}.{claims}".encode())
            with open(sig, "wb") as f:
                f.write(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
            verified = subprocess.run(["openssl", "dgst", "-sha256", "-verify", pub, "-signature", sig, data],
                                      capture_output=True, text=True)
            self.assertIn("Verified OK", verified.stdout)

    @unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
    def test_a_file_that_is_not_a_key_is_refused(self):
        with self.assertRaisesRegex(ga.Failure, "openssl could not sign"):
            ga.sign(b"not a key", b"data")

    def test_the_signing_key_never_outlives_the_call(self):
        seen = {}

        def run(cmd, input=None, capture_output=True):
            seen["path"] = cmd[-1]
            seen["exists"] = os.path.exists(cmd[-1])
            return types.SimpleNamespace(returncode=0, stdout=b"sig", stderr=b"")

        ga.sign(b"KEY", b"data", run=run, which=lambda t: "/usr/bin/openssl")
        self.assertTrue(seen["exists"])
        self.assertFalse(os.path.exists(seen["path"]))
        self.assertNotIn(b"KEY", b" ".join(c.encode() for c in ["openssl", "dgst", "-sha256", "-sign", seen["path"]]))


class Check(Env):
    def run_check(self, config=None):
        args = types.SimpleNamespace(identity="default")
        return ga.cmd_check(args, config or self.config, opener=self.github, signer=fake_signer)

    def test_check_names_the_bot_and_its_rights(self):
        result = self.run_check()
        self.assertEqual(result["app"], "acme-agent")
        self.assertEqual(result["commitsAs"], "acme-agent[bot] <41+acme-agent[bot]@users.noreply.github.com>")
        self.assertTrue(result["canPushAndOpenPullRequests"])
        self.assertEqual(result["repositoryNames"], ["acme/api", "acme/web"])
        self.assertNotIn("warnings", result)

    def test_missing_write_permission_is_named(self):
        self.github.permissions = {"contents": "read", "pull_requests": "write"}
        result = self.run_check()
        self.assertFalse(result["canPushAndOpenPullRequests"])
        self.assertIn("contents: write", " ".join(result["warnings"]))

    def test_a_configured_repo_the_app_cannot_reach_is_named(self):
        result = self.run_check(dict(self.config, repos=["acme/web", "acme/secret"]))
        self.assertIn("acme/secret", " ".join(result["warnings"]))

    def test_check_writes_nothing_to_github(self):
        self.run_check()
        writes = [c for c in self.github.calls if c[0] != "GET" and not c[1].endswith("/access_tokens")]
        self.assertEqual(writes, [])


class Credential(Env):
    def helper(self, operation, text):
        args = types.SimpleNamespace(identity="default", operation=operation)
        with mock.patch.object(ga, "current_token", side_effect=lambda i, c: ("ghs_x", {})):
            return ga.cmd_credential(args, self.config, stdin=io.StringIO(text))

    def test_get_for_github_answers_with_the_token(self):
        self.assertEqual(self.helper("get", "protocol=https\nhost=github.com\n\n"),
                         "username=x-access-token\npassword=ghs_x")

    def test_other_hosts_get_nothing(self):
        self.assertEqual(self.helper("get", "protocol=https\nhost=gitlab.com\n"), "")
        self.assertEqual(self.helper("get", "protocol=http\nhost=github.com\n"), "")

    def test_store_is_ignored(self):
        self.assertEqual(self.helper("store", "protocol=https\nhost=github.com\npassword=ghs_x\n"), "")

    def test_erase_drops_the_cached_token(self):
        self.token()
        self.helper("erase", "protocol=https\nhost=github.com\n")
        self.assertFalse(os.path.exists(ga.cache_path("default")))


class Wire(Env):
    def setUp(self):
        super().setUp()
        if not shutil.which("git"):
            self.skipTest("git not installed")
        self.repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "https://github.com/acme/web.git"], check=True)

    def wire(self, **kw):
        args = types.SimpleNamespace(identity="default", repo=self.repo, **kw)
        return ga.cmd_wire(args, self.config, opener=self.github, signer=fake_signer)

    def local(self, *a):
        return subprocess.run(["git", "-C", self.repo, "config", "--local", *a], capture_output=True, text=True).stdout

    def test_wire_sets_the_helper_and_identity_in_this_repo_only(self):
        result = self.wire()
        helpers = self.local("--get-all", ga.HELPER_KEY).splitlines()
        self.assertEqual(helpers[0], "")
        self.assertIn("credential", helpers[1])
        self.assertEqual(self.local("user.name").strip(), "acme-agent[bot]")
        self.assertEqual(result["commitsAs"], "acme-agent[bot] <41+acme-agent[bot]@users.noreply.github.com>")
        global_name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True,
                                     env=dict(os.environ, HOME=self.tmp.name)).stdout
        self.assertEqual(global_name, "")

    def test_the_persons_global_helper_never_answers_in_a_wired_repo(self):
        subprocess.run(["git", "config", "--global", ga.HELPER_KEY,
                        "!f() { echo username=person; echo password=WRONG; }; f"], check=True)
        self.wire()
        fill = subprocess.run(["git", "-C", self.repo, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        self.assertNotIn("WRONG", fill.stdout)

    def test_wiring_twice_leaves_one_helper(self):
        self.wire()
        self.wire()
        self.assertEqual(len(self.local("--get-all", ga.HELPER_KEY).splitlines()), 2)

    def test_an_ssh_remote_is_warned_about(self):
        subprocess.run(["git", "-C", self.repo, "remote", "set-url", "origin", "git@github.com:acme/web.git"], check=True)
        self.assertIn("SSH", " ".join(self.wire()["warnings"]))

    def test_unwire_removes_what_wire_set(self):
        self.wire()
        ga.cmd_unwire(types.SimpleNamespace(identity="default", repo=self.repo), self.config)
        self.assertEqual(self.local("--get-all", ga.HELPER_KEY), "")
        self.assertEqual(self.local("user.name"), "")

    def test_a_folder_outside_a_repo_is_refused(self):
        outside = os.path.join(self.tmp.name, "plain")
        os.makedirs(outside)
        with self.assertRaisesRegex(ga.Failure, "not inside a git repository"):
            ga.cmd_wire(types.SimpleNamespace(identity="default", repo=outside), self.config,
                        opener=self.github, signer=fake_signer)


class EnvLines(Env):
    def test_env_lines_hold_no_token_or_key(self):
        text = ga.cmd_env(types.SimpleNamespace(identity="default"), self.config, opener=self.github,
                          signer=fake_signer)
        self.assertIn("GIT_CONFIG_KEY_1=" + ga.HELPER_KEY, text)
        self.assertIn("GIT_AUTHOR_NAME=acme-agent[bot]", text)
        self.assertNotIn("ghs_", text)
        self.assertNotIn("KEY1", text)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_env_lines_outrank_the_global_helper(self):
        subprocess.run(["git", "config", "--global", ga.HELPER_KEY,
                        "!f() { echo username=person; echo password=WRONG; }; f"], check=True)
        text = ga.cmd_env(types.SimpleNamespace(identity="default"), self.config, opener=self.github,
                          signer=fake_signer)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", **dict(line.split("=", 1) for line in text.splitlines()))
        repo = os.path.join(self.tmp.name, "r")
        subprocess.run(["git", "init", "-q", repo], check=True)
        fill = subprocess.run(["git", "-C", repo, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, env=env)
        self.assertNotIn("WRONG", fill.stdout)


class Gh(Env):
    def test_gh_gets_the_token_for_its_process_only(self):
        seen = {}

        def execvpe(name, argv, env):
            seen.update(name=name, argv=argv, token=env.get("GH_TOKEN"))

        args = types.SimpleNamespace(identity="default", gh_args=["--", "pr", "list"])
        with mock.patch.object(ga, "current_token", return_value=("ghs_x", {})):
            ga.cmd_gh(args, self.config, execvpe=execvpe, which=lambda t: "/usr/bin/gh")
        self.assertEqual(seen, {"name": "gh", "argv": ["gh", "pr", "list"], "token": "ghs_x"})
        self.assertNotIn("GH_TOKEN", os.environ)


class StoreAndForget(Env):
    def store(self, **kw):
        source = os.path.join(self.tmp.name, "downloaded.pem")
        with open(source, "wb") as f:
            f.write(b"NEWKEY")
        args = types.SimpleNamespace(identity="bot", app_id="321", key_file=source, owner="acme", **kw)
        return ga.cmd_store_credentials(args, {}, signer=fake_signer), source

    def test_store_copies_the_key_privately_and_records_the_app(self):
        result, source = self.store()
        target = ga.default_key_path("bot")
        self.assertEqual(open(target, "rb").read(), b"NEWKEY")
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        self.assertEqual(ga.load_config("bot"), {"appId": "321", "owner": "acme"})
        self.assertIn(source, " ".join(result["warnings"]))

    def test_a_non_numeric_app_id_is_refused(self):
        args = types.SimpleNamespace(identity="bot", app_id="my-app", key_file="x", owner=None)
        with self.assertRaisesRegex(ga.Failure, "numeric"):
            ga.cmd_store_credentials(args, {}, signer=fake_signer)

    def test_forget_deletes_the_key_and_cache(self):
        self.store()
        ga.current_token("bot", ga.load_config("bot"), now=NOW, opener=self.github, signer=fake_signer)
        result = ga.cmd_forget(types.SimpleNamespace(identity="bot"), ga.load_config("bot"))
        self.assertFalse(os.path.exists(ga.default_key_path("bot")))
        self.assertFalse(os.path.exists(ga.cache_path("bot")))
        self.assertTrue(result["forgotten"])

    def test_forget_keeps_a_key_file_it_did_not_make(self):
        path = os.path.join(self.tmp.name, "mine.pem")
        with open(path, "wb") as f:
            f.write(b"MINE")
        result = ga.cmd_forget(types.SimpleNamespace(identity="x"), {"appId": "1", "keyFile": path})
        self.assertTrue(os.path.exists(path))
        self.assertEqual(result["keptKeyFile"], path)
        self.assertIn("still works", " ".join(result["warnings"]))

    def test_forget_says_the_environment_still_holds_credentials(self):
        os.environ.update({"GITHUB_APP_ID": "1", "GITHUB_APP_PRIVATE_KEY": "K"})
        result = ga.cmd_forget(types.SimpleNamespace(identity="default"), {})
        self.assertIn("still set in the environment", " ".join(result["warnings"]))


class Regressions(Env):
    """Bugs found by bug-hunter; each test failed before its fix."""

    def test_gh_takes_its_own_leading_options(self):
        seen = {}
        with mock.patch.object(ga, "current_token", return_value=("ghs_x", {})), \
                mock.patch.object(ga.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(ga.os, "execvpe", side_effect=lambda n, argv, env: seen.update(argv=argv)):
            code = ga.main(["--identity", "default", "gh", "-R", "acme/web", "pr", "list"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"], ["gh", "-R", "acme/web", "pr", "list"])

    def test_a_key_with_escaped_newlines_in_the_environment_is_read(self):
        os.environ.update({"GITHUB_APP_ID": "1", "GITHUB_APP_PRIVATE_KEY": "-----BEGIN\\nLINE\\n-----END\\n"})
        self.assertEqual(ga.app_credentials("default", {})[1], b"-----BEGIN\nLINE\n-----END\n")

    def test_a_reinstalled_app_is_found_again(self):
        self.token()
        self.github.installations = [{"id": 8, "account": {"login": "acme"}}]
        real = self.github.__call__

        def opener(req, timeout=None):
            if "/installations/7/" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message": "x"}'))
            return real(req, timeout)

        token, cached = ga.current_token("default", self.config, now=NOW + 31 * 60, opener=opener,
                                         signer=fake_signer)
        self.assertEqual(cached["installationId"], "8")


class SigningRegression(Env):
    """Found by bug-hunter's second iteration; failed before its fix."""

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_the_persons_signing_key_never_signs_the_apps_commits(self):
        subprocess.run(["git", "config", "--global", "commit.gpgsign", "true"], check=True)
        repo = os.path.join(self.tmp.name, "signed")
        subprocess.run(["git", "init", "-q", repo], check=True)
        ga.cmd_wire(types.SimpleNamespace(identity="default", repo=repo), self.config, opener=self.github,
                    signer=fake_signer)
        effective = subprocess.run(["git", "-C", repo, "config", "commit.gpgsign"], capture_output=True, text=True)
        self.assertEqual(effective.stdout.strip(), "false")

    def test_env_lines_turn_off_signing_too(self):
        text = ga.cmd_env(types.SimpleNamespace(identity="default"), self.config, opener=self.github,
                          signer=fake_signer)
        pairs = dict(line.split("=", 1) for line in text.splitlines())
        keys = {pairs[k]: pairs[k.replace("KEY", "VALUE")] for k in pairs if k.startswith("GIT_CONFIG_KEY_")}
        self.assertEqual(keys.get("commit.gpgsign"), "false")
        self.assertEqual(int(pairs["GIT_CONFIG_COUNT"]), sum(k.startswith("GIT_CONFIG_KEY_") for k in pairs))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_unwire_gives_back_the_persons_own_repo_settings(self):
        repo = os.path.join(self.tmp.name, "mine")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "me@work.example"], check=True)
        ga.cmd_wire(types.SimpleNamespace(identity="default", repo=repo), self.config, opener=self.github,
                    signer=fake_signer)
        ga.cmd_unwire(types.SimpleNamespace(identity="default", repo=repo), self.config)
        after = subprocess.run(["git", "-C", repo, "config", "--local", "user.email"], capture_output=True, text=True)
        self.assertEqual(after.stdout.strip(), "me@work.example")


class Main(Env):
    def test_output_is_one_ascii_json_object(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = ga.main(["--identity", "nobody", "check"])
        self.assertEqual(code, 1)
        self.assertTrue(out.getvalue().isascii())
        self.assertFalse(json.loads(out.getvalue())["ok"])

    def test_token_errors_go_to_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ga.main(["--identity", "nobody", "token"])
        self.assertEqual((code, out.getvalue()), (1, ""))
        self.assertIn("github_app:", err.getvalue())

    def test_a_bad_identity_name_is_refused(self):
        with self.assertRaises(ga.Failure):
            ga.resolve_identity("../x")


if __name__ == "__main__":
    unittest.main()
