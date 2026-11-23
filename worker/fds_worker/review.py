"""Öneri biçimi: kodla çizilmiş kadın sunucunun anlattığı anime / dizi / film öneri videoları.

research_collect : LLM konuya uygun 4-6 GERÇEK yapım seçer (konu yapım adı veriyorsa onları kullanır); her yapım
                   AniList (anime), TMDB (anahtar varsa) ve Vikipedi'de aranır. Hiçbir katalogda bulunamayan yapım
                   atılır (uydurma yapım önerilmez). Afiş ve yapı bilgileri (yıl, tür, bölüm, puan) plana yazılır.
script_doc       : giriş → her yapım bir bölüm (oneri_1..n) → kapanış. Sunucu birinci ağızdan, sıcak ve spoiler'sız
                   konuşur. Görüş ("bence", "en sevdiğim sahne türü") serbesttir; OLGULAR (yıl, stüdyo, bölüm, ödül, konu)
                   iddialardan gelir ve belgeseldeki gibi kodla denetlenir.
asset_match      : her yapımın afişi indirilir ve o yapımın sahnelerine atanır (sunucu sahnelerinde görsel gerekmez).
"""
from __future__ import annotations

import json

from . import catalog, llm, script as SC, sources as S, storage
from .handlers import StepResult
from .research import LANG_NAME, SYSTEM

LAYOUTS = ["host", "title", "poster", "mood", "full"]
OPEN_SHARE, CLOSE_SHARE = 0.08, 0.06
KIND_WORD = {"anime": "anime", "series": "TV series", "film": "film"}

REVIEW_PLAN = """
Plan a ~1 minute YouTube SHORTS RECOMMENDATION video (anime / TV series / film picks) presented by a host.
Topic: {topic}
Narration language: {lang}

The video is a ~1 minute vertical SHORTS, so keep it focused: if the topic names specific titles, use exactly those
(at most 3, in that order). Otherwise pick 1-3 REAL, well-known titles that clearly fit the topic (no adult/hentai titles).
Never invent a title.
Return JSON:
{{"titles": [{{"name_en": "official English/international title as on AniList/TMDB/Wikipedia",
              "name_native": "the title as commonly used in {lang}",
              "kind": "anime|series|film", "year": first release year,
              "wiki_en": "exact English Wikipedia article title (e.g. 'Dark (TV series)')"}}],
  "theme": "one short line: what connects these picks",
  "core_keywords": [every title in English and native spelling]}}
"""

REVIEW_NEEDS = """the factual claims a SPOILER-FREE recommendation video would need, for each title:
what kind of work it is (anime / series / film, format), release year, creators / studio / director / main cast,
number of seasons / episodes or runtime, source material (manga, novel...), genres, the PREMISE (only the setup of the
first episode(s) — never late twists, deaths or endings), themes and tone, notable music/animation/visual style,
reception (scores, awards, popularity), and age suitability / content notes (graphic violence, horror, mature themes)
if the sources state them. Aim for 5-8 claims per title; skip spoilers and off-topic material."""

