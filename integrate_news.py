from pathlib import Path

p = Path('docs/index.html')
if not p.exists():
    raise SystemExit('docs/index.html missing')

s = p.read_text(encoding='utf-8')
marker = '<!-- DAILY_NEWS_LINK -->'
block = '''<div class="card" id="daily-news"><h2>📰 Daily Global & Indian Market News</h2><p class="note">Top market-moving news, affected sectors, stocks to watch and likely impact.</p><p><a href="news.html">Open today's Market News Intelligence →</a></p></div>''' + marker

if marker in s:
    start = s.find('<div class="card" id="daily-news">')
    marker_end = s.find(marker) + len(marker)
    if start >= 0:
        s = s[:start] + block + s[marker_end:]
    else:
        s = s[:s.find(marker)] + block + s[marker_end:]
else:
    if '</main>' in s:
        s = s.replace('</main>', block + '</main>', 1)
    else:
        s += block

# Keep the research workbench visible from the main dashboard without making
# run_daily.py responsible for knowing about secondary pages.
research_marker = '<!-- RESEARCH_LINK -->'
research_block = '''<div class="card" id="research"><h2>📊 Nifty & F&O Research</h2><p class="note">Expiry/weekly behaviour, gaps, historical analogues, outliers and F&O stock ranking.</p><p><a href="research.html">Open Nifty & F&O Research →</a></p></div>''' + research_marker
if research_marker in s:
    start = s.find('<div class="card" id="research">')
    marker_end = s.find(research_marker) + len(research_marker)
    if start >= 0:
        s = s[:start] + research_block + s[marker_end:]
    else:
        s = s[:s.find(research_marker)] + research_block + s[marker_end:]
else:
    if '</main>' in s:
        s = s.replace('</main>', research_block + '</main>', 1)
    else:
        s += research_block

p.write_text(s, encoding='utf-8')
print('Integrated daily news and research links into dashboard')
# Research dashboard rebuild trigger: research_engine.py + research_v2.py generate docs/research.html.
