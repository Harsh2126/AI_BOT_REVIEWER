"""
GitHub PR Code Review Bot
Fetches PR diffs, reviews them with Groq, and posts comments back to GitHub.
"""

import os
import json
import re
import sys
import httpx
from github import Github

# ── Constants ────────────────────────────────────────────────────────────────

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_DIFF_CHARS = 50_000

SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the provided PR diff and return a JSON response with:
1. An overall summary of the changes
2. Specific inline comments for issues found

Return ONLY valid JSON in this exact format:
{
  "summary": "Overall assessment of the PR...",
  "inline_comments": [
    {
      "path": "path/to/file.py",
      "line": 42,
      "comment": "Specific issue or suggestion for this line"
    }
  ]
}

Focus on: bugs, security issues, performance problems, and code quality.
Keep comments concise and actionable. Only flag real issues, not style preferences."""


# ── GitHub helpers ────────────────────────────────────────────────────────────

def get_pr_diff(repo, pr_number: int) -> tuple[object, str]:
    pr = repo.get_pull(pr_number)
    diff_parts = []
    total_chars = 0

    for f in pr.get_files():
        header = f"--- a/{f.filename}\n+++ b/{f.filename}\n"
        patch = f.patch or ""
        chunk = header + patch + "\n"

        if total_chars + len(chunk) > MAX_DIFF_CHARS:
            diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n[truncated]\n")
            break

        diff_parts.append(chunk)
        total_chars += len(chunk)

    return pr, "".join(diff_parts)


def post_review(pr, summary: str, inline_comments: list[dict]) -> None:
    review_comments = []

    for item in inline_comments:
        path = item.get("path", "")
        line = item.get("line")
        comment = item.get("comment", "")

        if not (path and line and comment):
            continue

        review_comments.append({
            "path": path,
            "line": int(line),
            "body": comment,
        })

    try:
        pr.create_review(
            commit=pr.get_commits().reversed[0],
            body=f"## 🤖 Groq Code Review\n\n{summary}",
            event="COMMENT",
            comments=review_comments,
        )
        print(f"✅ Posted review with {len(review_comments)} inline comment(s).")
    except Exception as e:
        print(f"⚠️  Inline review failed ({e}), falling back to issue comment.")
        body_lines = [f"## 🤖 Groq Code Review\n\n{summary}"]
        for c in inline_comments:
            body_lines.append(f"\n**`{c.get('path')}` line {c.get('line')}:** {c.get('comment')}")
        pr.create_issue_comment("\n".join(body_lines))


# ── Groq helper ───────────────────────────────────────────────────────────────

def review_diff_with_groq(api_key: str, diff: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Please review this PR diff:\n\n```diff\n{diff}\n```"},
        ],
    }

    response = httpx.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"].strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    github_token = os.environ["GITHUB_TOKEN"]
    groq_key = os.environ["GROQ_API_KEY"]
    repo_name = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])

    gh = Github(github_token)
    repo = gh.get_repo(repo_name)

    print(f"🔍 Fetching diff for PR #{pr_number} in {repo_name}...")
    pr, diff = get_pr_diff(repo, pr_number)

    if not diff.strip():
        print("No diff found — skipping review.")
        sys.exit(0)

    print("🤖 Sending diff to Groq for review...")
    result = review_diff_with_groq(groq_key, diff)

    summary = result.get("summary", "No summary provided.")
    inline_comments = result.get("inline_comments", [])

    print(f"📝 Review ready: {len(inline_comments)} inline comment(s).")
    post_review(pr, summary, inline_comments)


if __name__ == "__main__":
    main()
