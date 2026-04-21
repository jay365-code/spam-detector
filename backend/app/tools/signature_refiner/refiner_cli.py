import asyncio
import argparse
import os
import json
from dotenv import load_dotenv

from .cluster_svc import ClusterService
from .llm_analyzer import LLMAnalyzer
from .user_interface import UserInterface

# .env 로드
dotenv_path = os.path.join(os.path.dirname(__file__), "../../../.env")
load_dotenv(dotenv_path)

async def main():
    parser = argparse.ArgumentParser(description="Signature Deduplicator - LLM 기반 중복/파편화 시그니처 정제 도구")
    parser.add_argument("--report", required=True, help="분석 대상이 되는 report.json 파일의 절대 경로")
    args = parser.parse_args()

    report_path = args.report
    if not os.path.exists(report_path):
        print(f"Error: Report file not found at {report_path}")
        return

    print("🔍 [Phase 1] JSON 분석 및 85% 유사도 타겟 클러스터 탐지 중...")
    
    # 1. 클러스터링
    data, clusters = ClusterService.find_target_clusters(report_path)
    
    if not clusters:
        print("✅ 시그니처가 파편화된 클러스터가 발견되지 않았습니다. 정제할 항목이 없습니다.")
        return
        
    print(f"🎯 총 {len(clusters)}개의 타겟 클러스터를 발견했습니다. LLM 검토를 시작합니다...\n")

    # 2. LLM 초기화
    analyzer = LLMAnalyzer()
    
    applied_count = 0
    logs = data.get("logs", {})

    # 3. 클러스터별 LLM 검토 및 순차 Confirm
    for idx, cluster in enumerate(clusters, 1):
        print(f"🤖 그룹 {idx}에 대한 LLM 심층 분석 중...")
        proposed = await analyzer.analyze_cluster(cluster)
        
        # 4. 리뷰 및 결재
        is_approved = UserInterface.prompt_confirmation(cluster, proposed, idx, len(clusters))
        
        if is_approved:
            new_signature = proposed.get("signature")
            b_len = len(new_signature.encode('cp949', errors='replace'))
            
            # 클러스터 내 원본 로그들 덮어쓰기 실시
            for item in cluster:
                log_id = item['log_id']
                if log_id in logs:
                    logs[log_id]['result']['ibse_signature'] = new_signature
                    logs[log_id]['result']['ibse_len'] = b_len
                    # 꼬리표 추가
                    existing_cat = logs[log_id]['result'].get('ibse_category', '')
                    if "refined_by_llm" not in existing_cat:
                         logs[log_id]['result']['ibse_category'] = (existing_cat + " (refined_by_llm)").strip()
            applied_count += 1

    # 5. 최종 데이터 덮어쓰기 처리
    if applied_count > 0:
        print(f"\n💾 총 {applied_count}개의 클러스터에 대해 승인이 완료되어 원본 파일에 덮어씁니다...")
        # 백업 본능
        backup_path = report_path + ".refiner.back"
        if not os.path.exists(backup_path):
             import shutil
             shutil.copyfile(report_path, backup_path)
             
        with open(report_path, 'w', encoding='utf-8') as f:
             json.dump(data, f, ensure_ascii=False, indent=2)
        print("🎉 파일 업데이트가 완전히 종료되었습니다!")
    else:
        print("\n⏩ 승인된 항목이 없어 파일이 수정되지 않았습니다.")

if __name__ == "__main__":
    asyncio.run(main())
