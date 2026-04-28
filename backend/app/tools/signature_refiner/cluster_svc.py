import json
import re
from difflib import SequenceMatcher

class ClusterService:
    @staticmethod
    def normalize_text(text: str) -> str:
        return re.sub(r'\s+', '', text)

    @staticmethod
    def find_target_clusters(report_path: str = None, similarity_threshold: float = 0.85, data: dict = None):
        if data is None:
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                raise Exception(f"Failed to read report: {e}")

        items = []
        logs = data.get('logs', {})
        for key, log in logs.items():
            res = log.get('result', {})
            # is_spam이고 자체 추출기(ibse)가 돌았던 항목만
            if res.get('is_spam') and 'ibse_signature' in res:
                items.append({
                    'log_id': key,
                    'message': log.get('message', ''),
                    'norm_msg': ClusterService.normalize_text(log.get('message', '')),
                    'current_signature': res.get('ibse_signature', '')
                })

        clusters = []
        visited = set()

        for i in range(len(items)):
            if i in visited:
                continue
            
            cluster = [items[i]]
            visited.add(i)
            
            for j in range(i + 1, len(items)):
                if j in visited:
                    continue
                ratio = SequenceMatcher(None, items[i]['norm_msg'], items[j]['norm_msg']).ratio()
                if ratio >= similarity_threshold:
                    cluster.append(items[j])
                    visited.add(j)
                    
            # 2개 이상 모인 클러스터 중, 서로 다른 시그니처가 하나라도 존재하는 그룹만 도출
            if len(cluster) > 1:
                sigs = set([item['current_signature'] for item in cluster if item['current_signature']])
                if len(sigs) > 1:
                    clusters.append(cluster)

        return data, clusters

    @staticmethod
    def find_all_similar_clusters(report_path: str = None, similarity_threshold: float = 0.85, data: dict = None):
        """
        정제기 등 특화 필터 없이, 단순히 스팸 메시지들의 내용이 기준(85%) 이상 일치하는 
        모든 그룹(2개 이상 문서가 묶인 그룹)을 반환하는 클러스터링 로직.
        data가 직접 전달되면 파일 읽기를 생략한다 (운영 서버에서 프론트엔드가 직접 로그를 전송하는 경우).
        """
        if data is None:
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                raise Exception(f"Failed to read report: {e}")

        items = []
        logs = data.get('logs', {})
        for key, log in logs.items():
            # 스팸과 햄을 구분하지 않고 전체 메시지(스팸+햄)를 대상으로 클러스터링
            items.append({
                'log_id': key,
                'message': log.get('message', ''),
                'norm_msg': ClusterService.normalize_text(log.get('message', '')),
            })

        clusters = []
        visited = set()

        # 클러스터 ID 부여자
        cluster_id_counter = 1

        for i in range(len(items)):
            if i in visited:
                continue
            
            cluster = [items[i]]
            visited.add(i)
            
            for j in range(i + 1, len(items)):
                if j in visited:
                    continue
                len1 = len(items[i]['norm_msg'])
                len2 = len(items[j]['norm_msg'])
                
                # SequenceMatcher 의 최대 가능 ratio = 2.0 * M / T
                # 여기서 M 의 최대값은 작은 문자열의 길이, T = len1 + len2
                # 이 값이 스레시홀드를 넘지 못하면 굳이 무거운 SequenceMatcher를 돌릴 필요가 없음
                max_possible_ratio = (2.0 * min(len1, len2)) / (len1 + len2) if (len1 + len2) > 0 else 0
                
                if max_possible_ratio < similarity_threshold:
                    continue

                ratio = SequenceMatcher(None, items[i]['norm_msg'], items[j]['norm_msg']).ratio()
                if ratio >= similarity_threshold:
                    cluster.append(items[j])
                    visited.add(j)
                    
            # 2개 이상 묶인 무리만 도출 (1개짜리 단독 메시지는 클러스터 뷰 타겟에서 제외)
            if len(cluster) > 1:
                # 결과에 cluster_id 를 부여하여 프론트에서 랜더링 시 활용
                clusters.append({
                    "cluster_id": cluster_id_counter,
                    "items": cluster
                })
                cluster_id_counter += 1

        return data, clusters
