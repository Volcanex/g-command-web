"""compile.py stamps the shell's own assets so a deploy is never hidden by cache."""
import compile as c


def test_stamps_existing_assets_and_changes_with_content(tmp_path, monkeypatch):
    (tmp_path / "css").mkdir()
    css = tmp_path / "css" / "a.css"
    css.write_text("x")
    monkeypatch.setattr(c, "STATIC_SRC", tmp_path)
    shell = '<link href="/css/a.css"><script src="/js/missing.js"></script>'
    first = c.stamp_shell_assets(shell)
    assert "/css/a.css?v=" in first
    assert 'src="/js/missing.js"' in first  # absent file left alone
    css.write_text("y")
    assert c.stamp_shell_assets(shell) != first


def test_leaves_font_preloads_unstamped(tmp_path, monkeypatch):
    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "f.woff2").write_bytes(b"f")
    monkeypatch.setattr(c, "STATIC_SRC", tmp_path)
    shell = '<link rel="preload" href="/css/f.woff2">'
    assert c.stamp_shell_assets(shell) == shell
