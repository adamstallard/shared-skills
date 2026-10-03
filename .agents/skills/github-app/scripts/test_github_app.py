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


NAME, EMAIL = "acme-agent[bot]", "41+acme-agent[bot]@users.noreply.github.com"
WRONG_HELPER = "!f() { echo username=person; echo password=WRONG; }; f"


def git(*args, env=None, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, env=env, check=check).stdout


def config_files(root):
    """Every git config file under `root`, with its bytes, to prove none was written."""
    found = {}
    for folder, _, files in os.walk(root):
        for name in files:
            if name in ("config", ".gitconfig", "config.worktree") or name.endswith(".inc"):
                path = os.path.join(folder, name)
                with open(path, "rb") as f:
                    found[path] = f.read()
    return found


class AgentEnv(Env):
    """The agent's environment, built by `run`, applied to real git with a scratch HOME."""

    def setUp(self):
        super().setUp()
        if not shutil.which("git"):
            self.skipTest("git not installed")
        patches = [mock.patch.object(ga, "commit_identity", return_value=(NAME, EMAIL)),
                   mock.patch.object(ga, "current_token", return_value=("ghs_x", {}))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        git("config", "--global", "user.name", "Person")
        git("config", "--global", "user.email", "person@example.com")

    def agent(self, *command):
        seen = {}
        args = types.SimpleNamespace(identity="default", rest=["--", *(command or ["git"])])
        ga.cmd_run(args, self.config, execvpe=lambda n, argv, env: seen.update(env), which=lambda c: "/bin/" + c)
        return seen

    def repo(self, name="repo"):
        path = os.path.join(self.tmp.name, name)
        git("init", "-q", path)
        return path

    def commit(self, repo, env=None):
        git("-C", repo, "commit", "-q", "--allow-empty", "-m", "x", env=env)
        return git("-C", repo, "log", "-1", "--format=%an <%ae>|%cn <%ce>").strip()

    def test_run_commits_as_the_bot(self):
        repo = self.repo()
        bot = f"{NAME} <{EMAIL}>"
        self.assertEqual(self.commit(repo, self.agent()), f"{bot}|{bot}")

    def test_the_persons_global_helper_never_answers_for_the_agent(self):
        git("config", "--global", ga.HELPER_KEY, WRONG_HELPER)
        repo = self.repo()
        fill = subprocess.run(["git", "-C", repo, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, env=dict(self.agent(), GIT_TERMINAL_PROMPT="0"))
        self.assertNotIn("WRONG", fill.stdout)

    def test_the_persons_signing_key_never_signs_the_apps_commits(self):
        git("config", "--global", "commit.gpgsign", "true")
        repo = self.repo()
        self.assertEqual(git("-C", repo, "config", "commit.gpgsign", env=self.agent()).strip(), "false")

    def test_gh_gets_a_token_for_its_process_only(self):
        self.assertEqual(self.agent("gh")["GH_TOKEN"], "ghs_x")
        self.assertNotIn("GH_TOKEN", os.environ)

    # Regressions from repository wiring, which wrote .git/config; each failed under it.

    def test_the_agent_in_a_worktree_never_changes_the_main_checkout(self):
        main = self.repo("main")
        self.commit(main)
        worktree = os.path.join(main, ".claude", "worktrees", "agent")
        git("-C", main, "worktree", "add", "-q", worktree, "-b", "agent")
        before = config_files(self.tmp.name)
        self.assertEqual(self.commit(worktree, self.agent()).split("|")[0], f"{NAME} <{EMAIL}>")
        self.assertEqual(config_files(self.tmp.name), before)
        self.assertEqual(self.commit(main), "Person <person@example.com>|Person <person@example.com>")

    def test_a_global_author_setting_never_beats_the_bot(self):
        git("config", "--global", "author.name", "Person")
        git("config", "--global", "author.email", "person@example.com")
        git("config", "--global", "committer.email", "person@example.com")
        bot = f"{NAME} <{EMAIL}>"
        self.assertEqual(self.commit(self.repo(), self.agent()), f"{bot}|{bot}")

    def test_an_included_email_never_beats_the_bot(self):
        inc = os.path.join(self.tmp.name, "work.inc")
        with open(inc, "w") as f:
            f.write("[user]\n\temail = person@work.example\n")
        repo = self.repo()
        git("-C", repo, "config", "user.name", "Person")
        git("-C", repo, "config", "include.path", inc)
        self.assertEqual(self.commit(repo, self.agent()).split("|")[0], f"{NAME} <{EMAIL}>")

    def test_nothing_writes_git_config_even_with_git_dir_set(self):
        other = self.repo("other")
        repo = self.repo()
        os.environ["GIT_DIR"] = os.path.join(other, ".git")
        before = config_files(self.tmp.name)
        self.agent()
        ga.cmd_env(types.SimpleNamespace(identity="default", offset=None), self.config)
        ga.cmd_wire(types.SimpleNamespace(identity="default", project=repo), self.config)
        ga.cmd_unwire(types.SimpleNamespace(identity="default", project=repo), self.config)
        self.assertEqual(config_files(self.tmp.name), before)

    def test_run_keeps_the_callers_own_git_config_variables(self):
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="/srv/x")
        env = self.agent()
        repo = self.repo()
        self.assertEqual(git("-C", repo, "config", "--get-all", "safe.directory", env=env).strip(), "/srv/x")
        self.assertEqual(git("-C", repo, "config", "commit.gpgsign", env=env).strip(), "false")


class EnvLines(Env):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ga, "commit_identity", return_value=(NAME, EMAIL))
        patcher.start()
        self.addCleanup(patcher.stop)

    def lines(self, offset=None, identity="default"):
        return ga.cmd_env(types.SimpleNamespace(identity=identity, offset=offset), self.config)

    def sourced(self, *texts):
        """What `set -a; . file` in sh gives a process, for each file in turn."""
        paths = []
        for i, text in enumerate(texts):
            paths.append(os.path.join(self.tmp.name, f"role{i}.env"))
            with open(paths[-1], "w") as f:
                f.write(text + "\n")
        script = "set -a; " + " ".join(f'. "{p}";' for p in paths) + \
            ' exec "$0" -c "import json, os; print(json.dumps(dict(os.environ)))"'
        out = subprocess.run(["sh", "-c", script, sys.executable], capture_output=True, text=True,
                             env={"PATH": os.environ["PATH"], "HOME": self.tmp.name}, check=True)
        return json.loads(out.stdout)

    def test_env_lines_hold_no_token_or_key(self):
        text = self.lines()
        self.assertNotIn("ghs_", text)
        self.assertNotIn("KEY1", text)

    @unittest.skipUnless(shutil.which("sh"), "sh not installed")
    def test_env_lines_source_in_sh_to_exact_values(self):
        tricky = 'acme "agent" $HOME `id` \\ it\'s [bot]'
        with mock.patch.object(ga, "commit_identity", return_value=(tricky, EMAIL)):
            text = self.lines()
            wanted = ga.agent_env("default", tricky, EMAIL)
        got = self.sourced(text)
        self.assertEqual({k: got.get(k) for k in wanted}, wanted)

    def test_env_lines_follow_systemds_double_quote_rules(self):
        # systemd.exec(5), EnvironmentFile=: inside "…", a backslash before any of "\`$ keeps that
        # character; any other character is kept as is. Every value is wrapped this way.
        for line in self.lines().splitlines():
            key, value = line.split("=", 1)
            self.assertRegex(key, r"^[A-Z_][A-Z0-9_]*$")
            self.assertTrue(value.startswith('"') and value.endswith('"'), line)
            self.assertNotRegex(value[1:-1], r'(?<!\\)(\\\\)*["$`]')

    def test_env_lines_turn_off_signing_too(self):
        pairs = ga.agent_env("default", NAME, EMAIL)
        keys = {pairs[k]: pairs[k.replace("KEY", "VALUE")] for k in pairs if k.startswith("GIT_CONFIG_KEY_")}
        self.assertEqual(keys.get("commit.gpgsign"), "false")
        self.assertEqual(int(pairs["GIT_CONFIG_COUNT"]), sum(k.startswith("GIT_CONFIG_KEY_") for k in pairs))

    @unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git or sh not installed")
    def test_env_lines_outrank_the_global_helper(self):
        subprocess.run(["git", "config", "--global", ga.HELPER_KEY, WRONG_HELPER], check=True)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", **{k: v for k, v in self.sourced(self.lines()).items()
                                                            if k.startswith(("GIT_", "GITHUB_"))})
        repo = os.path.join(self.tmp.name, "r")
        subprocess.run(["git", "init", "-q", repo], check=True)
        fill = subprocess.run(["git", "-C", repo, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, env=env)
        self.assertNotIn("WRONG", fill.stdout)

    def test_env_refuses_when_git_config_variables_are_already_set(self):
        os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="*")
        with self.assertRaisesRegex(ga.Failure, "--offset"):
            self.lines()

    @unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git or sh not installed")
    def test_offset_lines_appended_to_a_file_keep_its_settings(self):
        existing = 'GIT_CONFIG_COUNT="1"\nGIT_CONFIG_KEY_0="safe.directory"\nGIT_CONFIG_VALUE_0="/srv/x"'
        got = self.sourced(existing, self.lines(offset=1))
        env = dict(os.environ, **{k: v for k, v in got.items() if k.startswith("GIT_")})
        repo = os.path.join(self.tmp.name, "r")
        subprocess.run(["git", "init", "-q", repo], check=True)
        read = lambda *a: subprocess.run(["git", "-C", repo, "config", *a], capture_output=True, text=True,
                                         env=env).stdout.strip()
        self.assertEqual(read("--get-all", "safe.directory"), "/srv/x")
        self.assertEqual(read("commit.gpgsign"), "false")


