import sys

# Add the project root to sys.path to allow importing 'app'
# Assuming this script is in backend/verify_captcha.py and app is in backend/app
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from app.agents.url_agent.tools import PlaywrightManager

async def test():
    print("Initializing PlaywrightManager...")
    # Headless=False to see the browser action if possible (though agent is headless usually, this script runs in user terminal)
    # Since I am an agent, I cannot see the GUI, but the user might. 
    # Whatever, let's keep headless=True for stability unless debugging.
    # Actually, to debug 'click', headless=True is fine as long as we log.
    manager = PlaywrightManager(headless=True) 
    await manager.start()
    
    # Test specific URL provided by user
    url = "https://2cm.es/1guvO" 
    print(f"Testing URL: {url}")
    
    try:
        result = await manager.scrape_url(url)
        
        print("-" * 50)
        print(f"Final Title: {result.get('title')}")
        print(f"Captcha Detected: {result.get('captcha_detected')}")
        print(f"Final URL: {result.get('url')}")
        print(f"Status: {result.get('status')}")
        print(f"Error: {result.get('error')}")
        print("-" * 50)
        
        if result.get('captcha_detected'):
            print("Suggests bypass failed or page is still suspicious.")
        else:
            print("Captcha not detected (or bypassed successfully).")
            
    except Exception as e:
        print(f"Test Error: {e}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test())
