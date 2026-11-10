# ddtuning-public-feeds
Public RSS feeds generated from DD Tuning articles. No credentials.

## Доступ до сайту (Cloudflare)

Сторінки статей ddtuning.com.ua закриті перевіркою Cloudflare для країн поза Україною та Європою, а GitHub
Actions працює зі США. Генератор проходить її лише з секретним ключем: секрет репозиторію `DDTUNING_RSS_KEY`
передається заголовком `X-DDTuning-RSS-Key`. Правило Cloudflare пропускає запит, тільки якщо збігаються ключ,
хост `ddtuning.com.ua`, мережа GitHub (AS8075), метод GET/HEAD і шлях: `/google-news-sitemap.xml`,
`/novosti-…`, `/korysni-stati-…`, `/nashi-roboty-…`. Каталог і решта сайту ключем не відкриваються.
Генератор не йде за переадресаціями на інші хости, тож ключ не покидає сайт.