STYLE_REVIEW = """NARRATION STYLE (very important — this is what makes the channel fun):
- You are {host}: a witty, high-energy, slightly cheeky anime-fan host (a fierce ninja girl). FIRST PERSON, talking
  directly to the viewer with "siz" in casual, spoken Turkish. Sound like an excited friend, NOT an encyclopedia.
- Use personality: playful reactions ("Ciddiyim!", "Evet, doğru duydunuz.", "Hazır mısınız?"), rhetorical questions,
  vivid comparisons and metaphors as OPINION ("bu seri adeta bir duygu rollercoaster'ı"), light humour and a little
  dramatic tension. Vary rhythm: a very short punchy line, then a longer one. Exclamation marks are welcome (not every line).
- Tell it like a story: describe the premise with vivid, emotional words (what is at stake, how it feels), never as a dry
  summary. Weave facts in naturally — NEVER list stats. At most ONE number per scene; drop boring numbers rather than
  stacking them (no "X incelemeye dayanarak yüzde Y onay" style lines).
- At most TWO facts per scene. Never cram author + director + studio + dates into one sentence; spread them out or drop
  the least interesting. A date range counts as two numbers: say only the year ("doksan yedide çıktı").
- The HOOK must be bold and specific to this title (a dare, a dramatic image, a surprising claim from the claims).
  BAD hooks: "X izlediniz mi?", "Hazır mısınız?", "Bugün size X'i anlatacağım." GOOD: "Kılıcı kendisinden büyük bir adam düşünün."
- Avoid report Turkish: no "-mıştır/-miştir", no "tarafından üretilmiş olan", no "olarak karşımıza çıkıyor",
  no "bu yapım", no "inceliyorum". Prefer active, lively verbs ("Bones çizmiş", "müzikleri Akira Senju'dan").
- "bence" ONLY for real opinions, never in front of a fact. Do not call something "the best of all time" as a fact.
- STRICTLY SPOILER-FREE: only the premise / setup. Never reveal twists, deaths, villains' identities or endings.
- If the claims show the work is dark, violent or for adults, give a quick friendly heads-up ("Uyarayım: kan ve şiddet bol,
  yetişkinlere göre!"). Never invent content warnings the claims do not support.
- Every FACT (year, studio, director, cast, episodes/seasons, runtime, score, award, plot setup) must come from the claims.
  Opinions, feelings, jokes and comparisons need no claim. Do not invent personal anecdotes ("dün gece izledim").
- Short spoken sentences (4-16 words). Numbers as words when read aloud. No brackets, no stage directions, no claim ids.

EXAMPLE of the wanted voice (do not copy, just the tone):
  KÖTÜ: "Bones stüdyosu tarafından büyük bir özenle üretilmiş olan bu yapım toplam altmış dört bölüm sürüyor."
  İYİ:  "Altmış dört bölüm! Ama inanın, hiçbiri boşa değil. Bones resmen döktürmüş."
  KÖTÜ: "Rotten Tomatoes üzerinde on dört incelemeye dayanarak yüzde yüz onay derecesine sahip."
  İYİ:  "Eleştirmenler mi? Tek bir kötü söz yok. Yüzde yüz!"
"""


def host_name(conn) -> str:
    row = conn.execute("select value from settings where key='presenter_name'").fetchone()
    return str(row["value"]) if row and row["value"] else "Ayla"


def style(conn) -> str:
    return STYLE_REVIEW.replace("{host}", host_name(conn))


# ----------------------------------------------------------------- araştırma
def collect(conn, step, p) -> StepResult:
    from .research import _store_sources

    lang = p["language"]
    plan = llm.complete_json(conn, SYSTEM, REVIEW_PLAN.format(minutes=p["target_minutes"], topic=p["topic"],
                                                              lang=LANG_NAME.get(lang, lang)),
                             task="research_plan_review", temperature=0.3)
    wanted = [x for x in (plan.get("titles") or []) if isinstance(x, dict) and x.get("name_en")][:3]   # Shorts: en fazla 3
    found: list[S.Source] = []
    errors: list[str] = []
    titles: list[dict] = []

    def run(name, fn, *args):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 — bir kaynak çökerse diğerleri sürer
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
            return None

    for w in wanted:
        kind = w.get("kind") if w.get("kind") in KIND_WORD else "series"
        meta: dict = {}
        srcs: list[S.Source] = []
        if kind == "anime":
            hit = run("anilist", catalog.anilist, w["name_en"], w.get("year") if isinstance(w.get("year"), int) else None)
            if hit:
                meta.update({k: v for k, v in hit[0].items() if v})
                srcs.append(hit[1])
        hit = run("tmdb", catalog.tmdb, w["name_en"], kind, lang, w.get("year") if isinstance(w.get("year"), int) else None)
        if hit:
            # TMDB afişi daha yüksek çözünürlüklü; AniList'in puanı/stüdyosu anime için öncelikli
            for k, v in hit[0].items():
                if v and (k not in meta or k in ("poster_url", "poster_page", "poster_source", "name_local")):
                    meta[k] = v
            srcs.append(hit[1])
        wiki = run("wikipedia:en", S.wikipedia, w.get("wiki_en") or f"{w['name_en']} {KIND_WORD[kind]}", "en", 1) or []
        wiki = [x for x in wiki if catalog.similar(w["name_en"], x.title.split(" (")[0])]
        srcs += wiki
        if lang != "en" and w.get("name_native") and len(titles) < 3:
            local = run(f"wikipedia:{lang}", S.wikipedia, w["name_native"], lang, 1) or []
            srcs += [x for x in local if catalog.similar(w["name_native"], x.title.split(" (")[0])
                     or catalog.similar(w["name_en"], x.title.split(" (")[0])]
        if not srcs:
            errors.append(f"bulunamadı: {w['name_en']} (öneriden çıkarıldı)")
            continue
        if not meta.get("poster_url") and wiki:
            pic = run("wikipedia:poster", catalog.wikipedia_poster, wiki[0].title, "en")
            if pic:
                meta.update({"poster_url": pic[0], "poster_page": pic[1], "poster_source": "wikipedia"})
        ref = f"oneri_{len(titles) + 1}"
        t = catalog.Title(ref=ref, name=w.get("name_native") or meta.get("name_local") or w["name_en"], kind=kind,
                          original=meta.get("original"), year=meta.get("year") or None, genres=meta.get("genres") or [],
                          score=meta.get("score"), score_source=meta.get("score_source"), episodes=meta.get("episodes"),
                          seasons=meta.get("seasons"), runtime=meta.get("runtime"), studio=meta.get("studio"),
                          format=meta.get("format"), poster_url=meta.get("poster_url"), poster_page=meta.get("poster_page"),
                          poster_source=meta.get("poster_source"), color=meta.get("color"), url=meta.get("url"))
        titles.append({**t.to_json(), "name_en": w["name_en"]})
        found += srcs
    if not titles:
        raise RuntimeError("Önerilecek yapımların hiçbiri kataloglarda bulunamadı: " + " | ".join(errors))
    keywords = list(dict.fromkeys([t["name_en"] for t in titles] + [t["name"] for t in titles]
                                  + [x for x in plan.get("core_keywords") or [] if isinstance(x, str)]))
    plan["titles"] = titles
    plan["core_keywords"] = keywords
    return _store_sources(conn, step, p, plan, found, keywords, errors)


