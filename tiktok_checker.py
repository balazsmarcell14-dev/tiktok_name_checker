import random
import string
import time
import signal
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Global flag to stop execution
stop_flag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C to stop gracefully."""
    global stop_flag
    stop_flag = True
    print("\n\n[!] Stopping... Please wait for current checks to finish...")

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

def generate_usernames(length: int, count: int = 10000) -> list:
    """Generate random usernames with letters, numbers, underscores and periods."""
    characters = string.ascii_lowercase + string.digits + '_.'
    usernames = set()
    
    while len(usernames) < count:
        # First char must be a letter or number (TikTok requirement)
        first = random.choice(string.ascii_lowercase + string.digits)
        # Last char must be a letter or number (can't end with _ or .)
        last = random.choice(string.ascii_lowercase + string.digits)
        if length <= 2:
            username = first + last if length == 2 else first
        else:
            middle = ''.join(random.choices(characters, k=length - 2))
            # Avoid consecutive _ or . 
            while '..' in middle or '__' in middle or '._' in middle or '_.' in middle:
                middle = ''.join(random.choices(characters, k=length - 2))
            username = first + middle + last
        usernames.add(username)
    
    return list(usernames)

async def check_username(page, username: str) -> tuple:
    """Check if a TikTok username is available."""
    global stop_flag
    if stop_flag:
        return (username, None)
    
    try:
        url = f"https://www.tiktok.com/@{username}"
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Wait for page to fully render
        await page.wait_for_timeout(1200)
        
        title = await page.title()
        title_lower = title.lower()
        
        # Primary check: page title
        if "couldn't find" in title_lower:
            return (username, True)   # Possibly available (could be banned)
        elif f"@{username}" in title_lower:
            return (username, False)  # Taken
        
        # Secondary check: uniqueid in page content (only present on real profiles)
        content = await page.content()
        if f'"uniqueId":"{username}"' in content:
            return (username, False)  # Taken
        
        if "couldn't find this account" in content.lower():
            return (username, True)   # Possibly available
        
        return (username, None)   # Ambiguous = error
        
    except PlaywrightTimeout:
        return (username, None)
    except Exception as e:
        return (username, None)

async def verify_username_signup(page, username: str) -> bool:
    """Verify username by checking TikTok's signup page username field."""
    try:
        # Navigate to signup page
        await page.goto("https://www.tiktok.com/signup", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        
        # Try the username check via TikTok's internal API
        result = await page.evaluate('''async (username) => {
            try {
                const response = await fetch(`https://www.tiktok.com/api/uniqueid/check/?uniqueId=${username}&aid=1988`, {
                    method: 'GET',
                    credentials: 'include'
                });
                const data = await response.json();
                return data;
            } catch(e) {
                return null;
            }
        }''', username)
        
        if result and "isValid" in str(result):
            return result.get("isValid", False)
        
        return None
    except Exception:
        return None

async def worker(browser, usernames: list, results: dict, progress: dict, total: int, worker_id: int):
    """Worker that processes usernames with its own browser context."""
    global stop_flag
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    page = await context.new_page()
    
    for username in usernames:
        if stop_flag:
            break
        
        username, is_available = await check_username(page, username)
        
        if is_available is True:
            results["available"].append(username)
        elif is_available is False:
            results["taken"].append(username)
        else:
            results["errors"].append(username)
        
        progress["checked"] += 1
        checked = progress["checked"]
        elapsed = time.time() - progress["start_time"]
        rate = checked / elapsed if elapsed > 0 else 0
        
        print(f"\rProgress: {checked}/{total} ({checked*100//total}%) | "
              f"Available: {len(results['available'])} | Taken: {len(results['taken'])} | "
              f"Errors: {len(results['errors'])} | Rate: {rate:.2f}/s", end="", flush=True)
        
        # Small delay between requests
        if not stop_flag:
            await page.wait_for_timeout(100)
    
    await context.close()

async def verification_worker(browser, usernames: list, verified: list, progress: dict, total: int):
    """Worker for verification round."""
    global stop_flag
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    page = await context.new_page()
    
    for username in usernames:
        if stop_flag:
            break
        
        progress["checked"] += 1
        print(f"\rVerifying: {progress['checked']}/{total} - @{username}    ", end="", flush=True)
        
        try:
            # First try the API check
            api_result = await verify_username_signup(page, username)
            
            if api_result is True:
                verified.append(username)
                await page.wait_for_timeout(500)
                continue
            elif api_result is False:
                await page.wait_for_timeout(500)
                continue
            
            # Fallback: re-check the profile page
            url = f"https://www.tiktok.com/@{username}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2500)
            
            title = await page.title()
            title_lower = title.lower()
            content = await page.content()
            content_lower = content.lower()
            
            # Check for banned account indicators
            banned_indicators = [
                "account banned",
                "account suspended",
                "violated community guidelines",
                "violation of our",
                "permanently banned"
            ]
            is_banned = any(ind in content_lower for ind in banned_indicators)
            
            if is_banned:
                continue  # Skip banned accounts
            
            # Re-check availability
            if "couldn't find" in title_lower:
                if f'"uniqueId":"{username}"' not in content:
                    verified.append(username)
                    
        except Exception:
            pass
        
        await page.wait_for_timeout(500)
    
    await context.close()

async def main_async():
    global stop_flag
    
    print("=" * 50)
    print("       TikTok Username Availability Checker")
    print("              (Playwright Edition)")
    print("=" * 50)
    print()
    
    # Get username length from user
    while True:
        try:
            length = int(input("Enter the number of characters for usernames (3-20): "))
            if 3 <= length <= 20:
                break
            else:
                print("Please enter a number between 3 and 20.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Get number of usernames to generate
    while True:
        try:
            count = int(input("Enter number of usernames to generate (default 500): ") or "500")
            if 1 <= count <= 100000:
                break
            else:
                print("Please enter a number between 1 and 100000.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Get number of browser tabs
    while True:
        try:
            workers = int(input("Enter number of browser tabs (1-10, default 5): ") or "5")
            if 1 <= workers <= 10:
                break
            else:
                print("Please enter a number between 1 and 10.")
        except ValueError:
            print("Please enter a valid number.")
    
    print(f"\nGenerating {count} usernames with {length} characters...")
    usernames = generate_usernames(length, count)
    print(f"Generated {len(usernames)} unique usernames.")
    
    print(f"\nStarting browser with {workers} tab(s)...")
    print("Press Ctrl+C to stop and save progress.\n")
    
    # Split usernames among workers
    batch_size = len(usernames) // workers
    batches = []
    for i in range(workers):
        start = i * batch_size
        end = start + batch_size if i < workers - 1 else len(usernames)
        batches.append(usernames[start:end])
    
    results = {"available": [], "taken": [], "errors": []}
    progress = {"checked": 0, "start_time": time.time()}
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Create worker tasks
            tasks = []
            for i, batch in enumerate(batches):
                task = asyncio.create_task(worker(browser, batch, results, progress, len(usernames), i))
                tasks.append(task)
            
            # Wait for all workers
            await asyncio.gather(*tasks)
            
            await browser.close()
            
    except Exception as e:
        print(f"\n[!] Error: {e}")
    
    print("\n")
    
    # Summary
    elapsed_time = time.time() - progress["start_time"]
    total_checked = len(results["available"]) + len(results["taken"]) + len(results["errors"])
    
    print("=" * 50)
    if stop_flag:
        print("              RESULTS (STOPPED EARLY)")
    else:
        print("                    RESULTS")
    print("=" * 50)
    print(f"Total checked: {total_checked}")
    print(f"Available usernames: {len(results['available'])}")
    print(f"Taken usernames: {len(results['taken'])}")
    print(f"Errors/Unknown: {len(results['errors'])}")
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
    print()
    
    # Save available usernames from first pass only
    if results["available"]:
        filename = f"available_usernames_{length}chars.txt"
        with open(filename, "w") as f:
            for username in sorted(results["available"]):
                f.write(username + "\n")
        print(f"Available usernames saved to: {filename}")
    
    # Show all available usernames
    if results["available"]:
        print(f"\nAll {len(results['available'])} available usernames:")
        print("-" * 30)
        for username in sorted(results["available"]):
            print(f"  @{username}")
        print("-" * 30)
    else:
        print("\nNo available usernames found.")
    print("\n" + "=" * 50)
    input("Press Enter to exit...")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
