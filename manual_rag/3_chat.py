# 3단계: 매뉴얼 상담 챗봇 (묻고 답하며 이어 가는 대화)
# 실행: streamlit run 3_chat.py   (먼저 python 1_convert.py 로 manual_chunks.json 을 만드세요)
import json
import os

import anthropic
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5-5"
MARK = "[다음 질문]"  # AI가 답 끝에 붙이는 표시. 이 아래 줄들은 버튼으로 보여 준다
HISTORY = 8          # AI에게 함께 보내는 이전 대화 수 (질문과 답을 각각 1개로 셈)

GREETING = ("안녕하세요, 국민취업지원제도 매뉴얼 도우미예요. "
            "용어를 몰라도 괜찮으니 궁금한 걸 편하게 물어보세요.")
STARTERS = ["구직자가 처음 오면 뭘 물어봐야 해요?",
            "1유형과 2유형이 뭐가 달라요?",
            "수당은 얼마 받아요?"]

CHAT_PROMPT = f"""당신은 국민취업지원제도 신규 상담사 옆자리에 앉은 선배 상담사처럼 돕는 챗봇입니다.
상대는 제도를 잘 몰라서 용어가 틀리거나, 질문이 짧고 모호할 수 있습니다.

말하는 방식
- 대화하듯 짧게 답하세요. 결론부터 3~4문장. 표나 긴 목록은 상담사가 요청할 때만 씁니다.
- 질문이 모호하면 여러 경우를 다 설명하지 말고, 무엇을 묻는지 한 가지만 되물으세요.
- 상담사가 일상어를 쓰면 매뉴얼 용어를 짚어 주세요. (예: "실업급여는 매뉴얼에서 구직급여라고 해요")
- 인사나 잡담에는 출처 없이 짧게 답하세요.

근거
- 반드시 [매뉴얼 발췌]에 있는 내용만 근거로, 2026년 매뉴얼 기준으로 답하세요.
- 근거로 쓴 부분의 위치를 답 끝에 (출처: Part … > …) 형식으로 적으세요.
- 발췌에 근거가 없거나, 고용센터마다 해석이 다를 수 있는 내용이면 추측하지 말고
  "⚠ 팀장 확인 필요"라고 적은 뒤 무엇을 확인해야 하는지 알려 주세요.
- 구직자의 이름, 주민등록번호, 연락처는 묻지 마세요.

다음 질문
- 답의 맨 끝에 줄을 바꿔 {MARK} 라고 쓰고, 그 아래에 상담사가 이어서 물을 만한 질문 2~3개를
  한 줄에 하나씩 쓰세요. 상담사가 말하는 말투로, 20자 이내로 씁니다.
- 되물었을 때는 상담사가 고를 수 있는 대답을 그 자리에 쓰세요."""

