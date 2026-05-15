# TARGET_SPEC — model / macierz cech

Dokument sterujący gate przed pierwszym automatycznym buildem macierzy treningowej (wg planu „Uwolnienie bottlenecks danych’’). Szczegóły operacyjne epików: [DATA_GAP_PROTOCOL.md](DATA_GAP_PROTOCOL.md).


## Właściciel i aktualizacja

- **Owner:** _wpisać_
- **Deadline decyzji progów:** _data_
- Przy benchmarku **„przed/po’’** utrzymuj **tę samą** wartość `options.footballcsv_cache_fallback` w diag ( oraz tę samą flagę przy `build_integration_supplement` ) — zmiana lustra fałszuje porównanie `join_would_succeed_count` bez jawnego eksperymentu (patrz [DATA_GAP_PROTOCOL.md](DATA_GAP_PROTOCOL.md)).

Powtórzenia produkcyjne:

- Baseline regressji (histogram populacji lookup_miss):  
  `python scripts/integration_diag.py -F --skip-lookup-miss-sample --footballcsv-cache-fallback`
- RCA `lookup_miss` (próbka + `lookup_miss_diagnosis_sample`, **osobny plik** żeby nie nadpisać baseline):  
  `python scripts/integration_diag.py --footballcsv-cache-fallback -n 200 --output data/integrated/integration_diag_rca_lookup_miss.json`
- Po zmianie danych/meta:  
  `python scripts/build_integration_supplement.py --footballcsv-cache-fallback` →  
  `python scripts/model_input_coverage.py` oraz `python scripts/integration_coverage.py` → [`coverage_latest.json`](../data/integrated/coverage_latest.json)
- **Klon / CI (RAW):** `data/raw/` poza Gitem — przed testami zależnych od feedów: `python scripts/download_flashscore_integration_feeds.py`; przy lukach meta Tier‑1 (IDS ⊄ mega-list): `python scripts/download_flashscore_domestic_results_seeds.py` (szczegóły: [DATA_GAP_PROTOCOL.md](DATA_GAP_PROTOCOL.md) § Utrzymanie).

## Kohorty

| Etykieta           | Wymóg                                      | Uwagi inferencji                         |
|--------------------|---------------------------------------------|------------------------------------------|
| **A (time-aware)** | `unix_kickoff` w meta (+ ewentualnie join) | split czasowy / walk-forward; anty-leak  |
| **B (RAW-only)**   | niepuste `df_*`; kickoff nieobowiązkowy     | tylko eksploracja; jawny protokół leak   |

## Replay artefaktów („przed/po’’)

Baseline **diag** i osobny plik RCA — nie kopiuj liczb między nimi bez etykiety.

