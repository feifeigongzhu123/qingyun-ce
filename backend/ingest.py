# -*- coding: utf-8 -*-
"""
将 Excel 历年录取数据导入 SQLite，并把「选科要求」解析成可查询的结构化字段。

用法:
    python ingest.py [excel路径] [db路径]
默认:
    excel = ../22-25年全国高校在辽宁的专业录取分数.xlsx
    db    = ../db/qingyun.db
"""
import os
import re
import sys
import sqlite3

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_EXCEL = os.path.join(ROOT_DIR, "22-25年全国高校在辽宁的专业录取分数.xlsx")
DEFAULT_DB = os.path.join(ROOT_DIR, "db", "qingyun.db")

# 再选科目词汇（长词在前，避免「物理」误匹配「生物」）
SUBJECT_TOKENS = ("思想政治", "化学", "生物", "地理", "物理", "历史")
SUBJ_RE = re.compile("|".join(SUBJECT_TOKENS))


def parse_subject_req(raw, category):
    """解析选科要求文本 -> (first_choice, reselect_mode, subjects list)

    first_choice: '物理' | '历史' | '不限'
    reselect_mode: 'none' | 'any' | 'all'
    """
    raw = "" if raw is None else str(raw).strip()

    first = None
    if "首选物理" in raw:
        first = "物理"
    elif "首选历史" in raw:
        first = "历史"
    elif "不限" in raw:
        first = "不限"

    if first is None:
        # 选科要求缺失时，按科类回退
        if category == "物理类":
            first = "物理"
        elif category == "历史类":
            first = "历史"
        else:
            first = "不限"

    rest = ""
    if "再选" in raw:
        rest = raw.split("再选", 1)[1].strip()

    mode = "none"
    subjects = []
    if rest and not rest.startswith("不限"):
        if "/" in rest or "2选1" in rest:
            mode = "any"
        else:
            # 单科，或「A、B(2科必选)」都是「全部必选」
            mode = "all"
        seen = []
        for m in SUBJ_RE.findall(rest):
            if m not in seen:
                seen.append(m)
        subjects = seen
        if not subjects:
            mode = "none"

    return first, mode, subjects


def to_int(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip()
        if s == "" or s.lower() == "nan":
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


def main():
    excel = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXCEL
    db_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    print(f"[1/4] 读取 Excel: {excel}")
    df = pd.read_excel(excel, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"    原始行数: {len(df)}, 列: {list(df.columns)}")

    # 统一列名
    ren = {
        "学校所在": "province",
        "年份": "year",
        "院校名称": "school",
        "院校代码": "school_code",
        "科类": "category",
        "批次": "batch",
        "专业": "major",
        "专业代码": "major_code",
        "所属专业组": "group_name",
        "专业备注": "remark",
        "选科要求": "subject_req",
        "录取人数": "admit_count",
        "最低分数": "min_score",
        "最低位次": "min_rank",
        "学校性质": "school_nature",
        "是否985": "is_985",
        "是否211": "is_211",
    }
    df = df.rename(columns=ren)

    # 必填校验
    for col in ["year", "school", "category", "major", "min_score", "province", "school_nature"]:
        if col not in df.columns:
            raise SystemExit(f"缺少必需列: {col}")

    print("[2/4] 清洗与解析选科要求 ...")
    out = pd.DataFrame()
    out["year"] = df["year"].map(to_int)
    out["school"] = df["school"].fillna("").str.strip()
    out["school_code"] = df.get("school_code", "").fillna("").str.strip()
    out["category"] = df["category"].fillna("").str.strip()
    out["batch"] = df.get("batch", "").fillna("").str.strip()
    out["major"] = df["major"].fillna("").str.strip()
    out["major_code"] = df.get("major_code", "").fillna("").str.strip()
    out["group_name"] = df.get("group_name", "").fillna("").str.strip()
    out["remark"] = df.get("remark", "").fillna("").str.strip()
    out["subject_req"] = df.get("subject_req", "").fillna("").str.strip()
    out["admit_count"] = df.get("admit_count", "").map(to_int)
    out["min_score"] = df["min_score"].map(to_int)
    out["min_rank"] = df.get("min_rank", "").map(to_int)
    out["province"] = df["province"].fillna("").str.strip()
    out["school_nature"] = df["school_nature"].fillna("").str.strip()
    out["is_985"] = (df.get("is_985", "").fillna("否").str.strip() == "是").astype(int)
    out["is_211"] = (df.get("is_211", "").fillna("否").str.strip() == "是").astype(int)

    # 解析选科
    first_list, mode_list, subj_list = [], [], []
    for req, cat in zip(out["subject_req"], out["category"]):
        f, m, s = parse_subject_req(req, cat)
        first_list.append(f)
        mode_list.append(m)
        subj_list.append(",".join(s))
    out["first_choice"] = first_list
    out["reselect_mode"] = mode_list
    out["reselect_subjects"] = subj_list

    # 中外合作标签：学校性质为合作办学，或专业备注含「中外合作」
    coop_nature = out["school_nature"].isin(
        ["中外合作办学", "内地与港澳台地区合作办学", "境外高校独立办学"]
    )
    coop_major = out["remark"].str.contains("中外合作", na=False)
    out["is_coop"] = (coop_nature | coop_major).astype(int)

    # 丢无效行
    before = len(out)
    out = out[out["min_score"].notna() & (out["school"] != "") & (out["major"] != "")]
    print(f"    丢弃无效行: {before - len(out)}")

    print("[3/4] 写入 SQLite ...")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE admission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            school TEXT NOT NULL,
            school_code TEXT,
            category TEXT,
            batch TEXT,
            major TEXT NOT NULL,
            major_code TEXT,
            group_name TEXT,
            remark TEXT,
            subject_req TEXT,
            first_choice TEXT,
            reselect_mode TEXT,
            reselect_subjects TEXT,
            admit_count INTEGER,
            min_score INTEGER NOT NULL,
            min_rank INTEGER,
            province TEXT,
            school_nature TEXT,
            is_985 INTEGER,
            is_211 INTEGER,
            is_coop INTEGER
        )
    """)
    out.to_sql("admission", conn, if_exists="append", index=False)

    # 索引
    cur.execute("CREATE INDEX idx_year_cat ON admission(year, category)")
    cur.execute("CREATE INDEX idx_school_major ON admission(school, major)")
    cur.execute("CREATE INDEX idx_province ON admission(province)")
    cur.execute("CREATE INDEX idx_score ON admission(year, min_score)")
    conn.commit()

    n = cur.execute("SELECT COUNT(*) FROM admission").fetchone()[0]
    print(f"[4/4] 完成: {db_path} 共 {n} 行")
    # 简单自检
    for row in cur.execute(
        "SELECT year, COUNT(*) FROM admission GROUP BY year ORDER BY year"
    ):
        print(f"    {row[0]}: {row[1]} 行")
    conn.close()


if __name__ == "__main__":
    main()
