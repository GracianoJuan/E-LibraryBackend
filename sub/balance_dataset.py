import argparse
import re
import sys
from itertools import combinations

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_INPUT     = "books_cleaned_updated.csv"
DEFAULT_OUTPUT    = "books_balanced.csv"
MIN_BOOKS         = 6
MAX_BOOKS         = 6
GENRE_COL         = "genre"
TEXT_COL          = "description"
GENRE_SEP         = ";"          # separator used in multi-genre labels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tokenize(text: str) -> set:
    if not isinstance(text, str) or not text.strip():
        return set()
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(text.split())


def jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def build_sim_matrix(token_sets: list) -> np.ndarray:
    n = len(token_sets)
    mat = np.zeros((n, n), dtype=np.float32)
    for i, j in combinations(range(n), 2):
        sim = jaccard(token_sets[i], token_sets[j])
        mat[i, j] = sim
        mat[j, i] = sim
    return mat


def assign_primary_genre(df: pd.DataFrame, genre_col: str,
                          sep: str, valid_genres: set) -> pd.Series:
    def pick(label):
        if not isinstance(label, str):
            return np.nan
        parts = [g.strip() for g in label.split(sep)]
        for g in parts:
            if g in valid_genres:
                return g
        return np.nan

    return df[genre_col].map(pick)


def adaptive_threshold(df: pd.DataFrame, primary_col: str,
                        text_col: str, min_books: int) -> float:
    all_sims = []
    for genre in df[primary_col].dropna().unique():
        sub = df[df[primary_col] == genre]
        tokens = [tokenize(t) for t in sub[text_col]]
        for i, j in combinations(range(len(tokens)), 2):
            all_sims.append(jaccard(tokens[i], tokens[j]))
    return float(np.median(all_sims)) if all_sims else 0.05


def filter_genre(indices, token_sets, threshold, min_books, max_books):
    n = len(indices)
    mat = build_sim_matrix(token_sets)

    required_neighbours = min_books - 1
    connected = (mat >= threshold).sum(axis=1) >= required_neighbours
    kept_local = [i for i, ok in enumerate(connected) if ok]

    if len(kept_local) < min_books:
        return []

    if len(kept_local) > max_books:
        sub_mat = mat[np.ix_(kept_local, kept_local)]
        mean_sim = sub_mat.mean(axis=1)
        top = np.argsort(mean_sim)[::-1][:max_books].tolist()
        kept_local = [kept_local[k] for k in sorted(top)]

    return [indices[k] for k in kept_local]


