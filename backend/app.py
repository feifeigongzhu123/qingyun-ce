# -*- coding: utf-8 -*-
"""
青云策 · 辽宁高考志愿查询后端

启动:
    python -m uvicorn app:app --host 127.0.0.1 --port 8000
或:
    python app.py

接口:
    GET  /api/meta          下拉框/筛选项元数据
    POST /api/query         核心查询（学年分数匹配 + 历年参考）
    GET  /                  前端页面
"""
import os
import sqlite3
from collections import defaultdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.environ.get("QYCE_DB", os.path.join(ROOT_DIR, "db", "qingyun.db"))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
FRONTEND = os.path.join(FRONTEND_DIR, "index.html")

FIRST_TO_CATEGORY = {"物理": "物理类", "历史": "历史类"}
RESELECT_OPTIONS = ["化学", "生物", "思想政治", "地理"]

app = FastAPI(title="青云策 · 辽宁志愿查询", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- 选科资格判断 ----------------
def is_eligible(row, first, reselect_set):
    fc = row["first_choice"]
    if fc not in ("不限", first):
        return False
    mode = row["reselect_mode"]
    if mode == "none":
        return True
    subjects = [s for s in (row["reselect_subjects"] or "").split(",") if s]
    if not subjects:
        return True
    if mode == "any":
        return any(s in reselect_set for s in subjects)
    if mode == "all":
        return all(s in reselect_set for s in subjects)
    return True


# ---------------- 元数据 ----------------
@app.get("/api/meta")
def meta():
    conn = get_conn()
    try:
        years = [r[0] for r in conn.execute("SELECT DISTINCT year FROM admission ORDER BY year DESC")]
        provinces = [r[0] for r in conn.execute(
            "SELECT province FROM admission GROUP BY province ORDER BY COUNT(*) DESC")]
        natures = [r[0] for r in conn.execute(
            "SELECT school_nature FROM admission GROUP BY school_nature ORDER BY COUNT(*) DESC")]
        batches = [r[0] for r in conn.execute(
            "SELECT batch FROM admission GROUP BY batch ORDER BY COUNT(*) DESC")]
    finally:
        conn.close()
    return {
        "years": years,
        "provinces": provinces,
        "natures": natures,
        "batches": batches,
        "reselect_options": RESELECT_OPTIONS,
        "first_options": ["物理", "历史"],
    }


# ---------------- 查询请求 ----------------
class QueryBody(BaseModel):
    year: int
    score: int
    first: str = Field(..., description="首选：物理/历史")
    reselect: list[str] = Field(default_factory=list, description="再选2门")
    province: list[str] = Field(default_factory=list)
    nature: list[str] = Field(default_factory=list)
    coop_only: bool = False
    exclude_coop: bool = False
    feat_985: bool = False
    feat_211: bool = False
    batch: list[str] = Field(default_factory=list)
    major_keyword: str = ""
    band: str = "all"           # all | strict | chong | wen | bao
    margin: int = 15
    limit: int = 100


def load_history(conn, pairs, category):
    """pairs: set[(school, major)] -> { (school,major): [ {year, score_min, score_max, rank_min, rank_max, count} ] }"""
    if not pairs:
        return {}
    clauses = []
    params = [category]
    for school, major in pairs:
        clauses.append("(school=? AND major=?)")
        params.extend([school, major])
    sql = (
        "SELECT school, major, year, MIN(min_score) smin, MAX(min_score) smax,"
        " MIN(min_rank) rmin, MAX(min_rank) rmax, COUNT(*) cnt "
        "FROM admission WHERE category=? AND (" + " OR ".join(clauses) + ") "
        "GROUP BY school, major, year ORDER BY year"
    )
    out = defaultdict(list)
    for r in conn.execute(sql, params):
        out[(r["school"], r["major"])].append({
            "year": r["year"],
            "score_min": r["smin"],
            "score_max": r["smax"],
            "rank_min": r["rmin"],
            "rank_max": r["rmax"],
            "count": r["cnt"],
        })
    return out


@app.post("/api/query")
def query(body: QueryBody):
    category = FIRST_TO_CATEGORY.get(body.first)
    if not category:
        return {"error": "首选科目必须是 物理 或 历史", "items": [], "total": 0}
    reselect_set = set(body.reselect or [])

    # --- 基础 SQL 过滤（能下推的都下推） ---
    where = ["year=?", "category=?"]
    params = [body.year, category]
    if body.province:
        where.append("province IN (%s)" % ",".join("?" * len(body.province)))
        params.extend(body.province)
    if body.nature:
        where.append("school_nature IN (%s)" % ",".join("?" * len(body.nature)))
        params.extend(body.nature)
    if body.coop_only:
        where.append("is_coop=1")
    if body.exclude_coop:
        where.append("is_coop=0")
    if body.feat_985:
        where.append("is_985=1")
    if body.feat_211:
        where.append("is_211=1")
    if body.batch:
        where.append("batch IN (%s)" % ",".join("?" * len(body.batch)))
        params.extend(body.batch)
    if body.major_keyword:
        where.append("major LIKE ?")
        params.append(f"%{body.major_keyword.strip()}%")

    sql = (
        "SELECT id, school, school_code, category, batch, major, major_code, remark, "
        "subject_req, first_choice, reselect_mode, reselect_subjects, admit_count, "
        "min_score, min_rank, province, school_nature, is_985, is_211, is_coop "
        "FROM admission WHERE " + " AND ".join(where)
    )

    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()

        margin = max(0, body.margin)
        scored = []
        for r in rows:
            if not is_eligible(r, body.first, reselect_set):
                continue
            diff = body.score - (r["min_score"] or 0)  # 我比最低分高多少
            if diff < -margin:          # 明显够不着
                continue
            if diff < 0:
                band = "冲"
            elif diff <= margin:
                band = "稳"
            else:
                band = "保"

            if body.band == "strict" and diff < 0:
                continue
            if body.band in ("chong", "wen", "bao"):
                if band != {"chong": "冲", "wen": "稳", "bao": "保"}[body.band]:
                    continue

            scored.append((band, diff, r))

        total = len(scored)
        band_order = {"冲": 0, "稳": 1, "保": 2}

        # 按档位分组，组内按最低位次从优（位次小=更好），位次缺失排后
        by_band = {"冲": [], "稳": [], "保": []}
        for item in scored:
            by_band[item[0]].append(item)
        for b in by_band:
            by_band[b].sort(key=lambda x: (x[2]["min_rank"] is None, x[2]["min_rank"] or 0))

        # 选前 limit 条：单一档位直接截断；冲稳保则跨档轮转，保证三档都出现
        if body.band in ("chong", "wen", "bao"):
            one = {"chong": "冲", "wen": "稳", "bao": "保"}[body.band]
            selected = by_band[one][: body.limit]
        else:
            selected = []
            idx = {b: 0 for b in by_band}
            active = [b for b in ("冲", "稳", "保") if by_band[b]]
            while len(selected) < body.limit:
                progressed = False
                for b in active:
                    if len(selected) >= body.limit:
                        break
                    if idx[b] < len(by_band[b]):
                        selected.append(by_band[b][idx[b]])
                        idx[b] += 1
                        progressed = True
                if not progressed:
                    break

        # 展示时按 冲→稳→保 分档，档内按位次排序
        selected.sort(key=lambda x: (band_order[x[0]], x[2]["min_rank"] is None, x[2]["min_rank"] or 0))
        top = selected

        pairs = {(r["school"], r["major"]) for _, _, r in top}
        history = load_history(conn, pairs, category)

        items = []
        for band, diff, r in top:
            items.append({
                "school": r["school"],
                "school_code": r["school_code"],
                "major": r["major"],
                "major_code": r["major_code"],
                "remark": r["remark"],
                "batch": r["batch"],
                "subject_req": r["subject_req"],
                "admit_count": r["admit_count"],
                "min_score": r["min_score"],
                "min_rank": r["min_rank"],
                "diff": diff,
                "band": band,
                "province": r["province"],
                "school_nature": r["school_nature"],
                "is_985": r["is_985"],
                "is_211": r["is_211"],
                "is_coop": r["is_coop"],
                "history": history.get((r["school"], r["major"]), []),
            })

        band_count = {"冲": 0, "稳": 0, "保": 0}
        for b, _, _ in scored:
            band_count[b] += 1

        return {
            "year": body.year,
            "category": category,
            "total": total,
            "returned": len(items),
            "band_count": band_count,
            "items": items,
        }
    finally:
        conn.close()


@app.get("/")
def index():
    if os.path.exists(FRONTEND):
        return FileResponse(FRONTEND)
    return {"error": "前端页面不存在", "path": FRONTEND}


# 前端已改为纯静态（读取 data.json），让本地后端也能托管这些静态文件
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
