# Internal notes

## Triplestore driver comparison

| | GraphDB | QLever |
|---|---|---|
| `load_from_file` | HTTP POST to running server immediately | stages file to `input/`, defers index build |
| `sparql_update` | HTTP POST, persisted immediately | queued pre-index, applied post-index, then `rebuild-index` to persist |
| `rewrite_repository` | DELETE + recreate repository via REST API | wipe `input/`, copy Qleverfile |
| named graphs | standard SPARQL `INTO GRAPH` at load time | `multi_input_json` `graph` key at index time |
| server lifecycle | external, unmanaged | controlled via `qlever start/stop/rebuild-index` |
| `drop_context` | `DROP GRAPH` via SPARQL | no-op (index is rebuilt from scratch) |
