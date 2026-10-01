"""Notification channels, all configured through environment variables.

  ntfy (phone push):  NTFY_TOPIC, optional NTFY_SERVER, NTFY_TOKEN
  email (SMTP):       SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
                      EMAIL_TO, optional EMAIL_FROM
  GitHub issue:       GITHUB_TOKEN + GITHUB_REPOSITORY (set automatically in
                      Actions). Opening an issue that @mentions the repo
                      owner makes GitHub send its own email/app notification.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage


class Notifier:
    def __init__(self, env: dict | None = None, dry_run: bool = False):
        env = dict(os.environ if env is None else env)
        self.dry_run = dry_run
        self.ntfy_topic = env.get("NTFY_TOPIC", "").strip()
        self.ntfy_server = (env.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        self.ntfy_token = env.get("NTFY_TOKEN", "").strip()
        self.smtp = {k: env.get(k, "").strip() for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_TO", "EMAIL_FROM")}
        self.github_token = env.get("GITHUB_TOKEN", "").strip()
        self.github_repo = env.get("GITHUB_REPOSITORY", "").strip()
        self.github_owner = env.get("GITHUB_REPOSITORY_OWNER", "").strip() or self.github_repo.split("/")[0]
        self.github_api = (env.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
        self.issues_enabled = env.get("GITHUB_ISSUE_ALERTS", "true").strip().lower() not in ("false", "0", "no", "off")

    # -- what is configured -------------------------------------------------
    @property
    def has_email(self) -> bool:
        return bool(self.smtp["SMTP_HOST"] and self.smtp["EMAIL_TO"])

    @property
    def has_issues(self) -> bool:
        return bool(self.issues_enabled and self.github_token and self.github_repo)

    def channels(self) -> list[str]:
        names = []
        if self.ntfy_topic:
            names.append("ntfy")
        if self.has_email:
            names.append("email")
        if self.has_issues:
            names.append("github-issue")
        return names

    # -- push + email -------------------------------------------------------
    def send(self, title: str, message: str, url: str = "", priority: int = 3, tags: tuple = ()) -> bool:
        """Send via ntfy and email. True if at least one of them delivered."""
        print(f"\n=== NOTIFY: {title}\n{message}\n")
        if self.dry_run:
            return True
        delivered = 0
        if self.ntfy_topic:
            delivered += self._try("ntfy", self._ntfy, title, message, url, priority, tags)
        if self.has_email:
            delivered += self._try("email", self._email, title, message + (f"\n\n{url}" if url else ""))
        return delivered > 0

    def _try(self, name, fn, *args) -> int:
        try:
            fn(*args)
            print(f"  sent via {name}")
            return 1
        except Exception as exc:
            print(f"  {name} failed: {exc}")
            return 0

    def _ntfy(self, title, message, url, priority, tags):
        payload = {"topic": self.ntfy_topic, "title": title, "message": message, "priority": priority, "tags": list(tags)}
        if url:
            payload["click"] = url
            payload["actions"] = [{"action": "view", "label": "Open", "url": url}]
        headers = {"Content-Type": "application/json"}
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"
        req = urllib.request.Request(self.ntfy_server, json.dumps(payload).encode(), headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()

    def _email(self, subject, body):
        s = self.smtp
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s["EMAIL_FROM"] or s["SMTP_USERNAME"] or s["EMAIL_TO"]
        msg["To"] = s["EMAIL_TO"]
        msg.set_content(body)
        port = int(s["SMTP_PORT"] or 587)
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(s["SMTP_HOST"], port, context=ctx, timeout=30)
        else:
            server = smtplib.SMTP(s["SMTP_HOST"], port, timeout=30)
            server.starttls(context=ctx)
        with server:
            if s["SMTP_USERNAME"]:
                server.login(s["SMTP_USERNAME"], s["SMTP_PASSWORD"])
            server.send_message(msg)

    # -- GitHub issues --------------------------------------------------------
    def open_issue(self, issues: dict, key: str, title: str, body: str) -> bool:
        """Open an issue for `key`, or comment on the one already open."""
        if not self.has_issues or self.dry_run:
            return False
        mention = f"@{self.github_owner} " if self.github_owner else ""
        try:
            number = issues.get(key)
            if number:
                self._github("POST", f"/issues/{number}/comments", {"body": mention + body})
            else:
                issue = self._github("POST", "/issues", {"title": title, "body": mention + body})
                issues[key] = issue["number"]
            print(f"  GitHub issue #{issues[key]} updated")
            return True
        except Exception as exc:
            print(f"  GitHub issue failed: {exc}")
            return False

    def close_issue(self, issues: dict, key: str, comment: str) -> None:
        number = issues.pop(key, None)
        if not number or not self.has_issues or self.dry_run:
            return
        try:
            self._github("POST", f"/issues/{number}/comments", {"body": comment})
            self._github("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
        except Exception as exc:
            print(f"  closing GitHub issue #{number} failed: {exc}")

    def _github(self, method: str, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.github_api}/repos/{self.github_repo}{path}",
            json.dumps(payload).encode(),
            {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
