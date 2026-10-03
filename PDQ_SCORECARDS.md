# The seven wrong answers, with their scorecards

*One page per clip: what the pod's rules do today, and where each case stands after my changes.*

Nada. 27 September 2026. Appendix to the weekly update.

Every printout below was made with the pod's ORIGINAL rules on my 134-film index, so this
is what production behaviour looks like on these clips. The status line above each one says
what my changed engine does differently.

## Krrish 3

Platform: tiktok. Votes: 1 wrong / 1 correct.

**Status: REMAINING. Decided by the pre-scan.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.12s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\vt_tiktok_com_ZSqbUnAX9_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'LANDSCAPE', 'SQUARE'])
[SCAN] whole-clip pre-scan HIT in 6.6s: vidx=5 frames=27 min_hamming=6 -> early accept (skipped full pass-1)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=SCAN_ACCEPT
  reached_end=True
  reason=whole-clip pre-scan HIT
  progress=180.03s / 180.03s
  decoded_frames=0 kept_frames=0 hashes=0
============================================================

Query time: 7.45s
Top candidates:
- matched= 27  avg_hamming=  6.0  offset= 1128.9s  movie=226904:Krrish 3 (tmdb=204435)

HINTS (1 movies with avg_hamming < 45):
  1. 226904:Krrish 3 (tmdb=204435)
     range=0-20  frames=27  avg_hamming=6.0

[EARLY EXIT] SCAN: whole-clip pre-scan min_hamming=6 frames=27

[ORCH] PDQ early accept -> movie_id=5 (SCAN: whole-clip pre-scan min_hamming=6 frames=27)

------------------------------------------------------------
VERDICT: 226904:Krrish 3 (tmdb=204435)
         rule: SCAN: whole-clip pre-scan min_hamming=6 frames=27
         SCAN_ACCEPT; 7.4s
```

## Smile

Platform: unknown. Votes: 1 wrong / 0 correct.

**Status: REMAINING. Decided by the probe, 3 frames agreeing at distance 22.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.00s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\www_facebook_com_share_v_1HfRzy1imt_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'SQUARE'])
[SCAN] no early-accept -> running full pass-1 (cropped)
[PROBE] likely_match=True min_neighbor_hamming=22 closest_movie=5300:Smile (tmdb=882598) closest_group=SQUARE hashes=16 elapsed=2.50s
[PROBE] P0 triggered: min_hamming=22<30 -> early exit eligible

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=EARLY_ACCEPT
  reached_end=False
  reason=P0: probe min_hamming=22 < 30
  progress=2.50s / 183.72s
  decoded_frames=21 kept_frames=8 hashes=32
============================================================

Query time: 6.87s
Top candidates:
- matched=  5  avg_hamming= 26.8  offset= 6520.0s  movie=5300:Smile (tmdb=882598)

HINTS (1 movies with avg_hamming < 45):
  1. 5300:Smile (tmdb=882598)
     range=20-35  frames=5  avg_hamming=26.8

[EARLY EXIT] P0: probe min_hamming=22 < 30

[ORCH] PDQ early accept -> movie_id=6 (P0: probe min_hamming=22 < 30)

------------------------------------------------------------
VERDICT: 5300:Smile (tmdb=882598)
         rule: P0: probe min_hamming=22 < 30
         EARLY_ACCEPT; 6.9s
```

## Captain America: Civil War

Platform: tiktok. Votes: 1 wrong / 0 correct.

**Status: REMAINING. Decided by the pre-scan on 4 frames at distance 12.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.00s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\vm_tiktok_com_ZN8Yn16tp_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'LANDSCAPE', 'SQUARE'])
[SCAN] whole-clip pre-scan HIT in 7.5s: vidx=10 frames=4 min_hamming=12 -> early accept (skipped full pass-1)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=SCAN_ACCEPT
  reached_end=True
  reason=whole-clip pre-scan HIT
  progress=36.29s / 36.29s
  decoded_frames=0 kept_frames=0 hashes=0
============================================================

