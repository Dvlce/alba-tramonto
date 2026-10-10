"""Real portal navigation, notebook save/failure, accessibility and history recovery."""
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys, secret_file
from service import Service
from store import Store


async def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name in ('web.html', 'web.css', 'web.js', 'portal-motion.js',
                     'tramonto.html', 'tramonto.css', 'tramonto.js', 'tramonto-lab.js', 'tramonto-font.js', 'tramonto-math.js', 'tramonto-study.js',
                     'notte.html', 'notte.css', 'notte.js'):
            shutil.copy2(ROOT / name, root / name)
        shutil.copytree(ROOT / 'vendor', root / 'vendor')
        settings = Settings(root=root, admins=(1,))
        store = Store(settings.data / 'alba.sqlite3')
        keys = Keys(store, secret_file(settings.data / 'auth.key'))
        service = Service(store, settings, keys, Engine(store, settings, None), Backups(store, settings))
        store.register(1, 'Admin')
        username, password = keys.set_web_password(1, 1, 'admin')
        server = TestServer(web_app(service))
        await server.start_server()
        errors = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={'width':1440, 'height':1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(str(server.make_url('/')))
                await page.locator('.portal-transition[data-space=alba]').wait_for()
                await page.screenshot(path=str(artifacts / 'portal-alba-entrance.png'))
                await page.locator('.portal-transition').wait_for(state='detached')
                await page.locator('#username').fill(username)
                await page.locator('#password').fill(password)
                await page.locator('#loginButton').click()
                await page.locator('#dashboard').wait_for(state='visible')
                menu_style = None
                for path, ready in [('/', '#dashboard'), ('/tramonto', '#bookList button'), ('/notte', '#streamState')]:
                    await page.goto(str(server.make_url(path)))
                    await page.locator(ready).first.wait_for(state='visible')
                    await page.locator('.portal-transition').wait_for(state='detached')
                    trigger = page.locator('[data-portal-trigger]')
                    await trigger.press('ArrowDown')
                    assert await page.locator('#siteMenu a[href="/"]').evaluate('e => e === document.activeElement')
                    await page.keyboard.press('End')
                    assert await page.locator('#notteLink').evaluate('e => e === document.activeElement')
                    assert await page.locator('#siteMenu a[aria-current="page"]').get_attribute('href') == path
                    style = await page.locator('#siteMenu').evaluate("e => {const s=getComputedStyle(e);return [s.width,s.borderRadius,s.padding,getComputedStyle(e.querySelector('a')).fontSize,getComputedStyle(e.querySelector('a')).minHeight]}")
                    if menu_style is None:
                        menu_style = style
                    assert style == menu_style, (path, style, menu_style)
                    name = {'/':'alba', '/tramonto':'tramonto', '/notte':'notte'}[path]
                    await page.screenshot(path=str(artifacts / ('portal-menu-' + name + '.png')))
                    await page.keyboard.press('Escape')
                    assert await trigger.evaluate('e => e === document.activeElement')
                    assert await trigger.get_attribute('aria-expanded') == 'false'
                    await page.set_viewport_size({'width':390, 'height':844})
                    await trigger.click()
                    box = await page.locator('#siteMenu').bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= 390 and box['y'] + box['height'] <= 844, (path, box)
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    await page.screenshot(path=str(artifacts / ('portal-menu-' + name + '-mobile.png')))
                    await page.keyboard.press('Escape')
                    await page.set_viewport_size({'width':1440, 'height':1000})
                await page.goto(str(server.make_url('/')))
                await page.locator('#dashboard').wait_for(state='visible')
                await page.locator('.portal-transition').wait_for(state='detached')
                await page.locator('#albaSymbol').click()
                await page.locator('#tramontoLink').click()
                await page.locator('.portal-transition[data-space=tramonto][data-phase=leave]').wait_for()
                await page.screenshot(path=str(artifacts / 'portal-tramonto-transition.png'))
                await page.wait_for_url('**/tramonto')
                await page.locator('#bookList button').wait_for()
                await page.locator('.portal-transition').wait_for(state='detached')
                await page.locator('#newNote').click()
                await page.locator('#noteEditor').wait_for(state='visible')
                await page.locator('#richEditor').fill('Appunto salvato prima della transizione.')
                await page.locator('[data-portal-trigger]').click()
                await page.locator('.portal-menu a[href="/notte"]').click()
                await page.wait_for_url('**/notte')
                await page.locator('.portal-transition').wait_for(state='detached')
                await page.locator('[data-portal-trigger]').click()
                await page.locator('#siteMenu a[href="/tramonto"]').click()
                await page.wait_for_url('**/tramonto')
                await page.locator('#noteEditor').wait_for(state='visible')
                assert 'Appunto salvato' in await page.locator('#richEditor').inner_text()
                await page.locator('.portal-transition').wait_for(state='detached')
                # A failed save must prevent navigation and leave the editor usable.
                await page.route('**/api/tramonto/notes/*', lambda route: route.abort() if route.request.method == 'PUT' else route.continue_())
                await page.locator('#richEditor').fill('Modifica con server non disponibile.')
                if await page.locator('[data-portal-trigger]').get_attribute('aria-expanded')!='true':
                    await page.locator('[data-portal-trigger]').click()
                await page.locator('#siteMenu a[href="/"]').click()
                await page.locator('#saveStatus').filter(has_text='Non salvato').wait_for()
                assert page.url.endswith('/tramonto')
                assert await page.locator('.portal-transition').count() == 0
                await page.unroute('**/api/tramonto/notes/*')
                if await page.locator('[data-portal-trigger]').get_attribute('aria-expanded')!='true':
                    await page.locator('[data-portal-trigger]').click()
                await page.locator('#siteMenu a[href="/"]').click()
                await page.wait_for_url(str(server.make_url('/')))
                await page.locator('.portal-transition').wait_for(state='detached')
                # System and app preferences both suppress the shared animation.
                await page.emulate_media(reduced_motion='reduce')
                await page.locator('#albaSymbol').click()
                await page.locator('#tramontoLink').click()
                await page.wait_for_url('**/tramonto')
                assert await page.locator('.portal-transition').count() == 0
                await page.locator('#noteEditor').wait_for(state='visible')
                await page.emulate_media(reduced_motion='no-preference')
                await page.evaluate("localStorage.setItem('alba.motion','off')")
                if await page.locator('[data-portal-trigger]').get_attribute('aria-expanded')!='true':
                    await page.locator('[data-portal-trigger]').click()
                await page.locator('#siteMenu a[href="/"]').click()
                await page.wait_for_url(str(server.make_url('/')))
                assert await page.locator('.portal-transition').count() == 0
                await page.evaluate("localStorage.setItem('alba.motion','on')")
                await page.go_back()
                await page.locator('#noteEditor').wait_for(state='visible')
                await page.locator('.portal-transition').wait_for(state='detached')
                # Mobile dimensions, dark palette and print never leave a blocking layer.
                await page.set_viewport_size({'width':390, 'height':844})
                await page.locator('#appearanceButton').click()
                await page.locator('#notesTheme').select_option('black')
                await page.locator('#notesPalette').select_option('violet')
                await page.locator('#appearanceSettingsClose').click()
                await page.reload()
                await page.locator('.portal-transition[data-theme=black][data-palette=violet]').wait_for()
                await page.screenshot(path=str(artifacts / 'portal-tramonto-mobile.png'))
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.emulate_media(media='print')
                assert await page.locator('.portal-transition').evaluate("e => getComputedStyle(e).display") == 'none'
                await page.emulate_media(media='screen')
                await page.locator('.portal-transition').wait_for(state='detached')
                await browser.close()
        finally:
            await server.close()
            store.close()
        assert not errors, errors
    print('Portal menu/motion OK: identical menu geometry, current space, keyboard/focus, three spaces, save/failure recovery, reduced/off motion, history, mobile, print and no JS errors.')


async def live(url):
    """Read-only check of the deployed login, assets and reduced motion."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width':1440, 'height':1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = await page.goto(url)
        assert response.status == 200
        await page.locator('#login').wait_for(state='visible')
        # Freeze a representative frame for visual review of the real deployment.
        await page.evaluate("""() => document.querySelector('.portal-transition')?.getAnimations({subtree:true}).forEach(a => {a.pause(); a.currentTime = 300;})""")
        await page.screenshot(path=str(ROOT / 'artifacts' / 'portal-live-alba.png'))
        await page.locator('.portal-transition').wait_for(state='detached')
        await page.locator('[data-portal-trigger]').click()
        assert await page.locator('#siteMenu a[aria-current=page]').get_attribute('href') == '/'
        assert not await page.locator('#tramontoLink').is_visible()
        assert not await page.locator('#notteLink').is_visible()
        await page.keyboard.press('Escape')
        asset = await page.request.get(url.rstrip('/') + '/assets/portal-motion.js?v=20261004')
        assert asset.status == 200
        assert await asset.text() == (ROOT / 'portal-motion.js').read_text()
        await page.set_viewport_size({'width':390, 'height':844})
        await page.emulate_media(reduced_motion='reduce')
        await page.reload()
        await page.locator('#login').wait_for(state='visible')
        assert await page.locator('.portal-transition').count() == 0
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(ROOT / 'artifacts' / 'portal-live-mobile.png'))
        assert not errors, errors
        await browser.close()
    print('Live portal OK: HTTPS login, deployed asset matches, mobile, reduced motion, no JS errors.')


if __name__ == '__main__':
    asyncio.run(live(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--live' else main())
