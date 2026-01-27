import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
# playwright-stealth 라이브러리 API 호환성 문제로 수동 stealth 사용
import base64
import random
import time

# 강화된 Stealth 스크립트 (Cloudflare, Turnstile 우회용)
ENHANCED_STEALTH_SCRIPT = """
// 1. navigator.webdriver 완전 제거
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});
delete navigator.__proto__.webdriver;

// 2. Chrome runtime 시뮬레이션
window.chrome = {
    runtime: {
        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
        OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        connect: function() {},
        sendMessage: function() {},
        id: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'
    },
    csi: function() {},
    loadTimes: function() { return {}; }
};

// 3. Plugins 시뮬레이션 (실제 Chrome처럼)
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ];
        plugins.length = 3;
        return plugins;
    },
    configurable: true
});

// 4. Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ko-KR', 'ko', 'en-US', 'en'],
    configurable: true
});

// 5. Platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
    configurable: true
});

// 6. Hardware Concurrency (CPU cores)
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true
});

// 7. Device Memory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true
});

// 8. WebGL Vendor/Renderer 스푸핑
const getParameterProxyHandler = {
    apply: function(target, thisArg, args) {
        const param = args[0];
        const gl = thisArg;
        // UNMASKED_VENDOR_WEBGL
        if (param === 37445) {
            return 'Google Inc. (NVIDIA)';
        }
        // UNMASKED_RENDERER_WEBGL
        if (param === 37446) {
            return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
        }
        return Reflect.apply(target, thisArg, args);
    }
};
try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
    }
} catch(e) {}

// 9. Permission API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// 10. Connection API (rtt값 등)
Object.defineProperty(navigator, 'connection', {
    get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false
    }),
    configurable: true
});

// 11. Headless 탐지 방지
Object.defineProperty(document, 'hidden', {
    get: () => false,
    configurable: true
});
Object.defineProperty(document, 'visibilityState', {
    get: () => 'visible',
    configurable: true
});

// 12. iframe contentWindow 탐지 방지
try {
    const elementDescriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            return elementDescriptor.get.call(this);
        }
    });
} catch(e) {}

// 13. toString 함수 스푸핑 (함수가 native code로 보이도록)
const nativeToStringFunctionString = Error.toString().replace(/Error/g, 'toString');
const oldToString = Function.prototype.toString;
function newToString() {
    if (this === window.navigator.permissions.query) {
        return 'function query() { [native code] }';
    }
    return oldToString.call(this);
}
Function.prototype.toString = newToString;

console.log('[Stealth] Enhanced anti-detection script loaded.');
"""

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

    async def simulate_human_behavior(self, page: Page):
        """
        Human-like behavior 시뮬레이션 (마우스 움직임, 스크롤 등)
        """
        try:
            # 1. 랜덤 마우스 움직임
            for _ in range(random.randint(2, 4)):
                x = random.randint(100, 300)
                y = random.randint(100, 500)
                await page.mouse.move(x, y, steps=random.randint(5, 15))
                await page.wait_for_timeout(random.randint(50, 150))
            
            # 2. 랜덤 스크롤
            scroll_amount = random.randint(50, 150)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await page.wait_for_timeout(random.randint(100, 300))
            await page.evaluate(f"window.scrollBy(0, -{scroll_amount // 2})")
            
            print("[Playwright] Human behavior simulated.")
        except Exception as e:
            print(f"[Playwright] Human behavior simulation warning: {e}")

    async def wait_for_bot_protection(self, page: Page, max_wait: int = 15) -> bool:
        """
        다양한 봇 방어 페이지(Cloudflare, 부정클릭방지 등)가 해결될 때까지 대기
        Returns: True if protection passed, False otherwise
        """
        print(f"[Playwright] Waiting for bot protection to resolve (max {max_wait}s)...")
        
        # 다양한 봇 방어 시스템 감지 키워드
        protection_indicators = [
            # Cloudflare
            "Verifying you are human",
            "Just a moment",
            "Checking your browser",
            "Please wait",
            "cf-spinner",
            "challenge-running",
            # 한국 봇 방어 시스템
            "부정클릭방지",
            "부정클릭 방지",
            "자동화방지",
            "봇 감지",
            "접근제한",
            "INVALID ACCESS",
            # 일반적인 봇 방어
            "bot protection",
            "ddos protection",
            "security check",
            "browser check"
        ]
        
        initial_url = page.url
        
        for i in range(max_wait):
            try:
                text_content = await page.evaluate("document.body.innerText")
                html_content = await page.content()
                current_url = page.url
                
                # URL이 변경되었으면 리다이렉트 완료
                if current_url != initial_url and i > 2:
                    print(f"[Playwright] Redirected to: {current_url}")
                    await page.wait_for_timeout(1000)
                    return True
                
                # Protection이 여전히 활성화되어 있는지 확인
                is_protection_active = any(
                    indicator.lower() in text_content.lower() or indicator.lower() in html_content.lower()
                    for indicator in protection_indicators
                )
                
                # Protection이 해제되고 실제 콘텐츠가 있는지 확인
                if not is_protection_active and len(text_content.strip()) > 50:
                    print(f"[Playwright] Bot protection passed after {i+1}s")
                    return True
                
                # Human-like 행동 중간중간 수행
                if i % 3 == 0:
                    await self.simulate_human_behavior(page)
                
                # 페이지 새로고침 시도 (일부 봇 방어는 새로고침으로 해결)
                if i == 7:
                    print("[Playwright] Attempting page reload...")
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                
                await page.wait_for_timeout(1000)
                
            except Exception as e:
                print(f"[Playwright] Protection wait error: {e}")
                await page.wait_for_timeout(1000)
        
        print(f"[Playwright] Bot protection timeout after {max_wait}s")
        return False

    async def wait_for_cloudflare_challenge(self, page: Page, max_wait: int = 15) -> bool:
        """
        Cloudflare JS Challenge가 자동으로 해결될 때까지 대기 (Legacy - wait_for_bot_protection으로 대체)
        Returns: True if challenge passed, False otherwise
        """
        print(f"[Playwright] Waiting for Cloudflare challenge (max {max_wait}s)...")
        
        challenge_indicators = [
            "Verifying you are human",
            "Just a moment",
            "Checking your browser",
            "Please wait",
            "cf-spinner",
            "challenge-running"
        ]
        
        for i in range(max_wait):
            try:
                text_content = await page.evaluate("document.body.innerText")
                html_content = await page.content()
                
                # Challenge가 여전히 진행 중인지 확인
                is_challenge_active = any(
                    indicator.lower() in text_content.lower() or indicator.lower() in html_content.lower()
                    for indicator in challenge_indicators
                )
                
                if not is_challenge_active:
                    print(f"[Playwright] Cloudflare challenge passed after {i+1}s")
                    return True
                
                # Human-like 행동 중간중간 수행
                if i % 3 == 0:
                    await self.simulate_human_behavior(page)
                
                await page.wait_for_timeout(1000)
                
            except Exception as e:
                print(f"[Playwright] Challenge wait error: {e}")
                await page.wait_for_timeout(1000)
        
        print(f"[Playwright] Cloudflare challenge timeout after {max_wait}s")
        return False

    async def attempt_captcha_bypass(self, page: Page) -> bool:
        """
        Verify/Not a robot 버튼 클릭 시도 (Cloudflare Turnstile 포함)
        """
        try:
            # 1. Human-like behavior 먼저 수행
            await self.simulate_human_behavior(page)
            
            # 2. Cloudflare Turnstile iframe 처리
            turnstile_frames = page.frames
            for frame in turnstile_frames:
                if 'turnstile' in frame.url or 'challenges.cloudflare.com' in frame.url:
                    print(f"[Playwright] Found Turnstile frame: {frame.url}")
                    try:
                        # Turnstile 체크박스 클릭 시도
                        checkbox = frame.locator("input[type='checkbox']")
                        if await checkbox.count() > 0 and await checkbox.first.is_visible():
                            # 체크박스 위치로 마우스 이동 후 클릭
                            box = await checkbox.first.bounding_box()
                            if box:
                                await page.mouse.move(
                                    box['x'] + box['width'] / 2 + random.randint(-2, 2),
                                    box['y'] + box['height'] / 2 + random.randint(-2, 2),
                                    steps=random.randint(10, 20)
                                )
                                await page.wait_for_timeout(random.randint(100, 300))
                                await page.mouse.click(
                                    box['x'] + box['width'] / 2,
                                    box['y'] + box['height'] / 2
                                )
                                print("[Playwright] Turnstile checkbox clicked")
                                await page.wait_for_timeout(3000)
                                return True
                    except Exception as frame_err:
                        print(f"[Playwright] Turnstile frame interaction error: {frame_err}")
            
            # 3. 일반적인 봇 확인 버튼 선택자들
            candidates = [
                "text=Not a robot", 
                "text=로봇이 아님", 
                "text=로봇이 아닙니다",
                "text=Verify you are human",
                "button:has-text('Not a robot')",
                "button:has-text('Verify')",
                "button:has-text('Continue')",
                "input[value='Not a robot']",
                "#challenge-stage input",
                "#challenge-stage button",
                ".cf-turnstile",
                "[data-testid='challenge-btn']"
            ]
            
            for selector in candidates:
                try:
                    elements = await page.locator(selector).all()
                    for el in elements:
                        if await el.is_visible():
                            print(f"[Playwright] Clicking candidate: {selector}")
                            # 마우스로 자연스럽게 이동 후 클릭
                            box = await el.bounding_box()
                            if box:
                                await page.mouse.move(
                                    box['x'] + box['width'] / 2 + random.randint(-3, 3),
                                    box['y'] + box['height'] / 2 + random.randint(-3, 3),
                                    steps=random.randint(8, 15)
                                )
                                await page.wait_for_timeout(random.randint(50, 150))
                            await el.click(timeout=3000)
                            await page.wait_for_timeout(3000)
                            return True
                except:
                    pass
            
            # 4. 좌표 기반 클릭 (Turnstile 체크박스 일반 위치)
            # Turnstile은 보통 페이지 중앙에 위치
            try:
                viewport = page.viewport_size
                if viewport:
                    center_x = viewport['width'] // 2
                    center_y = viewport['height'] // 2
                    
                    # 체크박스는 보통 중앙 왼쪽에 위치
                    click_x = center_x - 100 + random.randint(-10, 10)
                    click_y = center_y + random.randint(-20, 20)
                    
                    await page.mouse.move(click_x, click_y, steps=15)
                    await page.wait_for_timeout(200)
                    await page.mouse.click(click_x, click_y)
                    print(f"[Playwright] Coordinate click at ({click_x}, {click_y})")
                    await page.wait_for_timeout(3000)
            except Exception as coord_err:
                print(f"[Playwright] Coordinate click error: {coord_err}")
            
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
                
                # 새 컨텍스트 생성 (모바일 에뮬레이션 - SMS는 모바일에서 클릭되므로)
                print("[Playwright] Creating mobile context (iPhone emulation)...")
                context = await self.browser.new_context(
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=3,
                    is_mobile=True,
                    has_touch=True,
                    ignore_https_errors=True  # SSL 인증서 오류 무시 (스팸 사이트 분석용)
                )
                print("[Playwright] Mobile context created (iPhone 14 Pro emulation).")
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
            
            # 강화된 봇 감지 우회 Stealth 스크립트 적용
            await page.add_init_script(ENHANCED_STEALTH_SCRIPT)
            
            print(f"[Playwright] Page created with enhanced stealth. Navigating to {url}...")
            
            # 1. 페이지 로드 (타임아웃 20초로 증가)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            print(f"[Playwright] Navigation complete. Status: {response.status if response else 'None'}")
            
            # 리디렉션 최종 URL 업데이트
            final_url = page.url
            result["url"] = final_url

            if response:
                result["status_code"] = response.status
            
            # 2. Human-like behavior 시뮬레이션
            await self.simulate_human_behavior(page)
            
            # 3. 렌더링 대기 (동적 콘텐츠) - 시간 증가
            print("[Playwright] Waiting for content...")
            await page.wait_for_timeout(2000)
            
            # 4. 봇 방어 시스템 감지 및 대기 (Cloudflare, 부정클릭방지 등)
            text_content_initial = await page.evaluate("document.body.innerText")
            bot_protection_indicators = [
                # Cloudflare
                "verifying you are human", "just a moment", "checking your browser", "cf-spinner",
                # 한국 봇 방어 시스템
                "부정클릭방지", "부정클릭 방지", "자동화방지", "invalid access", "접근제한",
                # 일반
                "bot protection", "security check"
            ]
            is_bot_protected = any(ind in text_content_initial.lower() for ind in bot_protection_indicators)
            
            if is_bot_protected:
                print("[Playwright] Bot protection detected. Waiting for auto-resolution...")
                # 봇 방어 자동 해결 대기 (최대 25초)
                protection_passed = await self.wait_for_bot_protection(page, max_wait=25)
                if not protection_passed:
                    print("[Playwright] Protection not auto-resolved. Attempting manual bypass...")
                    await self.attempt_captcha_bypass(page)
                    await page.wait_for_timeout(3000)
                    
                    # 다시 텍스트 확인
                    text_content_initial = await page.evaluate("document.body.innerText")
                    
                    # 여전히 보호 중이면 플래그 설정
                    if any(ind in text_content_initial.lower() for ind in bot_protection_indicators):
                        result["bot_protection_active"] = True
                        print("[Playwright] Bot protection still active after bypass attempts.")

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
