#!/usr/bin/env python3
"""개발의 기초 — 빌드 스크립트.

  python3 src/build.py            전체(모든 장 + 표지 + 용어 사전 + 검색 색인)
  python3 src/build.py ch03       해당 장의 HTML만 다시 만든다 (다른 파일은 건드리지 않음)

원고는 src/content/chNN.md (pandoc Markdown), 그림은 src/fig/chNN/*.svg.
필요한 도구: pandoc, Python 3 + beautifulsoup4.
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
OUT_CH = ROOT / 'chapters'
CUR = json.loads((SRC / 'curriculum.json').read_text(encoding='utf-8'))
PARTS = {p['id']: p for p in CUR['parts']}
PART_NO = {p['id']: i for i, p in enumerate(CUR['parts'])}
CHAPTERS = CUR['chapters']
CH = {c['id']: c for c in CHAPTERS}
DEFS = (SRC / 'defs.svg').read_text(encoding='utf-8')
SITE = json.loads((SRC / 'site.json').read_text(encoding='utf-8'))
PHOTOS = json.loads((SRC / 'photos.json').read_text(encoding='utf-8')) if (SRC / 'photos.json').exists() else {}

CALLOUTS = {
    'analogy': ('비유로 이해하기', 'i-bulb'),
    'note': ('참고', 'i-book'),
    'tip': ('요령', 'i-check'),
    'warn': ('주의', 'i-warn'),
    'myth': ('흔한 오해', 'i-cross'),
    'try': ('직접 해 보기', 'i-terminal'),
    'ai': ('AI에게 맡길 때', 'i-robot'),
    'key': ('핵심', 'i-bolt'),
}
TAIL_IDS = {'pairs', 'case', 'summary', 'quiz', 'ai', 'terms', 'more'}
warnings = []


def warn(ch, msg):
    warnings.append(f'[{ch}] {msg}')


def ch_no(cid):
    return int(cid[2:])


def ch_label(cid):
    return f'{ch_no(cid)}장'


def esc(s):
    return html.escape(str(s), quote=True)


def icon(name):
    return f'<svg viewBox="0 0 48 48" aria-hidden="true"><use href="#{name}"/></svg>'


def pandoc(md_text):
    r = subprocess.run(
        ['pandoc', '-f', 'markdown-smart-implicit_figures-raw_tex+east_asian_line_breaks', '-t', 'html5',
         '--mathml', '--wrap=none', '--section-divs'],
        input=md_text.encode('utf-8'), capture_output=True)
    if r.returncode != 0:
        raise SystemExit('pandoc 실패: ' + r.stderr.decode('utf-8'))
    if r.stderr.strip():
        for line in r.stderr.decode('utf-8').splitlines():
            warnings.append('[pandoc] ' + line)
    return r.stdout.decode('utf-8')


def attr(div, name):
    return div.get('data-' + name) or div.get(name) or ''


def load_svg(cid, name):
    p = SRC / 'fig' / cid / name
    if not p.exists():
        return None
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'<\?xml[^>]*\?>', '', s)
    s = re.sub(r'<!DOCTYPE[^>]*>', '', s).strip()
    m = re.match(r'<svg\b([^>]*)>', s)
    if not m:
        return None
    a = m.group(1)
    a = re.sub(r'\s(width|height)="[^"]*"', '', a)
    if 'viewBox' not in a:
        warn(cid, f'{name}: viewBox 없음')
    if 'role=' not in a:
        a += ' role="img"'
    return '<svg' + a + '>' + s[m.end():]


def text_of(node):
    return re.sub(r'\s+', ' ', node.get_text(' ', strip=True))


def inner(node):
    return ''.join(str(c) for c in node.contents)


def render_chapter_body(cid, md_text, root='../'):
    """md → (body_html, toc[(id,title)], search_entries, terms)"""
    soup = BeautifulSoup(pandoc(md_text), 'html.parser')
    is_ch = cid in CH
    no = ch_no(cid) if is_ch else 0
    blobs = {}

    def stash(raw):
        key = f'@@BLOB{len(blobs)}@@'
        blobs[key] = raw
        return key

    # 그림
    k = 0
    for div in soup.select('div.fig'):
        k += 1
        name = attr(div, 'src')
        svg = load_svg(cid, name)
        cap = inner(div).strip()
        cap = re.sub(r'^<p>(.*)</p>$', r'\1', cap, flags=re.S)
        fid = 'fig-' + re.sub(r'\.svg$', '', name)
        if svg is None:
            warn(cid, f'그림 파일 없음: {name}')
            body = f'<div class="callout myth"><div class="co-h">그림 없음</div><p><code>{esc(name)}</code></p></div>'
        else:
            if '<title' not in svg:
                svg = re.sub(r'(<svg\b[^>]*>)', lambda m: m.group(1) + f'<title>{esc(text_of(div))}</title>', svg, count=1)
            body = stash(svg)
        fig = BeautifulSoup(
            f'<figure class="fig" id="{esc(fid)}"><div class="fig-body" tabindex="0" title="눌러서 크게 보기">{body}</div>'
            f'<figcaption>' + (f'<b>그림 {no}-{k}</b>' if is_ch else '') + f'{cap}</figcaption></figure>', 'html.parser')
        div.replace_with(fig)

    # 사진·만화
    def media(div, kind):
        name = attr(div, 'src')
        folder = 'photo' if kind == 'photo' else 'comic'
        if not (ROOT / 'assets' / folder / name).exists():
            warn(cid, f'{kind} 파일 없음: {name}')
        cap = inner(div).strip()
        cap = re.sub(r'^<p>(.*)</p>$', r'\1', cap, flags=re.S)
        alt = attr(div, 'alt') or text_of(div)
        credit = ''
        meta = PHOTOS.get(name)
        if kind == 'photo' and meta:
            who = esc(meta.get('author', ''))
            lic = esc(meta.get('license', ''))
            src = esc(meta.get('source', ''))
            credit = f'<span class="credit">사진: {who} · {lic} · <a href="{src}" target="_blank" rel="noopener">Wikimedia Commons</a></span>'
        elif kind == 'photo':
            warn(cid, f'사진 출처 정보 없음(photos.json): {name}')
        extra = ' half' if 'half' in (div.get('class') or []) else ''
        return BeautifulSoup(
            f'<figure class="{kind}{extra}"><img src="{root}assets/{folder}/{esc(name)}" alt="{esc(alt)}" loading="lazy">'
            f'<figcaption>{cap}{credit}</figcaption></figure>', 'html.parser')

    for div in soup.select('div.photo'):
        div.replace_with(media(div, 'photo'))
    for div in soup.select('div.comic'):
        div.replace_with(media(div, 'comic'))
    for div in soup.select('div.photos'):
        div['class'] = ['photo-row']

    # 상자류
    for cls, (label, ic) in CALLOUTS.items():
        for div in soup.select(f'div.{cls}'):
            title = attr(div, 'title')
            lab = f'{label} · {esc(title)}' if title else label
            for a in ('title', 'data-title'):
                if div.has_attr(a):
                    del div[a]
            div['class'] = ['callout', cls]
            head = BeautifulSoup(f'<div class="co-h">{icon(ic)}{lab}</div>', 'html.parser')
            div.insert(0, head)
    for div in soup.select('div.goals'):
        div.insert(0, BeautifulSoup(f'<div class="co-h">{icon("i-check")}이 장을 마치면</div>', 'html.parser'))
    for div in soup.select('div.case'):
        title = attr(div, 'title')
        lab = f'실전 사례 · {esc(title)}' if title else '실전 사례'
        for a in ('title', 'data-title'):
            if div.has_attr(a):
                del div[a]
        div.insert(0, BeautifulSoup(f'<div class="co-h">{icon("i-search")}{lab}</div>', 'html.parser'))
    for div in soup.select('div.deep'):
        title = attr(div, 'title') or '더 깊이 보기'
        det = soup.new_tag('details')
        det['class'] = ['deep']
        summ = BeautifulSoup(f'<summary><small>한 걸음 더</small>{esc(title)}</summary>', 'html.parser')
        body = soup.new_tag('div')
        body['class'] = ['deep-body']
        for c in list(div.contents):
            body.append(c.extract())
        det.append(summ)
        det.append(body)
        div.replace_with(det)

    # 확인 문제
    qs = soup.select('div.q')
    for q in qs:
        ans = q.find('div', class_='a')
        body = soup.new_tag('div')
        body['class'] = ['q-body']
        for c in list(q.contents):
            if c is ans:
                continue
            body.append(c.extract())
        q.insert(0, body)
        if ans is None:
            warn(cid, '확인 문제에 정답(.a)이 없음: ' + text_of(q)[:30])
            continue
        det = soup.new_tag('details')
        det['class'] = ['a']
        summ = soup.new_tag('summary')
        summ.string = '정답 보기'
        box = soup.new_tag('div')
        for c in list(ans.contents):
            box.append(c.extract())
        det.append(summ)
        det.append(box)
        ans.replace_with(det)
    if qs:
        wrap = soup.new_tag('div')
        wrap['class'] = ['quiz']
        qs[0].insert_before(wrap)
        for q in qs:
            wrap.append(q.extract())

    # 용어
    terms = []
    for div in soup.select('div.terms'):
        dl = div.find('dl')
        if not dl:
            warn(cid, '.terms 안에 정의 목록이 없음')
            continue
        dl['class'] = ['terms']
        for dt in dl.find_all('dt'):
            raw = text_of(dt)
            m = re.match(r'^(.*?)\s*[\(（]([^)）]*)[\)）]\s*$', raw)
            name, en = (m.group(1), m.group(2)) if m else (raw, '')
            dd = dt.find_next_sibling('dd')
            terms.append({'term': name, 'en': en, 'def': text_of(dd) if dd else '', 'ch': cid})
            dt.clear()
            dt.append(NavigableString(name))
            if en:
                sm = soup.new_tag('small')
                sm.string = en
                dt.append(sm)
        div.replace_with(dl.extract())

    # 표, 링크, 코드
    for t in soup.find_all('table'):
        w = soup.new_tag('div')
        w['class'] = ['table-wrap']
        t.wrap(w)
    for a in soup.find_all('a', href=True):
        if re.match(r'https?://', a['href']):
            a['target'] = '_blank'
            a['rel'] = 'noopener'
    for a in soup.select('pre a[aria-hidden]'):
        a.decompose()

    # 제목 번호·앵커·목차·검색
    toc, entries = [], []
    n = 0
    for sec in soup.select('section.level2'):
        h = sec.find('h2')
        sid = sec.get('id', '')
        title = text_of(h)
        if re.search(r'[^\x00-\x7f]', sid):
            warn(cid, f'h2에 영문 id를 지정하세요: "{title}"')
        if is_ch and sid not in TAIL_IDS:
            n += 1
            h.insert(0, BeautifulSoup(f'<span class="sec-n">{no}.{n}</span>', 'html.parser'))
        h.append(BeautifulSoup(f'<a class="anchor" href="#{esc(sid)}" aria-label="이 절의 링크">#</a>', 'html.parser'))
        toc.append((sid, title))
        if is_ch and sid not in ('more',):
            txt = text_of(sec)
            entries.append({'u': f'chapters/{cid}.html#{sid}', 'c': f'{ch_label(cid)} · {CH[cid]["title"]}', 't': title, 'x': txt[:2400], 'k': 'sec'})

    out = str(soup)
    for key, raw in blobs.items():
        out = out.replace(key, raw)
    if ':::' in soup.get_text():
        warn(cid, '본문에 ":::" 가 그대로 남아 있음 — 상자 문법을 확인하세요')
    return out, toc, entries, terms, {'figs': k, 'chars': len(soup.get_text()), 'sections': n, 'quiz': len(qs), 'terms': len(terms)}


def sidebar(active, root):
    parts = []
    for p in CUR['parts']:
        items = []
        for c in CHAPTERS:
            if c['part'] != p['id']:
                continue
            cur = ' aria-current="page"' if c['id'] == active else ''
            items.append(
                f'<li data-ch="{c["id"]}"><a href="{root}chapters/{c["id"]}.html"{cur}><span class="n">{ch_no(c["id"])}</span>'
                f'<span>{esc(c["title"])}</span><span class="done" aria-label="읽음">✓</span></a></li>')
        parts.append(f'<div class="side-part pc-{p["color"]}"><i></i>{PART_NO[p["id"]]}부 · {esc(p["title"])}</div><ol>{"".join(items)}</ol>')
    home_cur = ' aria-current="page"' if active == 'home' else ''

    def cur_of(pid):
        return ' aria-current="page"' if active == pid else ''
    return f'''<aside class="side" id="side" aria-label="전체 목차">
<a class="brand" href="{root}index.html"><b>{esc(CUR["title"])}</b><span>앱·게임·AI</span></a>
<button class="side-search search-open" type="button">{icon("i-search").replace("<svg", '<svg width="16" height="16"')}검색<kbd>/</kbd></button>
<div class="side-progress"><span>0장 읽음</span><div class="bar"><i></i></div></div>
<nav><ol class="side-top"><li><a href="{root}chapters/math.html"{cur_of("math")}><span class="n">∑</span><span>{esc(SITE["mathEntry"]["label"])}</span></a></li></ol>{"".join(parts)}</nav>
<div class="side-links"><a href="{root}index.html"{home_cur}>전체 지도</a><a href="{root}chapters/glossary.html"{cur_of("glossary")}>용어 사전</a><a href="{root}chapters/credits.html"{cur_of("credits")}>만든 사람들</a><a href="{SITE["repo"]}" target="_blank" rel="noopener">GitHub 저장소 ↗</a></div>
</aside>'''


def site_footer(root):
    roles = ' · '.join(f'{esc(r)} <b>{esc(w)}</b>' for r, w in SITE['roles'])
    links = ''.join(f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(n)}</a>' for n, u in SITE['links'])
    lic = SITE['license']
    return (f'<footer class="site-foot"><p class="dedication">{esc(SITE["dedication"])}</p>'
            f'<p>{roles}</p>'
            f'<p class="foot-links"><a href="{esc(SITE["repo"])}" target="_blank" rel="noopener">GitHub</a>{links}'
            f'<a href="{esc(lic["url"])}" target="_blank" rel="noopener license">{esc(lic["name"])}</a></p></footer>')


def page(title, body, page_id, root, crumb, toc=None, desc=''):
    toc_html = ''
    if toc:
        links = ''.join(f'<a href="#{esc(i)}">{esc(t)}</a>' for i, t in toc)
        toc_html = f'<nav class="toc" aria-label="이 장의 순서"><h2>이 장의 순서</h2>{links}</nav>'
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(SITE["author"])}">
<link rel="license" href="{esc(SITE["license"]["url"])}">
<script>try{{var t=JSON.parse(localStorage.getItem('csf-theme')||'""');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<link rel="stylesheet" href="{root}assets/site.css">
</head>
<body data-page="{esc(page_id)}" data-root="{root}">
{DEFS}
<a class="skip" href="#main">본문으로 건너뛰기</a>
{sidebar(page_id, root)}
<div class="shell">
<header class="top">
<button class="icon-btn menu-btn" id="menu-btn" type="button" aria-label="목차 열기">☰ 목차</button>
<div class="crumb">{crumb}</div>
<button class="icon-btn search-open" type="button">검색</button>
<button class="icon-btn" id="theme-btn" type="button">테마</button>
</header>
<div class="progress-line" aria-hidden="true"><i></i></div>
<main id="main" class="layout{' has-toc' if toc else ''}">
<article>
{body}
{site_footer(root)}
</article>
{toc_html}
</main>
</div>
<script src="{root}assets/site.js"></script>
</body>
</html>
'''


def chapter_page(cid):
    c = CH[cid]
    p = PARTS[c['part']]
    md = SRC / 'content' / f'{cid}.md'
    idx = [x['id'] for x in CHAPTERS].index(cid)
    prev_c = CHAPTERS[idx - 1] if idx > 0 else None
    next_c = CHAPTERS[idx + 1] if idx + 1 < len(CHAPTERS) else None
    stats, entries, terms = None, [], []
    if md.exists():
        body, toc, entries, terms, stats = render_chapter_body(cid, md.read_text(encoding='utf-8'))
    else:
        body, toc = '<div class="callout note"><p>이 장은 준비 중입니다.</p></div>', []
    pre = ''.join(f'<a class="chip" href="{x}.html">{ch_label(x)} {esc(CH[x]["title"])}</a>' for x in c.get('prereq', []))
    pre_html = f'<span class="chip">먼저 읽으면 좋은 장</span>{pre}' if pre else ''
    head = f'''<header class="ch-head pc-{p["color"]}">
<div class="ch-kicker"><span class="ch-no">{ch_no(cid)}장</span><span class="part">{PART_NO[p["id"]]}부 · {esc(p["title"])}</span></div>
<h1>{esc(c["title"])}</h1>
<p class="ch-sub">{esc(c["sub"])}</p>
<div class="ch-meta"><span class="chip">읽는 시간 약 {c["time"]}분</span>{pre_html}</div>
</header>'''
    pv = f'<a class="prev" href="{prev_c["id"]}.html"><small>← 이전 · {ch_label(prev_c["id"])}</small><b>{esc(prev_c["title"])}</b></a>' if prev_c else '<span></span>'
    nx = f'<a class="next" href="{next_c["id"]}.html"><small>다음 · {ch_label(next_c["id"])} →</small><b>{esc(next_c["title"])}</b></a>' if next_c else f'<a class="next" href="../index.html"><small>끝 →</small><b>전체 지도로 돌아가기</b></a>'
    foot = f'<footer class="ch-foot"><button class="read-btn" id="read-btn" type="button" aria-pressed="false">이 장을 다 읽었어요</button><nav class="pager" aria-label="이전·다음 장">{pv}{nx}</nav></footer>'
    crumb = f'{PART_NO[p["id"]]}부 {esc(p["title"])} › <b>{ch_label(cid)} {esc(c["title"])}</b>'
    out = page(f'{ch_label(cid)} {c["title"]} — {CUR["title"]}', head + body + foot, cid, '../', crumb, toc, c['sub'])
    OUT_CH.mkdir(exist_ok=True)
    (OUT_CH / f'{cid}.html').write_text(out, encoding='utf-8')
    return stats, entries, terms


def home_page():
    md = (SRC / 'content' / 'home.md').read_text(encoding='utf-8')
    top_md, _, bottom_md = md.partition('<!--CARDS-->')
    top, _, _, _, _ = render_chapter_body('home', top_md, root='')
    bottom = render_chapter_body('home', bottom_md, root='')[0] if bottom_md.strip() else ''
    blocks = []
    for p in CUR['parts']:
        cards = []
        for c in CHAPTERS:
            if c['part'] != p['id']:
                continue
            cards.append(
                f'<a class="card" href="chapters/{c["id"]}.html" data-ch="{c["id"]}" data-tracks="{" ".join(c["tracks"])}">'
                f'<i class="cn">{ch_no(c["id"])}장</i><b>{esc(c["title"])}</b><span>{esc(c["sub"])}</span><em>약 {c["time"]}분</em></a>')
        blocks.append(
            f'<section class="part-block pc-{p["color"]}" id="{p["id"]}"><div class="part-head"><span class="pn">{PART_NO[p["id"]]}부</span>'
            f'<h2>{esc(p["title"])}</h2><p>{esc(p["desc"])}</p></div><div class="cards">{"".join(cards)}</div></section>')
    total = sum(c['time'] for c in CHAPTERS)
    math_card = (f'<section class="part-block pc-warm" id="math-entry"><div class="cards"><a class="card" href="chapters/math.html">'
                 f'<b>{esc(SITE["mathEntry"]["label"])}</b></a></div></section>')
    tracks = ('<div class="tracks" role="group" aria-label="학습 경로">'
              '<button class="track-btn" data-track="all" aria-pressed="true" type="button">전체 보기</button>'
              '<button class="track-btn" data-track="core" aria-pressed="false" type="button">공통 기초</button>'
              '<button class="track-btn" data-track="game" aria-pressed="false" type="button">게임</button>'
              '<button class="track-btn" data-track="ai" aria-pressed="false" type="button">AI</button></div>')
    body = (top.replace('TOTALPLACEHOLDER', f'{len(CHAPTERS)}개 장 · 약 {round(total / 60)}시간')
            + f'<h2 id="map">전체 지도</h2>{tracks}'
            + math_card + ''.join(blocks) + bottom)
    out = page(f'{CUR["title"]} — {CUR["subtitle"]}', body, 'home', '', '<b>전체 지도</b>', None, CUR['subtitle'])
    (ROOT / 'index.html').write_text(out, encoding='utf-8')


def initial_of(s):
    ch = s[:1]
    if not ch:
        return '#'
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        lead = (code - 0xAC00) // 588
        return 'ㄱㄱㄴㄷㄷㄹㅁㅂㅂㅅㅅㅇㅈㅈㅊㅋㅌㅍㅎ'[lead]
    if ch.isascii() and ch.isalpha():
        return ch.upper()
    return '#'


def glossary_page(terms):
    """각 장의 용어 정리 + 약어 사전. 같은 낱말이 장마다 다른 뜻으로 쓰이면 모두 싣는다."""
    items = []
    seen = set()
    names = set()
    for t in terms:
        name = t['term'].strip()
        if not name or (name, t['ch']) in seen:
            continue
        seen.add((name, t['ch']))
        names.add(name)
        for part in re.split(r'[,/]', t['en']):
            names.add(part.strip())
        items.append(t)
    abbr_p = SRC / 'abbreviations.json'
    if abbr_p.exists():
        for a in json.loads(abbr_p.read_text(encoding='utf-8')):
            if a['term'] in names:
                continue
            items.append({'term': a['term'], 'en': a.get('full', ''),
                          'def': (a.get('ko', '') + ' — ' if a.get('ko') else '') + a.get('definition', ''), 'ch': ''})
    items.sort(key=lambda t: (t['term'].lower(), t['ch']))
    groups = {}
    for t in items:
        groups.setdefault(initial_of(t['term']), []).append(t)
    order = sorted(groups, key=lambda g: (0 if 'ㄱ' <= g <= 'ㅎ' else 1 if g != '#' else 2, g))
    parts = []
    entries = []
    for g in order:
        rows = []
        for t in groups[g]:
            link = f'<a href="{t["ch"]}.html#terms">{ch_label(t["ch"])} {esc(CH[t["ch"]]["title"])}</a>' if t['ch'] else ''
            en = f'<small>{esc(t["en"])}</small>' if t['en'] else ''
            k = esc((t['term'] + ' ' + t['en'] + ' ' + t['def']).lower())
            rows.append(f'<div class="gl-item" data-k="{k}"><b>{esc(t["term"])}</b>{en}{link}<p>{esc(t["def"])}</p></div>')
            u = f'chapters/{t["ch"]}.html#terms' if t['ch'] else 'chapters/glossary.html'
            where = f'용어 · {ch_label(t["ch"])}' if t['ch'] else '약어'
            entries.append({'u': u, 'c': where, 't': t['term'] + (f' ({t["en"]})' if t['en'] else ''), 'x': t['def'], 'k': 'term'})
        parts.append(f'<section class="gl-group"><h2 id="g-{esc(g)}">{esc(g)}</h2>{"".join(rows)}</section>')
    jump = ''.join(f'<a class="chip" href="#g-{esc(g)}">{esc(g)}</a>' for g in order)
    body = (f'<header class="ch-head"><h1>용어 사전</h1></header>'
            '<input id="gl-filter" class="gl-filter" type="search" placeholder="찾기" aria-label="용어 거르기">'
            f'<div class="ch-meta" style="margin-bottom:8px">{jump}</div>' + ''.join(parts))
    (OUT_CH / 'glossary.html').write_text(page(f'용어 사전 — {CUR["title"]}', body, 'glossary', '../', '<b>용어 사전</b>'), encoding='utf-8')
    return entries


def extra_page(pid, title, sub):
    """장이 아닌 단독 페이지(src/content/<pid>.md → chapters/<pid>.html). 검색 색인 항목을 돌려준다."""
    body, toc, _, _, _ = render_chapter_body(pid, (SRC / 'content' / f'{pid}.md').read_text(encoding='utf-8'))
    head = f'<header class="ch-head"><h1>{esc(title)}</h1></header>'
    (OUT_CH / f'{pid}.html').write_text(page(f'{title} — {CUR["title"]}', head + body, pid, '../', f'<b>{esc(title)}</b>', toc, sub), encoding='utf-8')
    soup = BeautifulSoup(body, 'html.parser')
    entries = []
    for sec in soup.select('section.level2'):
        h = sec.find('h2')
        entries.append({'u': f'chapters/{pid}.html#{sec.get("id", "")}', 'c': title, 't': text_of(h).rstrip('#').strip(), 'x': text_of(sec)[:2400], 'k': 'sec'})
    return entries


def credits_page():
    rows = []
    for name, m in sorted(PHOTOS.items()):
        rows.append(f'<tr><td><img src="../assets/photo/{esc(name)}" alt="" loading="lazy" style="width:120px;border-radius:8px;display:block"></td>'
                    f'<td>{esc(m.get("title", name))}</td><td>{esc(m.get("author", ""))}</td><td>{esc(m.get("license", ""))}</td>'
                    f'<td><a href="{esc(m.get("source", ""))}" target="_blank" rel="noopener">원본</a></td></tr>')
    extra_p = SRC / 'content' / 'credits.md'
    extra = render_chapter_body('credits', extra_p.read_text(encoding='utf-8'))[0] if extra_p.exists() else ''
    table = ('<div class="table-wrap"><table><thead><tr><th>사진</th><th>제목</th><th>저작자</th><th>라이선스</th><th>출처</th></tr></thead><tbody>'
             + ''.join(rows) + '</tbody></table></div>') if rows else ''
    body = f'<header class="ch-head"><h1>만든 사람들</h1></header>{extra}{table}'
    (OUT_CH / 'credits.html').write_text(page(f'만든 사람들 — {CUR["title"]}', body, 'credits', '../', '<b>만든 사람들</b>'), encoding='utf-8')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    targets = args or [c['id'] for c in CHAPTERS]
    all_entries, all_terms = [], []
    for cid in targets:
        if cid not in CH:
            raise SystemExit(f'모르는 장: {cid}')
        stats, entries, terms = chapter_page(cid)
        all_entries += entries
        all_terms += terms
        if stats:
            print(f'{cid}  절 {stats["sections"]:>2} · 그림 {stats["figs"]:>2} · 문제 {stats["quiz"]} · 용어 {stats["terms"]:>2} · 글자 {stats["chars"]:>6}  → chapters/{cid}.html')
        else:
            print(f'{cid}  (원고 없음 → 준비 중 페이지)')
    if not args:
        home_page()
        all_entries += glossary_page(all_terms)
        all_entries += extra_page('math', '수학 길잡이', '')
        credits_page()
        (ROOT / 'assets' / 'search-index.js').write_text('window.CSF_INDEX=' + json.dumps(all_entries, ensure_ascii=False, separators=(',', ':')) + ';', encoding='utf-8')
        print(f'index.html · glossary.html · math.html · credits.html · search-index.js ({len(all_entries)}항목)')
    if warnings:
        print('\n경고 ' + str(len(warnings)) + '건:')
        for w in warnings:
            print('  ' + w)


if __name__ == '__main__':
    main()
