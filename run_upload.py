#!/usr/bin/env python3
import os
import sys
import json
import csv
import shutil
import time
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import print as rprint

# Initialize Rich Console
console = Console()

# Configuration file path
CONFIG_PATH = Path("config.json")

def as_bool(value, default=False):
    """Converts config/env values like true, 1, yes into booleans."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def setting_bool(settings, name, default=False, env_name=None):
    """Reads a boolean setting, allowing an environment variable override."""
    if env_name and env_name in os.environ:
        return as_bool(os.environ.get(env_name), default)
    return as_bool(settings.get(name), default)

def setting_int(settings, name, default):
    """Reads an integer setting with a safe fallback."""
    try:
        return int(settings.get(name, default))
    except (TypeError, ValueError):
        return default

def safe_artifact_name(value):
    """Makes filenames safe for screenshots, HTML dumps, and reports."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned[:120] or "upload"

def prompt_settings_gui(current_url, current_tag, current_officer):
    """
    Displays a Tkinter popup window to let the user configure the run.
    Returns: (website_url, tag_to_select, officer_to_select, save_as_default, start_run)
    """
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        return None  # Fallback to CLI

    # Create root
    root = tk.Tk()
    root.title("Upload Automator Settings")
    root.geometry("480x340")
    root.resizable(False, False)
    
    # Center the window on the screen
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    # Apply nice styling
    style = ttk.Style()
    style.theme_use('clam')
    
    # Configure colors/fonts
    bg_color = "#f5f5f7" # Apple-like light gray
    root.configure(bg=bg_color)
    
    style.configure("TLabel", background=bg_color, font=("Helvetica", 11))
    style.configure("Header.TLabel", font=("Helvetica", 14, "bold"), foreground="#1d1d1f")
    style.configure("TButton", font=("Helvetica", 11))
    style.configure("TCheckbutton", background=bg_color, font=("Helvetica", 11))

    # Title Banner
    banner = ttk.Label(root, text="Configure Upload Settings", style="Header.TLabel")
    banner.pack(pady=(20, 15))

    # Main Form Frame
    frame = ttk.Frame(root, padding="10 10 10 10")
    frame.pack(fill=tk.BOTH, expand=True)
    
    # Grid configuration
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=3)

    # URL
    ttk.Label(frame, text="Website URL:").grid(row=0, column=0, sticky="e", padx=5, pady=8)
    url_var = tk.StringVar(value=current_url)
    url_entry = ttk.Entry(frame, textvariable=url_var, width=35)
    url_entry.grid(row=0, column=1, sticky="w", padx=5, pady=8)

    # Tag
    ttk.Label(frame, text="Tag option:").grid(row=1, column=0, sticky="e", padx=5, pady=8)
    tag_var = tk.StringVar(value=current_tag)
    tag_entry = ttk.Entry(frame, textvariable=tag_var, width=35)
    tag_entry.grid(row=1, column=1, sticky="w", padx=5, pady=8)

    # Officer
    ttk.Label(frame, text="Officer/Admin:").grid(row=2, column=0, sticky="e", padx=5, pady=8)
    officer_var = tk.StringVar(value=current_officer)
    officer_entry = ttk.Entry(frame, textvariable=officer_var, width=35)
    officer_entry.grid(row=2, column=1, sticky="w", padx=5, pady=8)

    # Save Checkbox
    save_var = tk.BooleanVar(value=False)
    save_cb = ttk.Checkbutton(frame, text="Save these values as defaults in config.json", variable=save_var)
    save_cb.grid(row=3, column=0, columnspan=2, pady=(15, 5))

    # Action Buttons Frame
    btn_frame = ttk.Frame(root, padding="0 10 0 20")
    btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

    # State variables
    result = {
        "url": current_url,
        "tag": current_tag,
        "officer": current_officer,
        "save": False,
        "start": False
    }

    def on_start():
        result["url"] = url_var.get().strip()
        result["tag"] = tag_var.get().strip()
        result["officer"] = officer_var.get().strip()
        result["save"] = save_var.get()
        result["start"] = True
        root.destroy()

    def on_cancel():
        root.destroy()

    # Buttons
    cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
    cancel_btn.pack(side=tk.RIGHT, padx=(10, 30))

    start_btn = ttk.Button(btn_frame, text="Start Uploads", command=on_start)
    start_btn.pack(side=tk.RIGHT, padx=10)

    # Bind Enter key to on_start
    root.bind('<Return>', lambda event: on_start())
    root.bind('<Escape>', lambda event: on_cancel())

    root.mainloop()
    
    return result

