#!/usr/bin/env python3
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel


console = Console()
CONFIG_PATH = Path("config.json")


def load_config():
    if not CONFIG_PATH.exists():
        console.print("[red]Error: config.json not found.[/red]")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def main():
    config = load_config()
    login_config = config.get("login", {})
    upload_url = config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact")

    console.print(Panel(
        "[bold green]Contact List Viewer[/bold green]\n"
        "This opens the Help2Rent contact-list area for inspection only.\n"
        "It does not upload files, submit forms, or move spreadsheets.",
        border_style="green",
    ))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        if login_config.get("required", False):
            page.goto(login_config.get("url", "https://www.help2rent.co.uk/login"))
            if login_config.get("username") and login_config.get("password"):
                try:
                    console.print("[cyan]Logging in...[/cyan]")
                    page.fill(login_config.get("username_selector"), login_config.get("username"))
                    page.fill(login_config.get("password_selector"), login_config.get("password"))
                    page.click(login_config.get("submit_selector"))
                    page.wait_for_load_state("networkidle")
                except Exception as e:
                    console.print(f"[yellow]Automatic login did not complete: {e}[/yellow]")
                    console.print("[yellow]Please log in manually in the browser window.[/yellow]")
                    input("Press Enter here after login is complete...")

        console.print(f"[cyan]Opening contact-list area: {upload_url}[/cyan]")
        page.goto(upload_url)
        page.wait_for_load_state("networkidle")

        console.print(Panel(
            "The browser is open for testing.\n"
            "Use it to inspect contact lists and search for names.\n"
            "Press Enter in this terminal when you are finished to close it.",
            border_style="yellow",
        ))
        input("Press Enter to close the testing browser...")
        browser.close()


if __name__ == "__main__":
    main()
