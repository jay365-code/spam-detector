import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
import base64
import random

class PlaywrightManager:
    """
    Playwright 브라우저 관리 및 스크래핑 유틸리티
    """
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.playwright = None
        self.loop = None

    async def start(self):
        current_loop = asyncio.get_running_loop()
        
        # Detect if we are in a new event loop (e.g. restart of asyncio.run)
        if self.loop and self.loop != current_loop:
            # Old loop is closed or different, discard stale objects
            self.browser = None
            self.playwright = None
            
        self.loop = current_loop

        if not self.playwright:
            self.playwright = await async_playwright().start()
        
        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )

    async def stop(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def attempt_captcha_bypass(self, page: Page) -> bool:
        """
        Verify/Not a robot 버튼 클릭 시도
        """
        try:
            # 일반적인 봇 확인 버튼 선택자들
            candidates = [
                "text=Not a robot", 
                "text=로봇이 아님", 
                "text=로봇이 아닙니다",
                "button:has-text('Not a robot')",
                "button:has-text('Verify')",
                "input[value='Not a robot']",
                ".g-recaptcha", # 클릭 가능한 요소가 아닐 수 있음
                "#challenge-stage", # CF Turnstile container (클릭은 내부에 해야 함)
                "iframe[src*='turnstile']", # Turnstile iframe
            ]
            
            # 1. 텍스트/버튼 기반 클릭
            for selector in candidates:
                # 간단한 텍스트 기반 버튼
                elements = await page.locator(selector).all()
                for el in elements:
                    if await el.is_visible():
                        print(f"[Playwright] Clicking candidate: {selector}")
                        try:
                            await el.click(timeout=2000)
                            await page.wait_for_timeout(2000) # 반응 대기
                            return True
                        except:
                            pass
                            
            # 2. CF Turnstile 등 iframe 내부 클릭 (복잡하지만 시도)
            # (여기서는 단순 클릭만 시도하고, 좌표 기반 등은 제외)
            
            return False
            
        except Exception as e:
            print(f"[Playwright] Bypass error: {e}")
            return False

    async def scrape_url(self, url: str) -> dict:
        """
        URL을 방문하여 텍스트 및 스크린샷 캡처 (Auto-Recovery)
        """
        result = {
            "url": url,
            "title": "",
            "text": "",
            "screenshot_b64": "",
            "status": "failed",
            "error": ""
        }

        context = None
        
        # Retry logic for browser connection
        for attempt in range(2):
            try:
                print(f"[Playwright] Attempt {attempt+1} for {url}. Loop: {id(asyncio.get_running_loop())}")
                
                # Always call start() to ensure loop compatibility
                # start() internal logic handles the "already started in same loop" case efficiently
                print(f"[Playwright] Checking browser state... (Headless: {self.headless})")
                await self.start()
                
                # 새 컨텍스트 생성 (매번 깨끗한 상태)
                print("[Playwright] Creating context...")
                context = await self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                print("[Playwright] Context created.")
                break # Success
            except Exception as e:
                print(f"Browser connection failed (Attempt {attempt+1}): {e}")
                # Force reset
                self.browser = None
                self.playwright = None
                self.loop = None
                if attempt == 1:
                    result["error"] = f"Browser Init Failed: {str(e)}"
                    return result

        if not context:
             result["error"] = "Could not create browser context"
             return result

        try:
            page = await context.new_page()
            print(f"[Playwright] Page created. Navigating to {url}...")
            
            # 1. 페이지 로드 (타임아웃 15초)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            print(f"[Playwright] Navigation complete. Status: {response.status if response else 'None'}")
            
            # 리디렉션 최종 URL 업데이트
            final_url = page.url
            result["url"] = final_url # redirect 반영

            if response:
                result["status_code"] = response.status
            
            # 2. 렌더링 대기 (동적 콘텐츠)
            print("[Playwright] Waiting for content...")
            await page.wait_for_timeout(3000) # 3초 대기

            # 2.5 팝업 닫기 시도 (Heuristic)
            popup_count = 0
            try:
                # 일반적인 닫기 버튼 선택자들
                close_selectors = [
                    "text=닫기", "text=Close", "text=오늘 하루", "text=그만보기",
                    "button[class*='close']", "div[class*='close']", 
                    "button[aria-label='Close']", "button[aria-label='닫기']",
                    ".modal-close", ".popup-close"
                ]
                
                for selector in close_selectors:
                    # 보이는 요소만 클릭 (옵션: timeout 짧게)
                    closes = await page.locator(selector).all()
                    for close_btn in closes:
                        if await close_btn.is_visible():
                            try:
                                await close_btn.click(timeout=1000)
                                await page.wait_for_timeout(500) # 클릭 후 잠시 대기
                                popup_count += 1
                            except:
                                pass # 클릭 실패해도 무시하고 계속
            except Exception as e_popup:
                # 팝업 닫기 중 에러가 나도 메인 로직은 진행
                print(f"Popup close warning: {e_popup}")
            
            result["popup_count"] = popup_count

            
            # 3. 데이터 추출
            result["title"] = await page.title()
            
            # visible text만 추출 평가
            text_content = await page.evaluate("document.body.innerText")
            
            # 3.5 캡차 탐지 및 우회 시도 (Heuristic)
            result["captcha_detected"] = False
            captcha_keywords = ["captcha", "recaptcha", "turnstile", "사람 확인", "로봇이 아닙니다", "not a robot", "human check"]
            lower_text = text_content.lower()
            if any(k in lower_text for k in captcha_keywords):
                result["captcha_detected"] = True
                print(f"[Playwright] Captcha/Interstitial detected. Attempting bypass...")
                # Bypass 시도
                if await self.attempt_captcha_bypass(page):
                    # 우회 성공 가능성 있으므로 텍스트/타이틀 다시 추출
                    print("[Playwright] Bypass action performed. Refreshing content...")
                    result["title"] = await page.title()
                    text_content = await page.evaluate("document.body.innerText")
                    # 재검사
                    result["captcha_detected"] = False 
                    lower_text = text_content.lower()
                    if any(k in lower_text for k in captcha_keywords):
                         result["captcha_detected"] = True # 여전히 캡차면 True 유지

            result["text"] = text_content[:5000] # 너무 길면 자름
            
            # 4. 스크린샷 캡처
            print("[Playwright] capturing screenshot...")
            screenshot_bytes = await page.screenshot(type="jpeg", quality=60, full_page=False)
            result["screenshot_b64"] = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            result["status"] = "success"
            print(f"[Playwright] Success. Title: {result['title']}")

        except Exception as e:
            print(f"[Playwright] Scraping Error: {e}")
            result["error"] = str(e)
            result["status"] = "error"
        
        finally:
            print("[Playwright] Closing context.")
            await context.close()
            
        return result

# Singleton 인스턴스 (필요시)
# manager = PlaywrightManager()