| Rola | Plik wyjściowy | Ostatnio w repo (przykład) |
|------|----------------|---------------------------|
| **Regress / baseline** diag | [`integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) | `generated_at=2026-05-15T19:00:14Z`, `footballcsv_cache_fallback=true`, `-F`, `--skip-lookup-miss-sample`; `feeds_used_count=6`, `augment_seed_count=7985`, `meta_index_size=9891`; `skipped_no_meta=4153`, `join_would_succeed=535`, `skipped_no_row=1736` (po domestic `/wyniki/` seeds 2526 — patrz Tier‑1) |
| **RCA lookup_miss** | [`integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json) | `generated_at=2026-05-15T19:02:42Z`; `n=200`, bez `-F`; próbka `hist_sample`: `csv_index_empty=97`, `no_ordered_hit_after_pmR=103` |
| **Supplement → enrichment** | `supplement.sqlite` + [`model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json) | Build z `--footballcsv-cache-fallback` (**2026-05-15**); `generated_at=2026-05-15T19:02:34Z`; `enrichment_join_hit_count=535` (~4.41% manifestu) |
| **Coverage** (RAW / kubki; nie zlewaj z enrichment) | [`coverage_latest.json`](../data/integrated/coverage_latest.json) | `generated_at=2026-05-15` (sesja po domestic seeds + supplemencie) |

## Progi X / Y / N_min

Liczone z artefaktów przy **replay** wskazanym w linii „Powiązany replay’’ oraz w **tabeli Replay** powyżej.

| Cel                                            | Metryka (operacjonalna)                                                                                                    | Baseline → target                         | Powiązany replay                                                                     |
|------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|-------------------------------------------|--------------------------------------------------------------------------------------|
| Meta kickoff względem manifestu IDS            | \( \texttt{kickoff\_aggregate\_global.present\_unix\_ok} / \texttt{ids\_total\_manifest\_events} \)                         | **55.3%** → **65.9%** (7988/12141, po domestic seeds) → **X %** | regress: [`integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) (wiersz 1 tabeli) |
| Supplement / join w scope „z meta’’            | \( \texttt{join\_would\_succeed\_count} / (\texttt{ids\_in\_join\_scope} - \texttt{skipped\_no\_meta}) \)                    | **1.70%** (17/999) → **23.6%** (535/2271) → **Y %** | jak meta + supplement z `footballcsv_cache_fallback=true`                              |
| Kanały enrichment (SQLite / coverage manifest) | `enrichment_join_hit_count` vs `event_total` w [`model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json) | **34** (~0.28%) → **535** (~4.41%) → **≥ N_min hit** | ostatni wiersz tabeli **Replay artefaktów** oraz dopasowany `supplement.sqlite` |

Interpretacja „join’’ w drugim wierszu: ułamek zdarzeń w join scope z **kompletną** meta (`skipped_no_meta` wyzerowane per zdarzenie), dla których można zbudować wiersz z `lookup_fd_row` przy obecnym indeksie CSV / ścieżce supplement (nie uwzględnia kolejnego etapu zapisu do SQLite ani eskalacji do mirror cache).

---

## Tier‑1 — priorytet **luka meta** (harvest AA / kolejność feedów)

**Problem:** bez wpisu `event_id` w bundlu meta nie da się zasadnie joinować ani supplementu ani diag — patrz `skipped_no_meta` oraz **`skipped_no_meta_by_dataset`** i **`skipped_no_meta_event_id_sample_by_dataset`** (ograniczona lista ID do sprawdzenia w RAW mega-liście — generuje `integration_diag`; wypisz: `python scripts/meta_gap_event_id_sample.py`) w diag (`schema_version` **„4’’**).

**Przed kolejną zmianą kolejności feedów lub ponownym pobraniem tych samych URL-i:** zweryfikuj w RAW (`data/raw/flashscore/feeds/*.txt`), czy próbkowany brakujący `event_id` z wybranego `dataset_label` **w ogóle występuje** w którymś z plików mega-list / slice. Jeśli nie — kolejny krok to **inny feed**, **[`slice_flashscore_list_feed.py`](../scripts/slice_flashscore_list_feed.py)** z trafnym `--contains …`, lub rozszerzenie seedów HTML — nie identyczny `download_*` bez nowej ścieżki danych.

**Reguły wyboru (skrócona tablica ≤ 12):**

1. Rozważamy tylko zbiory z `in_join_scope_events ≥ 50` oraz `share` braku meta **`≥ 0.2`**.
2. Sortujemy malejąco wg `missing_meta`, tie-break „alfabet `dataset_label`’’.
3. Bierzemy **12 pierwszych** wierszy.

| `dataset_label`        | missing_meta (`share`) | N w join scope | Σ lookup_miss (populacja, `-F`) | Uwagi |
|------------------------|------------------------|----------------|----------------------------------|-------|
| laliga-2526           | 50 (28.4%)             | 176            | 86                              | po domestic `laliga_2526_wyniki.html`: meta z `/wyniki/` (~126/176 IDS w seedzie); reszta → CSV join |
| premier_league-2526   | 12 (7.1%)              | 168            | 56                              | `premier_league_2526_wyniki.html` |
| serie_a-2526          | 18 (10.7%)             | 168            | 50                              | `serie_a_2526_wyniki.html` |
| liga_portugal-2526    | 0 (0%)                 | 154            | 58                              | meta OK; dominuje `no_ordered_hit_after_pmR` |
| bundesliga-2526       | 33 (22.1%)             | 149            | 116                             | `bundesliga_2526_wyniki.html` |
| jupiler_league-2526   | 49 (34.8%)             | 141            | 92                              | `jupiler_league_2526_wyniki.html` |
| eredivisie-2526       | 72 (52.9%)             | 136            | 64                              | `eredivisie_2526_wyniki.html` |
| super_league-2526     | 66 (48.5%)             | 136            | 70                              | `super_league_2526_wyniki.html` |
| ligue_1-2526          | 94 (70.1%)             | 134            | 40                              | `ligue_1_2526_wyniki.html` |
| super_lig-2526        | 94 (71.2%)             | 132            | 38                              | `super_lig_2526_wyniki.html` |
| chance_liga-2526      | 40 (32.3%)             | 124            | 84                              | `chance_liga_2526_wyniki.html`; **nie mieszać `C1` MMZ z pucharem** |
| jupiler_league-2223   | 109 (100%)             | 109            | 0                               | starsze sezony: brak seedów 2223–2425 w tej iteracji |

Źródło liczb: klucze `skipped_no_meta_by_dataset`, `lookup_miss_category_histogram_by_dataset` w diag (patrz ścieżka poniżej). Aktualny manifest feedów dla kolejności overlapu: [`data/integrated/flashscore_list_feed_manifest.json`](../data/integrated/flashscore_list_feed_manifest.json); augmentation seedów: [`flashscore_integration_feeds.py`](../src/football_ai/integration/flashscore_integration_feeds.py) (`seed_augment_html_paths`).

**Gate RAW:** po dodaniu **`f_1_-1_5_pl_1`** (`download_flashscore_integration_feeds` → diag) ta sama próbka 24 × `event_id` z `skipped_no_meta_event_id_sample_by_dataset["laliga-2526"]` nadal daje **0/24** literalnych trafień w `data/raw/flashscore/feeds/**/*.txt` — to są **nadal** brakujące wobec bundla ID; równolegle globalnie `skipped_no_meta` spadło (**5425 → 5387**), a dla `laliga-2526` brak meta **171/176** (~97%, wcześniej 100%). Wariant `f_1_-1_X` z `X∈{0,1,2,3}` na `flashscore.pl` **nie** obejmował ścieżki `/hiszpania/laliga/` (tylko m.in. Tercera RFEF); `f_1_-1_5_pl_1` zawiera sekcję LaLiga.

**Preflight ROI (`f_1_-1_6` / `f_1_-1_7`, 2026-05-10):** delta parsowanych ID **bez przecięcia** z `laliga_2526.txt` / `premier_league_2526.txt`; merge `_7` nie zmienił `skipped_no_meta` — **odrzucono**.

**Iteracja Tier‑1 (2026-05-15) — domestic `/wyniki/` HTML:** [`download_flashscore_domestic_results_seeds.py`](../scripts/download_flashscore_domestic_results_seeds.py) → `data/raw/flashscore/seed_results/{league}_2526_wyniki.html` (augmentacja przez `seed_augment_html_paths`, jak UEFA). Preflight `laliga_2526`: w `f_1_-1_5_pl_1` tylko **5/176** IDS w bloku ZA; strona `/wyniki/` daje **~126/176** `~AA÷` vs IDS. **Efekt globalny:** `skipped_no_meta` **5387 → 4153** (−1234), `join_would_succeed` **17 → 535**, `augment_seed_count` **7985**. **Slice** z pliku już w unii **nie** dodaje nowych ID (tylko podzbiór tego samego źródła). Kolejne sezony 2223–2425: ten sam skrypt z `--season 2425` itd., gdy priorytet z tabeli (np. `jupiler_league-2223` 100% meta-gap).

---


## Sygnał **CSV / join** (rozłącznie od Tier‑1 meta)

Zbiorów poniżej **nie** dobiera się przez `share` braku meta (meta jest dostępna), lecz przez `lookup_miss_given_valid_unix` i histogram **`csv_index_empty`** / **`no_ordered_hit_after_pmR`**.

| `dataset_label`  | missing_meta | N scope | Σ lookup_miss | Dominująca kategoria `-F`     |
|------------------|--------------|---------|----------------|-------------------------------|
| fa_cup-2526      | 0            | 130     | 130            | `csv_index_empty` — jalapic ucięty ~2019; MMZ bez dedykowanego kodu FA w `raw/` (patrz notatki overlay). |
| fa_cup-2425      | 0            | 123     | 123            | `csv_index_empty` |
| fa_cup-2324      | 0            | 109     | 109            | `csv_index_empty` |
| fa_cup-2223      | 0            | 106     | 106            | `csv_index_empty` |
| carabao_cup-*    | 0            | 93×4    | 93 ×4          | `csv_index_empty` (każdy sezon osobno) |
| ekstraklasa-2526 | 0            | 159     | 142            | `no_ordered_hit_after_pmR` — meta OK; RCA: próbka w [`integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json) (`lookup_miss_diagnosis_sample`, m.in. 29× dla `ekstraklasa-2526`). |

