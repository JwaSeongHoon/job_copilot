# 2단계: 국민취업지원제도 매뉴얼 상담 도우미 (상담사 전용)
# 실행: streamlit run 2_app.py   (먼저 python 1_convert.py 로 manual_chunks.json 을 만드세요)
import json
import os

import anthropic
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5-5"

# 2026년 기준 중위소득 (매뉴얼 Part 02 표, 단위: 원)
MEDIAN_INCOME_2026 = {1: 2564238, 2: 4199292, 3: 5359036, 4: 6494738,
                      5: 7556719, 6: 8555952, 7: 9515150}

ANSWER_PROMPT = """당신은 국민취업지원제도 상담사를 돕는 업무 도우미입니다.
반드시 [매뉴얼 발췌]에 있는 내용만 근거로, 2026년 매뉴얼 기준으로 답하세요.
- 첫 문장에 결론을 말하고, 이어서 근거를 설명하세요.
- 근거로 쓴 부분의 위치를 (출처: Part … > …) 형식으로 적으세요.
- 발췌에 근거가 없거나, 고용센터마다 해석이 다를 수 있는 내용이면 추측하지 말고
  "⚠ 팀장 확인 필요"라고 적은 뒤 무엇을 확인해야 하는지 알려 주세요.
- 상담사가 구직자에게 바로 설명할 수 있게 쉬운 말로 쓰세요."""

REWRITE_PROMPT = """상담사의 질문을 국민취업지원제도 업무매뉴얼에서 검색하기 좋은 용어로 바꾸세요.
매뉴얼 용어 예시: 구직촉진수당, 취업성공수당, 지급액, 지급기간, 수급자격, 요건심사형, 선발형,
가구단위 소득, 기준 중위소득, 재산, 취업경험, 특정계층, 재참여 제한, 취업지원 종료, 유예.
검색어만 한 줄로 쓰고 다른 말은 하지 마세요."""


# ① 매뉴얼 조각 읽기 + 색인 만들기 (제목은 3번 넣어 더 중요하게 반영)
@st.cache_resource
def build_index():
    with open(os.path.join(HERE, "manual_chunks.json"), encoding="utf-8") as f:
        chunks = json.load(f)
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True)
    matrix = vectorizer.fit_transform([(c["source"] + "\n") * 3 + c["text"] for c in chunks])
    return chunks, vectorizer, matrix


# ② 검색하기
def search(query, k=6):
    chunks, vectorizer, matrix = build_index()
    scores = cosine_similarity(vectorizer.transform([query]), matrix)[0]
    return [chunks[i] | {"score": scores[i]} for i in scores.argsort()[::-1][:k]]


# ③ Claude 호출 (공통) · 같은 질문은 저장해 둔 답을 다시 써서 비용을 아낀다
@st.cache_data(show_spinner=False)
def call_claude(api_key, system, user_text):
    client = anthropic.Anthropic(api_key=api_key)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    if response.stop_reason == "refusal":
        return "AI가 이 요청에는 답하지 않았습니다. 질문을 바꿔 다시 해 보세요."
    return "".join(b.text for b in response.content if b.type == "text")


def excerpts(found):
    return "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in found)


def show_sources(found):
    with st.expander("📖 AI가 참고한 매뉴얼 발췌 보기"):
        for c in found:
            st.markdown(f"**{c['source']}** · 점수 {c['score']:.2f}")
            st.text(c["text"])


# ④ 화면
st.set_page_config(page_title="매뉴얼 상담 도우미", page_icon="📘", layout="wide")
st.title("📘 국민취업지원제도 매뉴얼 상담 도우미")
st.caption("2026년 업무매뉴얼 기준 · 상담사 전용 · 최종 판단은 상담사가 합니다.")

api_key = st.sidebar.text_input("Claude API 키", type="password",
                                value=os.environ.get("ANTHROPIC_API_KEY", ""))
