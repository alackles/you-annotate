from pathlib import Path

from app.importer import build_chapters, plain_text, split_chapters, utf16_len, utf16_slice

SAMPLE = (Path(__file__).parent.parent / "fixtures" / "sample.md").read_text()


def test_splits_on_top_level_headings_with_front_matter():
    chapters = split_chapters(SAMPLE)
    assert [title for title, _ in chapters] == ["Front matter", "Chapter I.", "Chapter II."]
    assert chapters[1][1].startswith("The author's account")


def test_no_front_matter_chapter_when_file_starts_with_heading():
    chapters = split_chapters("# One\n\nText.\n\n## Not a chapter\n\nMore.\n\n# Two\n\nEnd.")
    assert [title for title, _ in chapters] == ["One", "Two"]


def test_headingless_file_is_one_chapter():
    assert split_chapters("Just a paragraph.\n\nAnd another.") == [
        ("Front matter", "Just a paragraph.\n\nAnd another.")
    ]


def test_plain_text_matches_textcontent_rules():
    # Entities decode, tags vanish, whitespace between blocks is kept (as in the DOM).
    html = "<p>Fish &amp; <em>chips</em></p>\n<p>x&nbsp;y</p><!-- note -->"
    assert plain_text(html) == "Fish & chips\nx y"


def test_built_chapter_plain_is_text_of_html():
    ch = build_chapters(SAMPLE)[1]
    assert "<em>industrious</em>" in ch["html"]
    assert "*" not in ch["plain"] and "industrious beyond" in ch["plain"]


def test_utf16_offsets_count_astral_chars_as_two():
    s = "a\U0001F41Fb"  # fish emoji is two UTF-16 units, as in JS
    assert utf16_len(s) == 4
    assert utf16_slice(s, 1, 3) == "\U0001F41F"
    assert utf16_slice(s, 3, 4) == "b"
    assert utf16_slice(s, 1, 2) is None  # splits the surrogate pair
