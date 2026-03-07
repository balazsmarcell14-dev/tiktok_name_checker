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
    """Generate random usernames with letters and numbers."""
    characters = string.ascii_lowercase + string.digits
    usernames = set()
    
    while len(usernames) < count:
        username = ''.join(random.choices(characters, k=length))
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
        await page.wait_for_timeout(2000)
        
        title = await page.title()
        title_lower = title.lower()
        
        # Primary check: page title
        if "couldn't find" in title_lower:
            return (username, True)   # Available
        elif f"@{username}" in title_lower:
            return (username, False)  # Taken
        
        # Secondary check: uniqueid in page content (only present on real profiles)
        content = await page.content()
        if f'"uniqueId":"{username}"' in content:
            return (username, False)  # Taken
        
        if "couldn't find this account" in content.lower():
            return (username, True)   # Available
        
        return (username, None)   # Ambiguous = error
        
    except PlaywrightTimeout:
        return (username, None)
    except Exception as e:
        return (username, None)

async def worker(browser, usernames: list, results: dict, progress: dict, total: int):
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
            await page.wait_for_timeout(300)
    
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
            workers = int(input("Enter number of browser tabs (1-5, default 3): ") or "3")
            if 1 <= workers <= 5:
                break
            else:
                print("Please enter a number between 1 and 5.")
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
            for batch in batches:
                task = asyncio.create_task(worker(browser, batch, results, progress, len(usernames)))
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
    
    # Verification round
    verified_available = []
    if results["available"] and not stop_flag:
        print(f"\n[VERIFICATION] Re-checking {len(results['available'])} available usernames...")
        print("This ensures accuracy by checking each one twice.\n")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                
                for i, username in enumerate(results["available"]):
                    if stop_flag:
                        break
                    
                    print(f"\rVerifying: {i+1}/{len(results['available'])} - @{username}", end="", flush=True)
                    
                    try:
                        url = f"https://www.tiktok.com/@{username}"
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2500)  # Wait longer for verification
                        
                        title = await page.title()
                        title_lower = title.lower()
                        
                        # Primary: check page title
                        if "couldn't find" in title_lower:
                            verified_available.append(username)
                        elif f"@{username}" in title_lower:
                            pass  # Taken - don't add
                        else:
                            # Secondary: check content
                            content = await page.content()
                            if f'"uniqueId":"{username}"' in content:
                                pass  # Taken
                            elif "couldn't find this account" in content.lower():
                                verified_available.append(username)
                            
                    except Exception as e:
                        pass  # Skip on error during verification
                    
                    await page.wait_for_timeout(800)
                
                await browser.close()
                
        except Exception as e:
            print(f"\n[!] Verification error: {e}")
            verified_available = results["available"]  # Fall back to original list
        
        print("\n")
        
        false_positives = len(results["available"]) - len(verified_available)
        print(f"[VERIFICATION COMPLETE]")
        print(f"  Original available: {len(results['available'])}")
        print(f"  Verified available: {len(verified_available)}")
        print(f"  False positives removed: {false_positives}")
        print()
    else:
        verified_available = results["available"]
    
    # Save verified available usernames to file
    if verified_available:
        filename = f"available_usernames_{length}chars.txt"
        with open(filename, "w") as f:
            for username in sorted(verified_available):
                f.write(username + "\n")
        print(f"Verified available usernames saved to: {filename}")
    
    # Show ALL verified available usernames
    if verified_available:
        print(f"\nAll {len(verified_available)} VERIFIED available usernames:")
        print("-" * 30)
        for username in sorted(verified_available):
            print(f"  @{username}")
        print("-" * 30)
    else:
        print("\nNo verified available usernames found.")
    print("\n" + "=" * 50)
    input("Press Enter to exit...")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