Query time: 7.59s
Top candidates:
- matched=  4  avg_hamming= 12.0  offset= 5723.6s  movie=540:Captain America: Civil War (tmdb=271110)

HINTS (1 movies with avg_hamming < 45):
  1. 540:Captain America: Civil War (tmdb=271110)
     range=0-20  frames=4  avg_hamming=12.0

[EARLY EXIT] SCAN: whole-clip pre-scan min_hamming=12 frames=4

[ORCH] PDQ early accept -> movie_id=10 (SCAN: whole-clip pre-scan min_hamming=12 frames=4)

------------------------------------------------------------
VERDICT: 540:Captain America: Civil War (tmdb=271110)
         rule: SCAN: whole-clip pre-scan min_hamming=12 frames=4
         SCAN_ACCEPT; 7.6s
```

## Grave Encounters 2

Platform: tiktok. Votes: 1 wrong / 0 correct.

**Status: STOPPED by the P9E change. The engine now gives no answer here.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.00s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\vt_tiktok_com_ZSq1X4d4C_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'SQUARE'])
[SCAN] no early-accept -> running full pass-1 (cropped)
[PROBE] likely_match=False min_neighbor_hamming=62 closest_movie=186696:Yan Yana (tmdb=1546963) closest_group=SQUARE hashes=16 elapsed=2.25s
[EARLY ACCEPT] P9E: Only movie overall with avg<=35 (avg=34.0) and frames=2 (>=2)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=VIDEO_END
  reached_end=True
  reason=decoded until end-of-video
  progress=9.62s / 9.70s
  decoded_frames=78 kept_frames=31 hashes=124
============================================================

Query time: 6.75s
Top candidates:
- matched=  2  avg_hamming= 34.0  offset=  794.0s  movie=119306:Grave Encounters 2 (tmdb=134366)

HINTS (1 movies with avg_hamming < 45):
  1. 119306:Grave Encounters 2 (tmdb=134366)
     range=20-35  frames=2  avg_hamming=34.0

[EARLY EXIT] P9E: Only movie overall with avg<=35 (avg=34.0) and frames=2 (>=2)

[ORCH] PDQ early accept -> movie_id=13 (P9E: Only movie overall with avg<=35 (avg=34.0) and frames=2 (>=2))

------------------------------------------------------------
VERDICT: 119306:Grave Encounters 2 (tmdb=134366)
         rule: P9E: Only movie overall with avg<=35 (avg=34.0) and frames=2 (>=2)
         VIDEO_END; 6.7s
```

## The In Between

Platform: unknown. Votes: 1 wrong / 2 correct.

**Status: REMAINING. Decided by the pre-scan. Note: 2 users voted correct, 1 voted wrong.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.01s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\www_facebook_com_share_r_14woyxuzQk7_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[SCAN] whole-clip pre-scan HIT in 12.7s: vidx=17 frames=4 min_hamming=18 -> early accept (skipped full pass-1)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=SCAN_ACCEPT
  reached_end=True
  reason=whole-clip pre-scan HIT
  progress=30.03s / 30.03s
  decoded_frames=0 kept_frames=0 hashes=0
============================================================

Query time: 12.82s
Top candidates:
- matched=  4  avg_hamming= 18.0  offset=    5.0s  movie=83904:The In Between (tmdb=818750)

HINTS (1 movies with avg_hamming < 45):
  1. 83904:The In Between (tmdb=818750)
     range=0-20  frames=4  avg_hamming=18.0

[EARLY EXIT] SCAN: whole-clip pre-scan min_hamming=18 frames=4

[ORCH] PDQ early accept -> movie_id=17 (SCAN: whole-clip pre-scan min_hamming=18 frames=4)

------------------------------------------------------------
VERDICT: 83904:The In Between (tmdb=818750)
         rule: SCAN: whole-clip pre-scan min_hamming=18 frames=4
         SCAN_ACCEPT; 12.8s