class WiringFixture(Env):
    """A project folder with a .claude folder, and the bot's name and email without asking GitHub."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(ga, "commit_identity", return_value=(NAME, EMAIL))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = os.path.realpath(os.path.join(self.tmp.name, "project"))
        os.makedirs(os.path.join(self.project, ".claude"))
        self.path = ga.settings_path(self.project)

    def wire(self, identity="default"):
        return ga.cmd_wire(types.SimpleNamespace(identity=identity, project=self.project), self.config)

    def unwire(self):
        return ga.cmd_unwire(types.SimpleNamespace(identity="default", project=self.project), self.config)

    def settings(self):
        with open(self.path) as f:
            return json.load(f)

    def write(self, settings):
        with open(self.path, "w") as f:
            json.dump(settings, f)


class ProjectWiring(WiringFixture):
    """`wire --project` edits only the env keys it adds to .claude/settings.local.json."""

    def test_wire_adds_the_agents_env_and_no_token(self):
        self.wire()
        env = self.settings()["env"]
        self.assertIn(ga.WIRED_KEY, env)  # wire's record of what it wrote
        del env[ga.WIRED_KEY]
        self.assertEqual(env, ga.agent_env("default", NAME, EMAIL))
        self.assertNotIn("GH_TOKEN", env)

    def test_wire_then_unwire_gives_back_the_file_exactly(self):
        mine = {"permissions": {"allow": ["Bash(ls)"]}, "env": {"MY_VAR": "1", "PATH_EXTRA": "/x"}}
        self.write(mine)
        self.wire()
        self.assertEqual(self.settings()["permissions"], mine["permissions"])
        self.assertEqual(self.settings()["env"]["MY_VAR"], "1")
        self.wire()  # twice
        self.unwire()
        self.assertEqual(self.settings(), mine)

    def test_a_file_wire_created_is_removed_by_unwire(self):
        self.wire()
        self.unwire()
        self.assertFalse(os.path.exists(self.path))

    def test_unwire_without_wire_changes_nothing(self):
        mine = {"env": {"GIT_AUTHOR_EMAIL": "person@work.example", "GIT_CONFIG_COUNT": "1"}}
        self.write(mine)
        with self.assertRaisesRegex(ga.Failure, "no record"):
            self.unwire()
        self.assertEqual(self.settings(), mine)

    def test_wire_never_overwrites_the_persons_own_keys(self):
        for mine in ({"env": {"GIT_AUTHOR_EMAIL": "person@work.example"}},
                     {"env": {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                              "GIT_CONFIG_VALUE_0": "*"}}):
            self.write(mine)
            with self.assertRaisesRegex(ga.Failure, "already sets"):
                self.wire()
            self.assertEqual(self.settings(), mine)

    def test_unwire_leaves_a_key_the_person_changed_since_wire(self):
        self.wire()
        settings = self.settings()
        settings["env"]["GIT_AUTHOR_EMAIL"] = "person@work.example"
        self.write(settings)
        result = self.unwire()
        self.assertEqual(self.settings()["env"], {"GIT_AUTHOR_EMAIL": "person@work.example"})
        self.assertIn("GIT_AUTHOR_EMAIL", " ".join(result["warnings"]))

    def test_rewiring_to_another_identity_replaces_only_its_own_keys(self):
        self.write({"env": {"MY_VAR": "1"}})
        self.wire()
        self.wire(identity="other")
        self.assertEqual(self.settings()["env"]["GITHUB_APP_ACT_AS"], "other")
        self.unwire()
        self.assertEqual(self.settings(), {"env": {"MY_VAR": "1"}})

    def test_forget_leaves_a_wired_project_undoable(self):
        self.wire()
        ga.cmd_forget(types.SimpleNamespace(identity="default"), self.config)
        self.unwire()
        self.assertFalse(os.path.exists(self.path))

    def test_keys_whose_marker_was_deleted_by_hand_are_the_persons(self):
        self.wire()
        settings = self.settings()
        del settings["env"][ga.WIRED_KEY]
        self.write(settings)
        with self.assertRaisesRegex(ga.Failure, "no record"):
            self.unwire()
        with self.assertRaisesRegex(ga.Failure, "already sets"):
            self.wire()
        self.assertEqual(self.settings(), settings)

    def test_rewire_refuses_a_key_the_person_changed_since_wire(self):
        self.wire()
        settings = self.settings()
        settings["env"]["GIT_AUTHOR_EMAIL"] = "person@work.example"
        self.write(settings)
        with self.assertRaisesRegex(ga.Failure, "already sets GIT_AUTHOR_EMAIL"):
            self.wire(identity="other")
        self.assertEqual(self.settings(), settings)

    def test_an_unreadable_marker_is_refused_and_nothing_changes(self):
        mine = {"env": {ga.WIRED_KEY: "not json", "GIT_AUTHOR_NAME": "x"}}
        self.write(mine)
        for step in (self.wire, self.unwire):
            with self.assertRaisesRegex(ga.Failure, ga.WIRED_KEY):
                step()
        self.assertEqual(self.settings(), mine)


class SecondReview(WiringFixture):
    """Bugs found by the second review of the environment-only wiring; each test failed before its fix."""

    def child_env(self, identity="default", config=None):
        seen = {}
        with mock.patch.object(ga, "current_token", return_value=("ghs_x", {})):
            ga.cmd_run(types.SimpleNamespace(identity=identity, rest=["--", "git", "push"]),
                       self.config if config is None else config,
                       execvpe=lambda name, argv, env: seen.update(env), which=lambda c: "/bin/" + c)
        return seen

    def test_a_child_never_uses_credentials_that_belong_to_another_identity(self):
        other_key = os.path.join(self.tmp.name, "other.pem")
        with open(other_key, "wb") as f:
            f.write(b"OTHERKEY")
        os.environ.update(GITHUB_APP_ID="999", GITHUB_APP_PRIVATE_KEY_FILE=other_key)  # the default role's
        acme = {"appId": "123", "owner": "acme"}
        with open(ga.config_path("acme"), "w") as f:
            json.dump(acme, f)
        with open(ga.default_key_path("acme"), "wb") as f:
            f.write(b"ACMEKEY")
        child = self.child_env("acme", acme)
        self.assertEqual(ga.app_credentials("acme", acme, env=child), ("123", b"ACMEKEY"))
        self.assertEqual(ga.resolve_identity(None, child), "acme")

    def test_a_server_roles_file_still_pairs_its_identity_with_its_credentials(self):
        key = os.path.join(self.tmp.name, "reviewer.pem")
        with open(key, "wb") as f:
            f.write(b"REVIEWERKEY")
        role = {"GITHUB_APP_IDENTITY": "reviewer", "GITHUB_APP_ID": "555", "GITHUB_APP_PRIVATE_KEY_FILE": key,
                **ga.agent_env("reviewer", NAME, EMAIL)}
        self.assertEqual(ga.resolve_identity(None, role), "reviewer")
        self.assertEqual(ga.app_credentials("reviewer", {}, env=role), ("555", b"REVIEWERKEY"))

    def test_another_identitys_owner_in_the_environment_is_not_used(self):
        os.environ["GITHUB_APP_OWNER"] = "person-org"  # the default role's, not acme's
        with open(ga.default_key_path("acme"), "wb") as f:
            f.write(b"ACMEKEY")
        token, cached = self.token("acme", config={"appId": "123"})
        self.assertEqual(cached["installationId"], "7")

    def test_wire_keeps_the_settings_files_permissions(self):
        self.write({"env": {"ANTHROPIC_API_KEY": "secret"}})
        os.chmod(self.path, 0o600)
        self.wire()
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_wire_writes_through_a_symlinked_settings_file(self):
        real = os.path.join(self.tmp.name, "dotfiles-settings.json")
        with open(real, "w") as f:
            json.dump({"env": {"MINE": "1"}}, f)
        os.symlink(real, self.path)
        self.wire()
        self.assertTrue(os.path.islink(self.path))
        with open(real) as f:
            self.assertIn("GIT_CONFIG_COUNT", json.load(f)["env"])

    def test_a_failed_wire_changes_nothing(self):
        os.environ["GIT_CONFIG_COUNT"] = "x"
        with self.assertRaises(ga.Failure):
            self.wire()
        self.assertFalse(os.path.exists(self.path))

    def test_the_helper_answers_however_github_com_is_spelled(self):
        args = types.SimpleNamespace(identity="default", operation="get")
        with mock.patch.object(ga, "current_token", side_effect=lambda i, c: ("ghs_x", {})):
            for host in ("GitHub.com", "github.com:443"):
                got = ga.cmd_credential(args, self.config, stdin=io.StringIO(f"protocol=https\nhost={host}\n"))
                self.assertIn("password=ghs_x", got, host)


class ThirdReview(WiringFixture):
    """Bugs found by the third review; each test failed before its fix."""

    def test_unwire_through_a_dangling_symlink_cleans_the_file_wire_wrote(self):
        target = os.path.join(self.tmp.name, "dotfiles", "settings.json")
        os.makedirs(os.path.dirname(target))
        os.symlink(target, self.path)  # the target doesn't exist yet
        self.wire()
        self.unwire()
        self.assertTrue(os.path.islink(self.path))
        env = {}
        if os.path.exists(target):
            with open(target) as f:
                env = json.load(f).get("env", {})
        self.assertEqual([k for k in env if k.startswith(("GIT_", "GITHUB_APP_"))], [])

    def test_a_failed_settings_write_leaves_the_earlier_wiring_undoable(self):
        self.write({"permissions": {}})
        self.wire()
        with mock.patch.object(ga, "write_json", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                self.wire("other")
        self.unwire()
        self.assertEqual(self.settings(), {"permissions": {}})

    def test_a_failed_settings_write_changes_nothing(self):
        self.write({"permissions": {}})
        with mock.patch.object(ga.os, "replace", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                self.wire()
        self.assertEqual(self.settings(), {"permissions": {}})

    def test_the_no_credentials_error_never_suggests_lending_another_identitys_app(self):
        os.environ.update(GITHUB_APP_IDENTITY="reviewer", GITHUB_APP_ID="555", GITHUB_APP_PRIVATE_KEY="k")
        with self.assertRaises(ga.Failure) as e:
            ga.app_credentials("bob", {})
        self.assertNotIn("GITHUB_APP_IDENTITY=bob", str(e.exception))


class FourthReview(WiringFixture):
    """Bugs found by the review of wire's write order and symlink handling; each test failed before its fix."""

    def app_keys(self, path):
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [k for k in json.load(f).get("env", {}) if k.startswith(("GIT_", "GITHUB_APP_"))]

    def linked_to(self, target, env):
        with open(target, "w") as f:
            json.dump({"env": env}, f)
        if os.path.lexists(self.path):
            os.remove(self.path)
        os.symlink(target, self.path)

    def test_repointing_the_settings_link_never_orphans_the_apps_keys(self):
        a, b = os.path.join(self.tmp.name, "a.json"), os.path.join(self.tmp.name, "b.json")
        self.linked_to(a, {"MINE": "a"})
        self.wire()
        self.linked_to(b, {"MINE": "b"})
        self.wire()
        self.unwire()
        self.assertEqual(self.app_keys(b), [])
        os.remove(self.path)
        os.symlink(a, self.path)  # a.json carries its own record, so it can still be undone
        self.unwire()
        with open(a) as f:
            self.assertEqual(json.load(f), {"env": {"MINE": "a"}})

    def test_a_link_to_another_projects_file_shares_that_files_wiring(self):
        # The file is the unit: linked to the other project's file, this project's
        # settings are that file, so unwiring through either leaves no stale state.
        a = os.path.join(self.tmp.name, "a.json")
        other = os.path.realpath(os.path.join(self.tmp.name, "other"))
        os.makedirs(os.path.join(other, ".claude"))
        other_file = ga.settings_path(other)
        with open(other_file, "w") as f:
            json.dump({"env": {"THEIRS": "1"}}, f)
        self.linked_to(a, {"MINE": "a"})
        self.wire()
        ga.cmd_wire(types.SimpleNamespace(identity="default", project=other), self.config)
        os.remove(self.path)
        os.symlink(other_file, self.path)
        self.wire()
        self.unwire()
        with open(other_file) as f:
            self.assertEqual(json.load(f), {"env": {"THEIRS": "1"}})
        with self.assertRaisesRegex(ga.Failure, "no record"):
            ga.cmd_unwire(types.SimpleNamespace(identity="default", project=other), self.config)

    def test_a_settings_file_recreated_by_wire_is_removed_by_unwire(self):
        self.write({"permissions": {}})
        self.wire()
        os.remove(self.path)
        self.wire()
        self.unwire()
        self.assertFalse(os.path.exists(self.path))


