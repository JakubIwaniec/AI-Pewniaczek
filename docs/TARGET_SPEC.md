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

## Kohorty

| Etykieta           | Wymóg                                      | Uwagi inferencji                         |
|--------------------|---------------------------------------------|------------------------------------------|
| **A (time-aware)** | `unix_kickoff` w meta (+ ewentualnie join) | split czasowy / walk-forward; anty-leak  |
| **B (RAW-only)**   | niepuste `df_*`; kickoff nieobowiązkowy     | tylko eksploracja; jawny protokół leak   |

## Replay artefaktów („przed/po’’)

Baseline **diag** i osobny plik RCA — nie kopiuj liczb między nimi bez etykiety.

| Rola | Plik wyjściowy | Ostatnio w repo (przykład) |
|------|----------------|---------------------------|
| **Regress / baseline** diag | [`integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) | `2026-05-10T12:00:47Z`, `git_rev_short=8246107`, `footballcsv_cache_fallback=true`, `-F`, `--skip-lookup-miss-sample`, seed `42`, `R=7`; `meta_fingerprint_summary.feeds_used_count=5`, `feed_note=manifest_wild=55_count=5` |
| **RCA lookup_miss** | [`integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json) | `2026-05-09T22:19:39Z`; `n=200`, bez `-F` (klasyfikacja tylko próbki); w próbce **29** wierszy `ekstraklasa-2526`, kat. `no_ordered_hit_after_pmR` (**14.5 %** próbki; populacja zbioru 142 przy 982 miss łącznie) |
| **Supplement → enrichment** | `supplement.sqlite` + [`model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json) | Build z `--footballcsv-cache-fallback`; enrichment `generated_at=2026-05-09T22:19:48Z`; [`model_input_coverage_manifest.json`](../data/integrated/model_input_coverage_manifest.json) `manifest_revision=2026-05-09c` |
| **Coverage** (RAW / kubki; nie zlewaj z enrichment) | [`coverage_latest.json`](../data/integrated/coverage_latest.json) | `generated_at=2026-05-09T22:22:45Z`; `integration_coverage.py` po supplemencie |

## Progi X / Y / N_min

Liczone z artefaktów przy **replay** wskazanym w linii „Powiązany replay’’ oraz w **tabeli Replay** powyżej.

| Cel                                            | Metryka (operacjonalna)                                                                                                    | Baseline → target                         | Powiązany replay                                                                     |
|------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|-------------------------------------------|--------------------------------------------------------------------------------------|
| Meta kickoff względem manifestu IDS            | \( \texttt{kickoff\_aggregate\_global.present\_unix\_ok} / \texttt{ids\_total\_manifest\_events} \)                         | **55.3%** → **X %**                      | regress: [`integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) (wiersz 1 tabeli) |
| Supplement / join w scope „z meta’’            | \( \texttt{join\_would\_succeed\_count} / (\texttt{ids\_in\_join\_scope} - \texttt{skipped\_no\_meta}) \)                    | **1.70%** (17 / 999) → **Y %**           | jak meta + supplement z `footballcsv_cache_fallback=true`                              |
| Kanały enrichment (SQLite / coverage manifest) | `enrichment_join_hit_count` vs `event_total` w [`model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json) | **34 / 12141** (~0.28%) → **≥ N_min hit** | ostatni wiersz tabeli **Replay artefaktów** oraz dopasowany `supplement.sqlite` |

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
| laliga-2526           | 176 (100%)             | 176            | 0                               | czysty botleneck meta vs feed mega-list |
| premier_league-2526   | 168 (100%)             | 168            | 0                               | idem                                     |
| serie_a-2526          | 168 (100%)             | 168            | 0                               | idem                                     |
| liga_portugal-2526    | 154 (100%)             | 154            | 0                               | idem                                     |
| bundesliga-2526       | 149 (100%)             | 149            | 0                               | idem                                     |
| jupiler_league-2526   | 141 (100%)             | 141            | 0                               | idem                                     |
| eredivisie-2526       | 136 (100%)             | 136            | 0                               | idem                                     |
| super_league-2526     | 136 (100%)             | 136            | 0                               | idem                                     |
| ligue_1-2526          | 134 (100%)             | 134            | 0                               | idem                                     |
| super_lig-2526        | 132 (100%)             | 132            | 0                               | idem                                     |
| chance_liga-2526      | 124 (100%)             | 124            | 0                               | **Nie mieszać** kodu **`C1` MMZ** z pucharem — CLI mapuje **`CZE1` → „Czech Chance Liga’’** (`src/football_ai/cli.py`) |
| jupiler_league-2223   | 109 (100%)             | 109            | 0                               | sezonowy priorytet po sezonowych MAX z 2526 |

Źródło liczb: klucze `skipped_no_meta_by_dataset`, `lookup_miss_category_histogram_by_dataset` w diag (patrz ścieżka poniżej). Aktualny manifest feedów dla kolejności overlapu: [`data/integrated/flashscore_list_feed_manifest.json`](../data/integrated/flashscore_list_feed_manifest.json); augmentation seedów: [`flashscore_integration_feeds.py`](../src/football_ai/integration/flashscore_integration_feeds.py) (`seed_augment_html_paths`).

**Gate RAW (wdrożenie planu — jedna próba przy obecnym snapshotcie):** regress `integration_diag_latest.json` jak w tabeli **Replay**; dla `laliga-2526` próbka 24 × `event_id` z pola `skipped_no_meta_event_id_sample_by_dataset`: **0/24** występuje literalnie w plikach `data/raw/flashscore/feeds/**/*.txt` (brak wpisów mega-list przy tych ID). **Interpretacja wg planu:** skłania to ku zmianie **zakresu/priorytetu feedów / slice / seed**, a nie kolejnemu pobraniu tych samych URL bez zmiany; po zmianie — ponownie `download_flashscore_integration_feeds` → diag → pomiar.

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

---

## Decyzje otwarte (produkt / manifest)

Blokują **~47 %** `ids_never_attempted_join` i kubki przy sezonach 2223+ — sam supplement lub ponowny download kubkowy **bez zmian zakresu** nie zamyka problemu.

### Szablon zamknięcia (uzupełnij po przeglądzie — owner + data replay)

Po ustaleniu opcji wpisz konkret oraz **snapshot IDS** przy wyborze B („pełny freeze’’ do porównań bez sztucznego podniesienia metryki).

| Decyzja | Wybrane A/B/C lub linia kubków | Owner | Data | Freeze IDS (# commit / hash / lista) |
|---------|---------------------------------|-------|------|----------------------------------------|
| `unsupported_league_key` | | | | |
| FA / Carabao 2223+ | | | | |

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
- Diag JSON (schema `"4"`): [`data/integrated/integration_diag_latest.json`](../data/integrated/integration_diag_latest.json) (`baseline_bottleneck_hint`, `skipped_no_meta_by_dataset`, `skipped_no_meta_event_id_sample_by_dataset`, …)
- RCA próbki `lookup_miss` (osobny plik, bez nadpisywania baseline): [`data/integrated/integration_diag_rca_lookup_miss.json`](../data/integrated/integration_diag_rca_lookup_miss.json)
- Coverage: [`data/integrated/model_input_coverage_latest.json`](../data/integrated/model_input_coverage_latest.json)
- KPI RAW/kubki (różny od enrichment): [`data/integrated/coverage_latest.json`](../data/integrated/coverage_latest.json)
