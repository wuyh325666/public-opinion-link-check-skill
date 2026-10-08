"""Validate actual observations and render a local report; never infers website status."""
import argparse, collections, html, json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

STATUSES=('已删除／已下架','仍可访问','暂无法确认','未核查')

def combine(prepared, observations):
    sources={i['key']:i for i in prepared['items']}
    keys=set(sources)
    seen={}
    for o in observations:
        if o['key'] not in keys or o['key'] in seen:
            raise ValueError('观察 key 未知或重复: '+o['key'])
        if o.get('status') not in STATUSES: raise ValueError('无效状态')
        wechat_limit=o.get('classification_basis')=='wechat_tool_limit'
        rule_deleted=o.get('classification_basis') in ('recommended_page_redirect','target_id_mismatch','link_inaccessible')
        if wechat_limit:
            if sources[o['key']]['platform']!='微信视频号' or o['status']!='暂无法确认' or o.get('display_status')!='待复核（工具限制）':
                raise ValueError('视频号工具限制标记不一致')
            if not o.get('evidence'): raise ValueError('缺少工具限制说明')
            if not o.get('checked_at'):
                t=datetime.fromisoformat(o['recorded_at'].replace('Z','+00:00'))
                if t.tzinfo is None: raise ValueError('记录时间必须带时区')
        if o['status'] != '未核查' and not (wechat_limit and not o.get('checked_at')):
            if not o.get('evidence') or not o.get('checked_at'): raise ValueError('已核查项缺少证据或时间')
            t=datetime.fromisoformat(o['checked_at'].replace('Z','+00:00'))
            if t.tzinfo is None: raise ValueError('核查时间必须带时区')
        if rule_deleted:
            if sources[o['key']]['platform']=='微信视频号' or o['status']!=STATUSES[0] or not sources[o['key']].get('url') or (o.get('classification_basis')!='link_inaccessible' and not o.get('final_url')) or o.get('display_status')!='已删除（无法正常访问）':
                raise ValueError('跳转业务判定缺少落地URL或状态不一致')
        if o['status'] in STATUSES[:2] and not (rule_deleted and o['status']==STATUSES[0]) and o.get('target_matched') is not True:
            raise ValueError('明确结论必须确认目标匹配')
        seen[o['key']]=o
    items=[]
    for source in prepared['items']:
        observation=seen.get(source['key'],{'status':'未核查','checked_at':'','evidence':'缺少链接' if not source['url'] else '尚未访问','final_url':'','target_matched':False})
        item={**source,**{k:v for k,v in observation.items() if k not in source or k=='key'}}
        items.append(item)
    counts={s:sum(i['status']==s for i in items) for s in STATUSES}
    platforms={p:{s:sum(i['platform']==p and i['status']==s for i in items) for s in STATUSES}
               for p in dict.fromkeys(i['platform'] for i in items)}
    conflicts=[i['key'] for i in items if str(i['source'].get('链接探测','')) in ('删除','已删除','已下架') and i['status']=='仍可访问']
    return {**{k:v for k,v in prepared.items() if k!='items'}, 'items':items,'counts':counts,'platforms':platforms,'conflicts':conflicts}

def render(result):
    esc=lambda v:html.escape(str(v or ''),quote=True)
    total=len(result['items'])
    stats=''.join(f'<tr><td>{esc(s)}</td><td>{n}</td><td>{n/total:.1%}</td></tr>' for s,n in result['counts'].items()) if total else ''
    rows=[]
    for i in result['items']:
        url=i['url']; parsed=urlsplit(url)
        link=f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">打开原链接</a>' if parsed.scheme in ('http','https') and parsed.netloc else '缺少有效链接'
        rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (i['key'],i['platform'],i['source'].get('序号',''),i['source'].get('标题',''),i['source'].get('链接探测',''),i.get('display_status',i['status']),i.get('checked_at',''),i.get('evidence','')))+'<td>'+link+'</td></tr>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>舆情链接核查汇总</title><style>body{font:14px/1.6 system-ui;margin:28px;color:#223}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{text-align:left;padding:9px;border-bottom:1px solid #ddd;vertical-align:top}th{background:#eef1f6}a{color:#1556ad}h1{font-size:24px}</style><h1>舆情链接核查汇总</h1><p>来源：'+esc(result['source_name'])+f'。原始记录 {result["record_count"]} 条，核查项 {total} 条，去重链接 {result["unique_url_count"]} 个。</p><p>比例分母为全部核查项。删除统计包含按用户验收口径判定的链接无法访问、推荐页跳转或目标ID不一致，具体依据见明细；不证明处置因果。视频号工具限制单列待复核，未访问项不填写核查时间。</p><table><tr><th>本次状态</th><th>数量</th><th>占比</th></tr>'+stats+'</table><p>原标删除但当前仍可访问：'+esc('、'.join(result['conflicts']) or '无')+'</p><table><tr><th>原表位置</th><th>平台</th><th>原序号</th><th>原标题</th><th>原状态</th><th>本次结果</th><th>核查时间</th><th>依据及待复核原因</th><th>链接</th></tr>'+''.join(rows)+'</table></html>'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('prepared');p.add_argument('observations');p.add_argument('output');a=p.parse_args()
    result=combine(json.loads(Path(a.prepared).read_text()),json.loads(Path(a.observations).read_text()))
    dest=Path(a.output);dest.mkdir(parents=True,exist_ok=True)
    for name,content in [('result.json',json.dumps(result,ensure_ascii=False,indent=2)),('汇总.html',render(result))]:
        with (dest/name).open('x',encoding='utf-8') as f:f.write(content)
    print(json.dumps(result['counts'],ensure_ascii=False))
