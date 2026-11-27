# -*- coding: utf-8 -*-
"""
把 SQLite 数据库导出为前端纯静态版所需的 data.json。

为控制体积，对重复度高的字符串列做「字典编码」：
    - 字符串列存成字典下标（整数），字典放在 cat 里；
    - 数字列（年份、分数、位次、是否）直接存数值。
前端 buildIndex 时会还原成普通行，查询逻辑不受影响。

数据变了重新运行即可，前端只替换 data.json。
"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(ROOT_DIR, "db", "qingyun.db")
OUT_PATH = os.path.join(ROOT_DIR, "frontend", "data.json")

COLUMNS = [
    "year", "school", "category", "batch", "major", "major_code", "remark", "subject_req",
    "first_choice", "reselect_mode", "reselect_subjects",
    "min_score", "min_rank", "province", "school_nature",
    "is_985", "is_211", "is_coop",
]
NUMERIC = {"year", "min_score", "min_rank", "is_985", "is_211", "is_coop"}


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT " + ",".join(COLUMNS) + " FROM admission ORDER BY year, category, school, major"
    )
    raw = []
    for r in cur:
        raw.append([(r[c].strip() if isinstance(r[c], str) else r[c]) for c in COLUMNS])
    conn.close()

    cat_cols = [c for c in COLUMNS if c not in NUMERIC]
    dicts = {c: {} for c in cat_cols}   # value -> idx
    lists = {c: [] for c in cat_cols}   # idx -> value
    rows = []
    for r in raw:
        out = []
        for c, v in zip(COLUMNS, r):
            if c in NUMERIC:
                out.append(v)
            else:
                d = dicts[c]
                if v is None:
                    v = ""
                if v not in d:
                    d[v] = len(lists[c])
                    lists[c].append(v)
                out.append(d[v])
        rows.append(out)

    payload = {
        "version": "22-25",
        "generated_at": "2026-11-25",
        "columns": COLUMNS,
        "numeric": sorted(NUMERIC),
        "cat": lists,
        "rows": rows,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT_PATH)
    print(f"已导出 {len(rows)} 行 -> {OUT_PATH}")
    print(f"文件大小: {size/1024/1024:.2f} MB")
    for c in cat_cols:
        print(f"  字典 {c}: {len(lists[c])} 个唯一值")


if __name__ == "__main__":
    main()
