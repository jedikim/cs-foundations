#!/usr/bin/env python3
"""그림 검사 도구 — SVG를 실제 브라우저로 그려 PNG로 저장하고, 글자 겹침·넘침을 자동으로 찾는다.

  python3 src/figcheck.py ch03                 3장의 모든 그림 검사
  python3 src/figcheck.py ch03 cpu-cycle       그 그림만
  python3 src/figcheck.py ch03 --dark          다크 테마로도 렌더

결과: src/.preview/ch03/<이름>.png  (Read 도구로 열어 눈으로 확인)
필요한 것: Google Chrome (헤드리스 모드로 실행)
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
CSS = (ROOT / 'assets' / 'site.css').read_text(encoding='utf-8')
DEFS = (SRC / 'defs.svg').read_text(encoding='utf-8')

LINT_JS = r"""
(function(){
  var svg=document.querySelector('figure svg'), out=[];
  function add(level,msg){out.push(level+': '+msg);}
  var vb=svg.viewBox.baseVal, W=vb.width, H=vb.height;
  if(Math.round(W)!==760) add('ERROR','viewBox 너비가 760이 아님 ('+W+')');
  if(H<120||H>560) add('WARN','viewBox 높이 '+H+' — 권장 범위 160~520');
  var k=svg.getBoundingClientRect().width/W;
  function box(el){var r=el.getBoundingClientRect(), s=svg.getBoundingClientRect();return {x:(r.left-s.left)/k,y:(r.top-s.top)/k,w:r.width/k,h:r.height/k};}
  function label(el){return '"'+(el.textContent||'').trim().slice(0,18)+'"';}
  var texts=[].slice.call(svg.querySelectorAll('text')).filter(function(t){return (t.textContent||'').trim();});
  var tb=texts.map(function(t){var b=box(t);b.el=t;b.fs=parseFloat(getComputedStyle(t).fontSize);return b;});
  tb.forEach(function(b){
    if(b.x<4||b.y<2||b.x+b.w>W-4||b.y+b.h>H-2) add('ERROR','글자가 그림 밖으로 나감 '+label(b.el)+' x='+Math.round(b.x)+'~'+Math.round(b.x+b.w)+', y='+Math.round(b.y)+'~'+Math.round(b.y+b.h));
    if(b.fs<12) add('ERROR','글자가 너무 작음('+b.fs+'px) '+label(b.el));
  });
  for(var i=0;i<tb.length;i++)for(var j=i+1;j<tb.length;j++){
    var a=tb[i],b=tb[j];
    var ox=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x), oy=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);
    if(ox>3&&oy>a.h*0.3&&oy>b.h*0.3) add('ERROR','글자끼리 겹침 '+label(a.el)+' ↔ '+label(b.el));
  }
  var rects=[].slice.call(svg.querySelectorAll('rect.box, rect.solid, rect.panel, rect.ghost')).map(function(r){var b=box(r);b.el=r;return b;});
  tb.forEach(function(t){
    var cx=t.x+t.w/2, cy=t.y+t.h/2, best=null;
    rects.forEach(function(r){ if(cx>r.x&&cx<r.x+r.w&&cy>r.y&&cy<r.y+r.h){ if(!best||r.w*r.h<best.w*best.h) best=r; } });
    if(best){
      if(t.x<best.x+3||t.x+t.w>best.x+best.w-3) add('ERROR','글자가 상자 좌우를 넘침 '+label(t.el)+' (글자 폭 '+Math.round(t.w)+', 상자 폭 '+Math.round(best.w)+')');
      else if(t.y<best.y-1||t.y+t.h>best.y+best.h+1) add('WARN','글자가 상자 위아래에 걸침 '+label(t.el));
    }
  });
  [].slice.call(svg.querySelectorAll('[fill],[stroke],[style]')).forEach(function(el){
    var v=(el.getAttribute('fill')||'')+' '+(el.getAttribute('stroke')||'')+' '+(el.getAttribute('style')||'');
    if(/#[0-9a-fA-F]{3,8}\b|rgb\(/.test(v)) add('WARN','색을 직접 지정함(다크 테마에서 깨짐): <'+el.tagName+' '+v.trim().slice(0,40)+'>');
  });
  [].slice.call(svg.querySelectorAll('use')).forEach(function(u){
    var id=(u.getAttribute('href')||u.getAttribute('xlink:href')||'').slice(1);
    if(id&&!document.getElementById(id)) add('ERROR','없는 아이콘: #'+id);
  });
  [].slice.call(svg.querySelectorAll('[marker-end],[marker-start]')).forEach(function(el){
    ['marker-end','marker-start'].forEach(function(a){var m=/url\(#([^)]+)\)/.exec(el.getAttribute(a)||''); if(m&&!document.getElementById(m[1])) add('ERROR','없는 화살촉: #'+m[1]);});
  });
  if(svg.querySelector('style')) add('WARN','<style>를 그림 안에 넣지 마세요(공용 클래스 사용)');
  if(svg.querySelector('foreignObject')) add('WARN','foreignObject는 쓰지 마세요');
  var pre=document.createElement('pre');pre.id='lint';pre.textContent=JSON.stringify({w:W,h:H,texts:tb.length,issues:out});document.body.appendChild(pre);
})();
"""


def page_html(svg, theme):
    return f'''<!doctype html><html lang="ko" data-theme="{theme}"><head><meta charset="utf-8"><style>{CSS}</style>
<style>body{{padding:16px;width:792px}}figure.fig{{margin:0}}figure.fig .fig-body svg{{min-width:0}}#lint{{display:none}}</style></head>
<body>{DEFS}<figure class="fig"><div class="fig-body">{svg}</div></figure><script>{LINT_JS}</script></body></html>'''


def chrome(args):
    return subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                           '--allow-file-access-from-files'] + args, capture_output=True, timeout=60)


def check(cid, name, dark=False):
    p = SRC / 'fig' / cid / f'{name}.svg'
    svg = p.read_text(encoding='utf-8')
    svg = re.sub(r'<\?xml[^>]*\?>', '', svg).strip()
    m = re.search(r'viewBox="\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*"', svg)
    if not m:
        print(f'✗ {name}: viewBox="0 0 760 H" 가 필요합니다')
        return False
    w, h = float(m.group(1)), float(m.group(2))
    svg = re.sub(r'(<svg\b[^>]*?)\s(?:width|height)="[^"]*"', r'\1', svg)
    svg = re.sub(r'(<svg\b[^>]*?)\s(?:width|height)="[^"]*"', r'\1', svg)
    outdir = SRC / '.preview' / cid
    outdir.mkdir(parents=True, exist_ok=True)
    ok = True
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / 'f.html'
        f.write_text(page_html(svg, 'light'), encoding='utf-8')
        r = chrome(['--dump-dom', f.as_uri()])
        dom = r.stdout.decode('utf-8', 'replace')
        lm = re.search(r'<pre id="lint">(.*?)</pre>', dom, re.S)
        issues = ['ERROR: 검사 스크립트가 실행되지 않음 — SVG 문법 오류일 수 있습니다']
        if lm:
            issues = json.loads(html.unescape(lm.group(1)))['issues']
        height = int(h * (728 / w) + 16 * 2 + 14 * 2 + 4)
        themes = ['light'] + (['dark'] if dark else [])
        for th in themes:
            f.write_text(page_html(svg, th), encoding='utf-8')
            png = outdir / (f'{name}.png' if th == 'light' else f'{name}.dark.png')
            chrome([f'--window-size=792,{height}', '--force-device-scale-factor=1.5', f'--screenshot={png}', f.as_uri()])
        errs = [i for i in issues if i.startswith('ERROR')]
        mark = '✗' if errs else ('△' if issues else '✓')
        ok = not errs
        print(f'{mark} {cid}/{name}.svg  ({int(w)}×{int(h)})  → {(outdir / (name + ".png")).relative_to(ROOT)}')
        for i in issues:
            print('    ' + i)
    return ok


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dark = '--dark' in sys.argv
    if not args:
        raise SystemExit(__doc__)
    cid = args[0]
    names = args[1:] or sorted(p.stem for p in (SRC / 'fig' / cid).glob('*.svg'))
    bad = 0
    for n in names:
        if not check(cid, re.sub(r'\.svg$', '', n), dark):
            bad += 1
    print(f'\n{len(names)}개 중 문제 있는 그림 {bad}개' + ('' if bad else ' — 자동 검사 통과. PNG를 열어 눈으로도 확인하세요.'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
