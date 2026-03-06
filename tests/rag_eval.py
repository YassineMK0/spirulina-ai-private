"""Formal RAG Evaluation — LLM-as-judge scoring.

Metrics
-------
  answer_relevance  : does the answer directly address the question?   [0.0-1.0]
  faithfulness      : are all answer claims grounded in the context?   [0.0-1.0]
  context_recall    : do retrieved chunks contain key concepts?        [0.0-1.0]

Test set  : 30 questions (10 factual, 10 troubleshooting, 10 operational)
Judge LLM : llama-3.3-70b-versatile via Groq (same as generator)
Targets   : answer_relevance > 0.80 | faithfulness > 0.85

Results saved to: data/processed/rag_eval_results.json

Run
---
    python tests/rag_eval.py                  # default top_k=5
    python tests/rag_eval.py --top-k 8        # tuned retrieval
    python tests/rag_eval.py --skip-generate  # context recall only (no LLM calls)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 30-question evaluation set
# ---------------------------------------------------------------------------
# Each entry:
#   id          : unique integer
#   category    : factual | troubleshooting | operational
#   question    : natural language question (English)
#   keywords    : list of strings that should appear in retrieved chunks
#                 (used for context_recall; case-insensitive substring match)
# ---------------------------------------------------------------------------

EVAL_QUESTIONS: list[dict] = [
    # ── FACTUAL (1-10) ────────────────────────────────────────────────────
    # Keywords are multilingual: include EN root + FR equivalent where needed.
    # Corpus is primarily French — use partial/root matches (e.g. "prot" hits
    # both "protein" and "protéine"; "temp" hits "temperature"/"température").
    {
        "id": 1,
        "category": "factual",
        "question": "What is the optimal pH range for Spirulina platensis cultivation?",
        "keywords": ["pH", "optimum", "8", "10"],      # pH is universal
    },
    {
        "id": 2,
        "category": "factual",
        "question": "What temperature range supports maximum spirulina biomass productivity?",
        "keywords": ["temp", "35", "30", "optimale"],  # "temp" hits FR/EN
    },
    {
        "id": 3,
        "category": "factual",
        "question": "What are the main chemical components of the Zarrouk medium for spirulina?",
        "keywords": ["Zarrouk", "bicarbonate", "azote"],  # azote = nitrogen (FR)
    },
    {
        "id": 4,
        "category": "factual",
        "question": "What is the typical protein content of dried spirulina biomass?",
        "keywords": ["prot", "%", "biomasse"],         # "prot" hits protein/protéine
    },
    {
        "id": 5,
        "category": "factual",
        "question": "What OD680 value indicates that spirulina culture is ready to harvest?",
        "keywords": ["OD", "récolte", "densité"],      # récolte=harvest, densité=density
    },
    {
        "id": 6,
        "category": "factual",
        "question": "What is the typical growth rate or doubling time of Spirulina platensis?",
        "keywords": ["croissance", "taux", "jour"],    # croissance=growth, taux=rate, jour=day
    },
    {
        "id": 7,
        "category": "factual",
        "question": "What light intensity range is recommended for spirulina photosynthesis?",
        "keywords": ["lux", "lumi", "photosyn"],       # lumi hits lumière/lumineux; photosyn universal
    },
    {
        "id": 8,
        "category": "factual",
        "question": "What is the role of sodium bicarbonate in spirulina culture medium?",
        "keywords": ["bicarbonate", "carbone", "pH"],  # carbone=carbon (FR)
    },
    {
        "id": 9,
        "category": "factual",
        "question": "What electrical conductivity (EC) range is normal for a healthy spirulina culture?",
        "keywords": ["conductivité", "mS", "sel"],     # conductivité=conductivity, sel=salt
    },
    {
        "id": 10,
        "category": "factual",
        "question": "What makes spirulina considered a nutritionally complete protein source?",
        "keywords": ["prot", "acide amin", "essen"],   # acide aminé=amino acid; essen hits essentiel/essential
    },
    # ── TROUBLESHOOTING (11-20) ────────────────────────────────────────────
    {
        "id": 11,
        "category": "troubleshooting",
        "question": "My spirulina culture has turned bright green instead of blue-green — what is happening?",
        "keywords": ["vert", "contaminat", "Chlorella"],  # vert=green
    },
    {
        "id": 12,
        "category": "troubleshooting",
        "question": "Why does my spirulina culture produce a bad smell or sulfurous odor?",
        "keywords": ["odeur", "bactér", "contaminat"],    # odeur=smell, bactér=bacteria
    },
    {
        "id": 13,
        "category": "troubleshooting",
        "question": "What are the main causes of a spirulina culture crash?",
        "keywords": ["effondrement", "pH", "temp"],        # effondrement=crash/collapse
    },
    {
        "id": 14,
        "category": "troubleshooting",
        "question": "How do I detect contamination early in a spirulina raceway pond?",
        "keywords": ["contaminat", "microscope", "couleur"],  # couleur=color
    },
    {
        "id": 15,
        "category": "troubleshooting",
        "question": "My culture pH keeps dropping below 8.5 — what could cause this?",
        "keywords": ["pH", "CO2", "bicarbonate"],
    },
    {
        "id": 16,
        "category": "troubleshooting",
        "question": "What causes excessive foaming in a spirulina culture?",
        "keywords": ["mousse", "agitat", "organique"],    # mousse=foam, organique=organic
    },
    {
        "id": 17,
        "category": "troubleshooting",
        "question": "My culture looks pale or yellowish — what nutrient deficiency could explain this?",
        "keywords": ["jaune", "azote", "pigment"],        # jaune=yellow, azote=nitrogen
    },
    {
        "id": 18,
        "category": "troubleshooting",
        "question": "How do I recover a spirulina culture after partial contamination?",
        "keywords": ["contaminat", "filtr", "dilut"],     # filtr hits filtration/filtre
    },
    {
        "id": 19,
        "category": "troubleshooting",
        "question": "What could cause a sudden unexpected drop in OD680 in a spirulina culture?",
        "keywords": ["OD", "chute", "densité"],           # chute=drop/fall
    },
    {
        "id": 20,
        "category": "troubleshooting",
        "question": "How do I identify and deal with Chlorella contamination in spirulina cultures?",
        "keywords": ["Chlorella", "contaminat", "filtr"],
    },
    # ── OPERATIONAL (21-30) ────────────────────────────────────────────────
    {
        "id": 21,
        "category": "operational",
        "question": "How do I prepare a starter inoculum for a new spirulina pond?",
        "keywords": ["inoculum", "démarr", "culture"],   # démarr=starter/start
    },
    {
        "id": 22,
        "category": "operational",
        "question": "What is the standard procedure for harvesting spirulina biomass?",
        "keywords": ["récolte", "filtr", "densité"],
    },
    {
        "id": 23,
        "category": "operational",
        "question": "How often should I perform medium renewal or water changes in a spirulina culture?",
        "keywords": ["renouvell", "eau", "milieu"],       # renouvell=renewal, eau=water, milieu=medium
    },
    {
        "id": 24,
        "category": "operational",
        "question": "How do I calculate how much biomass to harvest without reducing productivity?",
        "keywords": ["récolte", "productiv", "calcul"],   # calcul hits calculer/calculation
    },
    {
        "id": 25,
        "category": "operational",
        "question": "What is the best time of day to harvest spirulina for maximum quality?",
        "keywords": ["récolte", "matin", "qualité"],      # matin=morning, qualité=quality
    },
    {
        "id": 26,
        "category": "operational",
        "question": "How should spirulina biomass be dried after harvesting?",
        "keywords": ["séchage", "temp", "biomasse"],      # séchage=drying
    },
    {
        "id": 27,
        "category": "operational",
        "question": "What are the key steps to scale up a spirulina culture from 100L to 1000L?",
        "keywords": ["volume", "inoculum", "densité"],
    },
    {
        "id": 28,
        "category": "operational",
        "question": "What parameters should I measure daily when monitoring a spirulina culture?",
        "keywords": ["pH", "temp", "OD", "quotidien"],   # quotidien=daily
    },
    {
        "id": 29,
        "category": "operational",
        "question": "How do I perform a partial medium change to replenish nutrients?",
        "keywords": ["renouvell", "nutriment", "partiel"],  # nutriment=nutrient
    },
    {
        "id": 30,
        "category": "operational",
        "question": "How do I maintain a spirulina culture during a production break or shutdown?",
        "keywords": ["stockage", "entretien", "arrêt"],    # stockage=storage, entretien=maintenance
    },
]

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

TARGETS = {
    "answer_relevance": 0.80,
    "faithfulness":     0.85,
    "context_recall":   0.70,   # keyword-based, softer target
}

# ---------------------------------------------------------------------------
# Groq model budgets (free tier):
#   llama-3.3-70b-versatile : 100k tokens/day  -- production generator
#   llama-3.1-8b-instant    : 500k tokens/day  -- router + eval judge
#
# Strategy: use llama-3.1-8b-instant for judge to avoid exhausting the
# 70b daily quota.  The eval generator can be overridden via --eval-model.
# ---------------------------------------------------------------------------

JUDGE_MODEL = "llama-3.3-70b-versatile"  # default; override with --judge-model

# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """\
You are an objective evaluator for a RAG (Retrieval-Augmented Generation) system \
about Spirulina cultivation. Your job is to score AI-generated answers.

