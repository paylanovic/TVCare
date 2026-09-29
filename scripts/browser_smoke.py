#!/usr/bin/env python3
"""Optional Playwright E2E. Uses an isolated synthetic TV, never real ADB."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs'/'screenshots'
OUTPUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='tvcare-browser-') as temp:
    process=subprocess.Popen([sys.executable,'-m','tvbakim','--demo','--no-browser','--data-dir',temp],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        process.stdout.readline()
        url=re.search(r'http://\S+',process.stdout.readline()).group(0)
        errors=[]
        with sync_playwright() as p:
            launch={'headless':True}
            if os.environ.get('TVCARE_CHROMIUM'): launch['executable_path']=os.environ['TVCARE_CHROMIUM']
            browser=p.chromium.launch(**launch)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' and ('Content Security Policy' in m.text or 'Refused to' in m.text) else None)
            page.goto(url)
            expect(page.locator('#demo-banner')).to_be_visible()
            assert '#token' not in page.url
            page.locator('[data-page="connection"]').click()
            page.locator('.inspect-device').click()
            expect(page.locator('#device-overview')).to_be_visible(timeout=15000)
            expect(page.locator('#health-metrics')).to_contain_text('408 MB')
            page.screenshot(path=str(OUTPUT/'desktop.png'),full_page=True)
            page.locator('[data-page="maintenance"]').click()
            page.locator('input[name="animation"][value="0.5"]').check()
            # Match visible package label; no auto-selected maintenance.
            page.locator('.package-item').filter(has_text='TCL Tarayıcı').locator('input').check()
            page.locator('#review-plan').click()
            expect(page.locator('#plan-dialog')).to_be_visible()
            expect(page.locator('#confirm-plan')).to_be_disabled()
            expect(page.locator('#plan-actions .plan-action')).to_have_count(4)
            page.locator('#confirm-checkbox').check()
            page.locator('#confirm-plan').click()
            expect(page.locator('#page-history')).to_be_visible(timeout=15000)
            expect(page.locator('#notice')).to_contain_text('İşlem tamamlandı')
            page.locator('.rollback-button').first.click()
            expect(page.locator('#plan-title')).to_contain_text('Geri alma')
            expect(page.locator('#plan-actions')).to_contain_text('Sistem varsayılanı')
            page.locator('#confirm-checkbox').check()
            page.locator('#confirm-plan').click()
            expect(page.locator('#page-history')).to_be_visible(timeout=15000)
            expect(page.locator('#notice')).to_contain_text('İşlem tamamlandı')
            expect(page.locator('#history-list article')).to_have_count(2)
            page.locator('[data-page="overview"]').click()
            page.locator('#refresh-inspect').click()
            expect(page.locator('#notice')).to_contain_text('Cihaz kontrolü tamamlandı',timeout=15000)
            with page.expect_download() as download:
                page.locator('#export-inspection').click()
            exported=json.loads(Path(download.value.path()).read_text())
            assert exported['evidence']=='synthetic_demo'
            assert 'serial_hash' not in json.dumps(exported)
            page.set_viewport_size({'width':390,'height':844})
            for view in ('overview','connection','maintenance','history','guide'):
                page.locator(f'[data-page="{view}"]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),view+' overflows'
            page.locator('[data-page="overview"]').click()
            page.screenshot(path=str(OUTPUT/'mobile.png'),full_page=True)
            # Tokenless context cannot read API or mutate a TV.
            other=browser.new_context()
            unauth=other.new_page(); unauth.goto(url.split('#')[0])
            expect(unauth.locator('#auth-gate')).to_be_visible()
            assert other.request.get(url.split('#')[0]+'api/status').status==401
            other.close(); browser.close()
        assert not errors,errors
        print('PASS: browser demo inspect → plan → apply → rollback → export; mobile five views; token gate; no JS/CSP errors')
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
