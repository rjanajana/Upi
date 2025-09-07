import json
import requests
import os
import re
import time
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

# 🔧 FIXED SETTINGS FOR BETTER SUCCESS RATE
MAX_RETRIES = 3          # Retry failed requests
CONCURRENCY_LIMIT = 4    # Reduced from 10 to avoid rate limiting
RETRY_DELAY = 1.5        # Delay between retries
REQUEST_DELAY = 0.3      # Small delay between requests

# 🔥 Show Stylish Banner with "WELCOME TO FF BY NARAYAN"
def show_banner():
    banner_text = Text("\n🔥 WELCOME TO FF BY NARAYAN 🔥", style="bold yellow")
    banner_panel = Panel(
        Align.center(banner_text),
        box=box.DOUBLE, # Double-line box for stylish look
        style="bold magenta",
        expand=True
    )
    console.print(banner_panel)

# 🔹 Extract UID & Password
def extract_uid_password(content):
    pattern = re.compile(r'"uid"\s*:\s*"(\d+)"\s*,\s*"password"\s*:\s*"([A-Fa-f0-9]+)"')
    return pattern.findall(content)

# 🔹 Fetch Token (Enhanced with Retry Logic)
def fetch_token(uid, password):
    url = API_URL.format(uid, password)
    
    for attempt in range(MAX_RETRIES):
        try:
            # Small delay before request to avoid overwhelming server
            if attempt > 0:
                time.sleep(RETRY_DELAY * attempt)  # Exponential backoff
            else:
                time.sleep(REQUEST_DELAY)
            
            response = requests.get(url, timeout=5)  # Increased timeout
            
            if response.status_code == 200:
                response_data = response.json()
                token = response_data.get("token", None)
                
                if token:
                    return {"uid": uid, "token": token, "status": "success"}
                else:
                    # API returned 200 but no token
                    continue
                    
            elif response.status_code == 429:  # Rate limited
                console.print(f"[yellow]Rate limited for UID {uid}, retrying...[/yellow]")
                time.sleep(RETRY_DELAY * 2)
                continue
                
            else:
                # Other HTTP errors
                console.print(f"[orange]HTTP {response.status_code} for UID {uid}, attempt {attempt + 1}[/orange]")
                continue
                
        except requests.Timeout:
            console.print(f"[red]Timeout for UID {uid}, attempt {attempt + 1}[/red]")
            continue
            
        except requests.RequestException as e:
            console.print(f"[red]Request error for UID {uid}: {str(e)[:50]}...[/red]")
            continue
            
        except Exception as e:
            console.print(f"[red]Unexpected error for UID {uid}: {str(e)[:50]}...[/red]")
            continue
    
    return {"uid": uid, "token": None, "status": "failed"}

# 🔹 Main Function (Enhanced)
def process_json(json_file):
    try:
        show_banner() # 🏆 Show Stylish Banner at the Start
        
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
        failed_uids = []
        
        table = Table(title="🚀 Token Retrieval Status", style="bold cyan", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("UID", style="yellow", justify="center")
        table.add_column("Status", style="green", justify="center")
        table.add_column("Attempt", style="blue", justify="center")

        success_count = 0 # ✅ Successful token count

        # 🏆 Enhanced Parallel Processing with Better Control
        with Progress(
            TextColumn("[bold cyan]Processing...[/bold cyan]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
        ) as progress:
            
            task = progress.add_task("Fetching Tokens", total=total_uids)
            
            # Process in smaller batches to avoid overwhelming the server
            batch_size = CONCURRENCY_LIMIT
            
            for i in range(0, len(uid_password_pairs), batch_size):
                batch = uid_password_pairs[i:i + batch_size]
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY_LIMIT) as executor:
                    future_to_uid = {executor.submit(fetch_token, uid, password): uid for uid, password in batch}
                    
                    for future in concurrent.futures.as_completed(future_to_uid):
                        result = future.result()
                        
                        if result["token"]:
                            tokens.append({"token": result["token"]})
                            table.add_row(result["uid"], "[bold green]✅ Success[/bold green]", "[blue]Final[/blue]")
                            success_count += 1
                        else:
                            failed_uids.append(result["uid"])
                            table.add_row(result["uid"], "[bold red]❌ Failed[/bold red]", "[red]All[/red]")
                        
                        progress.update(task, advance=1)
                
                # Small delay between batches
                if i + batch_size < len(uid_password_pairs):
                    time.sleep(0.5)

        console.print(table)
        console.print(f"\n[bold cyan]📊 Total IDs Processed:[/bold cyan] {total_uids}")
        console.print(f"[bold green]✅ Successful Tokens:[/bold green] {success_count}")
        console.print(f"[bold red]❌ Failed Attempts:[/bold red] {total_uids - success_count}")
        
        # Show success rate
        success_rate = (success_count / total_uids) * 100
        console.print(f"[bold yellow]📈 Success Rate:[/bold yellow] {success_rate:.1f}%")
        
        if failed_uids:
            console.print(f"\n[bold red]Failed UIDs:[/bold red] {', '.join(failed_uids[:10])}{'...' if len(failed_uids) > 10 else ''}")

        # 🔹 Save Tokens to "token_ind.json"
        if tokens:
            output_file = os.path.join(os.path.dirname(json_file), "token_ind.json")
            
            with open(output_file, "w", encoding="utf-8") as outfile:
                json.dump(tokens, outfile, indent=4, ensure_ascii=False)
                
            console.print(Panel(
                f"📂 {len(tokens)} tokens saved to: [bold green]{output_file}[/bold green]",
                style="bold magenta",
                box=box.HEAVY
            ))
        else:
            console.print("[bold red]❌ No tokens generated to save![/bold red]")

    except FileNotFoundError:
        console.print("[bold red]❌ Error: File not found. Please provide a valid path.[/bold red]")
    except json.JSONDecodeError:
        console.print("[bold red]❌ Error: Invalid JSON file format.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ Unexpected Error: {e}[/bold red]")

if __name__ == "__main__":
    json_path = console.input("[bold cyan]Enter JSON file path: [/bold cyan]").strip()
    process_json(json_path)
