## Football AI – data pipeline (MVP)

Ten projekt pobiera i wersjonuje **surowe (RAW)** dane piłkarskie (wyniki/terminarz/statystyki/składy) do dalszego feature engineering i trenowania modeli.

### Struktura
- `data/raw/` – surowe odpowiedzi/HTML/CSV (cache, możliwość wznowienia)
- `data/football_ai.sqlite` – metadane pobrań (co, kiedy, z jakiego URL, hash, status)
- `src/football_ai/` – kod ETL/CLI

### FA Cup i EFL Cup (jalapic / engsoccerdata)

CSV z repozytorium [jalapic/engsoccerdata](https://github.com/jalapic/engsoccerdata) (katalog upstream: `data-raw/`) są używane do joinu **FA Cup** i **Carabao (League Cup)** w supplement oraz w `integration_diag`. Licencja upstream: **CC BY 4.0** — przy publikacji pochodnych zachowaj atrybucję „James Curley / engsoccerdata”.

Pobranie lub **świeże odświeżenie** (z korzenia repo):

```bash
python scripts/download_engsoccerdata_cups.py --force
```

**Dlaczego `--force`:** skrypt korzysta z cache w SQLite (`raw_artifacts`). Przy stałym URL (`ref` domyślnie `master`) ten sam rekord oznacza *skip bez HTTP*. Zawartość na GitHubie pod `master` może się zmieniać — **bez `--force`** możesz zostać przy **starym** pliku na dysku. Pierwszy raz wystarczy uruchomienie bez `--force`; po zmianach upstream użyj `--force`.

Dodatkowe flagi:

- `--ref <branch|tag|sha>` — np. pin commita zamiast `master`
- `--min-delay SEKUNDY` — minimalny odstęp między żądaniami HTTP (domyślnie co najmniej 1.25)
- `--include-test` — dołącza dodatkowy plik pomocniczy `leagucuptest.csv`

Pliki lądują w `data/raw/engsoccerdata/cups/` (`facup.csv`, `leaguecup.csv`). Szczegóły źródeł i decyzji integracyjnych: [`data/integrated/FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt`](data/integrated/FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt).

**Granica upstream:** jeśli `facup.csv` / `leaguecup.csv` na wybranym `ref` **nie zawierają** sezonów wymaganych przez manifest, pełnego joinu nadal nie będzie — to wtedy kwestia **danych źródłowych** lub **MMZ overlay** / fork, nie samego narzędzia pobierania.

#### Szybki sanity check po pobraniu

Ostatnia sensowna data i sezon końcówki pliku (PowerShell lub bash, z korzenia repo):

```bash
python -c "import csv;from pathlib import Path;p=Path('data/raw/engsoccerdata/cups/facup.csv');r=[x for x in csv.DictReader(p.open(encoding='utf-8-sig')) if (x.get('Date') or '').strip().upper() not in ('','NA')];print('facup dated rows',len(r),'last',(r[-1].get('Date'),r[-1].get('Season')) if r else None)"
python -c "import csv;from pathlib import Path;p=Path('data/raw/engsoccerdata/cups/leaguecup.csv');r=[x for x in csv.DictReader(p.open(encoding='utf-8-sig')) if (x.get('Date') or '').strip().upper() not in ('','NA')];print('leaguecup dated rows',len(r),'last',(r[-1].get('Date'),r[-1].get('Season')) if r else None)"
```

*(Ścieżka katalogu: `engsoccerdata` — trzymaj się dokładnego zapisu w `data/raw/`.)*

Opcjonalnie potem uruchom `python scripts/integration_diag.py` lub `python scripts/build_integration_supplement.py` — komunikaty „jalapic cup index empty” ustąpią dopiero przy **faktycznie dopasowanych** sezonach w CSV.

**Luki meta / join:** po wygenerowaniu `data/integrated/integration_diag_latest.json` możesz uruchomić `python scripts/integration_gap_review.py` (streszczenie Tier‑1, `never_attempt_join`, lookup_miss). Szerszy protokół: [`docs/DATA_GAP_PROTOCOL.md`](docs/DATA_GAP_PROTOCOL.md).

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

