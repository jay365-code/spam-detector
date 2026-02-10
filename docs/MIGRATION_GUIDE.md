# Spam Detector 이관 가이드 (Migration Guide)

이 문서는 **Spam Detector** 프로젝트를 새로운 노트북(환경)으로 옮겨 실행하는 방법을 설명합니다.

## 1. 사전 준비 (Pre-requisites)
새로운 노트북에 다음 프로그램들이 설치되어 있어야 합니다.
- **Python 3.10 이상**: [python.org](https://www.python.org/downloads/) (설치 시 "Add Python to PATH" 체크 필수)
- **Node.js (LTS 버전)**: [nodejs.org](https://nodejs.org/) (Frontend 실행용)
- **Git**: [git-scm.com](https://git-scm.com/) (선택 사항, 코드 복사 시 편리)

## 2. 프로젝트 파일 복사
기존 노트북의 `Spam Detector` 폴더를 통째로 복사합니다.
단, 용량이 크거나 불필요한 다음 폴더들은 **제외**하고 복사하는 것이 좋습니다 (새 환경에서 다시 생성됨).
- `.venv` (Python 가상환경)
- `.git` (Git 저장소 정보 - 필요시 포함)
- `backend/frontend/node_modules` (Node.js 라이브러리)
- `backend/__pycache__` (캐시 파일)

**필수 포함 폴더/파일:**
- `backend/` (소스코드 전체)
- `backend/.env` (API 키 등 설정 파일 - **가장 중요**)
- `backend/data/` (ChromaDB 벡터 데이터베이스 - **학습 데이터 유지하려면 필수**)
- `spams/` (스팸 데이터 파일들)

## 3. 백엔드(Backend) 설정
명령 프롬프트(cmd) 또는 PowerShell을 열고 `Spam Detector` 폴더로 이동하여 진행합니다.

### 3.1 가상환경 생성 및 활성화
```bash
# 프로젝트 루트에서 실행
cd backend
python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
```

### 3.2 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 3.3 Playwright 브라우저 설치 (URL 분석용)
```bash
playwright install
```

## 4. 프론트엔드(Frontend) 설정
새로운 터미널을 열고 진행합니다.

```bash
cd backend/frontend
npm install
```

## 5. 실행 방법

### 통합 실행 (Backend + Frontend)
현재 구조상 Backend가 API 서버를 담당하고 Frontend는 개발 모드로 실행해야 할 수 있습니다.

**Backend 실행:**
```bash
# backend 폴더에서 (.venv 활성화 상태)
python run.py
# 또는
uvicorn app.main:app --reload
```
- 서버 주소: `http://localhost:8000`
- API 문서: `http://localhost:8000/docs`

**Frontend 실행:**
```bash
# backend/frontend 폴더에서
npm run dev
```
- 웹 접속: `http://localhost:5173` (Vite 기본 포트)

### 5.5 (선택) Spam Validator (Comparison Tool) 실행
이 도구는 `comparison-tool` 폴더에 위치하며 별도로 실행해야 합니다.

**Backend 실행:**
```bash
# 1. 이동
cd comparison-tool/backend

# 2. 가상환경 생성 (기본 앱과 별도 관리 추천)
python -m venv venv
venv\Scripts\activate

# 3. 라이브러리 설치
pip install -r requirements.txt

# 4. 서버 실행
uvicorn main:app --port 8001 --reload
```
- API 서버: `http://localhost:8001`

**Frontend 실행:**
```bash
# 1. 이동
cd comparison-tool/frontend

# 2. 설치
npm install

# 3. 실행
npm run dev
```
- 웹 접속: `http://localhost:5174` (기본 앱과 포트 충돌 시 자동으로 5174 할당됨)

## 6. 트러블슈팅
- **API 키 오류**: `.env` 파일이 `backend/` 폴더 내에 정확히 있는지 확인하세요.
- **DB 오류**: `backend/data/chroma_db` 폴더가 잘 복사되었는지 확인하세요. 없으면 처음부터 다시 임베딩해야 할 수 있습니다.
- **브라우저 오류**: URL 분석 시 에러가 나면 `playwright install`을 다시 실행하세요.
- **PowerShell 실행 오류**: `.venv\Scripts\activate` 실행 시 보안 오류가 발생하면 아래 명령어를 입력하세요.
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
  또는 Command Prompt(ad)를 사용하여 `backend/.venv/Scripts/activate.bat`를 실행하세요.
- **npm 명령어를 찾을 수 없음**: Node.js가 설치되지 않았거나 PATH에 등록되지 않았습니다.
  1. [nodejs.org](https://nodejs.org/)에서 LTS 버전을 다운로드하여 설치하세요.
  2. 설치 시 "Automatically install the necessary tools..." 체크박스는 선택하지 않아도 됩니다.
  3. 설치 후 **새로운 터미널(cmd/powershell)**을 열어야 `npm` 명령어가 인식됩니다.

## 7. 외부 접속 (같은 와이파이/네트워크의 다른 기기에서 접속)
Frontend를 띄운 노트북이 아닌, **다른 노트북이나 모바일 기기**에서 접속하려면 추가 설정이 필요합니다.

### 7.1 IP 주소 확인
서버가 실행된 노트북의 IP 주소를 확인합니다.
- Windows: `ipconfig` (IPv4 주소 확인, 예: `192.168.0.15`)
- Mac: `ifconfig`

### 7.2 Backend 실행 (Host 설정)
외부에서 접속할 수 있도록 `0.0.0.0`으로 실행해야 합니다.

**Spam Detector Backend:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Comparison Tool Backend (선택):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### 7.3 Frontend 코드 수정 (API 주소 변경)
Frontend가 Backend에 요청을 보낼 때 `localhost` 대신 **위에서 확인한 IP 주소**를 사용해야 합니다.

**Spam Detector Frontend:**
- 소스 코드 내에서 API 호출 주소를 `localhost`에서 `192.168.0.15` 등으로 변경해야 할 수 있습니다. (설정 파일이나 api.ts 확인 필요)

**Comparison Tool Frontend:**
- `comparison-tool/frontend/src/App.tsx` 파일을 엽니다.
- `http://localhost:8000` -> `http://192.168.0.15:8000` (예시)
- `http://localhost:8001` -> `http://192.168.0.15:8001` (예시)
- 저장 후 Frontend를 다시 실행합니다.

### 7.4 Frontend 실행 (Host 옵션)
```bash
npm run dev -- --host
```
- 실행 후 `Network: http://192.168.0.15:5173` 등의 주소가 표시됩니다.
- 이 주소로 다른 기기에서 접속할 수 있습니다.

### 7.5 방화벽 (Firewall)
접속이 안 된다면 Windows 방화벽에서 `8000`, `8001`, `5173`, `5174` 포트의 인바운드 연결을 허용해야 합니다.
(가장 쉬운 테스트 방법은 잠시 방화벽을 끄고 확인하는 것입니다.)