def titles(conn, project_id) -> list[dict]:
    row = conn.execute("select output from job_steps where project_id=%s and step_key='research_collect' and output is not null "
                       "order by finished_at desc nulls last limit 1", (project_id,)).fetchone()
    plan = ((row or {}).get("output") or {}).get("plan") or {}
    return [x for x in plan.get("titles") or [] if isinstance(x, dict) and x.get("ref")]


# ----------------------------------------------------------------- senaryo
def plan_acts(tl: list[dict], budget: int) -> tuple[list[str], dict[str, str], dict[str, tuple[int, int]]]:
    tl = tl or [{"ref": "oneri_1", "name": "Öneri"}]
    acts = ["giris"] + [t["ref"] for t in tl] + ["kapanis"]
    titles_ = {"giris": "Giriş", "kapanis": "Kapanış", **{t["ref"]: t.get("name") or t["ref"] for t in tl}}
    per = (1 - OPEN_SHARE - CLOSE_SHARE) / len(tl)
    share = {"giris": OPEN_SHARE, "kapanis": CLOSE_SHARE, **{t["ref"]: per for t in tl}}
    plan = {a: (round(budget * share[a]), max(2, round(budget * share[a] / SC.SCENE_WORDS))) for a in acts}
    return acts, titles_, plan


def assign_layouts(scenes: list[dict]) -> None:
    """Sahne düzeni kodla belirlenir: giriş/kapanış → host; yapımın ilk sahnesi → title (afiş + bilgi kartı);
    diğerleri poster / mood / full arasında döner (LLM'in geçerli önerisi varsa o kullanılır, ama art arda iki 'full' yok)."""
    cycle = ["poster", "mood", "full"]
    prev_act, k, last = None, 0, None
    for sc in scenes:
        act = sc.get("_act") or ""
        sc["title_ref"] = act if act.startswith("oneri_") else None
        if not act.startswith("oneri_"):
            lay = "host"
        elif act != prev_act:
            lay, k = "title", 0
        else:
            want = sc.get("layout")
            lay = want if want in ("poster", "mood", "full", "host") and not (want == "full" and last == "full") else cycle[k % 3]
            k += 1
        sc["layout"] = lay
        last, prev_act = lay, act


