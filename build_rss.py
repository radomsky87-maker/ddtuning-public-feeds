#!/usr/bin/env python3
"""Build full-content RSS for Drukarnia from DD Tuning's Google News sitemap."""
import argparse
import concurrent.futures
import datetime as dt
import email.utils
import html
from html.parser import HTMLParser
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SOURCE = 'https://ddtuning.com.ua/google-news-sitemap.xml'
HOST = 'ddtuning.com.ua'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9',
      'n': 'http://www.google.com/schemas/sitemap-news/0.9'}
CONTENT = 'http://purl.org/rss/1.0/modules/content/'
ET.register_namespace('content', CONTENT)

def fetch(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname != HOST:
        raise ValueError('Only HTTPS DD Tuning source URLs are permitted')
    request = urllib.request.Request(url, headers={'User-Agent': 'DDTuningRSS/1.0'})
    with urllib.request.urlopen(request, timeout=40) as response:
        if urllib.parse.urlsplit(response.url).hostname != HOST:
            raise ValueError('Unexpected redirect host')
        return response.read().decode('utf-8')

class Article(HTMLParser):
    allowed = {'p','br','h2','h3','h4','ul','ol','li','strong','b','em','i',
               'blockquote','a','img','table','thead','tbody','tr','th','td','figure','figcaption'}
    void = {'img','br','hr','input','meta','link','source','wbr','area','base','embed','param','track','col'}
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url, self.depth, self.active, self.skip = url, 0, None, None
        self.parts, self.meta = [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            self.meta[a.get('property') or a.get('name')] = a.get('content','')
        if tag not in self.void:
            self.depth += 1
        classes = set(a.get('class','').split())
        if self.active is None and 'article-text' in classes:
            self.active = self.depth
            return
        if self.active is None:
            return
        if self.skip is not None:
            return
        if tag in {'script','style','iframe','form','button','svg'} or 'article-products' in classes:
            if tag not in self.void:
                self.skip = self.depth
            return
        if tag not in self.allowed:
            return
        clean = []
        for key in ('href','src','alt','title','colspan','rowspan'):
            value = a.get(key)
            if value is None:
                continue
            if key in ('href','src'):
                value = urllib.parse.urljoin(self.url, value)
                if urllib.parse.urlsplit(value).scheme not in ('https','http'):
                    continue
            clean.append(f' {key}="{html.escape(value, quote=True)}"')
        self.parts.append('<' + tag + ''.join(clean) + '>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.active is not None:
            if self.skip is not None:
                if self.depth == self.skip:
                    self.skip = None
            elif self.depth == self.active:
                self.active = None
            elif tag in self.allowed and tag not in self.void:
                self.parts.append('</' + tag + '>')
        if tag not in self.void:
            self.depth -= 1

    def handle_data(self, data):
        if self.active is not None and self.skip is None:
            self.parts.append(html.escape(data))

def article(entry):
    url, title, date = entry
    parser = Article(url)
    parser.feed(fetch(url))
    body = ''.join(parser.parts).strip()
    if len(body) < 200:
        raise ValueError('Missing full article text: ' + url)
    image = parser.meta.get('og:image', '')
    if image:
        image = urllib.parse.urljoin(url, image)
        if urllib.parse.urlsplit(image).scheme == 'https':
            body = '<p><img src="' + html.escape(image, quote=True) + '" alt="' + html.escape(title, quote=True) + '"></p>' + body
    body += '<p>Першоджерело: <a href="' + html.escape(url, quote=True) + '">DD Tuning — ' + html.escape(title) + '</a></p>'
    return url, title, date, parser.meta.get('description',''), body

def build(source, output, limit):
    root = ET.fromstring(fetch(source))
    entries = []
    for item in root.findall('s:url', NS):
        url = item.findtext('s:loc','',NS).strip()
        title = item.findtext('n:news/n:title','',NS).strip()
        language = item.findtext('n:news/n:publication/n:language','',NS)
        date = dt.datetime.fromisoformat(item.findtext('n:news/n:publication_date','',NS).replace('Z','+00:00'))
        if date.tzinfo is None:
            raise ValueError('Publication date requires timezone')
        if language == 'uk' and title and date <= dt.datetime.now(dt.timezone.utc):
            entries.append((url,title,date))
    entries = sorted({e[0]: e for e in entries}.values(), key=lambda e:e[2], reverse=True)[:limit]
    if not entries:
        raise ValueError('No Ukrainian articles in sitemap')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        articles = list(pool.map(article, entries))
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss,'channel')
    for key,value in [('title','DD Tuning — новини та експертні статті'),('link','https://ddtuning.com.ua/'),('description','Власні публікації DD Tuning'),('language','uk'),('lastBuildDate',email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)))]:
        ET.SubElement(channel,key).text = value
    for url,title,date,description,body in articles:
        item = ET.SubElement(channel,'item')
        for key,value in [('title',title),('link',url),('pubDate',email.utils.format_datetime(date)),('description',description),('{'+CONTENT+'}encoded',body)]:
            ET.SubElement(item,key).text = value
        ET.SubElement(item,'guid', isPermaLink='true').text = url
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix+'.tmp')
    ET.ElementTree(rss).write(temp,encoding='utf-8',xml_declaration=True)
    ET.parse(temp)
    os.replace(temp,target)
    print(f'RSS validated: {len(articles)} full articles -> {target}')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source',default=SOURCE)
    p.add_argument('--output',default='output/drukarnia.xml')
    p.add_argument('--limit',type=int,default=30)
    args = p.parse_args()
    build(args.source,args.output,args.limit)
