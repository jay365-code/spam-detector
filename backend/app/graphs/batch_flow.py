import logging
import asyncio
from typing import TypedDict, Optional, Dict, Any, List

from langgraph.graph import StateGraph, END

from typing import Callable

# Define State
class BatchState(TypedDict):
    message: str
    s1_result: Dict[str, Any] # Rule check result
    prefetched_context: Optional[Dict[str, Any]] # [Batch Optimization] Injected Context
    pre_parsed_url: Optional[str] # KISA TXT에서 탭으로 파싱한 URL (있으면 본문 추출 대신 사용)
    pre_parsed_only_mode: Optional[bool]  # KISA TXT면 URL 없을 때 본문 추출 스킵 (Chat/Excel은 False)
    status_callback: Optional[Callable[[str], Any]] # [Log Streaming] status updates
    
    # Results
    content_result: Optional[Dict[str, Any]]
    url_result: Optional[Dict[str, Any]]
    ibse_result: Optional[Dict[str, Any]]
    
    # Final
    final_result: Optional[Dict[str, Any]]

logger = logging.getLogger(__name__)

def create_batch_graph(content_agent, url_agent, ibse_service, playwright_manager: Optional[Any] = None):
    """
    Factory to create the Unified Batch Graph with injected dependencies.
    """
    
    # --- Nodes ---
    
    async def content_node(state: BatchState):
        msg = state["message"]
        s1 = state.get("s1_result") or {}
        prefetched = state.get("prefetched_context")
        cb = state.get("status_callback")
        
        loop = asyncio.get_running_loop()
        
        if cb: await cb("🧩 [Unified Flow] Content Agent 의도 분석 노드 진입")
        
        if prefetched:
            res = await content_agent.acheck(msg, s1, status_callback=cb, content_context=prefetched)
        else:
            # Legacy/Fallback Mode
            res = await content_agent.acheck(msg, s1, status_callback=cb)
            
        return {"content_result": res}

    async def url_node(state: BatchState):
        msg = state["message"]
        content_result = state.get("content_result") or {}
        s1 = state.get("s1_result") or {}
        pre_parsed_url = state.get("pre_parsed_url")
        pre_parsed_only_mode = state.get("pre_parsed_only_mode", False)
        
        pre_parsed_url_invalidated = False
        # [NEW] 단축 URL 예외 처리: KISA 입력 URL이 파손된 단축(Shortener) URL일 경우 조기 차단
        if pre_parsed_url:
            import re
            from urllib.parse import urlparse
            test_url = pre_parsed_url if "://" in pre_parsed_url else "http://" + pre_parsed_url
            try:
                parsed = urlparse(test_url)
                domain = parsed.netloc.lower()
                path = parsed.path.strip("/")
                
                # 주요 단축 URL 서비스 식별
                shortener_domains = [
                   "bit.ly", "goo.gl", "buly.kr", "vo.la", "han.gl", 
                   "ko.gl", "tuney.kr", "sbz.kr", "me2.do", "vvd.bz", 
                   "url.kr", "m.site.naver.com", "vdo.kr"
                ]
                
                is_short = any(d in domain for d in shortener_domains)
                if is_short:
                   # 경로 부재 (길이 1 이하) OR 괄호/별표/한글 등 파손 문자 포함 여부 검사
                   if len(path) <= 1 or bool(re.search(r'[\[\]\*\(\)\{\}\<\>가-힣]', path)):
                       # KISA의 파싱 오류로 단축 도메인만 잘려나온 경우, 파라미터를 버리고 원문 본문에서 다시 URL 전체를 강제 추출하도록 유도
                       logger.warning(f"[URL Agent 단축 URL 필터] 원본 URL 필드가 훼손된 단축 URL({pre_parsed_url})로 판명되어 이를 무시하고 본문 추출 모드로 전환합니다.")
                       pre_parsed_url = None
                       pre_parsed_only_mode = False
                       pre_parsed_url_invalidated = True
            except Exception:
                pass
                
        cb = state.get("status_callback")
        if cb: await cb("🧩 [Unified Flow] URL Agent 분석 노드 진입")
        
        # 난독화 디코딩된 텍스트가 있으면 전달
        decoded_text = s1.get("decoded_text")
        res = await url_agent.acheck(msg, status_callback=cb, content_context=content_result, decoded_text=decoded_text, pre_parsed_url=pre_parsed_url, pre_parsed_only_mode=pre_parsed_only_mode, playwright_manager=playwright_manager)
        
        if pre_parsed_url_invalidated and isinstance(res, dict):
            res["pre_parsed_url_invalidated"] = True
            
        return {"url_result": res}

    async def ibse_node(state: BatchState):
        cb = state.get("status_callback")
        if cb: await cb("🧩 [Unified Flow] IBSE Agent 시그니처 추출 노드 진입")
        
        msg = state["message"]
        c_res = state.get("content_result") or {}
        obfuscated_urls = c_res.get("obfuscated_urls", [])
        
        # IBSE Agent is now Async
        res = await ibse_service.process_message(
            msg, 
            status_callback=cb,
            obfuscated_urls=obfuscated_urls
        )
        return {"ibse_result": res}


    def aggregator_node(state: BatchState):
        # Merge Logic
        c_res = state.get("content_result") or {}
        u_res = state.get("url_result") or {}
        i_res = state.get("ibse_result") or {}
        
        final = c_res.copy()
        
        # [Frontend UI Hint] 전달된 KISA 입력 URL 파라미터 보존
        final["pre_parsed_url"] = state.get("pre_parsed_url")
        
        # 1. URL Override Logic 및 Red Group(분리 감지) 조건 평가
        # [User Request 조건]
        # 1) content 햄 + URL 스팸
        # 2) 전체적인 의도는 스팸(Type B) + content 햄유사(명시적 악의 없음) + url(스팸 or inconclusive)
        
        c_is_spam = final.get("is_spam")
        existing_reason = final.get("reason", "")
        signals = final.get("signals", {})
        
        # content 햄 여부 파악: 실제 판정이 HAM인 경우에만 분리 감지 대상으로 산정.
        is_pure_content_ham = not c_is_spam
        # --- [NEW] 사전 AI 환각 URL 무결성 필터 ---
        # URL Agent의 판결을 적용하기 전에, 추출된 URL이 실제로 본문에 존재하는지 먼저 검증
        import urllib.parse
        import re
        
        fake_ips_detected = set()
        
        def is_url_in_message(url_str, original_msg, decoded_tmp):
            test_url = url_str if "://" in url_str else "http://" + url_str
            try:
                parsed = urllib.parse.urlparse(test_url)
                domain_parts = parsed.netloc.lower().split(':')[0]
                if domain_parts.startswith("www."):
                   domain_parts = domain_parts[4:]
                if not domain_parts:
                   return False
                # IP 주소 형태 배제 (오탐 방지)
                if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', domain_parts):
                   fake_ips_detected.add(domain_parts)
                   return False
                   
                # 퓨니코드(Punycode) 변환: xn-- 형태인 경우 본문 매칭을 위해 한글로 복원
                korean_domain = domain_parts
                if domain_parts.startswith('xn--'):
                   try:
                       korean_domain = domain_parts.encode("ascii").decode("idna")
                   except Exception:
                       pass
                       
                # KISA 입력 파라미터 보존
                pre_parsed = state.get("pre_parsed_url")
                if pre_parsed and (domain_parts in pre_parsed.lower() or korean_domain in pre_parsed.lower()):
                   return True
                
                # 원문, 디코딩문, 혹은 띄어쓰기 제거된 문자열에 도메인이 존재하는지 검증
                return (
                   (domain_parts in original_msg.lower()) or 
                   (korean_domain in original_msg.lower()) or
                   (domain_parts in decoded_tmp.lower()) or
                   (korean_domain in decoded_tmp.lower()) or
                   (domain_parts in re.sub(r'\s+', '', original_msg.lower())) or
                   (korean_domain in re.sub(r'\s+', '', original_msg.lower()))
                )
            except Exception:
                return False

        raw_msg = state.get("message", "")
        decoded_text = (state.get("s1_result") or {}).get("decoded_text", "")
        valid_extracted_urls = set()
        
        # 2. Content Agent가 찾은 복원 URL(난독화) 무조건 허용 (is_url_in_message 회피)
        c_obfuscated = c_res.get("obfuscated_urls") if c_res else []
        if not c_obfuscated:
            c_obfuscated = []
        elif isinstance(c_obfuscated, str): 
            c_obfuscated = [c_obfuscated]
            
        c_obf_clean = set(
            str(p).strip().replace("http://", "").replace("https://", "").rstrip("/")
            for p in c_obfuscated if p
        )
        for p in c_obf_clean:
            valid_extracted_urls.add(p)
            
        # 1. URL Agent가 식별한 URL 검증
        u_details = u_res.get("details", {}) if u_res else {}
        base_ext = str(u_details.get("extracted_url") or "").strip()
        if base_ext and base_ext.lower() != "none":
            for p in base_ext.split(","):
                p = p.strip()
                clean_p = p.replace("http://", "").replace("https://", "").rstrip("/")
                if clean_p in c_obf_clean or (p and is_url_in_message(p, raw_msg, decoded_text)):
                   valid_extracted_urls.add(p)
                   
        attempted_list = u_details.get("attempted_urls") or []
        for attempt in attempted_list:
            clean = attempt.replace("http://", "").replace("https://", "").strip().rstrip("/")
            if clean in c_obf_clean or (attempt and is_url_in_message(attempt, raw_msg, decoded_text)):
                if clean:
                   valid_extracted_urls.add(clean)
                
        # 환각이나 검열로 인해 최종적으로 남은 유효 URL이 "전혀" 없다면 URL Agent의 결과(u_res) 기각.
        # 단, 파기하기 전에 가짜 IP로 식별되었다면 원본 URL(pre_parsed_url 등) 삭제 명령 하달
        if fake_ips_detected and not valid_extracted_urls:
            final["drop_url"] = True
            final["drop_url_reason"] = "fake_ip"
            
        # (텍스트형 스팸이 Red Group으로 오분류되는 걸 차단)
        if not valid_extracted_urls:
            # 원문에 물리적으로 존재하지 않는 추측성 URL이라 기각(폐기)된 경우라도, UI 표출을 위해 목록은 남겨둠
            rejected_urls = []
            if u_res and u_res.get("details", {}).get("extracted_url") and u_res["details"]["extracted_url"].lower() != "none":
                rejected_urls.extend([p.strip() for p in u_res["details"]["extracted_url"].split(',') if p.strip()])
            if c_obfuscated:
                rejected_urls.extend([str(p).strip() for p in c_obfuscated if p])
                
            if rejected_urls:
                # 중복 제거
                unique_rejected = list(dict.fromkeys(rejected_urls))
                u_res = {
                   "details": {
                       "extracted_url": ", ".join(unique_rejected),
                       "attempted_urls": unique_rejected
                   }
                }
                if not final.get("drop_url"):
                   final["drop_url"] = True
                   final["drop_url_reason"] = "hidden_url"
            else:
                u_res = {}
            
        if u_res:
             final["url_result"] = u_res
             
             url_is_spam = u_res.get("is_spam")
             reason_lower = u_res.get("reason", "").lower()
             is_inconclusive = any(x in reason_lower for x in ["error", "inconclusive", "insufficient", "image only", "no url found", "no url extracted", "no url to scrape"])
             
             url_code = u_res.get("classification_code")
             url_reason = u_res.get("reason", "")
             
             # Red Group (붉은색 채우기) 발동 여부 검사
             # [수정] Red Group 판정 및 URL 스팸 통째로 덮어쓰기는 KISA 원본(입력 파라미터)에 URL 필드가 명시적으로 존재할 때만 발동
             has_input_url = bool(state.get("pre_parsed_url")) and not u_res.get("pre_parsed_url_invalidated")
             
             # --- [URL 단독 메시지 보호 강화 기능 제거] ---
             # URL Agent가 가이드라인(url_spam_guide.md)에 따라 익명 오픈채팅/방초대 등을 정확히 SPAM으로 식별하므로,
             # 파이프라인 단에서 키워드 기반으로 무조건 HAM으로 덮어쓰는(Override) 하드코딩된 보호 로직을 제거함.
             # 이를 통해 URL 에이전트의 최종 판단(is_spam)이 온전히 상위 노드로 전달되도록 함.
             # -----------------------------------
             
             force_red_group = False
             
             # Case 1: 완전 정상 텍스트 + 악성 단검(URL)
             if has_input_url and is_pure_content_ham and url_is_spam:
                # [수정] 텍스트가 정상(배송 등)이고 URL도 그에 연관된 정상적인 상거래(성인용품점 등)라면 면책 발동.
                if u_res.get("is_consistently_transactional") == True:
                    force_red_group = False
                    url_is_spam = False # 방어: 최종 판정에서 SPAM으로 넘어가지 않도록 변경
                    final["reason"] = f"{existing_reason} | [정보성/거래성 완전 일치: 면책특권 발동되어 URL 정상(HAM) 처리]"
                else:
                    force_red_group = True
                
             if force_red_group:
                # 붉은색 채우기 그룹 특수 처리 로직 (단순 URL 스팸 처리)
                final["is_spam"] = True
                final["reason"] = f"{existing_reason} | [텍스트 HAM + 악성 URL 분리 감지: 단순 URL 스팸 격리 ({url_reason[:30]})]"
                final["malicious_url_extracted"] = True
                final["url_spam_code"] = url_code
                final["red_group"] = True  # 명시적인 Red Group 카테고리 플래그 추가
             else:
                # Red Group에 해당하지 않는 경우의 기존 처리
                if is_inconclusive:
                    # Inconclusive -> Trust Content Verdict
                    if 'All URLs scanned' in url_reason:
                        final["reason"] = f"{existing_reason} | [URL: Inconclusive ({url_reason})]"
                    else:
                        final["reason"] = f"{existing_reason} | [URL: Suspected but Inconclusive ({url_reason})]"
                elif url_is_spam:
                    # Case 1: 본문이 비록 HAM이었더라도 URL이 SPAM이면 전체를 SPAM으로 격상.
                    final["is_spam"] = True
                    # 확률은 기존 확률과 새로 얻은 확률 중 높은 것으로 유지 보강
                    final["spam_probability"] = max(final.get("spam_probability", 0.0), u_res.get("spam_probability", 0.95))
                    
                    if has_input_url:
                        # [조건 충족] 입력 URL이 있을 때만 URL 정보로 전부 덮어씀 (Red Group 시각적 표기만 생략됨)
                        final["reason"] = f"{existing_reason} | [URL SPAM: {url_reason}]"
                        if url_code and str(url_code) != "0":
                            final["classification_code"] = url_code
                    else:
                        # [조건 미충족] 입력 URL이 빈칸이거나 단축 파손되어 본문에서 찾은 경우에는 기존(시그니처/텍스트) 사유 코드를 보호함
                        final["reason"] = f"{existing_reason} | ([보조] URL 탐지: {url_reason[:50]}...)"
                        
                        # [핫픽스] 텍스트가 HAM(오탐방지)이었을 경우 코드가 0번이 될 수 있으므로, URL의 스팸 코드를 "시그니처 판정"의 코드로 물려줍니다.
                        if url_code and str(url_code) != "0":
                            final["classification_code"] = url_code
                        
                        # [핫픽스] 이 케이스는 "URL 덮어쓰기" 명패를 버리고 "SIGNATURE" 간판을 채택할 것이므로,
                        # 아래 하단의 'URL 중복 시그니처 소거(Deduplication)' 필터로부터 시그니처를 지키기 위해 예외 쉴드를 부여합니다.
                        final["preserve_signature_override"] = True
                else:
                    # Case 3: URL(Safe) -> 명백히 안전한 사이트(CONFIRMED SAFE)인 경우, 본문과 어긋난 위장방패막이(Mismatched)인지 확인
                    is_confirmed_safe = u_res.get("is_confirmed_safe", False)
                    if is_confirmed_safe:
                        if final.get("is_spam"):
                            is_mismatched = u_res.get("is_mismatched", False)
                            spam_prob = final.get("spam_probability", 0.0)
                            
                            if is_mismatched:
                                # 확실한 역이용/방패막이로 판정된 경우만 SPAM 유지
                                final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE 판독되나, 본문-웹 명백한 불일치(위장/방패막이). SPAM 유지]"
                            else:
                                # 본문과 웹 내용이 어느 정도 일치하고 안전한 웹사이트라면, 단순 낚시성 홍보일 확률이 높으므로 HAM으로 억울함을 풀어줌
                                final["is_spam"] = False
                                final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE & Content Matched (오탐 방어 Override)]"
                            # Do NOT wipe final["classification_code"] to preserve Content Agent's original intent
                    else:
                       is_transactional_match = u_res.get("is_consistently_transactional", False)
                       if is_transactional_match and final.get("is_spam"):
                           # URL Agent가 '놀라운 연관성' 등 거래성 일치를 확신한 경우, Content Agent의 스미싱 오탐을 HAM으로 덮어씀
                           final["is_spam"] = False
                           final["reason"] = f"{existing_reason} | [URL: 상거래 완벽 일치(Transactional Match). 본문 스미싱/스팸 오탐 방어 Override]"
                       else:
                           # URL에 스팸 증거가 없어 HAM 판정되었으나, 명백히 안전하다는 증거(대형포털 등)도 없는 상태 (가입 유도, 빈 페이지 등)
                           # -> 기존 Content Agent 결과(SPAM)를 존중하여 덮어쓰지 않음
                           short_url_reason = url_reason[:80] + "..." if len(url_reason) > 80 else url_reason
                           final["reason"] = f"{existing_reason} | [URL 무혐의(원본 판단 유지) 요약: {short_url_reason}]"

        # Ensure malicious_url_extracted is explicitly in the final dict if set
        if "malicious_url_extracted" in final and final["malicious_url_extracted"] is True:
             # Ensure the value is properly returned
             final["malicious_url_extracted"] = True

        final["message_extracted_url"] = ", ".join(sorted(list(valid_extracted_urls)))

        # 2. Add IBSE Info
        if i_res:
             i_err = i_res.get("error")
             sig_val = i_res.get("signature") if not i_err else None
             if sig_val and str(sig_val).strip().upper() != "NONE":
                final["ibse_signature"] = sig_val
                final["ibse_len"] = i_res.get("byte_len_cp949", i_res.get("byte_len"))
             else:
                final["ibse_signature"] = None
             
             final["ibse_category"] = i_res.get("decision")
             
             # [NEW] 시그니처 추출 실패(unextractable) 조건으로 인해 정상 판단된 스팸을 무죄(HAM)로 덮어쓰는(Override) 악성 방어 로직 제거
             # URL Agent가 명백한 스팸으로 결정한 경우 우선순위를 지키기 위해 이 오버라이드 조건문은 폐기합니다.
             if final["ibse_category"] == "unextractable" and final.get("is_spam") is True:
                 # SPAM 판정을 유지하되 내역만 남김
                 existing_reason = final.get("reason", "")
                 final["reason"] = f"{existing_reason} | [IBSE: 시그니처 추출 불가(unextractable)이나 SPAM 판정 유지]"
                
             # [Broken URL Drop Logic]
             # IBSE Agent extracts a contextual sentence instead of the broken URL.
             # We must drop the URL from the final output to fulfill "URL : 없음" requirement.
             u_details = u_res.get("details", {}) if u_res else {}
             u_reason = u_res.get("reason", "").lower() if u_res else ""
             
             is_broken = u_details.get("is_broken_short_url") is True
             is_fake_ip = False
             
             # [숫자 난독화 / 가짜 IP 방어]
             extracted_for_check = str(u_details.get("extracted_url") or "")
             if extracted_for_check and not is_broken:
                import re, urllib.parse
                # 콤마로 여러 개가 연결되어 올 수 있으므로 분리해서 검사
                valid_url_parts = []
                for url_part in extracted_for_check.split(","):
                    url_part = url_part.strip()
                    if not url_part: continue
                    
                    parsed = urllib.parse.urlparse(url_part)
                    domain = parsed.netloc or parsed.path
                    # remove 'http://' or 'https://' from path if netloc was empty
                    if domain.startswith('//'):
                        domain = domain[2:]
                    domain = domain.split('/')[0].split(':')[0]
                    
                    is_ip_format = bool(re.match(r'^\d{1,3}(\.\d{1,3}){3}$', domain))
                    if is_ip_format:
                        # 사용자 요청안: 공인/사설 여부와 상관없이 모든 IP 형태(예: 1.4.7.9)는 URL 추출에서 강제 배제 (버전, 일반 숫자 나열 오탐 방지)
                        continue
                        
                    # [단독 도메인 (Bare Domain) 배제]
                    # 단축URL, .com, .net 등 어떠한 도메인이든 패스(path)나 파라미터가 없는 단독 도메인 형태면 엑셀 추출에서 100% 배제
                    if (not parsed.path or parsed.path == "/") and not parsed.query:
                        continue
                    
                    valid_url_parts.append(url_part)
                
                # 만약 가짜 IP들을 걸러내고 남은 정상 URL이 있다면 그것만 살린다
                if len(valid_url_parts) > 0:
                    u_details["extracted_url"] = ", ".join(valid_url_parts)
                else:
                    # 모든 파편이 다 가짜 IP였다면 fake ip 처리
                    is_fake_ip = True
             
             # User requested fix: Drop URL if Safe URL Injection is detected.
             # This is flagged by fp_sentinel_node setting final["drop_url"] = True later,
             # but we can also set it proactively here if we have a url_reason indicating it.
             url_reason = final.get("reason", "")
             url_reason_lower = url_reason.lower()
             is_injection = "위장 url" in url_reason_lower or "정상 도메인 위장" in url_reason_lower or "방패막이" in url_reason_lower or "decoy" in url_reason_lower or "safe url injection" in url_reason_lower
             
             # [Fix] Drop URL ONLY if it is a Fake IP, Safe Injection, Filtered Short URL, or Dead Domain(Typo).
             is_filtered_short = u_res.get("drop_url", False)
             is_dead_domain = any(keyword in u_reason for keyword in ["err_name_not_resolved", "dns_probe_finished_nxdomain", "err_connection_refused", "존재하지 않는 url", "네트워크 에러"])
             
             # [단독 도메인 오탐 방어 로직 제거]
             # 앞선 루프에서 모든 단독 도메인을 일괄 삭제하므로 이중 검증 불필요
             if is_injection or is_fake_ip or is_filtered_short or is_dead_domain:
                final["drop_url"] = True
                if is_fake_ip:
                    final["drop_url_reason"] = "empty_or_fake_ip"
                elif is_filtered_short:
                    final["drop_url_reason"] = "filtered_short_url"
                elif is_dead_domain:
                    final["drop_url_reason"] = "dead_domain"
                    final["reason"] = f"[URL Drop] 접속 불가 데드링크(오타 도메인 등) 간주 | {final.get('reason', '')}"
                else:
                    final["drop_url_reason"] = "safe_injection"
                
                # Drop the URL explicitly
                if "details" in u_res:
                    u_res["details"]["extracted_url"] = None
                valid_extracted_urls.clear()

             # 3. User Requested: If unextractable AND no URL was found, drop completely from Excel
             # If is_broken is True, treat it as no URL.
             has_extracted_url = bool(u_res and (u_res.get("target_urls") or u_res.get("current_url") or u_res.get("visited_history")))
             if is_broken: has_extracted_url = False
             # [수정] 정상(HAM) 메시지도 모두 엑셀 리포트에 포함되도록 exclude_from_excel 드롭 로직 제거
             
             # --- [UI 동기화 로직] ---
             # excel_handler.py 에서는 pre_parsed_url 기반으로 단독 도메인일 경우 무조건 삭제 처리함.
             # UI에서도 이와 형태를 맞추어 (URL) 텍스트를 제거하기 위해 drop_url 플래그를 사전에 활성화함.
             pre_url = state.get("pre_parsed_url")
             
             if not pre_url:
                # KISA 원본에 URL이 없는 경우, 
                # excel_handler.py 에서는 Red Group(is_separated) 조건이 아닐 때 무조건 빈칸으로 저장하므로 UI도 이를 똑같이 따라간다.
                is_separated = "[텍스트 HAM + 악성 URL 분리 감지" in str(final.get("reason", ""))
                if not is_separated:
                    final["drop_url"] = True
                    final["drop_url_reason"] = "empty_pre_parsed_url_sync"
                    
             elif pre_url and not final.get("drop_url"):
                import urllib.parse
                try:
                    # 엑셀 핸들러와 동일하게, 전체 URL이 단독 도메인들로만 구성되었거나 파손된 URL인지 검증
                    all_are_bare_or_corrupt = True
                    for u in pre_url.split(","):
                        u = u.strip()
                        if not u: continue
                        test_u = u if "://" in u else "http://" + u
                        parsed_u = urllib.parse.urlparse(test_u)
                        
                        # 파손된 형태 검사 (괄호, 별표 등. 단, 한글은 합법적인 커스텀 URL 슬러그일 수 있으므로 허용)
                        is_corrupt = bool(re.search(r'[\[\]\*\(\)\{\}\<\>]', parsed_u.path))
                        is_bare = (not parsed_u.path or parsed_u.path == "/") and not parsed_u.query
                        
                        if not is_bare and not is_corrupt:
                            all_are_bare_or_corrupt = False
                            break
                            
                    if all_are_bare_or_corrupt:
                        # 명백히 스팸으로 판정된 증거라면 예외적으로 보존
                        if final.get("red_group") or final.get("is_spam") or final.get("malicious_url_extracted"):
                            pass 
                        else:
                            final["drop_url"] = True
                            final["drop_url_reason"] = "bare_or_corrupt_domain_sync"
                except Exception:
                    pass
                 
        # [NEW] 단축 URL 이중 추출(엑셀 중복 등재) 방지
        # 유효한 URL 파편이 존재하고 최종적으로 폐기(drop_url)되지 않을 예정이라면,
        # URL중복제거 시트에서 이미 차단되므로 IBSE 문자열 시그니처는 무효화(None) 처리합니다.
        # 단, preserve_signature_override 플래그가 있는 경우(본문에서 살려내서 시그니처 위주로 가기로 한 놈)는 보호합니다.
        if valid_extracted_urls and not final.get("drop_url") and not final.get("preserve_signature_override"):
            if final.get("ibse_signature"):
                final["ibse_signature"] = None
                final["ibse_category"] = "unextractable (URL Deduplication Active)"
                
        # [NEW] 최종 안전망 (무죄 추정의 원칙)
        # 만약 판단된 SPAM 메시지이나, 유효한 URL이 없고(또는 drop_url 처리됨) IBSE 시그니처마저 추출 실패(unextractable)했다면,
        # 필터링 및 차단에 사용할 기술적 근거(지표)가 완벽히 소실된 상태이므로 강제로 HAM으로 오버라이드하여 오탐을 방지합니다.
        if final.get("is_spam") is True and str(final.get("ibse_category", "")).startswith("unextractable"):
            has_valid_url = bool(valid_extracted_urls and not final.get("drop_url"))
            if not has_valid_url:
                final["is_spam"] = False
                existing_reason = final.get("reason", "")
                final["reason"] = f"[HAM Override: 유효 URL 부재 및 시그니처 추출 불가로 인한 무죄 추정] | {existing_reason}"


                
        return {"final_result": final}

    def fp_sentinel_node(state: BatchState):
        """
        FP Sentinel (오탐 방지 정책 에이전트) - Type B 제거 및 간소화
        Type B 및 CNN 보호 로직이 제거되었으며, 최종 결과에 대한 단순 무결성 검증망 역할만 수행
        """
        final = state.get("final_result") or {}
        
        ibse_category = final.get("ibse_category")
        
        # [Old Legacy] 안전장치 해제 로그는 aggregator_node에서 처리하므로 삭제
        pass

        # Rulset 2: Type_A (Pure Spam)
        if final.get("is_spam") is True:
             semantic_class = "Type_A"
             learning_label = "SPAM"
             
        # Rulset 3: Ham
        else:
             semantic_class = "Ham"
             learning_label = "HAM"
             
        # 최종 HAM 판정 시, 앞서 병렬 실행된 IBSE 노드가 추출했던 문자열(시그니처) 초기화
        if semantic_class == "Ham":
             final["ibse_signature"] = None
             final["ibse_category"] = None
             final.pop("malicious_url_extracted", None)

        final["semantic_class"] = semantic_class
        final["learning_label"] = learning_label
        
        # [NEW] 안전망: 스팸으로 분류되었는데 분류 코드가 없을 경우 강제 할당
        if semantic_class != "Ham" and not final.get("classification_code"):
             # URL에 의해 스팸으로 뒤집힌 경우 url_spam_code 우선 적용, 없으면 기본 "0"
             final["classification_code"] = final.get("url_spam_code") or "0"
             
        # =====================================================================
        # [NEW] Batch Mode / Excel 가독성을 위한 Reason 상세 포맷팅 (Summary)
        # =====================================================================
        c_res = state.get("content_result") or {}
        u_res = state.get("url_result") or {}
        
        # 1. 텍스트 분석 결과
        c_reason = c_res.get("reason", "분석 생략됨").replace("\n", " ").strip()
        
        # 2. URL 분석 결과
        u_reason = u_res.get("summary") or u_res.get("reason", "")
        u_reason = u_reason.replace("\n", " ").strip() if u_reason else "URL 없음/분석 생략"
        
        # 3. 로직 변경 이력 추출 (기존 logic에서 '|') 로 이어붙인 로그들 포착
        raw_reason = final.get("reason", "")
        logic_steps = []
        for part in raw_reason.split("|"):
            part = part.strip()
            # 원본 c_reason과 다르면서 대괄호로 시작하는 로그 태그들을 필터링
            if part.startswith("[") and part != c_reason:
                logic_steps.append(f"- {part}")
                
        # (FP Override는 이미 위에서 원본 reason 문자열에 추가되므로 따로 넣지 않아도 로직상 split되어 잡힘, 
        # 단 drop_url 은 추가)
        if final.get("drop_url"):
             logic_steps.append(f"- [URL 배제 조치] 파이프라인에서 악성 여부 입증 부족(Safe Injection) 또는 데드링크 파제로 인해 URL 필드 삭제 처리됨")

        logic_str = "\n".join(logic_steps) if logic_steps else "- 특이사항 없이 Content Agent 판정 유지"
        
        # 최종 판정 직관화
        if final.get("is_spam"):
            final_verdict_str = "🚫 SPAM (스팸)"
        else:
            if "Override" in logic_str or "무죄 추정" in logic_str:
                final_verdict_str = "🛡️ HAM Override (시스템 오탐 방어 적용)"
            else:
                final_verdict_str = "✅ HAM (정상)"
        
        # 다중행 문자열 조립
        formatted_reason = (
            f"▼ [최종 판정]: {final_verdict_str}\n\n"
            f"[1. 텍스트 의도 분석]\n- {c_reason}\n\n"
            f"[2. URL 검증 분석]\n- {u_reason}\n\n"
            f"[3. 파이프라인 최종 의사결정 로그]\n{logic_str}"
        )
        final["reason"] = formatted_reason
             
        return {"final_result": final}
        

    # --- Conditional Logic ---
    
    def router(state: BatchState):
        c_res = state.get("content_result") or {}
        msg = state.get("message", "")
        s1 = state.get("s1_result") or {}
        
        # [Fallback] If Content Agent failed due to Quota Error, halt the pipeline immediately 
        c_reason = c_res.get("reason", "").lower()
        if "quota" in c_reason or "exhausted" in c_reason or "429" in c_reason:
            logger.warning(f"[Graph Router] Halting pipeline due to Quota Error in Content Agent.")
            return "aggregator_node"
            
        routes = []
        
        # Check URL existence (Pre-check) to avoid unnecessary agent call
        import re
        # 원본 메시지에서 URL 체크 (한글 도메인 지원)
        # url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
        url_pattern = re.compile(r'(?:https?://|www\.)\S+|[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.[a-zA-Z가-힣]{2,}')

        # 원본 메시지에서 URL 체크
        has_url = bool(url_pattern.search(msg))
        
        # 난독화 디코딩된 텍스트에서도 URL 체크
        decoded_text = s1.get("decoded_text")
        if decoded_text and not has_url:
            has_url = bool(url_pattern.search(decoded_text))
        
        # 또는 s1에서 이미 추출한 decoded_urls가 있으면 사용
        if s1.get("decoded_urls"):
            has_url = True
            
        # [NEW] KISA TXT 등으로 pre_parsed_url 이 명시적으로 넘어온 경우
        if state.get("pre_parsed_url"):
            has_url = True
            
        # [NEW] Content Agent가 난독화 복원 도메인을 찾아낸 경우 무조건 URL 검사 진행
        if c_res and c_res.get("obfuscated_urls"):
            has_url = True
            
        # If Content Spam -> Run URL (if exists) AND IBSE (Parallel)
        # If Content Ham -> Run URL (if exists) -> If URL Spam -> Aggregator
        
        # Logic: 
        # Always run URL if exists (to catch Phishing missed by Content)
        if has_url:
            routes.append("url_node")
            
        # Run IBSE if Content is Spam (정상 HAM 메시지에 대한 LLM 비용 소모를 방지하기 위함)
        if c_res.get("is_spam"):
            routes.append("ibse_node")
        
        if not routes:
            return "aggregator_node"
            
        return routes

    def url_to_ibse_router(state: BatchState):
        """
        URL Node 완료 후, 초기 라우터에서 비용 절감을 위해 스킵되었던 IBSE 추출기가
        'URL 은닉 파손 스팸' 탐지 조건에 의해 뒤늦게 시그니처가 필요해질 경우 지연 호출(Lazy Trigger)하는 라우터
        """
        u_res = state.get("url_result") or {}
        c_res = state.get("content_result") or {}
        
        # 1. 텍스트가 HAM이었어서 초기 병렬 라우터 분기에서 IBSE를 건너뛰었는가?
        content_was_ham = not c_res.get("is_spam")
        
        # 2. URL Agent가 스크래핑을 통해 이 메시지를 스팸으로 재판결(격상) 했는가?
        url_is_spam = u_res.get("is_spam")
        
        # 3. 입력 URL 파라미터가 없거나 파손되어서, 이 스팸 판결의 공로를 (URL) 덮어쓰기 대신 (SIGNATURE) 명패로 올려야 하는가?
        has_input_url = bool(state.get("pre_parsed_url")) and not u_res.get("pre_parsed_url_invalidated")
        
        if content_was_ham and url_is_spam and not has_input_url:
            return "ibse_node"
            
        return "aggregator_node"


    # --- Graph Construction ---
    workflow = StateGraph(BatchState)
    
    workflow.add_node("content_node", content_node)
    workflow.add_node("url_node", url_node)
    workflow.add_node("ibse_node", ibse_node)
    workflow.add_node("aggregator_node", aggregator_node)
    workflow.add_node("fp_sentinel_node", fp_sentinel_node)
    
    workflow.set_entry_point("content_node")
    
    # Conditional Edges from Content
    workflow.add_conditional_edges(
        "content_node",
        router,
        ["url_node", "ibse_node", "aggregator_node"]
    )
    
    # Conditional Edges from URL (Lazy IBSE Triggering for Hidden URL Spams)
    workflow.add_conditional_edges(
        "url_node",
        url_to_ibse_router,
        ["ibse_node", "aggregator_node"]
    )
    
    # Convergence
    workflow.add_edge("ibse_node", "aggregator_node")
    
    # FP Sentinel Policy Engine
    workflow.add_edge("aggregator_node", "fp_sentinel_node")
    workflow.add_edge("fp_sentinel_node", END)
    
    return workflow.compile()
