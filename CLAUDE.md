# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 성격

국민취업지원제도 상담사를 돕는 "상담사 코파일럿"의 MVP이자, 비개발자에게 RAG를 가르치는 **교육용 실습 코드**입니다. `docs/교안1_hello_RAG.pptx`, `docs/교안2_매뉴얼_RAG.pptx`가 각각 `hello_rag/`, `manual_rag/`와 짝을 이룹니다.

따라서 코드는 의도적으로 단순합니다. 수정할 때 다음 관례를 유지하세요.

- 폴더마다 `1_*.py` → `2_*.py` 순서로 실행하는 **번호 붙은 단일 파일 스크립트**. 모듈 분리·클래스·패키지 구조를 도입하지 않습니다.
- 주석은 한국어이고 `# ① 자료 읽기`, `# ② 색인 만들기`처럼 원 번호로 단계를 표시합니다. 교안의 설명 순서와 맞물려 있습니다.
- 화면 문구와 프롬프트는 쉬운 한국어로 씁니다.
- 두 폴더는 서로 import하지 않는 독립 실습입니다. 검색 로직이 중복되어 있는 것은 의도된 것입니다.

제품 요구사항과 배경은 `docs/상담사_코파일럿_기획서.md`에 있습니다(MVP = A 매뉴얼 Q&A + B 수급자격 판정 가이드, 나머지는 Phase 2).

## 실행 명령

테스트·린트·빌드 설정은 없습니다.

```powershell
pip install -r hello_rag/requirements.txt   # manual_rag 와 내용 동일 (streamlit, scikit-learn, anthropic)

# hello_rag: 가상의 사내 안내서로 하는 입문 실습
python hello_rag/1_search.py                # 검색만 (API 키 불필요, 터미널 대화형)
streamlit run hello_rag/2_app.py            # 검색 + Claude 답변

# manual_rag: 실제 업무매뉴얼
python manual_rag/1_convert.py              # .hwpx → manual_chunks.json
streamlit run manual_rag/2_app.py           # Q&A 탭 + 판정 가이드 탭
streamlit run manual_rag/3_chat.py          # 챗봇 (이어 묻기, 스트리밍, 다음 질문 버튼)
```

API 키는 `ANTHROPIC_API_KEY` 환경 변수가 있으면 사이드바 입력란에 기본값으로 채워지고, 없으면 사이드바에 직접 입력합니다.

검증은 수동입니다. `hello_rag/테스트질문.txt`에 질문 7개와 정답·출처가 있고, 7번은 자료에 없는 내용을 물어 "자료에서 찾을 수 없습니다"가 나오는지 보는 함정 질문입니다. `manual_rag`용 평가 세트는 아직 없습니다(기획서상 현업 질문 20문항 예정).

## 아키텍처

두 앱 모두 같은 흐름입니다: **조각 만들기 → TF-IDF 색인 → 코사인 유사도 상위 k개 → 조각을 프롬프트에 넣어 Claude 호출**. 벡터 DB나 임베딩 모델은 쓰지 않습니다.

- 색인은 `TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))`. 형태소 분석기 없이 한국어를 다루려고 글자 n-gram을 씁니다.
- 색인은 `@st.cache_resource`로 앱 시작 시 한 번만 만듭니다. `data/*.txt`나 `manual_chunks.json`을 바꾸면 Streamlit을 다시 시작해야 반영됩니다.
- Claude 호출은 두 앱이 같은 형태(`client.beta.messages.create`, `output_config={"effort": "low"}`, server-side fallback 베타, `stop_reason == "refusal"` 처리)를 씁니다. 한쪽을 바꾸면 다른 쪽도 맞추세요.

### hello_rag

`data/*.txt`를 빈 줄(`\n\n`) 기준으로 잘라 조각으로 만들고, 출처는 파일 이름입니다. 상위 3개를 씁니다.

### manual_rag

`1_convert.py` (HWPX → JSON)

- HWPX는 zip이고, `Contents/section{N}.xml`을 직접 파싱합니다. **`PARTS` 딕셔너리의 번호 1~7이 섹션 파일 번호와 Part 이름을 고정으로 매핑**하므로, 매뉴얼이 개정되어 Part 구성이 바뀌면 이 딕셔너리를 고쳐야 합니다.
- 폴더의 `.hwpx` 중 `glob` 첫 번째 파일만 읽습니다. 파일을 하나만 두세요.
- 표는 행마다 `칸 | 칸` 한 줄로 펴고, 중첩 표는 안쪽 표만 꺼내 중복을 막습니다.
- 제목 인식(`heading_of`)은 "칸이 정확히 2개인 표 행"이라는 매뉴얼의 조판 습관에 의존합니다: 첫 칸이 로마 숫자(Ⅰ~Ⅹ)면 장, 1~2자리 숫자면 절. 이것으로 `Part > 장 > 절` 형태의 `source` 경로를 만듭니다. 매뉴얼에 쪽 번호가 없어서 이 경로가 유일한 출처 표기입니다.
- 제목이 바뀌거나 버퍼가 `CHUNK_SIZE`(800자)를 넘으면 조각을 끊습니다. 그래서 같은 `source`를 가진 조각이 여러 개 생기고, 표가 조각 경계에서 잘릴 수 있습니다.
- 이미지로 된 도식은 추출하지 않습니다.