Przed zmianą **kodu** join: zweryfikuj dla `lookup_miss_given_valid_unix` przy `no_ordered_hit_after_pmR`, czy wiersze CSV (POL / `norm_club`, kolejność sortu przy PM+R) oraz parametry szerokiego okna (`diagnostic_wide_radius_days`, `lookup_miss_sampling.R`) faktycznie obejmują mecz przy danym `unix_kickoff` — przeczetuj `join_detail`/ścieżkę CSV, nie kolejny identyczny download feedów bez hipotezy. Lista JSON w jednej linii: `python scripts/rca_lookup_miss_filter.py --json data/integrated/integration_diag_rca_lookup_miss.json --dataset-prefix ekstraklasa`.

**Weryfikacja P1 / Epik D (2026-05-15):** `hCODSnKa`, `rXyiNLI0` — meta w bundlu (`unix_kickoff`, drużyny); `poland_filtered_index(POL.csv, "2025/26")` + `lookup_fd_row` → **brak trafienia** (kategoria `no_ordered_hit_after_pmR`). Bottleneck: **nazwy/data w POL** vs Flashscore, nie feed list. RCA odświeżone: [`integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json) (`2026-05-15`); filtr: `python scripts/rca_lookup_miss_filter.py --dataset-prefix ekstraklasa`. Populacja `ekstraklasa-2526`: **142** × `no_ordered_hit_after_pmR` (bez zmiany kategorii po domestic seeds — meta już była).

---

## Decyzje otwarte (produkt / manifest)

Blokują **~47 %** `ids_never_attempted_join` i kubki przy sezonach 2223+ — sam supplement lub ponowny download kubkowy **bez zmian zakresu** nie zamyka problemu.

### Szablon zamknięcia (uzupełnij po przeglądzie — owner + data replay)

Po ustaleniu opcji wpisz konkret oraz **snapshot IDS** przy wyborze B („pełny freeze’’ do porównań bez sztucznego podniesienia metryki).

| Decyzja | Wybrane A/B/C lub linia kubków | Owner | Data | Freeze IDS (# commit / hash / lista) |
|---------|---------------------------------|-------|------|----------------------------------------|
| `unsupported_league_key` | **C (propozycja)** — EDA zachowane; **wyłączyć z progów join** (`ids_never_attempted_join` ~47% do czasu mapy adapterów) | _TBD_ | _TBD_ | — |
| FA / Carabao 2223+ | **Defer → B/C** — bez nowego źródła jalapic: **nie** liczyć 2223+ w gate join; osobny epik źródło lub MMZ po audycie | _TBD_ | _TBD_ | — |

**Następny krok procesowy:** krótki review (≤30 min kwartalnie): priorytetyzacja **A vs C** dla `unsupported` oraz **freeze IDS vs nowe źródło** dla FA — bez tego gate uczenia zostaje na ~47 % `never_attempt_join`.

**SSoT list IDS w diag/supplement:** `league_manifest()` w [`data_integrity_flashscore.py`](../scripts/data_integrity_flashscore.py) + **`data/event_ids/*.txt`**.

1. **`unsupported_league_key`:** **A)** rozszerzyć mapę (np. [`LEAG_KEY_TO_CLI`](../src/football_ai/integration/join_football_data.py) + CSV/adapter); **B)** zawęzić IDS przed gate uczenia; **C)** zachować dane dla EDA ale **wyłączyć z progów join** (jawna lista „out-of-gate’’).

2. **FA Cup / Carabao 2223+:** sam restart `scripts/download_engsoccerdata_cups.py` przy jalapic bez nowych sezonów **rozwiązania nie przynosi** — wybierz linię: nowe źródło wyników lub fork CSV, przycięcie manifestu IDS do sezonów obecnych w jalapic lub epik MMZ-overlay dopiero po audycie pliku (**`C1` = Czech Chance Liga w MMZ, nie FA**; [`FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt`](../data/integrated/FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt)). Nie uzupełniaj „na ślepo’’ [`football_data_manifest_mmz_overlay.json`](../data/integrated/football_data_manifest_mmz_overlay.json).

---

## MMZ overlay / puchary (status)

`football_data_manifest_mmz_overlay.json` pozostaje **puste `{}`** dopóki nie ma zweryfikowanego, spójnego kodu CSV pod **wszystkie** sezony kubka — szczegóły i **no‑go**: [`FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt`](../data/integrated/FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt).

---

## Artefakty powiązane

- Protokół operacyjny pętli „pomiar → akcja → weryfikacja’’: [`docs/DATA_GAP_PROTOCOL.md`](DATA_GAP_PROTOCOL.md); szybkie zestawienie z diag JSON: `python scripts/integration_gap_review.py`.
- Tier‑1 RAW gate (lista `event_id`): [`scripts/meta_gap_event_id_sample.py`](../scripts/meta_gap_event_id_sample.py).
- Domestic `/wyniki/` seeds (Tier‑1): [`scripts/download_flashscore_domestic_results_seeds.py`](../scripts/download_flashscore_domestic_results_seeds.py).
- Diag JSON (schema `"4"`): [`data/integrated/integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) (`baseline_bottleneck_hint`, `skipped_no_meta_by_dataset`, `skipped_no_meta_event_id_sample_by_dataset`, …)
- RCA próbki `lookup_miss` (osobny plik, bez nadpisywania baseline): [`data/integrated/integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json)
- Coverage: [`data/integrated/model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json)
- KPI RAW/kubki (różny od enrichment): [`data/integrated/coverage_latest.json`](../data/integrated/coverage_latest.json)