def get_run_settings(config):
    settings = config.get("settings", {})
    current_url = config.get("website_url", "")
    current_tag = settings.get("tag_to_select", "")
    current_officer = settings.get("officer_to_select", "")

    if os.environ.get("SKIP_SETTINGS_PROMPT") == "1":
        console.print("[cyan]Using config.json settings without opening the settings popup.[/cyan]")
        return current_url, current_tag, current_officer
    
    gui_result = None
    try:
        gui_result = prompt_settings_gui(current_url, current_tag, current_officer)
    except Exception as e:
        console.print(f"[yellow]Could not load popup GUI ({e}). Falling back to terminal prompt...[/yellow]")
        
    if gui_result:
        if gui_result["start"]:
            url = gui_result["url"]
            tag = gui_result["tag"]
            officer = gui_result["officer"]
            
            # Update config in-memory
            config["website_url"] = url
            config["settings"]["tag_to_select"] = tag
            config["settings"]["officer_to_select"] = officer
            
            # Save as defaults if checked
            if gui_result["save"]:
                save_config(config)
                console.print("[green]✓ Settings saved to config.json as defaults.[/green]")
            return url, tag, officer
        else:
            # User cancelled or closed the window
            console.print("[yellow]Execution cancelled by user. Exiting.[/yellow]")
            sys.exit(0)
    else:
        # CLI fallback
        console.print(f"\n[bold]Current Run Settings:[/bold]")
        console.print(f"• Target Website:  [cyan]{current_url}[/cyan]")
        console.print(f"• Tag to Choose:   [yellow]{current_tag}[/yellow]")
        console.print(f"• Officer Name:    [yellow]{current_officer}[/yellow]")
        
        change_settings = Confirm.ask("\nWould you like to temporarily change settings for this run?")
        if change_settings:
            url = Prompt.ask("Enter Website URL", default=current_url)
            tag = Prompt.ask("Enter Tag name to select", default=current_tag)
            officer = Prompt.ask("Enter Officer/Admin name to select", default=current_officer)
            
            config["website_url"] = url
            config["settings"]["tag_to_select"] = tag
            config["settings"]["officer_to_select"] = officer
            
            save_defaults = Confirm.ask("Save these values as defaults in config.json?")
            if save_defaults:
                save_config(config)
            return url, tag, officer
        return current_url, current_tag, current_officer

def load_config():
    """Loads configuration from config.json, creating a template if missing."""
    if not CONFIG_PATH.exists():
        console.print("[red]Error: config.json not found![/red]")
        sys.exit(1)
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[red]Error reading config.json: {e}[/red]")
        sys.exit(1)

def save_config(config):
    """Saves updated configuration back to config.json."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save configuration changes: {e}[/yellow]")

def setup_directories(settings):
    """Ensures input, uploaded, failed, report, and error artifact folders exist."""
    input_folder = Path(settings.get("input_folder", "contacts-to-upload"))
    source_folder = Path(settings.get("source_folder") or input_folder)
    uploaded_folder = Path(settings.get("uploaded_folder", "contacts-to-upload/uploaded"))
    failed_folder = Path(settings.get("failed_folder", "contacts-to-upload/failed"))
    reports_folder = Path(settings.get("reports_folder", "contacts-to-upload/reports"))
    errors_folder = Path(settings.get("errors_folder", "contacts-to-upload/errors"))

    input_folder.mkdir(parents=True, exist_ok=True)
    source_folder.mkdir(parents=True, exist_ok=True)
    uploaded_folder.mkdir(parents=True, exist_ok=True)
    failed_folder.mkdir(parents=True, exist_ok=True)
    reports_folder.mkdir(parents=True, exist_ok=True)
    errors_folder.mkdir(parents=True, exist_ok=True)

    return input_folder, source_folder, uploaded_folder, failed_folder, reports_folder, errors_folder

def log_message(log_file_path, message):
    """Logs a timestamped message to both the console and log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    console.print(message)
    try:
        with open(log_file_path, "a") as f:
            f.write(formatted_message + "\n")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not write to log file: {e}[/yellow]")

