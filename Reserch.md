# 스팸 판정 불일치 원인 분석 보고서

## 1. 문제 현상 요약
동일한 목적지 URL(`http://samkorex.com/index.html` - 삼성전자 소개 페이지)과 거의 동일한 텍스트를 가진 두 메시지가 파이프라인에서 상이한 최종 판정을 받았습니다.

* **Case 1 ("안녕하세요 삼전에서..."):** 🚫 최종 SPAM 처리
  * **원인:** URL Agent가 `is_mismatched=true` 및 `is_confirmed_safe=false` 반환. 방패막이(Evasion) 사이트로 인식하여 URL 무혐의 판정을 내렸으나, 상위 파이프라인에서 Content Agent의 원래 판단(SPAM)을 그대로 유지함.
* **Case 2 ("이주희 삼전에서..."):** 🛡️ 최종 HAM (오탐 방어) 처리
  * **원인:** URL Agent가 `is_confirmed_safe=true` 및 `is_mismatched=false` 반환. 합법적 사업자 정보가 있는 안전한 사이트로 확정하여, 상위 파이프라인에서 '오탐 방어 Override' 로직이 발동, 전체 메시지를 HAM으로 덮어씀.

---

## 2. 파이프라인 코드 분석 (`backend/app/graphs/batch_flow.py`)

`batch_flow.py`의 `aggregator_node` 로직(547~572 라인)에 따르면, URL Agent가 반환하는 **`is_confirmed_safe`** 와 **`is_mismatched`** 의 상태에 따라 결과가 크게 달라집니다.

```python
is_confirmed_safe = u_res.get("is_confirmed_safe", False)
if is_confirmed_safe:
    if final.get("is_spam"):
        is_mismatched = u_res.get("is_mismatched", False)
        if is_mismatched:
            # 방패막이로 판정 -> SPAM 유지
            final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE 판독되나, 본문-웹 명백한 불일치(위장/방패막이). SPAM 유지]"
        else:
            # 안전한 사이트 & 내용 일치 -> HAM 으로 오버라이드 (Case 2 발동)
            final["is_spam"] = False
            final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE & Content Matched (오탐 방어 Override)]"
else:
    # URL이 무혐의라도 안전 확정이 아니면 기존 SPAM 판정 유지 (Case 1 발동)
    final["reason"] = f"{existing_reason} | [URL 무혐의(원본 판단 유지) 요약: {short_url_reason}]"
```

* **결론:** 두 케이스의 결과가 갈린 근본적인 이유는 LLM(URL Agent)이 **Case 1에서는 `is_confirmed_safe=False`**, **Case 2에서는 `is_confirmed_safe=True`** 를 반환했기 때문입니다.

---

## 3. LLM 프롬프트 가이드라인 충돌 분석 (`url_spam_guide.md`)

그렇다면 왜 LLM은 동일한 웹페이지에 대해 다른 판단을 내렸을까요? 
이는 `backend/data/url_spam_guide.md` 파일 내에 존재하는 **두 가지 상충되는 룰** 때문입니다. 메시지의 첫 단어("안녕하세요" vs "이주희")라는 미세한 토큰 차이로 인해 LLM이 주목하는 가이드라인 규칙이 달라졌습니다.

### 📌 충돌 지점 1: 우회(Evasion) 가설 (Case 1이 선택한 룰)
> *"우회(Evasion) 가설 판단력 위임: SMS는 도박/사기를 주장하는데 접속한 웹은 유튜브, 뉴스 기사, 카카오 채널일 경우 '방패막이용 미끼 가짜 링크다'라고 넘겨짚어서 해당 URL 자체에 SPAM 선고를 내리지 마십시오. 이 경우 URL 자체는 `is_spam=false`로 판정하되, 문맥의 심각한 어긋남을 감지했음을 보고하기 위해 **`is_mismatched=true` 로만 설정**해주십시오."*

* **Case 1의 사고:** 삼전 주식을 7만원에 판다는 사기 문자(피싱)인데, 실제 웹은 정상적인 기업 페이지네? 이건 방패막이(미끼) 링크구나! 👉 `is_mismatched=True`, `is_confirmed_safe=False` 반환.

### 📌 충돌 지점 2: 유니버설 사업자 면책 룰 (Case 2가 선택한 룰)
> *"유니버설 사업자 면책 룰: 접속한 웹페이지 하단에 **'사업자 등록번호'** 또는 그에 준하는 합법적인 업체 상호 정보가 온전히 기재되어 있는 경우... SMS 본문과 웹 콘텐츠 간의 텍스트가 서로 어긋나(미끼처럼) 보이더라도 **절대로 '기만적 불일치(Lure)'로 과잉 추론하여 `is_mismatched=true`나 SPAM으로 분류하지 마십시오.** ... 무조건 `is_confirmed_safe=true` 를 반환하십시오."*

* **Case 2의 사고:** 웹페이지 하단에 삼성전자의 실제 사업자 등록번호(124-81-00998)와 전영현 대표자 이름이 있네! 사업자 번호가 있으면 절대 과잉 추론하지 말라고 했으니 무조건 안전 사이트다! 👉 `is_mismatched=False`, `is_confirmed_safe=True` 반환.

---

## 4. 해결 방안 (수정 계획)

이러한 "대기업 사칭 피싱 스팸"이 사업자 번호 면책 룰 때문에 정상(HAM)으로 오분류되는 문제를 해결하려면, `url_spam_guide.md`의 지침을 명확하게 수정해야 합니다.

**[제안하는 프롬프트 수정안]**
1. **면책 룰 예외 조항 강화:** `url_spam_guide.md`의 '주의: 대형 포털 및 뉴스 사이트는 조건부 특권' 항목을 확장하여, **"대형 공식 기업 홈페이지(예: 삼성전자) 사칭"** 케이스를 명시적으로 추가합니다. 
2. **사업자 번호 룰 세분화:** 피싱/사기 메시지(예: 시세 대비 터무니없는 주식 공급)가 분명한데 대기업 사업자 정보가 있는 방패막이 사이트로 연결될 경우, **유니버설 사업자 면책 룰을 무시하고 반드시 `is_mismatched=true` 및 면책 불허**를 내리도록 예외 조건을 강력하게 삽입합니다.

이후 승인을 거쳐 `url_spam_guide.md` 코드를 수정할 예정입니다.