def script_review(conn, step, p) -> StepResult:
    wpm = SC._setting(conn, "narration_wpm", 125)
    budget = int(float(p["target_minutes"]) * wpm)
    claims, status = SC._claims_block(conn, p["id"])
    if not claims:
        raise RuntimeError("Senaryo için iddia yok; araştırma adımları tamamlanmalı")
    lang = LANG_NAME.get(p["language"], p["language"])
    tl = titles(conn, p["id"])
    acts, act_titles, plan = plan_acts(tl, budget)
    st = style(conn)
    info = "\n".join(f"- {t['ref']} = {t.get('name')} ({t.get('name_en')}, {t.get('kind')}, {t.get('year') or '?'})" for t in tl)

    outline = SC._llm_json(conn, f"""
Plan a {p['target_minutes']}-minute RECOMMENDATION video in {lang}, presented by {host_name(conn)}. Topic: {p['topic']}

Picks (fixed order):
{info}

Chapters (fixed order) with target scene counts:
{chr(10).join(f"- {a} = {act_titles[a]}: {plan[a][1]} scenes" for a in acts)}

- giris: a fun hook that promises the list's theme (no titles spoiled), the host greets the viewer briefly.
- each oneri_N: that title only — hook, spoiler-free premise, what makes it special, who would love it.
- kapanis: a friendly wrap-up asking which one the viewer will start with. No "like and subscribe".
- Use each claim in the chapter of its title. Do not invent facts.

Return JSON: {{"title": "video title", "logline": "one sentence",
  "acts": [{{"act": "giris", "beats": ["one line per scene + claim ids"], "claim_refs": ["C#"]}}, ...]}}

CLAIMS:
{claims}
""", "script_outline_review", 0.7)
    beats = {a.get("act"): a for a in outline.get("acts", [])}

    acts_out, all_errs, previous = [], [], ""
    for a in acts:
        words_target, n_scenes = plan[a]
        t = next((x for x in tl if x["ref"] == a), None)
        about = (f"This chapter is ONLY about: {t.get('name')} ({t.get('name_en')}, {t.get('kind')})." if t else "")
        prompt = f"""
You are writing ONE chapter of a {p['target_minutes']}-minute recommendation video in {lang}: "{outline.get('title', p['title'])}".
Logline: {outline.get('logline', '')}

CHAPTER: {a} = {act_titles[a]}. {about}
Write EXACTLY {n_scenes} scenes, about {int(SC.SCENE_WORDS * SC.LENGTH_BOOST)} words of narration each
(total about {int(words_target * SC.LENGTH_BOOST)} words). Each scene needs 3-4 full sentences.
Planned beats: {json.dumps(beats.get(a, {}).get('beats', []), ensure_ascii=False)}

{st}

{"The previous chapter ended with: " + chr(34) + previous[-400:] + chr(34) + " — continue smoothly with a short, playful transition." if previous else "This is the opening of the video."}

Each scene cites the claim ids it uses in "claim_refs" (pure opinion scenes may have an empty list).
"on_screen_text": a short punchy caption (genre, a mood word, "Kimler sevecek?", or the title) or null.
"layout": one of {LAYOUTS} — "host" = the host on screen talking, "poster" = the title's poster, "mood" = an animated
colour/mood graphic, "full" = poster full screen without the host. "visual_description" = what the viewer sees.
"search_keywords": 2 English phrases with the title name.

CAMERA = {SC.CAMERA}
TRANSITIONS = {SC.TRANSITIONS}

Return JSON: {{"scenes": [{SC.SCENE_SCHEMA[:-1]}, "layout": "poster"}}]}}

CLAIMS:
{claims}
"""
        data, errs = SC._write_with_repair(
            conn, prompt, lambda d, a=a, w=words_target, n=n_scenes: SC._validate_act(d, n, w, status, a, claims),
            f"script_review_{a.split('_')[0]}")
        scenes = data.get("scenes") or []
        acts_out.append({"act": a, "scenes": scenes})
        all_errs += errs
        previous = " ".join(sc.get("voiceover", "") for sc in scenes[-2:])

    scenes = [{**sc, "_act": x["act"]} for x in acts_out for sc in x["scenes"]]
    if not scenes:
        raise RuntimeError("Öneri senaryosu üretilemedi: " + "; ".join(all_errs[:5]))
    words_before = sum(SC.words(sc.get("voiceover", "")) for sc in scenes)
    scenes, edits = SC._edit(conn, p, "review", scenes, claims, status, budget,
                             "5. Keep the host's first-person voice and opinions; opinions need no claim, facts do.\n"
                             "6. Remove SPOILERS (twists, deaths, endings, villains' identities).\n"
                             "7. Keep each scene in its chapter (title); never move facts of one title into another.",
                             style=st)
    scenes, dd_notes = SC.dedupe_scenes(scenes, int(budget * (1 - SC.TOLERANCE)) - int(budget * 0.15))
    assign_layouts(scenes)
    full = {"title": outline.get("title") or p["title"], "logline": outline.get("logline"), "format": "review",
            "act_titles": act_titles, "host": host_name(conn), "titles": tl,
            "acts": [{"act": a, "scenes": [sc for sc in scenes if sc.get("_act") == a]} for a in acts],
            "editor_notes": edits.get("notes", []) + dd_notes}
    final_errs = SC.validate_doc(full, budget, status, acts) + [
        f"sahne {i}: kaynakta olmayan sayı {', '.join(n)}" for i, n in SC.number_issues(scenes, claims).items()]
    version, total = SC._save(conn, p["id"], "doc", full, scenes, wpm, final_errs)
    return StepResult(output={"version": version, "format": "review", "scenes": len(scenes), "words": total,
                              "words_before_edit": words_before, "est_minutes": round(total / wpm, 2),
                              "budget_words": budget, "chapters": [act_titles[a] for a in acts],
                              "editor_notes": full["editor_notes"][:12], "validation_errors": final_errs})