```

## The Northman

Platform: tiktok. Votes: 1 wrong / 0 correct.

**Status: REMAINING. Decided by the pre-scan on 6 frames at distance 6.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.00s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\vm_tiktok_com_ZS4MtfV2y_This_post_is_shared_via_TikTok_Lite_Download_TikTok_Lite.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'LANDSCAPE', 'SQUARE'])
[SCAN] whole-clip pre-scan HIT in 7.2s: vidx=25 frames=6 min_hamming=6 -> early accept (skipped full pass-1)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=SCAN_ACCEPT
  reached_end=True
  reason=whole-clip pre-scan HIT
  progress=131.67s / 131.67s
  decoded_frames=0 kept_frames=0 hashes=0
============================================================

Query time: 7.30s
Top candidates:
- matched=  6  avg_hamming=  6.0  offset= 2977.2s  movie=290:The Northman (tmdb=639933)

HINTS (1 movies with avg_hamming < 45):
  1. 290:The Northman (tmdb=639933)
     range=0-20  frames=6  avg_hamming=6.0

[EARLY EXIT] SCAN: whole-clip pre-scan min_hamming=6 frames=6

[ORCH] PDQ early accept -> movie_id=25 (SCAN: whole-clip pre-scan min_hamming=6 frames=6)

------------------------------------------------------------
VERDICT: 290:The Northman (tmdb=639933)
         rule: SCAN: whole-clip pre-scan min_hamming=6 frames=6
         SCAN_ACCEPT; 7.3s
```

## The Last Voyage of the Demeter

Platform: unknown. Votes: 1 wrong / 0 correct.

**Status: STOPPED by the P8 change. The engine now gives no answer here.**

```
index: C:\Users\nadaa\pdq_for_nada\data\index  (134 films, 16,744,500 fingerprints, opened in 0.00s, memory-mapped)
clip:  C:\Users\nadaa\pdq_for_nada\data\clips\www_facebook_com_share_v_1Hao6fkTco_.mp4

[ORCH][PDQ] starting query...
[ORCH][PDQ] Index ready: 1 shard(s)   (134 films, 16,744,500 fingerprints, groups searched: ['FULL', 'PORTRAIT', 'SQUARE'])
[SCAN] no early-accept -> running full pass-1 (cropped)
[PROBE] likely_match=False min_neighbor_hamming=76 closest_movie=218386:Armour of God (tmdb=10974) closest_group=PORTRAIT hashes=16 elapsed=1.12s
[STREAM EARLY EXIT] @ q_ts=25.8s — P8: 31 frames in 35-45 (>=30)

============================================================
[QUERY EXIT SUMMARY]
  exit_kind=EARLY_ACCEPT
  reached_end=False
  reason=P8: 31 frames in 35-45 (>=30)
  progress=25.75s / 2117.43s
  decoded_frames=207 kept_frames=75 hashes=565
============================================================

Query time: 26.51s
Top candidates:
- matched= 31  avg_hamming= 41.4  offset= 4931.0s  movie=73032:The Last Voyage of the Demeter (tmdb=635910)
- matched=  1  avg_hamming= 44.0  offset= 4207.0s  movie=9495:Hercules (tmdb=184315)

HINTS (2 movies with avg_hamming < 45):
  1. 73032:The Last Voyage of the Demeter (tmdb=635910)
     range=35-45  frames=31  avg_hamming=41.4
  2. 9495:Hercules (tmdb=184315)
     range=35-45  frames=1  avg_hamming=44.0

[EARLY EXIT] P8: 31 frames in 35-45 (>=30)

[ORCH] PDQ early accept -> movie_id=29 (P8: 31 frames in 35-45 (>=30))
[ORCH] this exit is from the weak band: the pod would wait 12s for audio or SSCD to disagree before sending it

------------------------------------------------------------
VERDICT: 73032:The Last Voyage of the Demeter (tmdb=635910)
         rule: P8: 31 frames in 35-45 (>=30)
         weak band: the pod would hold this answer 12s for audio or SSCD to object
         EARLY_ACCEPT; 26.5s
```
