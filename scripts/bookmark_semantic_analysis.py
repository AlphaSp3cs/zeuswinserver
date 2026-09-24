r"""
Safe bookmark HTML semantic analyzer for:
  C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\loads

Goals:
  1) Never crash on invalid/pathologically-named Windows folders.
  2) Extract folder hierarchy + heading context for each link.
  3) Build richer title/folder semantics.
  4) Produce one canonical report + one machine-readable summary JSON.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlparse

BASE = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\loads")
OUT_REPORT = BASE / "_bookmark_semantic_analysis.txt"
OUT_JSON = BASE / "_bookmark_semantic_summary.json"

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "gad_source", "msclkid", "fbclid", "_gl",
}

LINK_RE = re.compile(r'<DT><A HREF="([^"]+)"[^>]*>([^<]+)</A>', re.IGNORECASE)
HEADING_RE = re.compile(r'<DT><H3[^>]*>([^<]+)</H3>', re.IGNORECASE)


def is_safe_dir_name(name: str) -> bool:
    try:
        # Probe accessibility; Windows throws on truly invalid child names too.
        if any(bad in name for bad in ("\x00", "\n", "\r", "|", '"', "<", ">", "{", "}")):
            return False
        return True
    except Exception:
        return False


def clean_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        qs = [(k, v) for k, v in parse_qsl(parsed.query) if k not in TRACKING_PARAMS]
        return parsed._replace(
            query="&".join(f"{k}={v}" for k, v in qs)
        ).geturl()
    except Exception:
        return url


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def path_semantics(html_path: str, base: Path) -> tuple[list[str], str]:
    rel = Path(html_path).relative_to(base)
    folders = [p for p in rel.parent.parts if p not in (".", base.name)]
    stem = rel.stem
    return folders, stem


# Richer semantic buckets aligned to workflow use.
SEMANTIC_RULES: list[tuple[str, list[str]]] = [
    ("BrokerResearch / Prop Firm", [
        "broker", "prop firm", "prop", "apex", "ftmo", "fundednext", "multi",
        "alpha futures", "hola prime", "athena", "propfirmmatch", "vega",
        "tradingfirm", "capital", "metatrader", "mt5", "cfd",
    ]),
    ("Crypto / On-Chain / Mining", [
        "bitcoin", "btc", "crypto", "halving", "mining", "ethereum", "eth",
        "nicehash", "deephash", "hashlabs", "power law", "mvrv", "altcoin",
    ]),
    ("Equity Screener / Market Data", [
        "finviz", "barchart", "stockanalysis", "intellectia", "premarket",
        "most active", "screener", "futures", "cme", "stock", "equity",
    ]),
    ("Charting / Technical / AI Analysis", [
        "chart", "tradingview", "gptchart", "chartanalyzer", "natum",
        "chartsearcher", "technical", "indicators", "sharpcharts",
    ]),
    ("Macro / Calendar / News Sentiment", [
        "tradingeconomics", "cme", "macro", "calendar", "news",
    ]),
    ("AI Apps / Coding / Automation", [
        "bolt", "buildix", "prorealalgo", "strategyquant", "crawl4ai",
        "coding", "algo", "ea builder", "expert advisor", "ai ", " openai ",
    ]),
    ("Prediction Markets / Regime", [
        "polymarket", "world monitor", "forecaster",
    ]),
    ("Learning / Education / Cert", [
        "course", "udemy", "coursera", "certificate", "education",
        "learn", "master", "snhu", "online degree",
    ]),
    ("Inside Track / Insider / Whale", [
        "openinsider", "whalewisdom", "zacks", "seekingalpha",
        "ark invest", "insider", "13f", "13-F",
    ]),
    ("Corporate Admin / Legal / Tax", [
        "northwestregisteredagent", "incorporation", "sole proprietor",
        "llc formation", "legal", "business entity", "ein ", "irs ",
        "registered agent",
    ]),
    ("Broker Accounts / Login / SSO", [
        "sign in", "signin", "sso.", "enroll-edgar", "auth?",
        "login", "credentials", "filermanagement",
    ]),
    ("Robotics / AI / Science", [
        "robotics", "ibm think", "aws financial services", "machine learning",
        "artificial intelligence",
    ]),
    ("Mining Infrastructure / Hardware", [
        "bitmain", "mining equipment", "asic", "hosting",
    ]),
    ("Video / Content", [
        "youtube.com/watch", "vimeo", "video",
    ]),
]


def classify_item(text: str) -> str:
    blob = (text or "").lower()
    for label, keywords in SEMANTIC_RULES:
        for kw in keywords:
            if kw in blob:
                return label
    return "Unclassified"


def extract_html_links(text: str) -> list[dict]:
    links = []
    seen = set()
    for m in LINK_RE.finditer(text):
        url_raw, title = m.group(1), m.group(2).strip()
        url = clean_url(url_raw)
        key = (url, title)
        if key in seen:
            continue
        seen.add(key)
        links.append({"url": url, "title": title, "domain": domain(url)})
    return links


def extract_headings(text: str) -> list[str]:
    return [h.strip() for h in HEADING_RE.findall(text)]


def analyze_bookmarks() -> dict:
    html_files: list[str] = []
    skipped: list[dict] = []

    for root, dirs, files in os.walk(str(BASE)):
        safe_dirs = []
        for d in dirs:
            if not is_safe_dir_name(d):
                skipped.append({"path": os.path.join(root, d), "reason": "unsafe dir name"})
                continue
            test_path = os.path.join(root, d)
            try:
                # Probe; Windows raises on badly-formed or inaccessible paths.
                os.listdir(test_path)
                safe_dirs.append(d)
            except Exception as exc:
                skipped.append({"path": test_path, "reason": repr(exc)})
        dirs[:] = safe_dirs

        for f in files:
            if f.lower().endswith((".html", ".htm")):
                html_files.append(os.path.join(root, f))

    # First-pass file semantics from path/filename.
    raw_file_bucket_counter: Counter = Counter()
    file_records = []
    file_level_dupes = 0
    size_groups = defaultdict(list)
    for fp in sorted(html_files):
        folders, stem = path_semantics(fp, BASE)
        path_text = " ".join(folders + [stem])
        bucket = classify_item(path_text)
        raw_file_bucket_counter[bucket] += 1
        try:
            size = os.path.getsize(fp)
        except Exception:
            size = -1
        size_groups[size].append(fp)
        file_records.append({
            "path": fp,
            "folders": folders,
            "stem": stem,
            "file_bucket": bucket,
            "size": size,
        })

    dup_size_counts = {sz: paths for sz, paths in size_groups.items() if len(paths) > 1}
    for paths in dup_size_counts.values():
        file_level_dupes += len(paths) - 1

    # Parse link-level structure.
    total_links = 0
    total_headings = 0
    link_bucket_counter: Counter = Counter()
    heading_counter: Counter = Counter()
    link_rows = []
    file_link_counts = Counter()
    file_heading_counts = Counter()

    for rec in file_records:
        fp = rec["path"]
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            skipped.append({"path": fp, "reason": f"read failed: {exc}"})
            continue

        headings = extract_headings(text)
        links = extract_html_links(text)
        file_heading_counts[fp] = len(headings)
        file_link_counts[fp] = len(links)
        total_headings += len(headings)
        total_links += len(links)

        heading_context = " | ".join(headings) if headings else rec["stem"]

        for link in links:
            blob = " ".join([
                link["title"],
                link["domain"],
                rec["stem"],
                heading_context,
                " ".join(rec["folders"]),
            ])
            bucket = classify_item(blob)
            link_bucket_counter[bucket] += 1
            heading_counter[heading_context] += 1
            link_rows.append({
                "file": fp,
                "folders": rec["folders"],
                "file_stem": rec["stem"],
                "heading_path": heading_context,
                "title": link["title"],
                "url": link["url"],
                "domain": link["domain"],
                "link_bucket": bucket,
            })

    # Exact duplicate URLs across files.
    url_to_files = defaultdict(list)
    for row in link_rows:
        url_to_files[row["url"]].append(row["file"])
    duplicate_urls = {u: paths for u, paths in url_to_files.items() if len(paths) > 1}

    # Richer folder-level semantics: summarize keywords per folder.
    folder_keywords = defaultdict(Counter)
    for row in link_rows:
        for folder in row["folders"]:
            words = re.findall(r"[A-Za-z0-9]+", folder.lower())
            folder_keywords[folder].update(words)
    folder_profile = {}
    for folder, ctr in folder_keywords.items():
        top = ", ".join(w for w, _ in ctr.most_common(8))
        folder_profile[folder] = top

    return {
        "meta": {
            "base": str(BASE),
            "html_files_total": len(file_records),
            "total_headings": total_headings,
            "total_links": total_links,
            "skipped_paths": skipped,
            "file_level_dupe_groups": len(dup_size_counts),
            "file_level_dupe_links": file_level_dupes,
            "duplicate_url_groups": len(duplicate_urls),
            "duplicate_url_links": sum(len(v) for v in duplicate_urls.values()),
        },
        "file_buckets": dict(sorted(raw_file_bucket_counter.items())),
        "link_buckets": dict(sorted(link_bucket_counter.items())),
        "top_heading_contexts": dict(heading_counter.most_common(40)),
        "folder_profiles": folder_profile,
        "duplicate_url_examples": {
            u: paths[:5] for u, paths in list(duplicate_urls.items())[:20]
        },
        "large_dupe_groups": {
            str(size): paths[:10] for size, paths in sorted(dup_size_counts.items(), reverse=True)[:10]
        },
    }


def render_report(summary: dict) -> str:
    m = summary["meta"]
    lines = [
        "BOOKMARK SEMANTIC ANALYSIS",
        "=" * 60,
        f"Base: {m['base']}",
        f"HTML files: {m['html_files_total']}",
        f"Total headings: {m['total_headings']}",
        f"Total links: {m['total_links']}",
        f"Skipped paths: {len(m['skipped_paths'])}",
        "",
        "FILE-LEVEL BUCKETS",
        "-" * 60,
    ]
    for k, v in summary["file_buckets"].items():
        lines.append(f"  {k}: {v} files")

    lines += [
        "",
        "LINK-LEVEL SEMANTIC BUCKETS",
        "-" * 60,
    ]
    for k, v in summary["link_buckets"].items():
        lines.append(f"  {k}: {v} links")

    lines += [
        "",
        "TOP HEADING CONTEXTS",
        "-" * 60,
    ]
    for k, v in summary["top_heading_contexts"].items():
        lines.append(f"  {v:4d}  {k}")

    lines += [
        "",
        "FOLDER SEMANTICS",
        "-" * 60,
    ]
    for folder, top in sorted(summary["folder_profiles"].items()):
        lines.append(f"  {folder}: {top}")

    if summary["duplicate_url_examples"]:
        lines += [
            "",
            "DUPLICATE URL EXAMPLES",
            "-" * 60,
        ]
        for u, paths in summary["duplicate_url_examples"].items():
            lines.append(f"  URL: {u}")
            for p in paths:
                lines.append(f"    - {p}")

    if summary["large_dupe_groups"]:
        lines += [
            "",
            "FILE-SIZE DUPLICATE GROUPS",
            "-" * 60,
        ]
        for size, paths in summary["large_dupe_groups"].items():
            lines.append(f"  size {size} bytes, {len(paths)} files")
            for p in paths:
                lines.append(f"    - {p}")

    return "\n".join(lines)


def main() -> None:
    summary = analyze_bookmarks()
    report = render_report(summary)

    OUT_REPORT.write_text(report, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote report: {OUT_REPORT}")
    print(f"wrote json:   {OUT_JSON}")
    print("html_files_total =", summary["meta"]["html_files_total"])
    print("total_links      =", summary["meta"]["total_links"])
    print("skipped_paths    =", len(summary["meta"]["skipped_paths"]))


if __name__ == "__main__":
    main()
