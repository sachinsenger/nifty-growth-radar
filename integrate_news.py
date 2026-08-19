from pathlib import Path

p = Path('docs/index.html')
if not p.exists():
    raise SystemExit('docs/index.html missing')

s = p.read_text(encoding='utf-8')
marker = '<!-- DAILY_NEWS_LINK -->'
block = '''<div class="card" id="daily-news"><h2>📰 Daily Global & Indian Market News</h2><p class="note">Top market-moving news, affected sectors, stocks to watch and likely impact.</p><p><a href="news.html">Open today's Market News Intelligence →</a></p></div>''' + marker

# Idempotent replacement: handle both the normal block and a marker left by an
# earlier version, without failing if the surrounding card was edited.
if marker in s:
    start = s.find('<div class="card" id="daily-news">')
    marker_end = s.find(marker) + len(marker)
    if start >= 0:
        s = s[:start] + block + s[marker_end:]
    else:
        s = s[:s.find(marker)] + block + s[marker_end:]
else:
    insertion = block
    if '</main>' in s:
        s = s.replace('</main>', insertion + '</main>', 1)
    else:
        s += insertion

p.write_text(s, encoding='utf-8')
print('Integrated daily news link into dashboard')
