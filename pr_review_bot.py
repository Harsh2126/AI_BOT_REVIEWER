"""
GitHub PR Code Review Bot
Fetches PR diffs, reviews them with Gemini, and posts comments back to GitHub.
"""

import os
import json
import re
import sys
from github import Github
import google.generativeai as genai

# ── Constants ────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.0-flash"
MAX_DIFF_CHARS = 50_000  # Truncate very large diffs to stay within token limits

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
    """Return (pr_object, unified_diff_string)."""
    pr = repo.get_pull(pr_number)
    files = pr.get_files()

    diff_parts = []
    total_chars = 0

    for f in files:
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
    """Post a PR review with inline comments and a summary body."""
    review_comments = []

    # Collect valid commit SHAs for each file to anchor inline comments
    file_to_sha: dict[str, str] = {}
    for f in pr.get_files():
        if f.blob_url:
            # blob_url: https://github.com/owner/repo/blob/<sha>/path
            match = re.search(r"/blob/([a-f0-9]+)/", f.blob_url)
            if match:
                file_to_sha[f.filename] = match.group(1)

    head_sha = pr.head.sha

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
            body=f"## 🤖 Gemini Code Review\n\n{summary}",
            event="COMMENT",
            comments=review_comments,
        )
        print(f"✅ Posted review with {len(review_comments)} inline comment(s).")
    except Exception as e:
        # Fallback: post summary as a plain PR comment if review creation fails
        print(f"⚠️  Inline review failed ({e}), falling back to issue comment.")
        body_lines = [f"## 🤖 Gemini Code Review\n\n{summary}"]
        for c in inline_comments:
            body_lines.append(f"\n**`{c.get('path')}` line {c.get('line')}:** {c.get('comment')}")
        pr.create_issue_comment("\n".join(body_lines))


# ── Gemini helper ────────────────────────────────────────────────────────────

def review_diff_with_gemini(diff: str) -> dict:
    """Send diff to Gemini and return parsed JSON response."""
    model = genai.GenerativeModel(model_name=GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
    response = model.generate_content(f"Please review this PR diff:\n\n```diff\n{diff}\n```")

    raw = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    github_token = os.environ["GITHUB_TOKEN"]
    gemini_key = os.environ["GEMINI_API_KEY"]
    repo_name = os.environ["GITHUB_REPOSITORY"]          # "owner/repo"
    pr_number = int(os.environ["PR_NUMBER"])

    genai.configure(api_key=gemini_key)

    gh = Github(github_token)
    repo = gh.get_repo(repo_name)

    print(f"🔍 Fetching diff for PR #{pr_number} in {repo_name}...")
    pr, diff = get_pr_diff(repo, pr_number)

    if not diff.strip():
        print("No diff found — skipping review.")
        sys.exit(0)

    print("🤖 Sending diff to Gemini for review...")
    result = review_diff_with_gemini(diff)

    summary = result.get("summary", "No summary provided.")
    inline_comments = result.get("inline_comments", [])

    print(f"📝 Review ready: {len(inline_comments)} inline comment(s).")
    post_review(pr, summary, inline_comments)


if __name__ == "__main__":
    main()
