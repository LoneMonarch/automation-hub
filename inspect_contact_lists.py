#!/usr/bin/env python3
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()
CONFIG_PATH = Path("config.json")
REPORT_DIR = Path("contact-list-inspection")


def load_config():
    if not CONFIG_PATH.exists():
        console.print("[red]Error: config.json not found.[/red]")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def extract_visible_tables(page):
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('table')).map((table, tableIndex) => {
          const rows = Array.from(table.querySelectorAll('tr')).map((tr) =>
            Array.from(tr.querySelectorAll('th,td')).map((cell) => cell.innerText.trim())
          ).filter((row) => row.some(Boolean));
          return { tableIndex, rows };
        }).filter((table) => table.rows.length);
        """
    )


def extract_candidate_names_from_tables(tables):
    names = []
    for table in tables:
        rows = table.get("rows", [])
        if not rows:
            continue

        header = [clean_text(cell).lower() for cell in rows[0]]
        name_indexes = [
            i for i, cell in enumerate(header)
            if any(term in cell for term in ["name", "title", "contact", "list"])
        ]
        if not name_indexes:
            name_indexes = [0]

        for row in rows[1:]:
            for index in name_indexes:
                if index < len(row):
                    value = clean_text(row[index])
                    if value and value.lower() not in {"name", "title", "contact", "list"}:
                        names.append(value)
    return names


def extract_candidate_names_from_links(links):
    names = []
    for link in links:
        href = link.get("href", "")
        text = clean_text(link.get("text", ""))
        if "/marketing/contactlist/" not in href:
            continue
        if text:
            names.append(text)
    return names


def extract_page_snapshot(page):
    return {
        "url": page.url,
        "title": page.title(),
        "body_text": clean_text(page.locator("body").inner_text(timeout=5000)),
        "links": page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a[href]')).map((a) => ({
              text: a.innerText.trim(),
              href: a.href
            })).filter((a) => a.text || a.href)
            """
        ),
        "tables": extract_visible_tables(page),
    }


def save_report(snapshot, names):
    REPORT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_DIR / f"contact-list-snapshot-{timestamp}.json"
    csv_path = REPORT_DIR / f"contact-list-names-{timestamp}.csv"

    with open(json_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["contact_list_name"])
        for name in sorted(set(names), key=str.lower):
            writer.writerow([name])

    return json_path, csv_path


def login(page, login_config):
    page.goto(login_config.get("url", "https://www.help2rent.co.uk/login"))
    if login_config.get("username") and login_config.get("password"):
        console.print("[cyan]Logging in...[/cyan]")
        page.fill(login_config.get("username_selector"), login_config.get("username"))
        page.fill(login_config.get("password_selector"), login_config.get("password"))
        page.click(login_config.get("submit_selector"))
        page.wait_for_load_state("networkidle")


def main():
    config = load_config()
    login_config = config.get("login", {})
    target_url = config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact")

    console.print(Panel(
        "[bold green]Contact List Inspector[/bold green]\n"
        "Read-only Playwright scan. It does not upload files or submit forms.",
        border_style="green",
    ))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        if login_config.get("required", False):
            login(page, login_config)

        console.print(f"[cyan]Opening: {target_url}[/cyan]")
        page.goto(target_url)
        page.wait_for_load_state("networkidle")

        snapshot = extract_page_snapshot(page)
        names = (
            extract_candidate_names_from_tables(snapshot["tables"])
            + extract_candidate_names_from_links(snapshot["links"])
        )
        json_path, csv_path = save_report(snapshot, names)

        table = Table(title="Inspection Result", border_style="cyan")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("URL", snapshot["url"])
        table.add_row("Page title", snapshot["title"])
        table.add_row("Tables found", str(len(snapshot["tables"])))
        table.add_row("Candidate names found", str(len(set(names))))
        table.add_row("JSON report", str(json_path))
        table.add_row("CSV names", str(csv_path))
        console.print(table)

        if names:
            preview = sorted(set(names), key=str.lower)[:30]
            console.print("\n[bold]First candidate names:[/bold]")
            for name in preview:
                console.print(f"  - {name}")
        else:
            console.print("[yellow]No table-based contact-list names found on this page.[/yellow]")
            console.print("[yellow]The JSON report includes page links so we can identify the correct listing page.[/yellow]")

        browser.close()


if __name__ == "__main__":
    main()