`manual_chunks.json`은 **생성물**입니다. 직접 고치지 말고 `1_convert.py`를 고친 뒤 다시 생성하세요.

`2_app.py`

- 색인할 때 `source` 경로를 3번 반복해 앞에 붙여 제목에 가중치를 줍니다(`sublinear_tf=True`). 상위 6개를 씁니다.
- **Q&A 탭**은 Claude를 두 번 호출합니다. 먼저 `REWRITE_PROMPT`로 상담사의 일상어 질문을 매뉴얼 용어로 바꾸고, `원래 질문 + 바꾼 검색어`로 검색한 뒤, `ANSWER_PROMPT`로 답합니다.
- **판정 가이드 탭**은 고정된 검색어 문자열 + 메모로 검색합니다. 중위소득 대비 비율은 LLM에 맡기지 않고 `MEDIAN_INCOME_2026` 표로 코드에서 계산해 프롬프트에 넣습니다. 이 표는 매뉴얼 Part 02에서 손으로 옮긴 값이라 매뉴얼 연도가 바뀌면 함께 갱신해야 하고, 7인 가구까지만 있습니다.
- `call_claude`는 `@st.cache_data`로 (api_key, system, user_text)가 같으면 저장된 답을 재사용합니다. 프롬프트를 바꿔 실험할 때는 캐시 때문에 이전 답이 나올 수 있습니다.

`3_chat.py` (챗봇)

- `2_app.py`의 Q&A 탭을 대화형으로 바꾼 단계입니다. 색인·검색 코드는 `2_app.py`와 같고(의도된 중복), 판정 가이드는 `2_app.py`에만 있습니다.
- 대화 기록은 `st.session_state["talk"]`에 `{role, content, found, chips}`로 쌓습니다. Claude에는 최근 `HISTORY`개의 `role`/`content`만 보내고, 매뉴얼 발췌는 이번 질문에만 붙입니다(이전 턴의 발췌는 다시 보내지 않음).
- 턴마다 Claude를 두 번 호출합니다. `make_query`가 앞 대화를 보고 "그럼 청년은요?" 같은 질문을 완전한 검색어로 바꾸고, `stream_answer`가 `client.beta.messages.stream`으로 답을 한 글자씩 내보냅니다.
- 답 끝의 `[다음 질문]`(`MARK`) 아래 줄들은 화면에 보이지 않고 버튼으로 바뀝니다. 이 형식은 `CHAT_PROMPT`와 `stream_answer`의 파싱이 맞물려 있으니 한쪽만 바꾸지 마세요. 표시가 조각 사이에 잘려 올 수 있어 스트리밍 중에는 끝의 `len(MARK)`글자를 미뤄서 내보냅니다.
- API 키 없이 화면 흐름을 확인하려면 `streamlit.testing.v1.AppTest`로 실행하면서 `anthropic.Anthropic`을 가짜 클라이언트로 바꿔 끼우면 됩니다.

## 지켜야 할 제품 원칙

기획서와 `ANSWER_PROMPT`에 걸쳐 있는 규칙으로, 프롬프트나 화면을 고칠 때 유지해야 합니다.

- 답변은 매뉴얼 발췌에 있는 내용만 근거로 하고, `(출처: Part … > …)` 경로를 붙입니다.
- 근거가 없거나 고용센터마다 해석이 갈릴 수 있으면 추측하지 않고 "⚠ 팀장 확인 필요"로 표시합니다.
- 판정은 "예상 판정"이며 최종 판단은 상담사가 합니다.
- 구직자 개인정보(이름, 주민등록번호, 연락처)는 입력받지도 저장하지도 않습니다. 판정 가이드는 수치만 다룹니다.

## 기획서와 현재 구현의 차이

기획서는 "매뉴얼 전체를 컨텍스트에 넣고 프롬프트 캐시 적용, Sonnet 5.5 기본, HWPX → 마크다운 변환(병합 셀 보존)"을 적고 있지만, 실제 코드는 교육 목적에 맞춰 **TF-IDF 조각 검색 + `claude-opus-5-5` + JSON 조각**으로 구현되어 있습니다. 기획서의 기술 설계 표를 현재 코드의 설명으로 읽지 마세요.

## 기타

- `docs/`와 `manual_rag/`에 같은 `.hwpx` 매뉴얼이 한 부씩 있습니다. 변환기가 읽는 것은 `manual_rag/` 쪽입니다.
- `.hwpx`는 `.gitignore`로 제외되어 있습니다. 새로 받은 사본에서 `1_convert.py`를 돌리려면 매뉴얼을 `manual_rag/`에 직접 넣어야 합니다. 그래서 `manual_chunks.json`은 생성물이지만 커밋해 둡니다.
- `docs/~$*.pptx`는 PowerPoint가 열려 있을 때 생기는 잠금 파일입니다.
- 소스와 데이터는 모두 UTF-8이며 파일을 열 때 `encoding="utf-8"`을 명시합니다(Windows 기본 인코딩 회피).
