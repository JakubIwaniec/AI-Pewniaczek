from football_ai.integration.flashscore_domestic_results_seed import pol_wyniki_results_url


def test_laliga_url() -> None:
    u = pol_wyniki_results_url("laliga", "2526")
    assert u.endswith("/wyniki/")
    assert "/pilka-nozna/hiszpania/laliga-2025-2026/wyniki/" == u


def test_premier_url() -> None:
    u = pol_wyniki_results_url("premier_league", "2526")
    assert "anglia/premier-league-2025-2026" in u
