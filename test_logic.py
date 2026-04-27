import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from backend.app.graphs.batch_flow import aggregator_node

async def run():
    # 1. 가짜 IP 테스트 (KISA 원본이 2.0.1.7이고, AI가 casino.com 찾은 경우)
    state_fake_ip = {
        "pre_parsed_url": "2.0.1.7",
        "url_agent_result": {
            "is_spam": True,
            "is_confirmed_safe": False,
            "details": {"extracted_url": "casino.com"},
            "reason": "Found casino link"
        },
        "content_agent_result": {
            "is_spam": True,
            "malicious_url_extracted": True,
            "red_group": False,
            "reason": "도박 사이트 홍보"
        }
    }
    
    # 2. 데드링크 테스트 (단독 도메인인데 스팸 확정 못받은 경우)
    state_dead_link = {
        "pre_parsed_url": "bad-loan-4929.com",
        "url_agent_result": {
            "is_spam": False,
            "is_confirmed_safe": False,
            "details": {"extracted_url": "bad-loan-4929.com"},
            "reason": "[네트워크 에러: dns_probe_finished_nxdomain] 접속 불가로 Inconclusive"
        },
        "content_agent_result": {
            "is_spam": False,
            "malicious_url_extracted": False,
            "red_group": False,
            "reason": "일반 대출 안내 문자로 판단 (Ham)"
        }
    }
    
    print("=== 테스트 1: 가짜 IP 처리 (2.0.1.7) ===")
    try:
        res1 = await aggregator_node(state_fake_ip)
        final1 = res1.get("final_verdict", {})
        print(f"drop_url 상태: {final1.get('drop_url')}")
        print(f"drop_url_reason: {final1.get('drop_url_reason')}")
        print(f"오버라이드 존재여부: {'extracted_url_override' in final1}")
    except Exception as e:
        print("Error:", e)

    print("\n=== 테스트 2: 스팸 미확정 데드링크 보존 (bad-loan-4929.com) ===")
    try:
        res2 = await aggregator_node(state_dead_link)
        final2 = res2.get("final_verdict", {})
        print(f"drop_url 상태: {final2.get('drop_url', False)}")
        if final2.get('drop_url'):
            print(f"삭제 사유: {final2.get('drop_url_reason')}")
        else:
            print("결과: 안전하게 보존됨 (drop_url 발동 안함)")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(run())
