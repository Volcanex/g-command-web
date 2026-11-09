from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def page():
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        yield page
        browser.close()


BOOT = '''<script>
window.BRAIN_API = '/brain';
window.g = {tidy: x => x, plain: x => x};
window.pending = {};
window.calls = [];
window.fetch = url => {
  calls.push(url);
  return new Promise(resolve => pending[url] = data => resolve({ok: true, json: async () => data}));
};
</script>'''


def test_notes_render_while_stale_is_pending(page):
    page.set_content(BOOT + (ROOT / "pages/notes/content.html").read_text())
    assert page.evaluate("calls") == ["/brain/api/notes", "/brain/api/stale"]
    page.evaluate('''pending['/brain/api/notes']({notes: [{path:'ideas/fixture', title:'Fixture note',
        kind:'idea', status:'active', version:'1.0', updated:'2026-11-09'}],
        facets:{kinds:['idea'], statuses:['active']}})''')
    page.get_by_role("link", name="Fixture note", exact=True).wait_for()
    assert page.locator("[data-stale]").is_hidden()
    page.evaluate("pending['/brain/api/stale']({outstanding_detail: []})")


def test_manifest_cards_render_while_sidecars_and_gates_are_pending(page):
    page.set_content(BOOT + (ROOT / "pages/projects/content.html").read_text())
    page.evaluate("pending['/api/gcore']({manifest:{projects:[{id:'fixture', host:'h'}], services:[{repo:'fixture'}], hosts:[]}})")
    page.locator("[data-repo=fixture]").wait_for()
    assert "/api/levels/projects" in page.evaluate("calls")
    assert "/api/projects/meta" in page.evaluate("calls")
    page.evaluate("pending['/api/levels/projects']({projects:{fixture:{total:1, counts:{met:1}, blocking:{}}}})")
    page.get_by_text("1 of 1 met").wait_for()
    page.evaluate("""window.statusPaints = 0; g.status = () => statusPaints++;
        pending['/brain/api/status']({services:[{repo:'fixture',state:'up'}],dependencies:[]});""")
    page.evaluate("""pending['/api/projects/meta']({projects:{fixture:{shot:false}}});
        pending['/brain/api/nerves']({nodes:[]});
        pending['/brain/api/lineage']({nodes:[],links:[]});
""")
    page.wait_for_function("document.querySelector('[data-repo=fixture] .proj-thumb').classList.contains('noshot')")
    page.get_by_text("1 of 1 met").wait_for()
    assert page.evaluate("statusPaints") == 0
    assert page.locator("[data-health]").inner_text() == "Up"
    assert page.evaluate("calls.filter(x => x === '/brain/api/status').length") == 1
