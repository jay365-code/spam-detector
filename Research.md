# 스팸 탐지기 클러스터링(유사 메시지 묶어보기) 기능 분석 (Research)

## 1. 현상 요약
- **Localhost:** 저장된 JSON 리포트를 불러오거나 분석 후 "유사 메시지 묶어보기" 기능을 사용했을 때 클러스터링이 정상 동작함.
- **Remote Server:** 파일을 업로드하여 실시간 분석을 돌린 뒤 "유사 메시지 묶어보기" 버튼을 클릭하면 아무 동작도 일어나지 않음. (결과가 다름)

## 2. 원인 분석 (코드 상세 추적)

### 2.1 프론트엔드의 `activeReportFileName` 의존성 문제
`frontend/src/App.tsx` 파일 내에서 "유사 메시지 묶어보기" 버튼을 클릭하면 `toggleClusterViewMode` 함수가 호출됩니다. 기존 코드는 다음과 같았습니다.

```typescript
const toggleClusterViewMode = async () => {
  const nextVal = !isClusterViewMode;
  setIsClusterViewMode(nextVal);
  
  if (nextVal && activeReportFileName) { // 👈 원인 발생 지점
    // ... API fetch 로직 ...
  }
};
```
- `activeReportFileName` 상태값은 **사용자가 이전에 분석 완료하여 저장해 둔 `.json` 리포트 파일을 화면 우측 상단의 "불러오기(Open File)"를 통해 수동으로 로드했을 때만 값이 할당**됩니다.
- 반면 Remote 환경 등에서 엑셀을 업로드하여 **실시간으로 분석을 마친 직후**에는 `activeReportFileName`이 `null`입니다. 대신 `downloadFilename`에 파일명이 저장됩니다.
- 따라서 조건문(`&& activeReportFileName`)을 통과하지 못해, 프론트엔드에서 아예 백엔드 클러스터링 API를 호출(fetch)하지 않고 있었습니다. 
- Localhost에서 잘 작동했던 이유는 로컬 테스트 시 보통 저장된 기존 리포트 파일을 "불러오기" 해서 테스트했기 때문에 `activeReportFileName`이 채워져 있었기 때문입니다.

### 2.2 백엔드 API의 준비 상태
`backend/app/main.py`의 클러스터링 엔드포인트(`@app.post("/api/reports/{filename}/cluster-all")`)를 분석한 결과, 백엔드에는 이미 파일 시스템 없이도 동작할 수 있도록 훌륭하게 설계되어 있었습니다.

```python
# 백엔드 코드 요약
@app.post("/api/reports/{filename}/cluster-all")
async def cluster_all_api(filename: str, request: ClusterAllRequest = None):
    # 1순위: POST body에서 전달받은 logs 데이터 사용 (운영 서버 대응)
    if request and request.logs:
        data = {"logs": request.logs}
        _, clusters = ClusterService.find_all_similar_clusters(data=data)
```
즉, 백엔드는 파일(`filename`)이 물리적으로 존재하지 않더라도 클라이언트에서 실시간 `logs` 데이터만 `POST` Body로 보내주면 이를 이용해 인메모리에서 즉시 클러스터링을 돌려주는 로직을 갖추고 있었습니다. 오직 프론트엔드 호출 조건만이 문제였습니다.

### 2.3 동일한 버그 잠재 구역 발견 (Signature Refiner)
"시그니처 자동 정제(✨)" 기능을 담당하는 `SignatureRefinerModal` 컴포넌트 역시 `App.tsx`에서 Props를 넘겨받을 때 아래와 같이 하드코딩 되어 있었습니다.
```tsx
<SignatureRefinerModal
  reportFilename={activeReportFileName}
/>
```
이로 인해 실시간 분석 직후 LLM 시그니처 정제 기능을 실행하려고 하면 URL 경로가 `/api/reports/null/...` 과 같이 비정상적으로 요청되는 동일한 구조적 결함을 안고 있었습니다.

## 3. 해결 조치 사항 (`App.tsx` 코드 수정)

프론트엔드 `frontend/src/App.tsx`의 두 가지 지점을 수정하여 실시간 데이터(`logs`)가 있을 경우 항상 API가 정상 호출되도록 조치했습니다.

**[수정 1] `toggleClusterViewMode` 함수 개선**
```typescript
const targetFile = activeReportFileName || downloadFilename || 'realtime_report.json';
// activeReportFileName이 없더라도 현재 메모리상에 로그(logs) 데이터가 존재하면 실행
if (nextVal && Object.keys(logs).length > 0) {
  setIsFetchingClusters(true);
  try {
    const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(targetFile)}/cluster-all`, {
// ...
```

**[수정 2] `SignatureRefinerModal` Props 개선**
```typescript
<SignatureRefinerModal
  isOpen={isRefinerModalOpen}
  onClose={() => setIsRefinerModalOpen(false)}
  // Fallback 파일명 적용으로 'null' URL 요청 방지
  reportFilename={activeReportFileName || downloadFilename || 'realtime_report.json'}
  logs={logs}
// ...
```

## 4. 결론
원격 서버 자체의 버그가 아니라, **"실시간 데이터 분석 직후"** 라는 특정 시나리오에서 프론트엔드가 백엔드 API를 호출하지 않도록 막혀있던 UI 상태 분기(`activeReportFileName` 검사) 문제였습니다. 
해당 조건을 `Object.keys(logs).length > 0` (데이터 존재 유무)로 수정하고, 의미 없는 URL 호출을 막기 위해 가상의 Fallback 문자열(`realtime_report.json`)을 타겟으로 주도록 하여 문제를 말끔하게 해결했습니다. 이제 리포트를 불러오든 실시간 분석을 마쳤든 Remote 서버에서 클러스터링과 정제 기능 모두 완벽하게 동작합니다.
