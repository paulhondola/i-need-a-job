import pytest

from job_radar.cities import (
    DEFAULT_CITY_FILTER,
    ROMANIAN_CITIES,
    CityFilter,
    fold,
    parse_city_filter,
)


def test_fold_strips_all_romanian_diacritics_and_normalizes_whitespace():
    assert fold("  Timișoara  ") == "timisoara"
    assert fold("Timişoara") == "timisoara"
    assert fold("Târgu   Mureș") == "targu mures"
    assert fold("București,  Iași,  Brașov,  Constanța,  Ploiești,  Bacău") == (
        "bucuresti, iasi, brasov, constanta, ploiesti, bacau"
    )
    assert fold("Întorsura ĂÂÎȘŞȚŢ") == "intorsura aaisstt"


def test_parse_city_filter_defaults_to_timisoara():
    cf = parse_city_filter(None)
    assert isinstance(cf, CityFilter)
    assert cf == DEFAULT_CITY_FILTER
    assert cf.label == "Timișoara"
    assert not cf.is_all


def test_parse_city_filter_comma_separated_repeated_and_deduplicated():
    cf = parse_city_filter(["timisoara, cluj", "Cluj-Napoca", "bucharest, București"])
    assert [c.canonical for c in cf.cities] == ["Timișoara", "Cluj-Napoca", "Bucharest"]
    assert cf.label == "Timișoara, Cluj-Napoca, Bucharest"


def test_parse_city_filter_normalizes_hyphens_and_spaces_for_catalog_and_fallback():
    cf_cat = parse_city_filter(["targu-mures", "Târgu Mureș", "tg. mures"])
    assert [c.canonical for c in cf_cat.cities] == ["Târgu Mureș"]

    cf_fb = parse_city_filter(["baia-mare, baia mare", "Petroșani"])
    assert [c.canonical for c in cf_fb.cities] == ["Baia-Mare", "Petroșani"]
    assert cf_fb.cities[0].aliases == ("baia-mare",)
    assert cf_fb.cities[0].search_terms == ("Baia-Mare",)
    assert cf_fb.cities[1].aliases == ("petrosani",)
    assert cf_fb.cities[1].search_terms == ("Petrosani",)


@pytest.mark.parametrize(
    "raw", [["all"], ["Romania"], ["timisoara,all"], ["cluj", "ROMANIA"]]
)
def test_parse_city_filter_all_subsumes_individual_cities(raw):
    cf = parse_city_filter(raw)
    assert cf.is_all
    assert cf.cities == ()
    assert cf.label == "Romania"


@pytest.mark.parametrize("raw", [[""], ["   "], [", ,"], ["", "  ,  "]])
def test_parse_city_filter_rejects_blank_input(raw):
    with pytest.raises(ValueError, match="city"):
        parse_city_filter(raw)


@pytest.mark.parametrize(
    "loc",
    [
        "Timișoara",
        "Timişoara",
        "Timisoara",
        "TIMISOARA",
        "Timișoara, Timiș, Romania",
        "Romania, Timisoara",
        "Timisoara (Hybrid), RO",
        "Romania",
        " romania ",
        "Remote - Romania",
        "Romania (Remote)",
        "Remote, RO",
        "Bucharest, Romania (Remote)",
    ],
)
def test_default_filter_matches_timisoara_bare_romania_and_romania_remote(loc):
    assert DEFAULT_CITY_FILTER.matches(loc)


@pytest.mark.parametrize(
    "loc",
    [
        "Romania, Bucharest",
        "Bucharest, Romania (Hybrid)",
        "Cluj-Napoca, Romania",
        "Budapest, Hungary",
        "EMEA - Remote",
        "Remote - Europe",
        "Remote, ro",
        "",
        "   ",
    ],
)
def test_default_filter_rejects_other_cities_and_non_romania_remote(loc):
    assert not DEFAULT_CITY_FILTER.matches(loc)


def test_word_boundary_prevents_substring_collisions_and_matches_aliases():
    arad = parse_city_filter(["arad"])
    assert arad.matches("Arad, Romania")
    assert not arad.matches("Denver, Colorado")
    assert not arad.matches("Paradis, Germany")

    iasi = parse_city_filter(["iasi"])
    assert iasi.matches("Iași, Romania")
    assert not iasi.matches("Enthusiastic Team, Berlin")

    buc = parse_city_filter(["bucharest"])
    assert buc.matches("București, Sector 1, Romania")
    assert buc.matches("Bucuresti, RO")
    assert buc.matches("Bucharest, Romania")
    assert not buc.matches("Cluj-Napoca, Romania")

    cluj = parse_city_filter(["cluj"])
    assert cluj.matches("Cluj-Napoca, RO, 400002")
    assert cluj.matches("Cluj Napoca, Romania")
    assert cluj.matches("Cluj")

    tm_cj = parse_city_filter(["timisoara,cluj"])
    assert tm_cj.matches("Timisoara, RO")
    assert tm_cj.matches("Cluj-Napoca, Romania")
    assert not tm_cj.matches("Bucharest, Romania")

    fb = parse_city_filter(["baia-mare"])
    assert fb.matches("Baia Mare, Romania")
    assert fb.matches("Baia-Mare, RO")


@pytest.mark.parametrize(
    "loc",
    [
        "Romania",
        "Bucharest, Romania",
        "TIMISOARA, TM, RO, 307160",
        "Brasov, RO",
        "Remote (RO)",
        "Cluj",
        "București",
        "Târgu-Mureș",
    ],
)
def test_all_romania_matches_country_ro_code_and_catalog_cities(loc):
    cf = parse_city_filter(["all"])
    assert cf.matches(loc)


@pytest.mark.parametrize(
    "loc",
    [
        "Budapest, Hungary",
        "EMEA - Remote",
        "Pro Engineering, Berlin",
        "Remote, ro-land",
        "Denver, Colorado",
        "",
    ],
)
def test_all_romania_rejects_non_romania_locations(loc):
    cf = parse_city_filter(["all"])
    assert not cf.matches(loc)


def test_search_terms_for_specific_cities_and_all():
    assert DEFAULT_CITY_FILTER.search_terms() == ("Timisoara", "Romania")
    assert parse_city_filter(["bucharest,cluj"]).search_terms() == (
        "Bucharest",
        "Bucuresti",
        "Cluj",
        "Romania",
    )
    all_terms = parse_city_filter(["all"]).search_terms()
    assert all_terms[0] == "Romania"
    assert "Timisoara" in all_terms
    assert "Bucharest" in all_terms
    assert "Bucuresti" in all_terms
    assert "Cluj" in all_terms
    assert len(all_terms) == len(set(all_terms))
    assert len(ROMANIAN_CITIES) == 15
