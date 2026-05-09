# Protokół: identyfikacja braków i uzupełnianie (narzędzia z repo)

Operacyjna wersja planu dla zespołu: pętla **pomiar → klasyfikacja → akcja → weryfikacja**. Szybkie zestawienie z gotowego JSON: **`python scripts/integration_gap_review.py`**.

## Cel

(1) Zmierzyć luki przy obecnym manifeście, (2) przypisać wzorzec do **dominującej ścieżki naprawy** (przy przyczynach złożonych — **dwa etapy** kolejno, np. najpierw join scope / CSV, potem meta Tier‑1), (3) powtórzyć pomiar przy **niezmienionych istotnych opcjach** diag i ocenić wpływ ([`TARGET_SPEC.md`](TARGET_SPEC.md)).

---

## Etap 1 — Zbieranie sygnałów

Uruchomić z korzenia repo. W notatce lub w kolumnie „Replay’’ w TARGET_SPEC zapisać: **data wygenerowania**, **`git_rev_short`**, **`schema_version`**, **`options.footballcsv_cache_fallback`**, oraz czy był **tryb regressji** (`-F --skip-lookup-miss-sample`) czy **RCA** (diag **bez** skip próbki — wtedy dostępne `lookup_miss_diagnosis_sample`).

| Artefakt | Narzędzie | Kluczowe pola |
|----------|-----------|----------------|
| Meta / join przy CSV | [integration_diag.py](../scripts/integration_diag.py) → `integration_diag_latest.json` | `skipped_no_meta`, `skipped_no_meta_event_id_sample_by_dataset` (**próbka ID dla RAW gate**), `skipped_no_meta_by_dataset`, `ids_never_attempted_join`, `league_join_scope_table`, `kickoff_aggregate_global`; z `-F` → `lookup_miss_category_histogram_by_dataset` |
| Enrichment manifest | [model_input_coverage.py](../scripts/model_input_coverage.py) | `model_input_coverage_latest.json` — **po** świeżym [build_integration_supplement.py](../scripts/build_integration_supplement.py) |
| KPI kubków / domestic RAW | [integration_coverage.py](../scripts/integration_coverage.py) | `coverage_latest.json` — nie zlewaj automatycznie z `model_input_coverage` |
| Spójność IDS | [data_integrity_flashscore.py](../scripts/data_integrity_flashscore.py) | brak `/ puste pliki IDS` |

**Lejek „nigdy join’':** przy dużym `ids_never_attempted_join` najpierw `league_join_scope_table` + `join_detail` — **to nie Tier‑1 meta.**

### Dwa tryby `integration_diag`

| Cel | Komenda |
|-----|---------|
| Regresja / baseline | `python scripts/integration_diag.py -F --skip-lookup-miss-sample` (+ spójny `--footballcsv-cache-fallback`) |
| RCA lookup_miss | `python scripts/integration_diag.py --footballcsv-cache-fallback -n 200 --output data/integrated/integration_diag_rca_lookup_miss.json` (bez `--skip-lookup-miss-sample`; **osobny plik** chroni `integration_diag_latest.json`) |

Przy wyłącznie `--skip-lookup-miss-sample` nie oczekuj sensownego `lookup_miss_diagnosis_sample`.

### Baseline — zamroź `footballcsv_cache_fallback`

Nie przełączaj `options.footballcsv_cache_fallback` między „przed/po’’ przy porównaniu `join_would_succeed_count` bez jawnego eksperymentu.

### Tier‑1 (brak meta) — próbka `event_id` do RAW gate

Po świeżym regressie (`-F`) użyj [meta_gap_event_id_sample.py](../scripts/meta_gap_event_id_sample.py), żeby wypisać `event_id` z `skipped_no_meta_event_id_sample_by_dataset`; potem sprawdź literalnie w `data/raw/flashscore/feeds/*.txt`. Jeśli pola brak lub jest puste mimo dużego `skipped_no_meta` — uruchom ponownie najnowszy `integration_diag.py`.

---

## Etap 2 — Akcje (skrót)

- **Meta (A):** [download_flashscore_integration_feeds.py](../scripts/download_flashscore_integration_feeds.py), priorytet w [flashscore_list_feed_manifest.json](../data/integrated/flashscore_list_feed_manifest.json), [slice_flashscore_list_feed.py](../scripts/slice_flashscore_list_feed.py) (**sprawdź `priority`/`wildcard_priority`**), augmentacja HTML w [flashscore_integration_feeds.py](../src/football_ai/integration/flashscore_integration_feeds.py).
- **CSV (B):** puchary — [download_engsoccerdata_cups.py](../scripts/download_engsoccerdata_cups.py); MMZ bez ślepego overlay — [FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt](../data/integrated/FOOTBALL_DATA_MMZ_OVERLAY_NOTES.txt); ligi bez MMZ — mirror / `--footballcsv-cache-fallback` na supplemencie.
- **Enrichment vs diag (C):** patrz `join_would_succeed_count` / `skipped_no_row`; coverage po supplemencie.
- **RAW kubków (D):** [retry_cup_wyniki_backfill.py](../scripts/retry_cup_wyniki_backfill.py), [harvest_cups.py](../scripts/harvest_cups.py) — przy kubitach częściej przed / równolegle z A.

---

## Etap 3 — Weryfikacja

1. `integration_diag` (tryb zgodny z Replay).
2. `build_integration_supplement` (**ta sama** flaga `--footballcsv-cache-fallback`).
3. `model_input_coverage` po supplemencie.
4. Aktualizacja Replay w TARGET_SPEC.

---

## Ryzyka

Kolizje `event_id` między feedami („ostatni wygrywa’'); anti-bot Flashscore; puchary 2223+ wymagają nowego źródła przy stagnacji jalapic/MMZ — nie zapętlaj pobierania bez zmiany danych upstream.
