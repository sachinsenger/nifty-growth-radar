from pathlib import Path
p=Path('docs/index.html')
if not p.exists(): raise SystemExit('docs/index.html missing')
s=p.read_text(encoding='utf-8')
marker='<!-- DAILY_NEWS_LINK -->'
block=f'''<div class="card" id="daily-news"><h2>📰 Daily Global & Indian Market News</h2><p class="note">Top market-moving news, affected sectors, stocks to watch and likely impact.</p><p><a href="news.html">Open today's Market News Intelligence →</a></p></div>{marker}'''
if marker in s:
    start=s.index('<div class="card" id="daily-news">'); end=s.index(marker)+len(marker); s=s[:start]+block+s[end:]
else:
    s=s.replace('</main>',block+'</main>')
p.write_text(s,encoding='utf-8')
print('Integrated daily news link into dashboard')