st.sidebar.info("구직자의 이름, 주민등록번호, 연락처는 입력하지 마세요.")
if not os.path.exists(os.path.join(HERE, "manual_chunks.json")):
    st.error("manual_chunks.json 이 없습니다. 먼저 python 1_convert.py 를 실행하세요.")
    st.stop()
if not api_key:
    st.warning("왼쪽에 Claude API 키를 입력하세요.")
    st.stop()

tab_qa, tab_check = st.tabs(["💬 매뉴얼 Q&A", "✅ 수급자격 판정 가이드"])

with tab_qa:
    st.write("자주 묻는 질문 예시: 구직촉진수당은 한 달에 얼마인가요? · 대학생 졸업예정자는 언제부터 참여할 수 있나요?")
    question = st.text_input("질문을 입력하세요", key="qa")
    if question:
        with st.spinner("매뉴얼 용어로 바꿔 검색하는 중..."):
            keywords = call_claude(api_key, REWRITE_PROMPT, question)
            found = search(question + " " + keywords)
        st.caption(f"검색어: {keywords}")
        with st.spinner("답변을 쓰는 중..."):
            answer = call_claude(api_key, ANSWER_PROMPT,
                                 f"[매뉴얼 발췌]\n{excerpts(found)}\n\n[상담사 질문]\n{question}")
        st.markdown(answer)
        show_sources(found)

with tab_check:
    st.write("구직자에게 들은 답을 입력하면, 예상 유형과 다음에 물어볼 질문을 알려 줍니다.")
    col1, col2 = st.columns(2)
    age = col1.number_input("나이(만)", 15, 80, 28)
    military = col1.number_input("병역 이행 기간(개월, 없으면 0)", 0, 36, 0)
    members = col1.number_input("가구원 수(주민등록표 기준)", 1, 7, 1)
    income = col2.number_input("가구 월평균 총소득(만 원)", 0, 5000, 150)
    assets = col2.number_input("가구 재산 합계(만 원)", 0, 200000, 5000)
    work_days = col2.number_input("최근 2년 취업(알바 포함) 일수", 0, 730, 60)
    job_seeking_benefit = st.checkbox("현재 구직급여(실업급여)를 받고 있다")
    memo = st.text_area("기타 상황 메모 (예: 부모님과 같은 등본, 대학 4학년 2학기 재학 중)")

    ratio = income * 10000 / MEDIAN_INCOME_2026[members] * 100
    st.metric("기준 중위소득 대비 가구 소득", f"{ratio:.0f}%",
              help=f"{members}인 가구 중위소득 {MEDIAN_INCOME_2026[members]:,}원 기준 (코드로 계산)")

    if st.button("판정 가이드 보기"):
        case = (f"나이 만 {age}세, 병역 이행 {military}개월, 가구원 {members}명, "
                f"가구 월소득 {income}만 원(중위소득 {ratio:.0f}%), 재산 {assets}만 원, "
                f"최근 2년 취업 {work_days}일, 구직급여 수급 중: {'예' if job_seeking_benefit else '아니요'}, "
                f"메모: {memo or '없음'}")
        with st.spinner("매뉴얼을 찾아보는 중..."):
            found = search("수급자격 요건 Ⅰ유형 요건심사형 선발형 청년 특례 가구단위 소득 재산 취업경험 " + memo)
            guide = call_claude(api_key, ANSWER_PROMPT, f"""[매뉴얼 발췌]
{excerpts(found)}

[구직자 상황]
{case}

[요청]
1. 예상 유형(1유형 요건심사형 / 1유형 선발형 / 2유형 / 참여 불가)과 근거
2. 판정에 아직 부족한 정보와, 상담사가 다음에 물어볼 질문 2~3개
3. 1유형이 되기 어렵다면, 매뉴얼상 검토해 볼 수 있는 방법이 있는지""")
        st.markdown(guide)
        show_sources(found)
