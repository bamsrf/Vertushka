"""Классификация типа релиза — регресс-набор на реальные строки дампа.

Каждый кейс ниже — либо форма из топ-45 `format_type` прода, либо конкретный
релиз, который течёт в чужой фильтр. Правила менять можно, эти ожидания — нет.
"""
import pytest

from app.services.release_type import (
    ALBUM,
    COMPILATION,
    EP,
    OTHER,
    SINGLE,
    classify_format,
    classify_group,
)


@pytest.mark.parametrize(
    "fmt,expected",
    [
        # Явные типовые дескрипторы.
        ("CD, Album", ALBUM),
        ("Vinyl, LP", ALBUM),
        ("Cassette, Album", ALBUM),
        ("CD, Single", SINGLE),
        ("CD, Maxi-Single", SINGLE),
        ("CD, EP", EP),
        ("CD, Compilation", COMPILATION),
        # Mini-Album — это EP. Подстрока «album» уводила его в альбомы
        # (радиохедовский «Airbag / How Am I Driving?»).
        ("CD, Mini-Album", EP),
        # Голый «Mini» — 3" CD, носитель. По нему синглы Queen шли как EP.
        ("CD, Mini", None),
        # «Single Sided» — односторонняя кассета, носитель, а не сингл.
        ("Cassette, Single Sided", None),
        # Носитель без типа.
        ('Vinyl, 7"', SINGLE),
        ('Vinyl, 12"', SINGLE),
        ("Shellac, 10\"", SINGLE),
        # Служебное — не релиз артиста.
        ("CD, Transcription", OTHER),
        ("CD, Sampler", OTHER),
        ("CDr, Advance", OTHER),
        ("CD, Promo", OTHER),
        ("CDr, Mixtape", OTHER),
        ("CD, CD-ROM", OTHER),
        ('Floppy Disk, 3.5"', OTHER),
        # Видео. DVD-Audio — музыка, не видео.
        ("DVD, DVD-Video", OTHER),
        ("VHS, PAL", OTHER),
        ("UMD, Stereo", OTHER),
        ("Betacam SP, NTSC", OTHER),
        ("DVD, Album", ALBUM),
        # Нет доказательств — ни типа, ни служебной пометки.
        ("CD", None),
        ("Cassette", None),
        ("CD, Reissue", None),
        ("File, MP3", None),
        ("CD, Stereo", None),
        ("CDr, Mixed", None),
        (None, None),
        ("", None),
        # Полные описания из дампа (то, ради чего делался ре-ингест).
        # В усечённом виде это были 'Vinyl, 12"' → сингл и 'CD, Compilation'.
        ('Vinyl, 12", 33 ⅓ RPM, EP', EP),
        ('Vinyl, 12", 45 RPM, Sampler', OTHER),
        ("Vinyl, LP, Compilation, Album", COMPILATION),
        ("Vinyl, LP, Transcription", OTHER),
        ("CD, Sampler, Promo, Compilation", OTHER),
        # «Mixed» — способ подачи, не мусор: микс-сборник остаётся сборником,
        # а альбом с «Partially Mixed» — альбомом.
        ("CD, Compilation, Mixed", COMPILATION),
        ("CD, Album, Partially Mixed, Reissue", ALBUM),
    ],
)
def test_classify_format(fmt, expected):
    assert classify_format(fmt) == expected


def test_group_album_wins_by_plurality():
    """Флагманский альбом: Album-изданий большинство, промо не мешает."""
    assert classify_group([
        "CD, Album", "CDr, Promo", "Cassette, Album",
        "File, AAC", "File, FLAC", "Vinyl, LP",
    ]) == ALBUM


def test_group_ep_beats_single_lp_pressing():
    """«My Iron Lung» — EP с LP-изданием. bool_or давал album."""
    assert classify_group([
        "CD, EP", "CD, Single", "CDr, Test Pressing",
        "Cassette, EP", 'Vinyl, 12"', "Vinyl, EP", "Vinyl, LP",
    ]) == EP


def test_group_single_beats_mini_album():
    """«No Surprises / Running From Demons» — сингл, не альбом."""
    assert classify_group([
        "CD, Maxi-Single", "CD, Mini-Album", "CD, Promo",
        "CD, Single", "Cassette, Single",
    ]) == SINGLE


def test_group_mini_cd_single_stays_single():
    """«Bohemian Rhapsody»: 3"CD-издание не должно делать из сингла EP."""
    assert classify_group([
        'Acetate, 7"', "CD, Mini", "CD, Single", "Cassette, Single",
        "File, AAC", 'Vinyl, 12"', 'Vinyl, 7"',
    ]) == SINGLE


def test_group_ep_wins_tie_against_single():
    """«Queen's First E.P.» — по одному EP- и сингл-изданию, побеждает EP."""
    assert classify_group(["CD, EP", "CD, Mini", 'Vinyl, 7"']) == EP


def test_group_compilation_beats_album_on_tie():
    """«Curtain Call: The Hits» — сборник, при ничьей выигрывает он."""
    assert classify_group([
        "CD, Album", "CD, Compilation", "Cassette, Compilation",
        "File, AAC", "Vinyl, LP",
    ]) == COMPILATION


def test_group_all_service_is_other():
    """Тур-DVD целиком: ни одного музыкального издания."""
    assert classify_group([
        "DVD", "DVD, DVD-Video", "DVD, Enhanced", "DVD, NTSC", "UMD",
    ]) == OTHER


def test_group_unknown_is_other_not_album():
    """Интервью-диск без дескрипторов. Дефолт "album" и был мешаниной."""
    assert classify_group(["CD", "CD, Limited Edition"]) == OTHER


def test_group_digital_only_is_single():
    """Цифра без Album-пометки — почти всегда сингл; в «Другое» не прячем."""
    assert classify_group(["File, MP3", "File, FLAC"]) == SINGLE


def test_group_digital_with_vinyl_album():
    assert classify_group(["File, AAC", "Vinyl, LP"]) == ALBUM


def test_group_empty_is_other():
    assert classify_group([]) == OTHER
    assert classify_group([None]) == OTHER