def select_dropdown_option(page, selector, option_text, timeout_ms=5000):
    """
    Selects an option from a dropdown. Handles standard HTML <select> elements 
    and common custom dropdown layouts (div, span, li) by supporting case-insensitive 
    partial matching (substring).
    """
    try:
        # Wait for the element to be present
        page.wait_for_selector(selector, timeout=timeout_ms)
        locator = page.locator(selector).first
        
        # Check tag name
        tag_name = locator.evaluate("el => el.tagName.toLowerCase()")
        search_text = option_text.lower()
        
        if tag_name == "select":
            # Standard select: Find the child option element that contains option_text case-insensitively
            options = locator.locator("option").all()
            matching_option = None
            
            for opt in options:
                opt_text = opt.inner_text().strip().lower()
                opt_value = opt.get_attribute("value")
                opt_value_lower = opt_value.lower() if opt_value else ""
                
                if search_text in opt_text or search_text in opt_value_lower:
                    matching_option = opt
                    break
            
            if matching_option:
                full_val = matching_option.get_attribute("value")
                full_label = matching_option.inner_text().strip()
                try:
                    locator.select_option(value=full_val)
                    return True
                except Exception:
                    try:
                        locator.select_option(label=full_label)
                        return True
                    except Exception as e:
                        raise Exception(f"Found option '{full_label}' but failed to select it: {e}")
            else:
                # Compile a list of available options to print in the error for debugging
                available = [opt.inner_text().strip() for opt in options if opt.inner_text().strip()]
                raise Exception(f"No option matching '{option_text}' found. Available options: {', '.join(available)}")
        else:
            # Custom dropdown (like a div or button styled as a dropdown)
            # Click the dropdown selector to open it
            locator.click()
            time.sleep(0.5)  # Wait brief moment for animations/render
            
            # Look for common elements containing the partial text case-insensitively
            options_locators = [
                page.locator("[role='option']"),
                page.locator("li"),
                page.locator("div"),
                page.locator("span")
            ]
            
            for loc in options_locators:
                candidates = loc.all()
                for cand in candidates:
                    try:
                        if cand.is_visible():
                            cand_text = cand.inner_text().strip().lower()
                            if search_text in cand_text:
                                cand.click()
                                return True
                    except Exception:
                        continue
                        
            # If that didn't work, try clicking the text directly using Playwright's default substring selector
            try:
                target = page.locator(f"text={option_text}").first
                if target.is_visible():
                    target.click()
                    return True
            except Exception:
                pass
                
            raise Exception(f"Could not find a dropdown option containing '{option_text}'.")
            
    except Exception as e:
        raise Exception(f"Dropdown selection failed for selector '{selector}' and value '{option_text}': {str(e)}")

def clean_borough_name(stem):
    """Converts a file stem like 'Croydon_list-2026' to 'Croydon list 2026'."""
    return stem.replace("_", " ").replace("-", " ").strip()

def load_historical_upload_names(log_file_path):
    """Reads prior successful upload names from the local audit log."""
    if not log_file_path.exists():
        return set()

    names = set()
    success_pattern = re.compile(r"SUCCESS: Uploaded '.*?' as '(.*?)'\.")
    try:
        with open(log_file_path, "r") as f:
            for line in f:
                match = success_pattern.search(line)
                if match:
                    names.add(match.group(1).strip().lower())
    except Exception as e:
        console.print(f"[yellow]Warning: Could not read upload history: {e}[/yellow]")

    return names

def next_available_upload_name(base_name, used_names):
    """Returns base_name, or base_name 1/2/3, based on names already used locally."""
    candidate = base_name
    suffix = 1

    while candidate.lower() in used_names:
        candidate = f"{base_name} {suffix}"
        suffix += 1

    used_names.add(candidate.lower())
    return candidate

def discover_spreadsheets(input_folder, uploaded_folder, failed_folder, reports_folder=None, errors_folder=None):
    """Finds .xlsx files in the input folder and group subfolders."""
    excluded_dirs = {uploaded_folder.resolve(), failed_folder.resolve()}
    if reports_folder:
        excluded_dirs.add(reports_folder.resolve())
    if errors_folder:
        excluded_dirs.add(errors_folder.resolve())
    files = []

    for path in input_folder.rglob("*.xlsx"):
        resolved_parents = {parent.resolve() for parent in path.parents}
        if resolved_parents.intersection(excluded_dirs):
            continue
        if any(part.startswith(".") for part in path.relative_to(input_folder).parts):
            continue
        files.append(path)

    return sorted(files, key=lambda p: str(p.relative_to(input_folder)).lower())