def shorts_layouts(scenes: list[dict], tl: list[dict]) -> None:
    """Shorts: kanca ve kapanış sunucu; arada sahnenin andığı yapımın afişi (adı geçen ilk yapım, yoksa sıradaki)."""
    k = 0
    for i, sc in enumerate(scenes):
        if i == 0 or i == len(scenes) - 1 or not tl:
            sc["layout"], sc["title_ref"] = "host", None
            continue
        text = (sc.get("voiceover") or "") + " " + (sc.get("on_screen_text") or "")
        hit = next((t for t in tl if catalog._norm(t.get("name") or "") in catalog._norm(text)
                    or catalog._norm(t.get("name_en") or "") in catalog._norm(text)), None)
        t = hit or tl[min(k, len(tl) - 1)]
        if hit is None:
            k += 1
        sc["title_ref"] = t["ref"]
        sc["layout"] = "title" if i == 1 or scenes[i - 1].get("title_ref") != t["ref"] else "poster"


# ----------------------------------------------------------------- afişler
def match(conn, step) -> StepResult:
    """Her yapımın afişini indirir ve o yapımın sahnelerine atar. Afişler telif hakkı sahiplerinindir (promo)."""
    from .visuals import fetch_image, write_credits

    pid = step["project_id"]
    p = conn.execute("select slug from projects where id=%s", (pid,)).fetchone()
    tl = {t["ref"]: t for t in titles(conn, pid)}
    conn.execute("update scenes set asset_id=null where project_id=%s", (pid,))
    conn.execute("delete from assets where project_id=%s and scene_id is not null", (pid,))
    conn.execute("delete from assets where project_id=%s and source in ('anilist','tmdb','wikipedia') and scene_id is null", (pid,))
    stats = {"titles": len(tl), "posters": 0, "missing": [], "scenes_with_poster": 0}
    asset_of: dict[str, str] = {}
    for ref, t in tl.items():
        if not t.get("poster_url"):
            stats["missing"].append(t.get("name"))
            continue
        src = t.get("poster_source") or "web"
        aid = conn.execute(
            "insert into assets (project_id, kind, source, title, source_url, file_url, thumb_url, author, license, "
            "license_class, attribution, status, is_ai, query) values (%s,'image',%s,%s,%s,%s,%s,%s,%s,'promo',%s,'approved',false,%s) "
            "returning id",
            (pid, src, f"{t.get('name')} — afiş", t.get("poster_page"), t["poster_url"], t["poster_url"],
             "telif hakkı sahibi", "Telifli tanıtım görseli — yalnızca inceleme/eleştiri amaçlı",
             {"tmdb": "Görsel: TMDB (This product uses the TMDB API but is not endorsed or certified by TMDB.)",
              "anilist": "Görsel ve bilgi: AniList", "wikipedia": "Görsel: Wikipedia (non-free, fair use)"}.get(src),
             ref)).fetchone()["id"]
        asset_of[ref] = aid
    for sc in conn.execute("select id, title_ref from scenes where project_id=%s", (pid,)).fetchall():
        if sc["title_ref"] in asset_of:
            conn.execute("update scenes set asset_id=%s where id=%s", (asset_of[sc["title_ref"]], sc["id"]))
            stats["scenes_with_poster"] += 1
    if storage.configured():
        for ref, aid in asset_of.items():
            a = conn.execute("select * from assets where id=%s", (aid,)).fetchone()
            try:
                data, w, h = fetch_image(a["file_url"])
            except Exception as e:  # noqa: BLE001 — afiş yoksa kart afişsiz çizilir
                conn.execute("update assets set reject_reason=%s where id=%s", (f"indirilemedi: {type(e).__name__}", aid))
                stats["missing"].append(tl[ref].get("name"))
                continue
            key = storage.project_key(p["slug"], "assets", f"{aid}.jpg")
            sha = storage.upload_bytes(key, data, "image/jpeg")
            conn.execute("update assets set storage_key=%s, sha256=%s, bytes=%s, width=%s, height=%s where id=%s",
                         (key, sha, len(data), w, h, aid))
            stats["posters"] += 1
    write_credits(conn, pid, p["slug"])
    return StepResult(output=stats)
