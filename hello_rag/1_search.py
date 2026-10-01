# 1단계: 검색만 해 보기 (AI 없이, API 키 필요 없음)
# 실행: python 1_search.py
import glob
import os

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = os.path.dirname(os.path.abspath(__file__))

# ① 자료 읽기: data 폴더의 .txt 파일을 빈 줄 기준으로 잘라 "조각"으로 만든다
chunks = []
for path in sorted(glob.glob(os.path.join(HERE, "data", "*.txt"))):
    text = open(path, encoding="utf-8").read()
    for part in text.split("\n\n"):
        if part.strip():
            chunks.append({"source": os.path.basename(path), "text": part.strip()})
print(f"자료 조각 {len(chunks)}개를 읽었습니다.\n")

# ② 색인 만들기: 조각마다 글자 패턴을 숫자로 바꿔 둔다
vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))
matrix = vectorizer.fit_transform([c["text"] for c in chunks])

# ③ 검색하기: 질문과 가장 비슷한 조각 3개를 찾는다
while True:
    question = input("질문을 입력하세요 (끝내려면 엔터): ").strip()
    if not question:
        break
    scores = cosine_similarity(vectorizer.transform([question]), matrix)[0]
    top = scores.argsort()[::-1][:3]
    for rank, i in enumerate(top, start=1):
        print(f"\n[{rank}위] 점수 {scores[i]:.2f} · 출처 {chunks[i]['source']}")
        print(chunks[i]["text"])
    print("\n" + "-" * 50)
