## Football AI – data pipeline (MVP)

Ten projekt pobiera i wersjonuje **surowe (RAW)** dane piłkarskie (wyniki/terminarz/statystyki/składy) do dalszego feature engineering i trenowania modeli.

### Struktura
- `data/raw/` – surowe odpowiedzi/HTML/CSV (cache, możliwość wznowienia)
- `data/football_ai.sqlite` – metadane pobrań (co, kiedy, z jakiego URL, hash, status)
- `src/football_ai/` – kod ETL/CLI

### Szybki start (Windows / PowerShell)
Utwórz środowisko i zainstaluj zależności:

```bash
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Uruchom CLI:

```bash
python -m football_ai --help
```

### Uwaga dot. Flashscore
Flashscore może stosować zabezpieczenia anty-bot. Kod jest przygotowany pod cache, retry i wznawianie, ale scraper może wymagać dopracowania (np. Playwright) zależnie od zmian na stronie.

