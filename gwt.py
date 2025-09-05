import json
import requests
import os
import re
import concurrent.futures
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.align import Align
from rich import box

console = Console()
API_URL = "http://narayan-gwt-token.vercel.app/token?uid={}&password={}"

# 🔥 Show Stylish Banner with "WELCOME TO FF BY NARAYAN"
def show_banner():
    banner_text = Text("\n🔥 WELCOME TO FF BY NARAYAN 🔥", style="bold yellow")
    banner_panel = Panel(
        Align.center(banner_text),
        box=box.DOUBLE,  # Double-line box for stylish look
        style="bold magenta",
        expand=True
    )
    console.print(banner_panel)

# 🔹 Extract UID & Password
def extract_uid_password(content):
    pattern = re.compile(r'"uid"\s*:\s*"(\d+)"\s*,\s*"password"\s*:\s*"([A-Fa-f0-9]+)"')
    return pattern.findall(content)

# 🔹 Fetch Token (Runs in Parallel)
def fetch_token(uid, password):
    url = API_URL.format(uid, password)
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            response_data = response.json()
            return {"uid": uid, "token": response_data.get("token", None)}
        return {"uid": uid, "token": None}
    except requests.Timeout:
        return {"uid": uid, "token": None}
    except requests.RequestException:
        return {"uid": uid, "token": None}

# 🔹 Main Function
def process_json(json_file):
    try:
        show_banner()  # 🏆 Show Stylish Banner at the Start

        console.print(Panel(
            Text("🔥 JWT TOKEN GENERATOR 🔥", style="bold cyan"),
            style="bold blue",
            box=box.ROUNDED,
            expand=True
        ))

        with open(json_file, "r", encoding="utf-8") as file:
            content = file.read()

        uid_password_pairs = extract_uid_password(content)
        total_uids = len(uid_password_pairs)

        if total_uids == 0:
            console.print("[bold red]❌ Error: No valid UID and Password found.[/bold red]")
            return

        tokens = []
        table = Table(title="🚀 Token Retrieval Status", style="bold cyan", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("UID", style="yellow", justify="center")
        table.add_column("Status", style="green", justify="center")

        success_count = 0  # ✅ Successful token count

        # 🏆 Parallel Processing & Progress Bar
        with Progress(
            TextColumn("[bold cyan]Processing...[/bold cyan]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Fetching Tokens", total=total_uids)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_uid = {executor.submit(fetch_token, uid, password): uid for uid, password in uid_password_pairs}
                for future in concurrent.futures.as_completed(future_to_uid):
                    result = future.result()
                    if result["token"]:
                        tokens.append({"token": result["token"]})
                        table.add_row(result["uid"], "[bold green]✅ Success[/bold green]")
                        success_count += 1
                    else:
                        table.add_row(result["uid"], "[bold red]❌ Failed[/bold red]")
                    progress.update(task, advance=1)

        console.print(table)

        console.print(f"\n[bold cyan]📊 Total IDs Processed:[/bold cyan] {total_uids}")
        console.print(f"[bold green]✅ Successful Tokens:[/bold green] {success_count}")
        console.print(f"[bold red]❌ Failed Attempts:[/bold red] {total_uids - success_count}\n")

        # 🔹 Save Tokens to "token_ind.json"
        if tokens:
            output_file = os.path.join(os.path.dirname(json_file), "token_ind.json")  # ⬅️ Capital 'T' version
            with open(output_file, "w", encoding="utf-8") as outfile:
                json.dump(tokens, outfile, indent=4, ensure_ascii=False)
            console.print(Panel(
                f"📂 tokens saved to: [bold green]{output_file}[/bold green]",
                style="bold magenta",
                box=box.HEAVY
            ))

    except FileNotFoundError:
        console.print("[bold red]❌ Error: File not found. Please provide a valid path.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ Unexpected Error: {e}[/bold red]")

if __name__ == "__main__":
    json_path = console.input("[bold cyan]Enter JSON file path: [/bold cyan]").strip()
    process_json(json_path)