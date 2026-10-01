# 2단계: 검색 + AI 답변 웹 앱 (hello RAG)
# 실행: streamlit run 2_app.py
import glob
import os

import anthropic
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """당신은 국제커리어 직원의 질문에 답하는 사내 도우미입니다.
반드시 아래 [참고 자료]에 있는 내용만으로 답하세요.
참고 자료에 답이 없으면 지어내지 말고 "자료에서 찾을 수 없습니다"라고 답하세요.
답변 끝에는 근거가 된 파일 이름을 (출처: 파일이름) 형식으로 적으세요.
답변은 한국어로, 3문장 이내로 짧게 하세요."""


# ① 자료 읽기 + ② 색인 만들기 (앱을 켤 때 한 번만 실행)
@st.cache_resource
def build_index():
    chunks = []
    for path in sorted(glob.glob(os.path.join(HERE, "data", "*.txt"))):
        text = open(path, encoding="utf-8").read()
        for part in text.split("\n\n"):
            if part.strip():
                chunks.append({"source": os.path.basename(path), "text": part.strip()})
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))
    matrix = vectorizer.fit_transform([c["text"] for c in chunks])
    return chunks, vectorizer, matrix


# ③ 검색하기: 질문과 가장 비슷한 조각 k개
def search(question, k=3):
    chunks, vectorizer, matrix = build_index()
    scores = cosine_similarity(vectorizer.transform([question]), matrix)[0]
    return [chunks[i] | {"score": scores[i]} for i in scores.argsort()[::-1][:k]]


# ④ AI에게 묻기: 찾은 조각을 질문과 함께 보낸다
def ask_claude(api_key, question, found):
    context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in found)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"[참고 자료]\n{context}\n\n[질문]\n{question}"}],
    )
    if response.stop_reason == "refusal":
        return "AI가 이 질문에는 답하지 않았습니다. 질문을 바꿔 다시 해 보세요."
    return "".join(b.text for b in response.content if b.type == "text")


# ⑤ 화면
st.title("hello RAG · 국제커리어 사내 도우미")
st.caption("가상의 사내 안내서(data 폴더)를 찾아보고 답합니다.")

api_key = st.sidebar.text_input("Claude API 키", type="password",
                                value=os.environ.get("ANTHROPIC_API_KEY", ""))
question = st.text_input("질문을 입력하세요", placeholder="예: 상담실 예약은 어디서 하나요?")

if question:
    found = search(question)
    with st.expander("🔍 검색된 자료 조각 보기 (AI가 참고한 내용)"):
        for c in found:
            st.markdown(f"**{c['source']}** · 점수 {c['score']:.2f}")
            st.text(c["text"])
    if not api_key:
        st.warning("왼쪽에 Claude API 키를 입력하면 AI 답변을 볼 수 있습니다.")
    else:
        with st.spinner("AI가 답변을 쓰는 중..."):
            st.success(ask_claude(api_key, question, found))
