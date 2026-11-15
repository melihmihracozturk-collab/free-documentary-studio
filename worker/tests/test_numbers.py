from fds_worker import numbers as N


def test_turkish_number_words():
    assert N.extract("Milattan sonra yetmiş dokuz yılında") == {79}
    assert N.extract("bin yedi yüz altmış dört yılında İsis Tapınağı") == {1764}
    assert N.extract("en az iki yüz elli derece") == {250}
    assert N.extract("saatte bir buçuk milyon ton") == {1_500_000}
    assert N.extract("yetmiş dokuzda başladı, altmış ikideki deprem") == {79, 62}
    assert N.extract("on sekiz saat sürdü") == {18}
    assert N.extract("yirmi dört yirmi beş Ekim") == {24, 25}
    assert N.extract("takvimler bin yedi yüz altmış dördü gösterdiğinde") == {1764}
    assert N.extract("iki bin yıl önce") == {2000}
    assert N.extract("Bir şehir vardı; binalar yıkıldı, onlar kaçtı.") == set()   # 'bir' tanımlık, 'binalar'/'onlar' sayı değil


def test_digits_in_claims():
    assert N.extract("MS 62'de deprem; 1.500 kişi; 250 °C; 1,5 milyon ton; 4-6 metre") == {62, 1500, 250, 1_500_000, 4, 6}


def test_unsupported_numbers():
    claims = "C3 (5 Şubat 62) MS 62 depremi ciddi hasar verdi. C9 En az 250 °C sıcaklık."
    assert N.unsupported("Milattan sonra altmış iki yılının beş Şubat tarihinde", claims) == set()
    assert N.unsupported("Milattan sonra altmış yılının beş Şubat tarihinde", claims) == {60}
    assert N.unsupported("üç yüz derecelik sıcak", claims) == {300}
