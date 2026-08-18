"""Недельный дайджест: аналоги считаются отдельно от точных совпадений.

Смешать их в одну цифру — значит обещать «твою пластинку» там, где в наличии
чужой прессинг. В ленте они тоже разведены на две свёртки (buildDigest в
Mobile/app/notifications.tsx), push обязан отражать то же деление.
"""
from app.services import push_copy


def test_only_exact_matches_keeps_original_wording():
    title, body = push_copy.weekly_digest(count=5, artists=["Miles Davis"])
    assert title == "За неделю: 5 пластинок из вишлиста"
    assert body == "Miles Davis"


def test_alt_count_is_appended_not_merged():
    title, body = push_copy.weekly_digest(
        count=3, artists=["Radiohead", "Beastie Boys"], alt_count=4
    )
    # Точная цифра в title не раздувается аналогами
    assert title == "За неделю: 3 пластинки из вишлиста"
    assert body.startswith("и ещё 4 других издания")
    assert "Radiohead, Beastie Boys" in body


def test_alt_only_does_not_claim_wishlist_match():
    title, body = push_copy.weekly_digest(count=0, artists=["The White Stripes"], alt_count=2)
    assert title == "За неделю: 2 других издания"
    assert "из вишлиста" not in title
    assert body == "The White Stripes"


def test_body_never_empty_without_artists():
    _, body = push_copy.weekly_digest(count=2, artists=[])
    assert body
    _, alt_body = push_copy.weekly_digest(count=0, artists=[], alt_count=1)
    assert alt_body


def test_editions_plural_forms():
    assert push_copy.plural_editions(1) == "другое издание"
    assert push_copy.plural_editions(3) == "других издания"
    assert push_copy.plural_editions(5) == "других изданий"
    assert push_copy.plural_editions(11) == "других изданий"
    assert push_copy.plural_editions(21) == "другое издание"
