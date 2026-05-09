from football_ai.integration.flashscore_uefa_results_seed import (
    pol_wyniki_results_url,
    season_folder4_to_url_segment,
)


def test_season_segment() -> None:
    assert season_folder4_to_url_segment("2223") == "2022-2023"
    assert season_folder4_to_url_segment("2526") == "2025-2026"


def test_lm_url() -> None:
    u = pol_wyniki_results_url("liga_mistrzow", "2526")
    assert u.endswith("/wyniki/")
    assert "liga-mistrzow-2025-2026" in u


def test_conf_typo_slug() -> None:
    u = pol_wyniki_results_url("liga_konferencji", "2425")
    assert "liga-konfetrencji-2024-2025" in u
