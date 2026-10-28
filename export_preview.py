"""Export current saved reports and working client-side research filters.

Offline POST forms never pretend to save. No provider requests or inbox reads.
"""
import json
from pathlib import Path
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from flask import render_template
from app import app
from recommendations import load_snapshot, page_data


def main():
    root = Path(__file__).parent
    snapshot = load_snapshot()
    if not snapshot:
        raise RuntimeError('Publish a current-model snapshot before exporting the preview')
    sid = snapshot['id']
    css = (root/'static/styles.css').read_text()
    pages = {}
    client = app.test_client()
    paths = ['/', '/methodology', '/how-to-invest', '/disclosures', '/discover',
             '/discover?sort=combined', '/suggest-company', '/admin/login', '/data-status']
    paths += ['/top-opportunities?view='+v for v in ['all','screen','watchlist','partial','excluded']]
    for symbol in snapshot['reports']:
        paths += ['/search?'+urlencode({'q':symbol,'snapshot':sid}),
                  '/sources/'+symbol+'?'+urlencode({'snapshot':sid})]
    for path in paths:
        response=client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f'Preview route {path} failed: {response.status_code}')
        if path == '/data-status':
            import html
            pages[path]='<html><body><h1>Saved data status</h1><pre>'+html.escape(response.get_data(as_text=True))+'</pre></body></html>'
            continue
        soup=BeautifulSoup(response.get_data(as_text=True),'html.parser')
        if path.startswith('/search?') and not soup.select_one('article.report'):
            raise RuntimeError(f'Saved report did not render: {path}')
        for script in soup.find_all('script'): script.decompose()
        for link in soup.select('link[rel="stylesheet"], link[rel="icon"]'): link.decompose()
        style=soup.new_tag('style');style.string=css;soup.head.append(style)
        # Never include a real session token or a misleading enabled submission button.
        for field in soup.select('input[name="csrf_token"]'): field['value']='offline-preview'
        if path in {'/suggest-company','/admin/login'}:
            notice=soup.new_tag('p',attrs={'class':'data-warning'})
            notice.string='Offline preview: this form cannot save submissions or sign you in. These functions work in the running application after Railway setup.'
            soup.main.insert(0,notice)
            for button in soup.select('button[type="submit"]'): button.attrs.pop('disabled',None)
        pages[path]=str(soup)
    with app.test_request_context('/'):
        all_rows=render_template('partials/company_table.html',items=snapshot['rankings'],snapshot=snapshot)
    table=BeautifulSoup(all_rows,'html.parser')
    row_html={item['symbol']:str(row) for item,row in zip(snapshot['rankings'],table.select('tbody tr'))}
    excluded=[]
    excluded_html={}
    for page in range(1, 1+((snapshot['universe_count']+9)//10)):
        data=page_data(snapshot,page=page,view='excluded')
        excluded+=data['items']
        if not data['has_more']: break
    with app.test_request_context('/'):
        rendered=render_template('top_opportunities.html',**dict(page_data(snapshot,view='excluded'),items=excluded))
    soup=BeautifulSoup(rendered,'html.parser')
    cards=soup.select('section.container > div.section-stack > article.panel')
    for item,card in zip(excluded,cards): excluded_html[item['symbol']]=str(card)
    payload={'pages':pages,'rows':row_html,'excludedRows':excluded_html,
             'rankings':snapshot['rankings'],'excluded':excluded,'snapshot':sid,
             'names':{r['name'].casefold():r['symbol'] for r in snapshot['reports'].values()}}
    wrapper=(root/'preview_shell.html').read_text()
    (root/'PREVIEW.html').write_text(wrapper.replace('PAYLOAD_JSON',json.dumps(payload).replace('</','<\\/')))
    print(f'Exported {len(pages)} pages; {len(row_html)} ranked company rows; {len(excluded_html)} unrated rows.')


if __name__=='__main__': main()