def archived_group_folder_name(folder_name):
    """Formats a source group folder name for uploaded/failed archives."""
    normalized = folder_name.strip().lower()
    if normalized.endswith("files"):
        return folder_name
    if "spreadsheet" in normalized:
        return f"{folder_name} files"
    return f"{folder_name} spreadsheet files"

def destination_for_file(file_path, input_folder, destination_root):
    """Moves processed files into a formatted matching archive group folder."""
    relative_parent = file_path.relative_to(input_folder).parent
    if relative_parent == Path("."):
        destination_folder = destination_root
    else:
        archived_parts = list(relative_parent.parts)
        archived_parts[-1] = archived_group_folder_name(archived_parts[-1])
        destination_folder = destination_root.joinpath(*archived_parts)
    destination_folder.mkdir(parents=True, exist_ok=True)

    destination_path = destination_folder / file_path.name
    if not destination_path.exists():
        return destination_path

    suffix = 1
    while True:
        candidate = destination_folder / f"{file_path.stem} {suffix}{file_path.suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1

def is_excel_file_readable(file_path):
    """
    Performs a lightweight XLSX integrity check.
    XLSX files are ZIP containers, so this catches empty/corrupt files before browser upload.
    """
    import zipfile

    if file_path.stat().st_size == 0:
        return False, "File is empty."

    try:
        with zipfile.ZipFile(file_path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                return False, f"Excel archive contains a corrupt member: {bad_member}"
            required_members = {"[Content_Types].xml", "xl/workbook.xml"}
            missing = required_members.difference(set(archive.namelist()))
            if missing:
                return False, f"Excel archive is missing expected member(s): {', '.join(sorted(missing))}"
    except zipfile.BadZipFile:
        return False, "File is not a valid .xlsx ZIP archive."
    except Exception as e:
        return False, f"Could not validate Excel file: {e}"

    return True, ""

def limited_files_for_run(xlsx_files, settings):
    """Applies the configured per-run upload cap."""
    try:
        max_files = int(settings.get("max_files_per_run", 0) or 0)
    except (TypeError, ValueError):
        max_files = 0

    if max_files <= 0 or len(xlsx_files) <= max_files:
        return xlsx_files, len(xlsx_files), 0

    return xlsx_files[:max_files], len(xlsx_files), len(xlsx_files) - max_files

def write_csv_report(path, rows, fieldnames):
    """Writes a list of dictionaries as a CSV report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def write_dry_run_report(reports_folder, xlsx_files, input_folder, settings, used_upload_names, website_names=None):
    """Creates a preview CSV showing what would be uploaded and how it would be named."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = reports_folder / f"dry-run-{timestamp}.csv"
    preview_names = set(used_upload_names)
    website_names = website_names or set()
    rows = []

    for i, file_path in enumerate(xlsx_files, 1):
        base_name = f"{clean_borough_name(file_path.stem)} upload"
        proposed_name = next_available_upload_name(base_name, preview_names)
        valid, validation_error = is_excel_file_readable(file_path)
        rows.append({
            "order": i,
            "file": str(file_path.relative_to(input_folder)),
            "base_upload_name": base_name,
            "proposed_upload_name": proposed_name,
            "name_already_on_website": str(base_name.lower() in website_names).lower(),
            "tag": settings.get("tag_to_select", ""),
            "officer": settings.get("officer_to_select", ""),
            "xlsx_valid": str(valid).lower(),
            "validation_error": validation_error,
        })

    write_csv_report(report_path, rows, [
        "order",
        "file",
        "base_upload_name",
        "proposed_upload_name",
        "name_already_on_website",
        "tag",
        "officer",
        "xlsx_valid",
        "validation_error",
    ])
    return report_path

def detect_submission_result(page, selectors):
    """Classifies the post-submit page state."""
    success_selector = selectors.get("success_indicator")
    if success_selector:
        try:
            page.wait_for_selector(success_selector, timeout=5000)
            return "success", ""
        except Exception:
            return "error", f"Success indicator element ({success_selector}) did not appear."

    page_text = page.locator("body").inner_text().lower()
    duplicate_terms = [
        "already exist",
        "already exists",
        "already been taken",
        "already used",
        "existing contact list",
        "contact list with this name",
        "list with this name",
        "name already",
        "duplicate",
    ]
    success_terms = ["success", "uploaded", "complete", "done", "saved", "added"]
    error_terms = [
        "error",
        "fail",
        "invalid",
        "required",
        "wrong",
        "could not",
        "unable",
        "validation",
    ]

    if any(term in page_text for term in duplicate_terms):
        return "duplicate", "The website says a contact list with this name already exists."
    if any(term in page_text for term in success_terms):
        return "success", ""
    if any(term in page_text for term in error_terms):
        return "error", "Page contents suggest a validation or submission error occurred."

    return "success", ""

def load_website_contact_list_names(page):
    """Reads existing contact list names from the current Help2Rent marketing page."""
    try:
        names = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a[href]'))
              .filter((a) => a.href.includes('/marketing/contactlist/'))
              .map((a) => a.innerText.trim())
              .filter(Boolean)
            """
        )
        return {name.strip().lower() for name in names if name.strip()}
    except Exception as e:
        console.print(f"[yellow]Warning: Could not scan website contact-list names: {e}[/yellow]")
        return set()

def verify_upload_name_on_website(page, upload_url, upload_name, timeout_seconds=30):
    """Reloads the contact-list area and checks whether the expected upload name exists."""
    deadline = time.time() + timeout_seconds
    expected = upload_name.strip().lower()
    last_seen_count = 0

    while time.time() < deadline:
        try:
            page.goto(upload_url)
            page.wait_for_load_state("networkidle")
            names = load_website_contact_list_names(page)
            last_seen_count = len(names)
            if expected in names:
                return True, names
        except Exception:
            pass
        time.sleep(2)

    return False, set()

def save_error_artifacts(page, errors_folder, relative_file_name, upload_name):
    """Saves a screenshot and HTML dump for troubleshooting a failed upload."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = safe_artifact_name(f"{timestamp}-{Path(relative_file_name).stem}-{upload_name}")
    screenshot_path = errors_folder / f"{base_name}.png"
    html_path = errors_folder / f"{base_name}.html"

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save failure screenshot: {e}[/yellow]")
        screenshot_path = None

    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save failure HTML: {e}[/yellow]")
        html_path = None

    return screenshot_path, html_path

def run_automation():
    config = load_config()
    settings = config.get("settings", {})
    selectors = config.get("selectors", {})
    login_config = config.get("login", {})
    run_mode = os.environ.get("RUN_MODE", settings.get("run_mode", "normal")).strip().lower()
    fresh_reupload = run_mode in {"fresh_reupload", "reupload", "fresh"}
    dry_run = setting_bool(settings, "dry_run", False, "DRY_RUN")
    verify_after_upload = setting_bool(settings, "verify_after_upload", True, "VERIFY_AFTER_UPLOAD")
    max_file_attempts = max(1, setting_int(settings, "max_file_attempts", 2))
    verify_timeout_seconds = max(5, setting_int(settings, "verify_timeout_seconds", 30))
    
    input_folder, source_folder, uploaded_folder, failed_folder, reports_folder, errors_folder = setup_directories(settings)
    log_file_path = input_folder / "upload_log.txt"
    if fresh_reupload:
        used_upload_names = set()
        console.print("[cyan]Fresh re-upload mode is active: local upload_log.txt history will not affect new names.[/cyan]")
    else:
        used_upload_names = load_historical_upload_names(log_file_path)

    console.print(Panel(
        "[bold green]Contact List Upload Automator[/bold green]\n"
        "This tool automatically uploads Excel spreadsheet lists to your designated website.",
        border_style="green"
    ))

    # Scan for spreadsheets directly in contacts-to-upload and inside group folders.
    all_xlsx_files = discover_spreadsheets(source_folder, uploaded_folder, failed_folder, reports_folder, errors_folder)
    xlsx_files, total_pending_count, remaining_after_run = limited_files_for_run(all_xlsx_files, settings)
    
    if not xlsx_files:
        console.print(Panel(
            f"[yellow]No .xlsx files found in: [bold]{source_folder}[/bold][/yellow]\n"
            f"Please copy the Excel files you want to upload into [bold]{source_folder}[/bold] and run the script again.",
            title="Empty Folder",
            border_style="yellow"
        ))
        sys.exit(0)

    if remaining_after_run:
        console.print(Panel(
            f"[yellow]Found {total_pending_count} pending spreadsheets.[/yellow]\n"
            f"This run will upload the first [bold]{len(xlsx_files)}[/bold] files based on "
            f"`max_files_per_run`, leaving [bold]{remaining_after_run}[/bold] for later runs.",
            title="Batch Limit",
            border_style="yellow"
        ))

    # Summarize spreadsheets to upload
    table_title = "Pending Uploads (Dry Run)" if dry_run else "Pending Uploads"
    table = Table(title=table_title, border_style="cyan")
    table.add_column("File Name", style="cyan")
    table.add_column("Group Folder", style="green")
    table.add_column("Proposed Name Field", style="magenta")
    table.add_column("XLSX Check", style="yellow")
    preview_names = set(used_upload_names)
    for f in xlsx_files:
        proposed_name = next_available_upload_name(f"{clean_borough_name(f.stem)} upload", preview_names)
        group_folder = str(f.relative_to(source_folder).parent)
        if group_folder == ".":
            group_folder = "(main folder)"
        valid, validation_error = is_excel_file_readable(f)
        table.add_row(f.name, group_folder, proposed_name, "OK" if valid else validation_error)
    console.print(table)

    # Let user verify/modify configuration parameters via GUI or CLI fallback
    website_url, tag_to_select, officer_to_select = get_run_settings(config)

    # Start Playwright automation
    with sync_playwright() as p:
        headless = settings.get("headless", False)
        console.print(f"\n[cyan]Starting browser ({'Headless' if headless else 'Headed'} mode)...[/cyan]")
        
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        # Navigate to login if required, or start navigation
        manual_login_needed = login_config.get("manual_login_pause", True)
        
        if login_config.get("required", False):
            page.goto(login_config.get("url", ""))
            page.wait_for_load_state("networkidle")
            # Check if login details are configured
            if login_config.get("username") and login_config.get("password"):
                try:
                    console.print("[cyan]Attempting automatic login...[/cyan]")
                    username_selector = login_config.get("username_selector")
                    username = login_config.get("username")
                    username_field = page.locator(username_selector).first
                    page.wait_for_timeout(1000)
                    username_field.click()
                    username_field.press("Meta+A" if sys.platform == "darwin" else "Control+A")
                    username_field.press("Backspace")
                    username_field.clear()
                    if username_field.input_value():
                        raise Exception("The email field could not be cleared before login.")
                    username_field.fill(username)
                    if username_field.input_value().strip() != username:
                        raise Exception("The email field did not contain exactly one copy of the saved address.")
                    page.fill(login_config.get("password_selector"), login_config.get("password"))
                    page.click(login_config.get("submit_selector"))
                    page.wait_for_load_state("networkidle")
                    manual_login_needed = False
                except Exception as e:
                    console.print(f"[yellow]Warning: Automatic login failed ({e}). Switching to manual login...[/yellow]")
                    manual_login_needed = True

        if manual_login_needed:
            page.goto(config.get("website_url"))
            console.print(Panel(
                "[bold yellow]⚠️ Pause for Login / Setup ⚠️[/bold yellow]\n\n"
                "A browser window has opened. Please perform the following steps:\n"
                "1. Log in to the site if required.\n"
                "2. Navigate directly to the final file upload form page.\n\n"
                "[bold green]👉 Once the browser is on the upload page, return to this terminal and press ENTER to start automation.[/bold green]",
                border_style="yellow"
            ))
            input("Press Enter here in the terminal to start the upload loop...")
        else:
            # Automatic login was successful! Now navigate directly to the upload contacts page URL
            try:
                upload_url = config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact")
                console.print(f"[cyan]Navigating directly to: [underline]{upload_url}[/underline]...[/cyan]")
                page.goto(upload_url)
                page.wait_for_load_state("networkidle")
            except Exception as e:
                console.print(f"[yellow]Warning: Direct navigation failed ({e}).[/yellow]")
                console.print("[yellow]Please navigate to the upload form in the browser window manually.[/yellow]")
                input("Press Enter here in the terminal once you are on the Upload Contacts page...")

        website_upload_names = load_website_contact_list_names(page)
        if website_upload_names:
            used_upload_names.update(website_upload_names)
            console.print(f"[cyan]Found {len(website_upload_names)} existing contact-list names on the website.[/cyan]")
        else:
            console.print("[yellow]No existing website contact-list names were detected; using local upload history only.[/yellow]")

        if dry_run:
            report_path = write_dry_run_report(reports_folder, xlsx_files, source_folder, settings, used_upload_names, website_upload_names)
            console.print(Panel(
                f"[bold yellow]Dry run complete.[/bold yellow]\n"
                f"No files were uploaded or moved.\n"
                f"Preview report: [cyan]{report_path}[/cyan]",
                border_style="yellow"
            ))
            browser.close()
            return

        # Start Processing Loop
        results = {"success": [], "failed": [], "skipped": []}
        run_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_report_path = reports_folder / f"upload-run-{run_timestamp}.csv"
        run_report_rows = []
        log_message(log_file_path, f"Starting automation run. Found {len(xlsx_files)} files to upload. Mode: {run_mode}. Verification: {verify_after_upload}.")

        for i, file_path in enumerate(xlsx_files, 1):
            file_name = file_path.name
            relative_file_name = str(file_path.relative_to(source_folder))
            borough = clean_borough_name(file_path.stem)
            upload_name = next_available_upload_name(f"{borough} upload", used_upload_names)

            console.print(f"\n[bold cyan]Processing [{i}/{len(xlsx_files)}]: {relative_file_name}[/bold cyan]")
            
            try:
                valid_excel, validation_error = is_excel_file_readable(file_path)
                if not valid_excel:
                    raise Exception(validation_error)

                max_name_attempts = 10
                for name_attempt in range(1, max_name_attempts + 1):
                    last_error = None
                    for file_attempt in range(1, max_file_attempts + 1):
                        try:
                            # 1. Fill Name Input
                            if selectors.get("name_input"):
                                page.wait_for_selector(selectors.get("name_input"), timeout=5000)
                                page.fill(selectors.get("name_input"), upload_name)
                                console.print(f"  ✓ Filled name field with: '[magenta]{upload_name}[/magenta]'")
                            
                            # 2. Select Tag
                            if selectors.get("tag_dropdown") and tag_to_select:
                                select_dropdown_option(page, selectors.get("tag_dropdown"), tag_to_select)
                                console.print(f"  ✓ Selected tag: '[magenta]{tag_to_select}[/magenta]'")

                            # 3. Select Officer
                            if selectors.get("officer_dropdown") and officer_to_select:
                                select_dropdown_option(page, selectors.get("officer_dropdown"), officer_to_select)
                                console.print(f"  ✓ Selected officer: '[magenta]{officer_to_select}[/magenta]'")

                            # 4. Attach File
                            if selectors.get("file_input"):
                                # Playwright handles file inputs directly
                                page.set_input_files(selectors.get("file_input"), str(file_path))
                                console.print(f"  ✓ Attached file: [magenta]{file_name}[/magenta]")

                            # 5. Submit Form
                            if selectors.get("submit_button"):
                                page.click(selectors.get("submit_button"))
                                console.print("  ✓ Clicked Submit. Waiting for confirmation...")

                            # 6. Verify Upload Success
                            time.sleep(settings.get("delay_after_submit_seconds", 3.0))
                            submission_status, error_detail = detect_submission_result(page, selectors)

                            if submission_status == "success":
                                verified = True
                                if verify_after_upload:
                                    verified, refreshed_names = verify_upload_name_on_website(
                                        page,
                                        config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact"),
                                        upload_name,
                                        verify_timeout_seconds
                                    )
                                    used_upload_names.update(refreshed_names)
                                    if not verified:
                                        raise Exception(f"Upload submitted, but '{upload_name}' was not found on the contact-list page after verification.")
                                    console.print(f"  ✓ Verified website contains: '[magenta]{upload_name}[/magenta]'")

                                dest_path = destination_for_file(file_path, source_folder, uploaded_folder)
                                shutil.move(str(file_path), str(dest_path))
                                log_message(log_file_path, f"SUCCESS: Uploaded '{relative_file_name}' as '{upload_name}'. Moved file to '{dest_path.relative_to(input_folder)}'.")
                                results["success"].append(relative_file_name)
                                run_report_rows.append({
                                    "file": relative_file_name,
                                    "upload_name": upload_name,
                                    "status": "success",
                                    "attempts": file_attempt,
                                    "verified": str(verified).lower(),
                                    "destination": str(dest_path.relative_to(input_folder)),
                                    "error": "",
                                })
                                break

                            if submission_status == "duplicate" and name_attempt < max_name_attempts:
                                previous_name = upload_name
                                upload_name = next_available_upload_name(f"{borough} upload", used_upload_names)
                                log_message(log_file_path, f"DUPLICATE NAME: '{previous_name}' was rejected for '{relative_file_name}'. Retrying as '{upload_name}'.")
                                console.print(f"  [yellow]Name already exists. Retrying as '[magenta]{upload_name}[/magenta]'.[/yellow]")
                                break

                            raise Exception(error_detail or "Failed to confirm upload success.")
                        except Exception as attempt_error:
                            last_error = attempt_error
                            found_after_error = False
                            if verify_after_upload:
                                found_after_error, refreshed_names = verify_upload_name_on_website(
                                    page,
                                    config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact"),
                                    upload_name,
                                    verify_timeout_seconds
                                )
                                used_upload_names.update(refreshed_names)

                            if found_after_error:
                                dest_path = destination_for_file(file_path, source_folder, uploaded_folder)
                                shutil.move(str(file_path), str(dest_path))
                                log_message(log_file_path, f"SUCCESS: Uploaded '{relative_file_name}' as '{upload_name}' after recovery verification. Moved file to '{dest_path.relative_to(input_folder)}'.")
                                results["success"].append(relative_file_name)
                                run_report_rows.append({
                                    "file": relative_file_name,
                                    "upload_name": upload_name,
                                    "status": "success_after_recovery",
                                    "attempts": file_attempt,
                                    "verified": "true",
                                    "destination": str(dest_path.relative_to(input_folder)),
                                    "error": str(attempt_error),
                                })
                                break

                            if file_attempt < max_file_attempts:
                                log_message(log_file_path, f"RETRY: '{relative_file_name}' as '{upload_name}'. Attempt {file_attempt} failed: {attempt_error}")
                                console.print(f"  [yellow]Attempt {file_attempt} failed. Reloading form and retrying...[/yellow]")
                                page.goto(config.get("upload_url", "https://www.help2rent.co.uk/email/marketing/contact"))
                                page.wait_for_load_state("networkidle")
                                continue

                            raise last_error

                    if results["success"] and results["success"][-1] == relative_file_name:
                        break

                    if last_error and name_attempt >= max_name_attempts:
                        raise last_error

            except Exception as e:
                screenshot_path, html_path = save_error_artifacts(page, errors_folder, relative_file_name, upload_name)
                log_message(log_file_path, f"FAILED: '{relative_file_name}'. Reason: {str(e)}")
                dest_path = destination_for_file(file_path, source_folder, failed_folder)
                shutil.move(str(file_path), str(dest_path))
                results["failed"].append((relative_file_name, str(e)))
                run_report_rows.append({
                    "file": relative_file_name,
                    "upload_name": upload_name,
                    "status": "failed",
                    "attempts": max_file_attempts,
                    "verified": "false",
                    "destination": str(dest_path.relative_to(input_folder)),
                    "error": str(e),
                })
                
                # Check if we should pause on error
                console.print(f"[bold red]❌ Failed to upload '{relative_file_name}':[/bold red] {e}")
                if screenshot_path or html_path:
                    console.print(f"[yellow]Saved troubleshooting artifacts in: {errors_folder}[/yellow]")
                should_continue = Confirm.ask("Do you want to continue to the next file?", default=True)
                if not should_continue:
                    log_message(log_file_path, "Upload run aborted by user after failure.")
                    break

        # Generate run summary
        console.print("\n" + "="*50)
        console.print(Panel("[bold green]Automation Run Completed![/bold green]", border_style="green"))
        
        summary_table = Table(title="Run Summary", border_style="cyan")
        summary_table.add_column("Status", style="bold")
        summary_table.add_column("Count", style="cyan")
        summary_table.add_column("Files", style="magenta")
        
        summary_table.add_row("Uploaded Successfully", str(len(results["success"])), ", ".join(results["success"]) or "None")
        
        failed_names = [f[0] for f in results["failed"]]
        summary_table.add_row("Failed Uploads", str(len(results["failed"])), ", ".join(failed_names) or "None")
        
        console.print(summary_table)
        log_message(log_file_path, f"Run summary - Uploaded: {len(results['success'])}, Failed: {len(results['failed'])}")
        write_csv_report(run_report_path, run_report_rows, [
            "file",
            "upload_name",
            "status",
            "attempts",
            "verified",
            "destination",
            "error",
        ])
        console.print(f"[cyan]Run report saved to: {run_report_path}[/cyan]")
        
        # Keep browser open if errors occurred so user can inspect
        if results["failed"]:
            Confirm.ask("\nFailed uploads occurred. Press Enter to close the browser and exit...")
        else:
            time.sleep(2)
        
        browser.close()

if __name__ == "__main__":
    from automation_hub.ui import main
    sys.exit(main())
