"""Synthetic-only regression checks; does not connect to any website."""
import copy, tempfile
from pathlib import Path
from prepare import prepare, urls, identity
from report import combine, render

assert urls('=HYPERLINK("https://example.com/a","打开")')==['https://example.com/a']
assert urls('=SOMEFUNCTION("https://example.com/a")')==[]
assert urls('https://example.com/a\nhttps://example.com/b')==['https://example.com/a','https://example.com/b']
assert identity('https://www.iesdouyin.com/share/video/123')==identity('https://www.douyin.com/note/123')
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'sample.csv'
    p.write_text('序号,媒体,标题,链接,链接探测\n1,测试,<script>x</script>,https://example.com/a,删除\n2,测试,重复,https://example.com/a,正常\n3,测试,缺链接,,正常\n,,,,\n',encoding='utf-8')
    a=prepare(p)
    assert a['record_count']==3 and a['unique_url_count']==1
    assert len(a['items'])==3
    o={'key':a['items'][0]['key'],'status':'仍可访问','checked_at':'2026-01-01T09:00:00+08:00','evidence':'模拟可见内容','target_matched':True,'final_url':'https://example.com/a'}
    r=combine(a,[o]);assert r['counts']['未核查']==2 and len(r['conflicts'])==1
    assert '<script>x</script>' not in render(r) and '&lt;script&gt;' in render(r)
    rule={**o,'status':'已删除／已下架','display_status':'已删除（无法正常访问）','classification_basis':'target_id_mismatch','target_matched':False,'final_url':'https://example.com/other'}
    assert combine(a,[rule])['counts']['已删除／已下架']==1
    inaccessible={**rule,'classification_basis':'link_inaccessible','final_url':'','evidence':'模拟：原链接访问失败，按验收口径判定'}
    assert combine(a,[inaccessible])['counts']['已删除／已下架']==1
    try:combine(a,[{**inaccessible,'checked_at':''}])
    except ValueError:pass
    else:raise AssertionError('Missing actual observation time accepted')
    w=copy.deepcopy(a);w['items'][0]['platform']='微信视频号'
    try:combine(w,[rule])
    except ValueError:pass
    else:raise AssertionError('WeChat cannot use redirect deletion rule')
    wx={**o,'status':'暂无法确认','display_status':'待复核（工具限制）','classification_basis':'wechat_tool_limit','checked_at':'','recorded_at':'2026-01-01T09:00:00+08:00','target_matched':False}
    assert combine(w,[wx])['counts']['暂无法确认']==1
    for bad in [[o,o],[{**o,'key':'unknown'}],[{**o,'target_matched':False}],[{**o,'checked_at':'2026-01-01T09:00:00'}],[{**o,'evidence':''}]]:
        try:combine(a,bad)
        except ValueError:pass
        else:raise AssertionError('Invalid observation accepted')
print('Synthetic regression checks passed')
