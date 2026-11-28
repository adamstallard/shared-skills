"""Tests for credentials: the closed list of token shapes."""

import unittest

from credentials import matches_credentials


class CredentialPatterns(unittest.TestCase):
    def test_the_patterns(self) -> None:
        # @scenario inquisitor: The credential patterns
        for text in ("-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN OPENSSH PRIVATE KEY-----",
                     "-----BEGIN PGP PRIVATE KEY BLOCK-----", "token ghp_abc123",
                     "gho_x", "ghs_x", "ghu_x", "ghr_x", "github_pat_11ABC",
                     "sk-ant-api03-abc", "lin_api_abc", "lin_oauth_abc",
                     "key AKIAIOSFODNN7EXAMPLE here", "xoxb-1234",
                     "[the docs](https://x/?token=ghp_abc)"):
            self.assertTrue(matches_credentials(text), text)
        for text in ("sk_live_abc", "xoxo", "AKIA", "a `ghp_` prefix", "AKIAIOSFODNN7EXAMPLEX"):
            self.assertFalse(matches_credentials(text), text)

    def test_dotted_text_is_no_discord_token(self) -> None:
        # @scenario inquisitor: Dotted ordinary text is no Discord bot token
        for text in ("1.15.0", "www.example.com", "spec.md.bak"):
            self.assertFalse(matches_credentials(text), text)
        self.assertTrue(matches_credentials("A" * 24 + "." + "b-_c9z" + "." + "C" * 27))
        self.assertTrue(matches_credentials("x " + "A" * 26 + "." + "B" * 6 + "." + "C" * 38))
        self.assertFalse(matches_credentials("A" * 23 + "." + "B" * 6 + "." + "C" * 27))
        self.assertFalse(matches_credentials("A" * 24 + "." + "B" * 7 + "." + "C" * 27))


if __name__ == "__main__":
    unittest.main()
