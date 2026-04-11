import os

target = '''                # Acquire semaphore before doing heavy work (creating context)
                async with self._semaphore:
                    # ??컨텍?트 ?성 (모바?????이??- SMS??모바?에???릭???
                    logger.debug("Creating mobile context (iPhone emulation)...")
                    context = await self.browser.new_context('''

target2 = '''                # Acquire semaphore before doing heavy work (creating context)
                async with self._semaphore:
                    logger.debug("Creating mobile context (iPhone emulation)...")
                    context = await self.browser.new_context('''

replacement = '''                # Acquire semaphore before doing heavy work (creating context)
                async with self._semaphore:
                    is_kakao = "kakao.com" in url.lower()
                    if is_kakao:
                        logger.debug(f"Creating Desktop context for Kakao URL to prevent app deep-link hangs: {url}")
                        context = await self.browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            viewport={"width": 1920, "height": 1080},
                            device_scale_factor=1,
                            is_mobile=False,
                            has_touch=False,
                            ignore_https_errors=True
                        )
                    else:
                        logger.debug("Creating mobile context (iPhone emulation)...")
                        context = await self.browser.new_context('''

filepath = 'backend/app/agents/url_agent/tools.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Since there is broken encoding in the comment, we replace via regex or precise string matching.
import re
new_content = re.sub(
    r'async with self._semaphore:\s+logger\.debug\("Creating mobile context \(iPhone emulation\)\.\.\."\)\s+context = await self\.browser\.new_context\(',
    replacement.split('async with self._semaphore:')[1],
    content,
    flags=re.MULTILINE
)

# If regex failed because of the broken encoding comment, try a more robust split
if 'is_kakao' not in new_content:
    parts = content.split('async with self._semaphore:')
    if len(parts) > 1:
        sub_parts = parts[1].split('context = await self.browser.new_context(', 1)
        if len(sub_parts) > 1:
            new_second_half = replacement.split('async with self._semaphore:')[1].split('context = await self.browser.new_context(')[0] + 'context = await self.browser.new_context(' + sub_parts[1]
            content = parts[0] + 'async with self._semaphore:' + new_second_half
            new_content = content

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)
    print("Patched tools.py successfully.")