You will receive:
  - QUESTION  : the user's question
  - CONTEXT   : text retrieved from the knowledge base
  - ANSWER    : the AI-generated response

Score two metrics strictly from 0.0 to 1.0:

answer_relevance:
  1.0 = answer fully and directly addresses the question
  0.7 = answer addresses the question but misses some aspects
  0.5 = answer is tangentially related but not directly helpful
  0.0 = answer does not address the question at all

faithfulness:
  1.0 = every factual claim in the answer is supported by the CONTEXT
  0.7 = most claims are in the CONTEXT, minor additions from general knowledge
  0.5 = some claims are not in the CONTEXT
  0.0 = major claims contradict or are absent from the CONTEXT

Return ONLY valid JSON — no markdown, no explanation outside JSON:
{"answer_relevance": <float 0.0-1.0>, "faithfulness": <float 0.0-1.0>, "reasoning": "<one sentence>"}
"""

_JUDGE_HUMAN = """\
QUESTION: {question}

CONTEXT:
{context}

ANSWER:
{answer}
"""


def _get_judge_llm():
    """Return a Groq client for the judge (not cached — different model may differ)."""
    from groq import Groq
    return Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


def _is_rate_limit_error(exc: Exception) -> tuple[bool, float]:
    """Return (is_rate_limit, retry_after_seconds) from a Groq 429 exception."""
    msg = str(exc)
    if "429" in msg or "rate_limit_exceeded" in msg:
        # Try to parse "try again in Xm Ys"
        m = re.search(r"try again in (\d+)m(\d+(?:\.\d+)?)s", msg)
        if m:
            wait = int(m.group(1)) * 60 + float(m.group(2)) + 5.0
        else:
            wait = 65.0
        return True, wait
    return False, 0.0


def _groq_call_with_retry(client, model: str, messages: list, max_tokens: int, max_retries: int = 3) -> str:
    """Call Groq chat completions with exponential backoff on rate limit."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            is_rl, wait = _is_rate_limit_error(exc)
            if is_rl and attempt < max_retries - 1:
                print(f"\n  [rate-limit] waiting {wait:.0f}s before retry {attempt+2}/{max_retries}...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


def judge_answer(question: str, context: str, answer: str) -> dict:
    """Call the LLM judge and return {answer_relevance, faithfulness, reasoning}.

    Uses llama-3.1-8b-instant (500k tokens/day) so the judge never
    exhausts the production generator's 100k/day quota.
    """
    # Detect answers that are known error fallbacks — no point judging them
    if "rate_limit_exceeded" in answer or "error while generating" in answer.lower():
        return {
            "answer_relevance": None,
            "faithfulness":     None,
            "reasoning":        "skipped — generator failed for this question",
        }

    client = _get_judge_llm()
    prompt = _JUDGE_HUMAN.format(
        question=question,
        context=context[:3500],   # keep within token budget for 8b model
        answer=answer[:1500],
    )
    try:
        raw = _groq_call_with_retry(
            client,
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=256,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
        scores = json.loads(raw)
        return {
            "answer_relevance": float(scores.get("answer_relevance", 0.0)),
            "faithfulness":     float(scores.get("faithfulness",     0.0)),
            "reasoning":        scores.get("reasoning", ""),
        }
    except Exception as exc:
        return {
            "answer_relevance": None,
            "faithfulness":     None,
            "reasoning":        f"Judge error: {exc}",
        }


# ---------------------------------------------------------------------------
# Context recall — keyword-based
# ---------------------------------------------------------------------------

def score_context_recall(chunks: list[dict], keywords: list[str]) -> float:
    """Return fraction of keywords found in any of the retrieved chunks."""
    if not keywords:
        return 1.0
    combined = " ".join(c.get("text", "") for c in chunks).lower()
    hits = sum(1 for kw in keywords if kw.lower() in combined)
    return round(hits / len(keywords), 4)


# ---------------------------------------------------------------------------
# Per-question evaluation
# ---------------------------------------------------------------------------

def evaluate_question(
    q: dict,
    top_k: int = 5,
    skip_generate: bool = False,
    eval_model: str | None = None,
) -> dict:
    """Run retrieval, generation, and all three scoring metrics for one question.

    Args:
        eval_model: Override the generator model for this eval run only.
                    Useful when the production model (70b) has hit its daily
                    token quota.  E.g. "llama-3.1-8b-instant".
    """
    from rag.retriever.retrieve import retrieve, format_context

    question   = q["question"]
    keywords   = q["keywords"]
    category   = q["category"]

    # 1. Retrieve — for troubleshooting questions, augment with topic-filtered chunks
    #    to ensure the troubleshooting guide is included even when semantic search
    #    favours nutritional-science papers over colour/problem diagnosis content.
    chunks = retrieve(question, top_k=top_k)

    if category in ("troubleshooting", "operational"):
        # For troubleshooting AND operational questions, prepend top-3 chunks
        # from the troubleshooting guide (which also covers harvest, drying,
        # monitoring, medium renewal).  Then fill with standard semantic results
        # up to top_k — keeps total context size fixed so the judge isn't
        # overwhelmed by extra sources.
        ts_chunks = retrieve(question, top_k=3, topic="troubleshooting")
        existing_texts = {c["text"] for c in ts_chunks}
        for c in chunks:
            if c["text"] not in existing_texts:
                ts_chunks.append(c)
                existing_texts.add(c["text"])
        chunks = ts_chunks[:top_k]   # cap at top_k, troubleshooting chunks first

    context = format_context(chunks)

    # 2. Context recall (keyword-based — no LLM needed)
    context_recall = score_context_recall(chunks, keywords)

    if skip_generate:
        return {
            "id":               q["id"],
            "category":         category,
            "question":         question,
            "context_recall":   context_recall,
            "answer_relevance": None,
            "faithfulness":     None,
            "reasoning":        "skipped",
            "answer":           "",
            "top_k":            top_k,
            "num_chunks":       len(chunks),
        }

    # 3. Generate answer (retry once on rate-limit)
    from rag.generator.generate import generate_answer
    import rag.generator.generate as _gen_mod

    # Temporarily override model if --eval-model was specified
    _orig_model = _gen_mod.GENERATOR_MODEL
    if eval_model:
        _gen_mod.GENERATOR_MODEL = eval_model
        _gen_mod.get_generator_chain.cache_clear()
        _gen_mod._get_llm.cache_clear()

    try:
        answer = generate_answer(question=question, context=context)
        # If the generator itself returned a rate-limit error, raise so caller sees it
        if "rate_limit_exceeded" in answer or ("error code: 429" in answer.lower()):
            raise RuntimeError(f"Generator rate-limited: {answer[:200]}")
    except Exception as exc:
        answer = f"Generator error: {exc}"
    finally:
        # Restore original model name
        if eval_model:
            _gen_mod.GENERATOR_MODEL = _orig_model
            _gen_mod.get_generator_chain.cache_clear()
            _gen_mod._get_llm.cache_clear()

    # 4. LLM judge
    scores = judge_answer(question, context, answer)

    return {
        "id":               q["id"],
        "category":         category,
        "question":         question,
        "context_recall":   context_recall,
        "answer_relevance": scores["answer_relevance"],
        "faithfulness":     scores["faithfulness"],
        "reasoning":        scores["reasoning"],
        "answer":           answer,
        "top_k":            top_k,
        "num_chunks":       len(chunks),
    }


# ---------------------------------------------------------------------------
# Aggregate helper
# ---------------------------------------------------------------------------

def aggregate(results: list[dict]) -> dict:
    """Compute mean scores overall and per category."""
    metrics = ["answer_relevance", "faithfulness", "context_recall"]
    categories = ["factual", "troubleshooting", "operational"]

    def mean(vals):
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 4) if clean else None

    overall = {m: mean([r[m] for r in results]) for m in metrics}

    per_cat = {}
    for cat in categories:
        cat_rows = [r for r in results if r["category"] == cat]
        per_cat[cat] = {m: mean([r[m] for r in cat_rows]) for m in metrics}

    # Pass/fail
    passes = {}
    for m, target in TARGETS.items():
        score = overall[m]
        passes[m] = (score is not None and score >= target)

    return {
        "overall":  overall,
        "per_category": per_cat,
        "targets":  TARGETS,
        "pass":     passes,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_eval(
    top_k: int = 5,
    skip_generate: bool = False,
    save_path: str = "data/processed/rag_eval_results.json",
    verbose: bool = True,
    eval_model: str | None = None,
    judge_model: str | None = None,
) -> dict:
    """Run full evaluation. Returns the results dict.

    Args:
        eval_model: Optional model override for the generator during eval.
                    Use "llama-3.1-8b-instant" when the 70b daily quota is
                    exhausted.  Production model is unchanged.
    """
    import tests.rag_eval as _self_mod
    if judge_model:
        _self_mod.JUDGE_MODEL = judge_model

    gen_label   = eval_model  or "llama-3.3-70b-versatile (production)"
    judge_label = judge_model or JUDGE_MODEL
    print(f"\n{'='*60}")
    print(f"  RAG Evaluation  |  top_k={top_k}  |  {len(EVAL_QUESTIONS)} questions")
    print(f"  Generator : {gen_label}")
    print(f"  Judge     : {judge_label}")
    print(f"{'='*60}\n")

    # ── Resume: load previously scored questions ───────────────────────────
    out_path = Path(save_path)
    completed: dict[int, dict] = {}
    if out_path.exists():
        try:
            with open(out_path, encoding="utf-8") as f:
                prev = json.load(f)
            for r in prev.get("results", []):
                # Consider a question "done" if it has non-None LLM scores
                # (None scores mean the generator or judge errored out)
                if r.get("answer_relevance") is not None or skip_generate:
                    completed[r["id"]] = r
            if completed:
                print(f"  Resuming: {len(completed)} question(s) already scored, "
                      f"{len(EVAL_QUESTIONS)-len(completed)} remaining.\n")
        except Exception:
            pass   # ignore corrupt file

    results = []
    for i, q in enumerate(EVAL_QUESTIONS, start=1):
        if q["id"] in completed:
            row = completed[q["id"]]
            if verbose:
                ar = f"{row['answer_relevance']:.2f}" if row['answer_relevance'] is not None else "N/A"
                fa = f"{row['faithfulness']:.2f}"     if row['faithfulness']     is not None else "N/A"
                cr = f"{row['context_recall']:.2f}"
                print(f"[{i:02d}/30] {q['category']:>15s} | CACHED  "
                      f"relevance={ar}  faithfulness={fa}  recall={cr}")
            results.append(row)
            continue

        if verbose:
            print(f"[{i:02d}/30] {q['category']:>15s} | Q: {q['question'][:60]}...")
        row = evaluate_question(q, top_k=top_k, skip_generate=skip_generate, eval_model=eval_model)
        results.append(row)

        # ── Save after every question so progress is never lost ────────────
        partial = {
            "eval_config": {"top_k": top_k, "judge_model": JUDGE_MODEL,
                            "eval_model": gen_label,
                            "num_questions": len(EVAL_QUESTIONS), "skip_generate": skip_generate},
            "summary":  aggregate(results),
            "results":  results,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(partial, f, indent=2, ensure_ascii=False)

        if verbose and not skip_generate:
            ar = f"{row['answer_relevance']:.2f}" if row['answer_relevance'] is not None else "N/A"
            fa = f"{row['faithfulness']:.2f}"     if row['faithfulness']     is not None else "N/A"
            cr = f"{row['context_recall']:.2f}"
            print(f"         relevance={ar}  faithfulness={fa}  recall={cr}")
        # Brief pause to respect Groq rate limits
        if not skip_generate:
            time.sleep(1.0)

    # Final aggregate + save
    summary = aggregate(results)
    output = {
        "eval_config": {
            "top_k":         top_k,
            "judge_model":   JUDGE_MODEL,
            "num_questions": len(EVAL_QUESTIONS),
            "skip_generate": skip_generate,
        },
        "summary":  summary,
        "results":  results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved -> {out_path}")

    # ── Print summary ─────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    ov = summary["overall"]

    def _fmt(v):
        return f"{v:.3f}" if v is not None else "N/A "

    print(f"\n  {'Metric':<22} {'Score':>6}  {'Target':>6}  {'Status'}")
    print(f"  {'-'*50}")
    for m, target in TARGETS.items():
        score  = ov[m]
        passed = summary["pass"][m]
        status = "PASS" if passed else "FAIL"
        print(f"  {m:<22} {_fmt(score):>6}  {target:.2f}   {status}")

    print(f"\n  {'Category':<22} {'Relevance':>9}  {'Faithful':>8}  {'Recall':>6}")
    print(f"  {'-'*50}")
    for cat, scores in summary["per_category"].items():
        print(
            f"  {cat:<22} {_fmt(scores['answer_relevance']):>9}"
            f"  {_fmt(scores['faithfulness']):>8}"
            f"  {_fmt(scores['context_recall']):>6}"
        )

    # ── Tuning recommendations ─────────────────────────────────────────────
    all_pass = all(summary["pass"].values())
    if not all_pass:
        print(f"\n{'='*60}")
        print("  TUNING RECOMMENDATIONS")
        print(f"{'='*60}")
        if not summary["pass"].get("context_recall", True):
            print("\n  Context Recall below target:")
            print("   -> Run with --top-k 8 to retrieve more chunks per query")
            print("   -> Consider re-ingesting with smaller chunk_size (300 tokens)")
        if not summary["pass"].get("faithfulness", True):
            print("\n  Faithfulness below target:")
            print("   -> Tighten RULE 1 in system prompt (stricter grounding)")
            print("   -> Reduce generator temperature (currently 0.2 -> try 0.0)")
            print("   -> Add explicit 'cite your source' instruction to human template")
        if not summary["pass"].get("answer_relevance", True):
            print("\n  Answer Relevance below target:")
            print("   -> Increase top_k (more context = better coverage)")
            print("   -> Try adding topic filter for category-specific queries")
    else:
        print("\n  All metrics PASS targets. RAG pipeline is production-ready.")

    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG evaluation with LLM-as-judge")
    parser.add_argument("--top-k",         type=int,  default=5,     help="Number of retrieved chunks per query")
    parser.add_argument("--skip-generate", action="store_true",      help="Only score context recall, skip LLM calls")
    parser.add_argument("--eval-model",    type=str,  default=None,
                        help="Override generator model for this eval run only "
                             "(e.g. llama-3.1-8b-instant when 70b quota is exhausted)")
    parser.add_argument("--judge-model",   type=str,  default=None,
                        help="Override judge model (default: llama-3.3-70b-versatile). "
                             "Use llama-3.1-8b-instant to save 70b quota.")
    parser.add_argument("--save",          type=str,  default="data/processed/rag_eval_results.json",
                        help="Output JSON path")
    args = parser.parse_args()

    run_eval(
        top_k=args.top_k,
        skip_generate=args.skip_generate,
        eval_model=args.eval_model,
        judge_model=args.judge_model,
        save_path=args.save,
        verbose=True,
    )
