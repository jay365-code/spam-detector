class UserInterface:
    @staticmethod
    def prompt_confirmation(cluster_items, proposed_result, cluster_idx, total_clusters):
        """
        터미널에서 사용자에게 변경 사항을 제안하고 컨펌(Y/N/S)을 받습니다.
        """
        print(f"\n{'='*60}")
        print(f"🎯 [Cluster {cluster_idx}/{total_clusters}] 시그니처 정제 제안서")
        print(f"{'='*60}")
        
        # 원본 메시지 및 기존 시그니처 요약 출력
        print("[해당 그룹의 원본 파편화 내역 요약]")
        for i, item in enumerate(cluster_items[:3]): # 최대 3개까지만 보여줌
            msg_snippet = item['message'].replace("\n", " ")[:60] + "..."
            print(f"  - Msg {i+1}: {msg_snippet}")
            print(f"    ├─ 기존 시그니처: \033[91m{item['current_signature']}\033[0m")
        if len(cluster_items) > 3:
            print(f"  ... 외 {len(cluster_items) - 3}건 동일 패턴")

        print("\n[🤖 LLM 정제 결과]")
        decision = proposed_result.get("decision")
        if decision == "unextractable":
            print("  ❌ \033[93m추출 포기 (Unextractable)\033[0m: 유니크함 훼손 등 가이드라인 미달로 기존 సి그니처 유지를 결정했습니다.")
            print(f"  📝 사유: {proposed_result.get('reason')}")
            return False # 적용 안함
            
        elif decision == "error":
             print(f"  ⚠️ 시스템 에러: {proposed_result.get('reason')}")
             return False

        else:
            new_sig = proposed_result.get("signature", "")
            reason = proposed_result.get("reason", "")
            print(f"  ✅ \033[92m신규 통일 시그니처 제안:\033[0m \033[96m{new_sig}\033[0m")
            print(f"  📝 채택 사유: {reason}")
            
        # 사용자 입력 대기
        while True:
            ans = input("\n👉 위 제안을 이 클러스터 전체에 덮어쓰시겠습니까? [y(승인)/n(스킵=기존유지)]: ").lower().strip()
            if ans in ['y', 'yes']:
                return True
            elif ans in ['n', 'no', 's', 'skip']:
                print("  ⏩ 해당 클러스터는 기존 시그니처를 유지합니다.")
                return False
            else:
                print("  ⚠️ 잘못된 입력입니다. 'y' 또는 'n'을 입력하세요.")
