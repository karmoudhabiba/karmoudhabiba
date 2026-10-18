#!/usr/bin/env python3
"""Generate an SVG contribution heatmap using GitHub's GraphQL API."""

from __future__ import annotations

import datetime as dt
import os
import sys
import xml.sax.saxutils as xml
from pathlib import Path

import requests

USERNAME = "karmoudhabiba"
GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT = Path("dist/contributions.svg")
COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def contribution_data(token: str) -> tuple[list[dict], int]:
    today = dt.date.today()
    start = today - dt.timedelta(days=364)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """
    response = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "query": query,
            "variables": {
                "login": USERNAME,
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{today.isoformat()}T23:59:59Z",
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + "; ".join(
            error.get("message", "unknown error") for error in payload["errors"]
        ))
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {USERNAME}")
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    return days, calendar["totalContributions"]


def calculate_streaks(days: list[dict]) -> tuple[int, int]:
    active_dates = {
        dt.date.fromisoformat(day["date"])
        for day in days
        if day["contributionCount"] > 0
    }
    longest = current = run = 0
    previous = None
    for day in sorted(active_dates):
        run = run + 1 if previous and day == previous + dt.timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    today = dt.date.today()
    cursor = today if today in active_dates else today - dt.timedelta(days=1)
    while cursor in active_dates:
        current += 1
        cursor -= dt.timedelta(days=1)
    return longest, current


def color_for(count: int, maximum: int) -> str:
    if count == 0:
        return COLORS[0]
    if maximum <= 1:
        return COLORS[4]
    level = min(4, max(1, (count * 4 + maximum - 1) // maximum))
    return COLORS[level]


def generate_svg(days: list[dict], total: int) -> str:
    cell, gap = 11, 3
    left, top = 42, 30
    columns = {}
    for day in days:
        date = dt.date.fromisoformat(day["date"])
        columns.setdefault(date.isocalendar().week, []).append((date, day))

    weeks: list[list[tuple[dt.date, dict]]] = []
    for week in sorted(columns):
        weeks.append(sorted(columns[week], key=lambda item: item[0]))

    max_count = max((day["contributionCount"] for day in days), default=0)
    width = left + max(1, len(weeks)) * (cell + gap) + 8
    height = top + 7 * (cell + gap) + 43
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="8" fill="#0d1117"/>',
        '<g font-family="ui-monospace, SFMono-Regular, Consolas, monospace" fill="#c9d1d9">',
        f'<text x="12" y="18" font-size="11">{total:,} contributions in the last year</text>',
    ]

    month_seen = set()
    for col, week in enumerate(weeks):
        x = left + col * (cell + gap)
        first_date = week[0][0]
        month_key = (first_date.year, first_date.month)
        if month_key not in month_seen and first_date.day <= 7:
            parts.append(
                f'<text x="{x}" y="27" font-size="9">{xml.escape(first_date.strftime("%b"))}</text>'
            )
            month_seen.add(month_key)

        for date, day in week:
            y = top + date.weekday() * (cell + gap)
            count = int(day["contributionCount"])
            tooltip = xml.escape(f"{count} contributions on {date.isoformat()}", {'"': "&quot;"})
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{color_for(count, max_count)}"><title>{tooltip}</title></rect>'
            )

    for weekday, label in [(0, "Mon"), (2, "Wed"), (4, "Fri")]:
        y = top + weekday * (cell + gap) + 9
        parts.append(f'<text x="7" y="{y}" font-size="9">{label}</text>')

    longest, current = calculate_streaks(days)
    summary_y = top + 7 * (cell + gap) + 20
    parts.append(
        f'<text x="12" y="{summary_y}" font-size="10">'
        f'Current streak: {current} day(s)  |  Longest streak: {longest} day(s)</text>'
    )
    legend_y = summary_y + 18
    parts.append(f'<text x="{width - 142}" y="{legend_y}" font-size="9" fill="#8b949e">Less</text>')
    for index, color in enumerate(COLORS):
        parts.append(
            f'<rect x="{width - 111 + index * 14}" y="{legend_y - 9}" width="10" height="10" '
            f'rx="2" fill="{color}"/>'
        )
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts)


def main() -> int:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        print("Missing GH_TOKEN/GITHUB_TOKEN. Set a token with permission to read user contributions.", file=sys.stderr)
        return 1
    try:
        days, total = contribution_data(token)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(generate_svg(days, total), encoding="utf-8")
        print(f"Generated {OUTPUT} for {USERNAME}: {total} contributions.")
        return 0
    except (requests.RequestException, KeyError, TypeError, RuntimeError, ValueError) as exc:
        print(f"Failed to generate contribution heatmap: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
