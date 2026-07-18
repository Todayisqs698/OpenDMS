"""Match user question to relevant CodeBanana doc pages using keyword scoring.

Usage:
    python match_pages.py "<user question>"

Output:
    One line per match: <id>|<title>|<url>
    Up to 3 results, sorted by score descending.
    Prints NO_MATCH if nothing scores above 0.
"""
import json
import os
import re
import sys


def score_page(page, question_lower, tokens):
    score = 0

    # Keywords: +2 per keyword that appears in the question
    for kw in page["keywords"]:
        if kw.lower() in question_lower:
            score += 2

    # Aliases: +3 per alias phrase that appears in the question
    for alias in page.get("aliases", []):
        if alias.lower() in question_lower:
            score += 3

    # Title words: +2 if any title word appears in tokens
    title_tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', page["title"].lower()))
    if title_tokens & set(tokens):
        score += 2

    return score


def main():
    if len(sys.argv) < 2:
        print("Usage: match_pages.py '<question>'", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    question_lower = question.lower()
    tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', question_lower))

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pages_path = os.path.join(skill_dir, "references", "pages.json")

    with open(pages_path, encoding="utf-8") as f:
        pages = json.load(f)

    scored = []
    for page in pages:
        s = score_page(page, question_lower, tokens)
        if s > 0:
            scored.append((s, page))

    scored.sort(key=lambda x: -x[0])
    top = scored[:3]

    if not top:
        print("NO_MATCH")
        return

    for _, page in top:
        print(f"{page['id']}|{page['title']}|{page['url']}")


if __name__ == "__main__":
    main()