class FifthReview(WiringFixture):
    """Bugs found by the review of wire's record check; each test failed before its fix."""

    app_keys, linked_to = FourthReview.app_keys, FourthReview.linked_to

    def test_a_moved_project_can_still_be_unwired(self):
        self.write({"env": {"MINE": "1"}})
        self.wire()
        moved = self.project + "-moved"
        os.rename(self.project, moved)
        self.project, self.path = moved, ga.settings_path(moved)
        self.unwire()
        self.assertEqual(self.app_keys(self.path), [])


class SixthReview(WiringFixture):
    """Bugs found by the review of wire's in-file bookkeeping; each test failed before its fix."""

    def test_overlapping_writes_never_corrupt_the_settings_file(self):
        import threading
        self.write({"env": {"MINE": "keep"}})
        first_inside, release = threading.Event(), threading.Event()
        real_dump, calls = json.dump, []

        def slow_dump(data, f, **kw):
            calls.append(1)
            if len(calls) == 1:  # the first writer stops halfway, with its temp file open
                f.write("{")
                first_inside.set()
                release.wait(5)
                f.seek(0)
            real_dump(data, f, **kw)

        with mock.patch.object(ga.json, "dump", side_effect=slow_dump):
            # The writer that finishes last writes less, so any leftover bytes from the other show.
            first = threading.Thread(target=lambda: ga.write_json(self.path, {"env": {"A": "x"}}))
            first.start()
            first_inside.wait(5)
            try:
                ga.write_json(self.path, {"env": {"B": "y" * 400}})
            except OSError:
                pass
            release.set()
            first.join(5)
        self.settings()  # parses: the file is whole, whichever writer won

    def test_a_wired_value_edited_to_a_non_string_is_treated_as_changed(self):
        self.wire()
        settings = self.settings()
        settings["env"]["GIT_CONFIG_COUNT"] = 4
        self.write(settings)
        result = self.unwire()
        self.assertIn("GIT_CONFIG_COUNT", " ".join(result.get("warnings", [])))
        self.assertNotIn("GIT_AUTHOR_NAME", self.settings().get("env", {}))


