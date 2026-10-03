# pdq_for_nada/data

## What this folder is

The scripts put their files here. Git ignores everything in it except this note.

| what appears here | made by | what it is |
|---|---|---|
| `movies_catalogue.csv` | `1_get_movie_catalogue.py` | Every film in the whole Trace library: id, title, TMDB id. About 9,500 lines. |
| `movies_to_include.txt` | `1_get_movie_catalogue.py` | The films you want in your index. Edit this file. One film per line. |
| `blobs/` | `2_build_index.py` | One downloaded fingerprint file per film. Kept, so a rebuild does not download again. |
| `index/` | `2_build_index.py` | Your search index, in the same layout the pod uses. Delete this folder to start again. |
| `index/index_contents.txt` | `2_build_index.py` | The films that are inside the index right now. |
| `clips/` | you, or `3_identify_clip.py` | Clips you test with. Downloads from links land here too. |
| `tests/` | `tests/check_end_to_end.py` | The film slice, the clips and the small index that test makes. Safe to delete. |
| `wrong_pdq_clips.csv` | `4_pull_wrong_pdq_clips.py` | The clips PDQ answered and a user said wrong. The work. |
| `correct_pdq_clips.csv` | `4_pull_wrong_pdq_clips.py` | The clips PDQ answered and a user said correct. The control. |
