"""Read a supplied workbook without modifying it; emit resumable audit items."""
import argparse, csv, hashlib, json, re
from pathlib import Path
from urllib.parse import urlsplit

URL = re.compile(r'https?://[^\s<>"\u3000]+')

def identity(url):
    p=urlsplit(url)
    if p.hostname in ('www.douyin.com','www.iesdouyin.com','douyin.com','iesdouyin.com'):
        m=re.fullmatch(r'/(?:share/)?(?:video|note)/(\d+)/?',p.path)
        if m: return 'douyin:'+m.group(1)
    return url

def urls(value, hyperlink=None):
    text = str(value or '').strip()
    if text.startswith('='):
        m = re.match(r'=\s*HYPERLINK\s*\(\s*"((?:[^"]|"")+)"\s*[,;]', text, re.I)
        text = m.group(1).replace('""', '"') if m else ''
    candidates = ([hyperlink] if hyperlink else []) + URL.findall(text)
    return list(dict.fromkeys(u for u in candidates if u and re.match(r'^https?://', u)))

def prepare(path, header_row=1):
    path = Path(path)
    tables = []
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        tables.append((path.stem, rows, {}))
    elif path.suffix.lower() == '.xlsx':
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=False)
        for s in wb:
            tables.append((s.title, [[c.value for c in r] for r in s],
                           {(c.row, c.column): c.hyperlink.target for r in s for c in r if c.hyperlink}))
    else:
        raise ValueError('仅支持 .xlsx 或 UTF-8 CSV；请先另存旧版 .xls')
    result = {'source_name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'items': [], 'issues': [], 'record_count': 0}
    for name, rows, links in tables:
        if len(rows) < header_row:
            continue
        headers = [str(x or '').strip() for x in rows[header_row-1]]
        columns = [i for i,h in enumerate(headers) if h.lower() in ('链接','url','原链接','笔记链接','文章链接','视频链接')]
        if not columns:
            result['issues'].append(f'{name}: 未识别链接列，请人工检查该表头')
            continue
        if len(set(headers)) != len(headers):
            result['issues'].append(f'{name}: 存在重复/空表头，原始值保留为数组')
        for rownum, row in enumerate(rows[header_row:], header_row+1):
            if not any(v is not None and str(v).strip() for v in row):
                continue
            result['record_count'] += 1
            source = dict(zip(headers, row))
            found = []
            for i in columns:
                found += urls(row[i] if i < len(row) else None, links.get((rownum,i+1)))
            aliases={}
            for u in found: aliases.setdefault(identity(u),[]).append(u)
            found = [v[0] for v in aliases.values()] or ['']
            for index, url in enumerate(found, 1):
                result['items'].append({'key': f'{name}!{rownum}#{index}', 'sheet':name,'row':rownum,
                    'source':source,'source_headers':headers,'source_values':row,'url':url,'url_aliases':list(dict.fromkeys(aliases.get(identity(url),[]))),
                    'platform':str(source.get('媒体') or source.get('平台') or '未标平台')})
    result['unique_url_count'] = len({identity(i['url']) for i in result['items'] if i['url']})
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('input'); p.add_argument('output'); p.add_argument('--header-row',type=int,default=1)
    a=p.parse_args()
    if a.header_row < 1: p.error('header-row 必须大于 0')
    result=prepare(a.input,a.header_row)
    with Path(a.output).open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,default=str)
    print(json.dumps({k:v for k,v in result.items() if k!='items'},ensure_ascii=False))
