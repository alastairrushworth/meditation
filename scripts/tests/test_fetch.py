"""Episode-URL resolution is where the old generator sent readers to homepages."""

from fetch import _canonical_url, _is_episode_specific, _pick_audio, _record_id


def test_a_bare_homepage_is_not_an_episode_link():
    assert not _is_episode_specific("https://jackkornfield.com/", "https://jackkornfield.com/")
    assert not _is_episode_specific("https://www.tarabrach.com", "https://www.tarabrach.com/")
    assert not _is_episode_specific("", "https://x.com/")
    assert not _is_episode_specific("gid://art19-episode-locator/V0/abc", "https://x.com/")


def test_a_real_episode_page_is_kept():
    assert _is_episode_specific("https://www.tarabrach.com/meditation-being-here/",
                                "https://www.tarabrach.com/")


def test_canonical_url_ignores_scheme_host_case_and_trailing_slash():
    assert _canonical_url("http://WWW.Example.com/a/") == _canonical_url("https://example.com/a")


def test_the_same_episode_from_two_feeds_gets_one_id():
    # Dharma Seed's master feed and the centre's own feed carry the same talk.
    a = _record_id("https://dharmaseed.org/talks/97701/", "https://cdn/a.mp3", "g1", "T")
    b = _record_id("https://dharmaseed.org/talks/97701", "https://cdn/b.mp3", "g2", "T")
    assert a == b


def test_audio_falls_back_to_a_file_extension_when_the_mime_type_is_missing():
    entry = {"enclosures": [{"href": "https://cdn/x.mp3", "type": "", "length": "123"}]}
    assert _pick_audio(entry) == ("https://cdn/x.mp3", "audio/mpeg", 123)


def test_non_audio_enclosures_are_ignored():
    entry = {"enclosures": [{"href": "https://cdn/cover.jpg", "type": "image/jpeg"}]}
    assert _pick_audio(entry) == ("", "", None)
