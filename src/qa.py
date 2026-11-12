#!/usr/bin/env python3
"""전체 점검: 장의 뼈대, 분량, 링크, 그림·사진 파일, 문체.

  python3 src/qa.py          모든 장
  python3 src/qa.py ch07     한 장
"""
import json
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
CUR = json.loads((SRC / 'curriculum.json').read_text(encoding='utf-8'))
IDS = [c['id'] for c in CUR['chapters']]
EXTRA_IDS = ['math', 'code', 'trouble']
TAIL = ['pairs', 'case', 'summary', 'quiz', 'ai', 'terms', 'more']


def anchors(cid):
    p = SRC / 'content' / f'{cid}.md'
    if not p.exists():
        return None
    return set(re.findall(r'^##+ .*\{#([a-z0-9-]+)\}\s*$', p.read_text(encoding='utf-8'), re.M))


def check(cid):
    out = []
    p = SRC / 'content' / f'{cid}.md'
    if not p.exists():
        return ['원고 없음']
    s = p.read_text(encoding='utf-8')
    body = re.sub(r'```.*?```', '', s, flags=re.S)
    own = anchors(cid)
    # 뼈대
    if cid != 'ch00' and cid not in EXTRA_IDS:
        for t in TAIL:
            if t not in own:
                out.append(f'끝 절 없음: #{t}')
        nq = len(re.findall(r'^::: \{\.q\}', s, re.M))
        if nq != 5:
            out.append(f'확인 문제 {nq}개 (기준 5)')
        if not re.search(r'^::: \{\.lead\}', s, re.M):
            out.append('.lead 없음')
        if not re.search(r'^::: \{\.goals\}', s, re.M):
            out.append('.goals 없음')
    for m in re.finditer(r'^## (.*)$', s, re.M):
        if not re.search(r'\{#[a-z0-9-]+\}\s*$', m.group(1)):
            out.append(f'## 제목에 영문 id 없음: {m.group(1)[:30]}')
    if re.search(r'^# ', body, re.M):
        out.append('# (h1)을 쓰면 안 됨')
    # 상자 짝
    opens = len(re.findall(r'^:::+ *\{', s, re.M))
    closes = len(re.findall(r'^:::+\s*$', s, re.M))
    if opens != closes:
        out.append(f'상자 여닫음 불일치: 열기 {opens} / 닫기 {closes}')
    # 그림·사진
    figs = re.findall(r'\{\.fig[^}]*src="([^"]+)"', s)
    for f in figs:
        if not (SRC / 'fig' / cid / f).exists():
            out.append(f'그림 파일 없음: {f}')
    unused = {x.name for x in (SRC / 'fig' / cid).glob('*.svg')} - set(figs) if (SRC / 'fig' / cid).exists() else set()
    if unused:
        out.append(f'본문에서 쓰지 않은 그림: {sorted(unused)}')
    dup = {f for f in figs if figs.count(f) > 1}
    if dup:
        out.append(f'같은 그림을 두 번 씀: {sorted(dup)}')
    for f in re.findall(r'\{\.photo[^}]*src="([^"]+)"', s):
        if not (ROOT / 'assets' / 'photo' / f).exists():
            out.append(f'사진 파일 없음: {f}')
    for f in re.findall(r'\{\.comic[^}]*src="([^"]+)"', s):
        if not (ROOT / 'assets' / 'comic' / f).exists():
            out.append(f'만화 파일 없음: {f}')
    # 링크
    for m in re.finditer(r'\]\((ch\d\d|math|code|trouble)\.html(?:#([A-Za-z0-9_-]+))?\)', s):
        tid, anc = m.group(1), m.group(2)
        if tid not in IDS and tid not in EXTRA_IDS:
            out.append(f'없는 장으로 링크: {m.group(0)}')
        elif anc:
            ta = anchors(tid)
            if ta is not None and anc not in ta:
                out.append(f'없는 절로 링크: {tid}.html#{anc}')
    for m in re.finditer(r'\]\((?!https?://|ch\d\d\.html|(?:math|code|trouble|glossary)\.html|#|mailto:)([^)]+)\)', body):
        out.append(f'수상한 링크: {m.group(1)[:50]}')
    # 문체: 한다체 문장 비율
    prose = re.sub(r'## 용어 정리.*?(?=^## |\Z)', '', body, flags=re.S | re.M)
    sents = re.findall(r'[가-힣]+다\.(?=\s|$)', prose)
    plain = [x for x in sents if not re.search(r'(니다|시다)\.$', x)]
    if sents and len(plain) / len(sents) > 0.03:
        out.append(f'한다체 문장 의심 {len(plain)}/{len(sents)}: {", ".join(sorted(set(plain))[:6])}')
    if re.search(r'<(div|span|br|img|table|p)\b', body):
        out.append('원시 HTML 사용')
    if re.search(r'[\U0001F300-\U0001FAFF☀-➿]', re.sub(r'[①-⑳←-⇿✓✗▶➔➜]', '', body)):
        out.append('이모지 사용')
    return out


def main():
    targets = [a for a in sys.argv[1:]] or IDS
    bad = 0
    for cid in targets:
        issues = check(cid)
        if issues:
            bad += 1
            print(f'{cid}:')
            for i in issues:
                print('   - ' + i)
    print(f'\n{len(targets)}개 장 중 {bad}개에 확인할 점이 있습니다.' if bad else f'{len(targets)}개 장 모두 통과.')


if __name__ == '__main__':
    main()