REWRITE_PROMPT = """상담사와 챗봇의 대화를 보고, 마지막 질문을 국민취업지원제도 업무매뉴얼에서
검색하기 좋은 검색어로 바꾸세요. "그럼 청년은요?"처럼 앞 대화에 기대는 질문은
앞 대화의 주제를 넣어 완전한 검색어로 만듭니다.
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


# ③ 검색어 만들기: 앞 대화까지 보고 "그럼 청년은요?" 같은 질문을 완전한 검색어로 바꾼다
def make_query(client, history, question):
    talk = "\n".join(f"{'상담사' if m['role'] == 'user' else '챗봇'}: {m['content']}" for m in history)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=REWRITE_PROMPT,
        messages=[{"role": "user", "content": f"[앞 대화]\n{talk or '없음'}\n\n[마지막 질문]\n{question}"}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


# ④ 답변 받기: 글자가 만들어지는 대로 한 글자씩 내보낸다 (스트리밍)
def stream_answer(client, history, question, found, result):
    excerpts = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in found)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": f"[매뉴얼 발췌]\n{excerpts}\n\n[상담사 질문]\n{question}"})
    full, shown = "", 0
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=CHAT_PROMPT,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full += text
            answer = full.split(MARK)[0]
            # [다음 질문] 표시는 화면에 보이면 안 된다. 표시가 잘려서 올 수 있어 끝의 몇 글자는 잠시 미룬다
            safe = len(answer.rstrip()) if MARK in full else len(answer) - len(MARK)
            if safe > shown:
                yield from answer[shown:safe]
                shown = safe
        refused = stream.get_final_message().stop_reason == "refusal"
    answer, _, tail = full.partition(MARK)
    yield from answer.rstrip()[shown:]
    if refused:
        yield "\n\nAI가 이 질문에는 답하지 않았습니다. 질문을 바꿔 다시 해 보세요."
    result["chips"] = [line.strip(" -•·") for line in tail.splitlines() if line.strip(" -•·")][:3]


def show_sources(found):
    with st.expander("📖 근거 보기 (AI가 참고한 매뉴얼 발췌)"):
        for c in found:
            st.markdown(f"**{c['source']}** · 점수 {c['score']:.2f}")
            st.text(c["text"])


# ⑤ 화면
st.set_page_config(page_title="매뉴얼 상담 챗봇", page_icon="💬")
st.title("💬 국민취업지원제도 매뉴얼 챗봇")
st.caption("2026년 업무매뉴얼 기준 · 상담사 전용 · 최종 판단은 상담사가 합니다.")

api_key = st.sidebar.text_input("Claude API 키", type="password",
                                value=os.environ.get("ANTHROPIC_API_KEY", ""))
st.sidebar.info("구직자의 이름, 주민등록번호, 연락처는 입력하지 마세요.")
if st.sidebar.button("🗑 새 대화"):
    st.session_state.clear()
if not os.path.exists(os.path.join(HERE, "manual_chunks.json")):
    st.error("manual_chunks.json 이 없습니다. 먼저 python 1_convert.py 를 실행하세요.")
    st.stop()
if not api_key:
    st.warning("왼쪽에 Claude API 키를 입력하세요.")
    st.stop()

# 대화 기록은 화면이 다시 그려져도 남도록 session_state 에 둔다
talk = st.session_state.setdefault("talk", [])

# 지금까지의 대화를 말풍선으로 다시 그린다
with st.chat_message("assistant"):
    st.markdown(GREETING)
for m in talk:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("found"):
            show_sources(m["found"])

# 다음 질문 버튼: 마지막 답 아래에만 보여 준다. 누르면 그 글이 질문이 된다
chips = talk[-1].get("chips", []) if talk else STARTERS
for i, column in enumerate(st.columns(len(chips)) if chips else []):
    if column.button(chips[i], key=f"chip{i}", use_container_width=True):
        st.session_state["clicked"] = chips[i]
        st.rerun()

question = st.chat_input("궁금한 것을 물어보세요") or st.session_state.pop("clicked", None)
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        client = anthropic.Anthropic(api_key=api_key)
        history = [{"role": m["role"], "content": m["content"]} for m in talk[-HISTORY:]]
        result = {}
        try:
            with st.spinner("매뉴얼을 찾아보는 중..."):
                found = search(question + " " + make_query(client, history, question))
            answer = st.write_stream(stream_answer(client, history, question, found, result))
        except anthropic.AuthenticationError:
            st.error("API 키가 올바르지 않습니다. 왼쪽의 키를 확인하세요.")
            st.stop()
        except anthropic.APIError as e:
            st.error(f"AI 호출에 실패했습니다. 잠시 뒤 다시 시도하세요. ({e})")
            st.stop()
    talk.append({"role": "user", "content": question})
    talk.append({"role": "assistant", "content": answer, "found": found, "chips": result.get("chips", [])})
    st.rerun()  # 근거 보기와 다음 질문 버튼까지 포함해 다시 그린다