class LockPlacement(WiringFixture):
    def test_wire_and_unwire_leave_no_lock_file_in_the_project(self):
        self.write({"env": {"MINE": "1"}})
        self.wire()
        self.unwire()
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".lock")], [])


class LockReview(WiringFixture):
    """Bugs found by the review of the write path and its lock; each test failed before its fix."""

    def test_two_spellings_of_one_settings_file_share_one_lock(self):
        upper = os.path.join(self.tmp.name, "CaseProj")
        os.makedirs(os.path.join(upper, ".claude"))
        lower = os.path.join(self.tmp.name, "caseproj")
        if not os.path.exists(lower):
            self.skipTest("needs a case-insensitive file system")
        for project in (upper, lower):
            with ga.settings_lock(ga.settings_path(project)):
                pass
        self.assertEqual(len(os.listdir(os.path.join(ga.xdg_dir("state"), "locks"))), 1)

    def test_two_spellings_of_the_settings_files_own_name_share_one_lock(self):
        shared = os.path.join(self.tmp.name, "shared")
        os.makedirs(shared)
        with open(os.path.join(shared, "S.json"), "w") as f:
            f.write("{}")
        if not os.path.exists(os.path.join(shared, "s.json")):
            self.skipTest("needs a case-insensitive file system")
        for name in ("S.json", "s.json", "café.json", "café.json"):
            with ga.settings_lock(os.path.join(shared, name)):
                pass
        self.assertEqual(len(os.listdir(os.path.join(ga.xdg_dir("state"), "locks"))), 2)

    def test_greek_names_that_fold_to_decomposed_forms_share_one_lock(self):
        folder = os.path.join(self.tmp.name, "greek")
        os.makedirs(folder)
        # One file on APFS: precomposed U+0390, and capital iota + dialytika + tonos.
        for name in ("sΐ.json", "sΪ́.json"):
            with ga.settings_lock(os.path.join(folder, name)):
                pass
        self.assertEqual(len(os.listdir(os.path.join(ga.xdg_dir("state"), "locks"))), 1)

    def test_a_new_settings_file_follows_the_umask(self):
        old = os.umask(0o077)
        self.addCleanup(os.umask, old)
        self.wire()
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_a_path_that_is_not_utf8_can_be_locked(self):
        with ga.settings_lock(os.path.join(self.tmp.name, "proj\udcff", ".claude", "settings.local.json")):
            pass


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
                mock.patch.object(ga, "commit_identity", return_value=("b[bot]", "1+b[bot]@x")), \
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
