# 1단계: 한글 매뉴얼(.hwpx)을 AI가 읽을 수 있는 "조각" 파일로 바꾸기
# 실행: python 1_convert.py   (이 폴더에 .hwpx 파일 1개를 넣어 두세요)
import glob
import json
import os
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
PARTS = {
    1: "Part 01 국민취업지원제도 개괄",
    2: "Part 02 수급자격",
    3: "Part 03 취업지원서비스",
    4: "Part 04 수당 지급",
    5: "Part 05 부정수급 업무처리",
    6: "Part 06 조건부수급자 운영지침",
    7: "Part 07 청년 빈일자리 특화 취업지원프로그램",
}
ROMAN = set("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ")
CHUNK_SIZE = 800  # 조각 하나의 최대 글자 수


def text_of(element):
    """문단(또는 표 칸) 안의 글자를 모두 이어 붙인다."""
    return "".join("".join(t.itertext()) for t in element.iter(HP + "t")).strip()


def lines_of(section_root):
    """본문 문단은 한 줄로, 표는 한 행씩 '칸 | 칸' 형태로 꺼낸다."""
    for p in section_root.findall(HP + "p"):
        tables = list(p.iter(HP + "tbl"))
        if not tables:
            line = text_of(p)
            if line:
                yield line
            continue
        for tbl in tables:
            # 표 안에 또 표가 있으면 바깥 표는 건너뛴다 (안쪽 표에서 한 번만 꺼내 중복을 막음)
            if any(True for inner in tbl.iter(HP + "tbl") if inner is not tbl):
                continue
            for tr in tbl.findall(HP + "tr"):
                cells = [text_of(tc) for tc in tr.findall(HP + "tc")]
                row = " | ".join(c for c in cells if c)
                if row:
                    yield row


hwpx_files = glob.glob(os.path.join(HERE, "*.hwpx"))
if not hwpx_files:
    raise SystemExit("이 폴더에 .hwpx 파일이 없습니다. 매뉴얼 파일을 복사해 넣어 주세요.")

def heading_of(line):
    """제목 줄을 알아본다. 매뉴얼의 제목은 표 안에 'Ⅰ | 수급자격 요건' 모양으로 들어 있다."""
    cells = line.split(" | ")
    if len(cells) != 2 or len(cells[1]) > 40 or cells[1][0].isdigit():
        return None, None
    if cells[0] in ROMAN:
        return "장", f"{cells[0]} {cells[1]}"
    if cells[0].isdigit() and len(cells[0]) <= 2:
        return "절", f"{cells[0]}. {cells[1]}"
    return None, None


chunks = []
with zipfile.ZipFile(hwpx_files[0]) as z:
    for number, part_name in PARTS.items():
        root = ET.fromstring(z.read(f"Contents/section{number}.xml"))
        chapter, section, buffer = "", "", []

        def save():
            if buffer:
                source = " > ".join(x for x in [part_name, chapter, section] if x)
                chunks.append({"source": source, "text": "\n".join(buffer)})
                buffer.clear()

        for line in lines_of(root):
            kind, title = heading_of(line)
            if kind:  # 새 제목이 나오면 지금까지 모은 글을 한 조각으로 저장
                save()
                if kind == "장":
                    chapter, section = title, ""
                else:
                    section = title
                continue
            buffer.append(line)
            if sum(len(b) for b in buffer) > CHUNK_SIZE:
                save()
        save()

out_path = os.path.join(HERE, "manual_chunks.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=1)

print(f"변환 완료: 조각 {len(chunks)}개 → manual_chunks.json")
for part_name in PARTS.values():
    n = sum(1 for c in chunks if c["source"].startswith(part_name))
    print(f"  {part_name}: {n}개")
