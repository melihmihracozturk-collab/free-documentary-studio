import pytest

from fds_worker.licenses import allowed, classify


@pytest.mark.parametrize("texts,expected", [
    (("Public domain",), "pd"),
    (("PD-old-100",), "pd"),
    (("https://creativecommons.org/publicdomain/mark/1.0/",), "pd"),
    (("CC0",), "cc0"),
    (("https://creativecommons.org/publicdomain/zero/1.0/",), "cc0"),
    (("CC BY 4.0",), "by"),
    (("cc-by-2.0",), "by"),
    (("https://creativecommons.org/licenses/by/2.0/",), "by"),
    (("CC BY-SA 3.0",), "by-sa"),
    (("cc-by-sa-4.0",), "by-sa"),
    (("Attribution-ShareAlike 4.0 International",), "by-sa"),
    (("CC BY-NC 2.0",), "nc"),
    (("cc by-nc-sa 2.0",), "nc"),
    (("CC BY-NC-ND 4.0",), "nd"),                                   # en kısıtlayıcı: ND
    (("CC BY-ND 2.0",), "nd"),
    (("https://creativecommons.org/licenses/by-nc-nd/2.0/",), "nd"),
    (("All rights reserved",), "unknown"),
    (("",), "unknown"),
    ((None, None), "unknown"),
    (("Copyrighted free use",), "unknown"),                         # belirsiz → ret
])
def test_classify(texts, expected):
    assert classify(*texts) == expected


def test_policy_defaults():
    assert allowed("pd")[0] and allowed("cc0")[0] and allowed("by")[0]
    assert allowed("by-sa")[0]
    assert not allowed("by-sa", allow_sa=False)[0]
    assert not allowed("nc")[0]                                     # varsayılan: NC kapalı
    assert allowed("nc", allow_nc=True)[0]
    assert not allowed("nd", allow_nc=True)[0]                      # ND her zaman ret
    assert not allowed("unknown")[0]