def balance(input_path, output_path, min_books, max_books,
            fixed_threshold, genre_col, text_col):

    SEP = "=" * 64
    print(f"\n{SEP}")
    print("  BOOK DATASET BALANCER  (individual genres)")
    print(f"{SEP}")

    # ── Load ────────────────────────────────────────────────────────────────
    print(f"\n[1/6] Loading: {input_path}")
    try:
        df = pd.read_csv(input_path, encoding="latin-1")
    except FileNotFoundError:
        sys.exit(f"ERROR: File not found → {input_path}")
    print(f"      Rows: {len(df)}  |  Raw genre labels: {df[genre_col].nunique()}")

    # ── Split multi-genre labels → individual genre counts ──────────────────
    print(f"\n[2/6] Splitting multi-genre labels on '{GENRE_SEP}'")
    genre_series = (df[genre_col].dropna()
                                 .str.split(GENRE_SEP)
                                 .explode()
                                 .str.strip())
    individual_counts = genre_series.value_counts()
    print(f"      Unique individual genres found: {len(individual_counts)}")

    # ── Step 1: Drop individual genres below MIN_BOOKS ──────────────────────
    print(f"\n[3/6] Step 1 – Keep individual genres with >= {min_books} books")
    valid_genres = set(individual_counts[individual_counts >= min_books].index)
    dropped_genres = set(individual_counts.index) - valid_genres
    print(f"      Valid genres : {len(valid_genres)}")
    print(f"      Dropped      : {len(dropped_genres)}  {sorted(dropped_genres)}")

    # ── Assign each book its primary genre ──────────────────────────────────
    PRIMARY_COL = "_primary_genre"
    df[PRIMARY_COL] = assign_primary_genre(df, genre_col, GENRE_SEP, valid_genres)
    df_valid = df[df[PRIMARY_COL].notna()].copy().reset_index(drop=True)
    print(f"\n      Books assigned to a valid genre: {len(df_valid)}")
    print(f"      Books with no valid genre (excluded): {len(df) - len(df_valid)}")

    # ── Determine Jaccard threshold ─────────────────────────────────────────
    if fixed_threshold is not None:
        threshold = fixed_threshold
        t_label = f"{threshold:.4f}  (user-supplied)"
    else:
        threshold = adaptive_threshold(df_valid, PRIMARY_COL, text_col, min_books)
        t_label = f"{threshold:.4f}  (auto: median pairwise Jaccard)"
    print(f"\n      Jaccard threshold: {t_label}")

    # Pre-compute tokens
    tokens_all = [tokenize(t) for t in df_valid[text_col]]

    # ── Steps 2-4: Jaccard filtering per genre ──────────────────────────────
    print(f"\n[4/6] Steps 2-4 – Jaccard filtering per genre")
    print(f"      threshold={threshold:.4f}, required neighbours={min_books - 1}\n")

    kept_indices = []
    genre_report = {}

    for genre in sorted(valid_genres,
                        key=lambda g: -individual_counts[g]):
        mask      = df_valid[PRIMARY_COL] == genre
        local_idx = df_valid.index[mask].tolist()
        local_tok = [tokens_all[i] for i in local_idx]
        n_before  = len(local_idx)

        kept    = filter_genre(local_idx, local_tok,
                               threshold, min_books, max_books)
        n_after = len(kept)

        if not kept:
            status = "DROPPED  (< min after Jaccard filter)"
        elif n_after == n_before:
            status = f"kept all {n_after}"
        elif n_after == max_books and n_before > max_books:
            status = f"capped   {n_before} → {n_after}"
        else:
            status = f"trimmed  {n_before} → {n_after}"

        genre_report[genre] = {"before": n_before, "after": n_after, "status": status}
        kept_indices.extend(kept)

    df_balanced = df_valid.loc[kept_indices].copy().reset_index(drop=True)

    # Clean up helper columns
    df_balanced.drop(columns=[PRIMARY_COL], inplace=True)
    drop_cols = [c for c in df_balanced.columns if c.startswith("Unnamed:")]
    df_balanced.drop(columns=drop_cols, inplace=True)

    # ── Report ───────────────────────────────────────────────────────────────
    print(f"[5/6] Per-genre report")
    print(f"{'─' * 64}")
    print(f"  {'Genre':<26}  {'Before':>6}  {'After':>5}  Status")
    print(f"{'─' * 64}")
    for genre, info in genre_report.items():
        print(f"  {genre:<26}  {info['before']:>6}  {info['after']:>5}  {info['status']}")
    print(f"{'─' * 64}")

    if len(df_balanced) > 0:
        # Recompute primary genre on balanced df for reporting
        tmp = df_balanced.copy()
        tmp[PRIMARY_COL] = assign_primary_genre(tmp, genre_col, GENRE_SEP, valid_genres)
        counts_after = tmp[PRIMARY_COL].value_counts()
        print(f"\n  Final genres          : {counts_after.nunique()}")
        print(f"  Final books           : {len(df_balanced)}")
        print(f"  Min books/genre       : {counts_after.min()}")
        print(f"  Max books/genre       : {counts_after.max()}")
        print(f"  Mean books/genre      : {counts_after.mean():.1f}")
        print(f"\n  Distribution:")
        for g, cnt in counts_after.items():
            bar = "█" * cnt
            print(f"    {g:<26} {cnt:>3}  {bar}")
    else:
        print("\n  WARNING: No books survived. Try lowering --threshold.")

    # ── Save ─────────────────────────────────────────────────────────────────
    print(f"\n[6/6] Saving → {output_path}")
    df_balanced.to_csv(output_path, index=False, encoding="utf-8")
    print(f"      Done!  ({len(df_balanced)} rows written)")
    print(f"\n{SEP}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Balance books dataset by individual genre using Jaccard similarity."
    )
    p.add_argument("--input",     default=DEFAULT_INPUT)
    p.add_argument("--output",    default=DEFAULT_OUTPUT)
    p.add_argument("--min",       type=int, default=MIN_BOOKS,
                   help=f"Min books per genre (default: {MIN_BOOKS})")
    p.add_argument("--max",       type=int, default=MAX_BOOKS,
                   help=f"Max books per genre (default: {MAX_BOOKS})")
    p.add_argument("--threshold", default="auto",
                   help="Jaccard threshold: float or 'auto' (default: auto)")
    p.add_argument("--genre-col", default=GENRE_COL)
    p.add_argument("--text-col",  default=TEXT_COL)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fixed_threshold = None
    if args.threshold != "auto":
        try:
            fixed_threshold = float(args.threshold)
        except ValueError:
            sys.exit(f"ERROR: --threshold must be a float or 'auto', got: {args.threshold!r}")

    balance(
        input_path      = args.input,
        output_path     = args.output,
        min_books       = args.min,
        max_books       = args.max,
        fixed_threshold = fixed_threshold,
        genre_col       = args.genre_col,
        text_col        = args.text_col,
    )
