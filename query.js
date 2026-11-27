/*
 * 青云策 · 纯前端查询逻辑（无后端，按历年录取分对照，不做预测/分档）
 * 浏览器: <script src="query.js"></script> 后使用 window.QYCE
 * Node:   const QYCE = require('./query.js')
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.QYCE = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var FIRST_TO_CATEGORY = { "物理": "物理类", "历史": "历史类" };
  var KW_SPLIT = /[,，、;；\s]+/;

  function tokens(s) {
    if (Array.isArray(s)) return s.map(function (t) { return String(t).trim(); }).filter(Boolean);
    return String(s || "").split(KW_SPLIT).map(function (t) { return t.trim(); }).filter(Boolean);
  }
  function matchTags(val, toks, set) {
    if (!toks.length) return true;
    var v = String(val || "");
    for (var i = 0; i < toks.length; i++) {
      var t = toks[i];
      if (set && set.has(t)) { if (v === t) return true; }
      else if (v.indexOf(t) !== -1) return true;
    }
    return false;
  }
  function matchSub(val, toks) {
    if (!toks.length) return false;
    var v = String(val || "");
    for (var i = 0; i < toks.length; i++) if (v.indexOf(toks[i]) !== -1) return true;
    return false;
  }

  // 把备注归一成一个稳定的"方向键"，用于跨年匹配同一专业方向
  function remarkKey(raw) {
    var s = String(raw || "").trim();
    if (!s) return "";
    var special = s.indexOf("专项计划") !== -1 ? "|专项" : "";
    if (s.indexOf("中外合作") !== -1) {
      var m = s.match(/与\s*([^）);；]+?)(大学|学院)/);
      return "中外合作|" + (m ? m[1] : "") + special;
    }
    var mm = s.match(/[（(]([^）)]+)[）)]/);
    var core = mm ? mm[1] : s;
    core = core.replace(/[（()）]/g, "").trim();
    if (core.indexOf("、") !== -1) core = core.split("、")[0];
    core = core.replace(/(方向|专业)$/, "").trim();
    return core + special;
  }

  function buildIndex(json) {
    var columns = json.columns;
    var numeric = new Set(json.numeric || []);
    var cat = json.cat || {};
    var ix = {};
    columns.forEach(function (c, i) { ix[c] = i; });

    var rows = new Array(json.rows.length);
    for (var i = 0; i < json.rows.length; i++) {
      var src = json.rows[i];
      var out = new Array(src.length);
      for (var j = 0; j < src.length; j++) {
        var c = columns[j];
        out[j] = numeric.has(c) ? src[j] : (cat[c] ? cat[c][src[j]] : src[j]);
      }
      rows[i] = out;
    }

    var hist = new Map();
    for (var k = 0; k < rows.length; k++) {
      var r = rows[k];
      var key = r[ix.category] + "|" + r[ix.school] + "|" + r[ix.major] + "|" + remarkKey(r[ix.remark]);
      var m = hist.get(key);
      if (!m) { m = {}; hist.set(key, m); }
      var y = r[ix.year];
      var sc = r[ix.min_score], rk = r[ix.min_rank];
      var st = m[y];
      if (!st) { st = m[y] = { year: y, s_min: sc, s_max: sc, r_min: rk, r_max: rk, count: 0 }; }
      if (sc < st.s_min) st.s_min = sc;
      if (sc > st.s_max) st.s_max = sc;
      if (rk != null) {
        st.r_min = (st.r_min == null) ? rk : Math.min(st.r_min, rk);
        st.r_max = (st.r_max == null) ? rk : Math.max(st.r_max, rk);
      }
      st.count++;
    }

    function countBy(col) {
      var mp = new Map();
      for (var t = 0; t < rows.length; t++) {
        var v = rows[t][ix[col]];
        mp.set(v, (mp.get(v) || 0) + 1);
      }
      return Array.from(mp.entries()).sort(function (a, b) { return b[1] - a[1]; }).map(function (e) { return e[0]; });
    }
    var years = Array.from(new Set(rows.map(function (r) { return r[ix.year]; }))).sort(function (a, b) { return b - a; });
    var schools = Array.from(new Set(rows.map(function (r) { return r[ix.school]; }))).sort();
    var majors = Array.from(new Set(rows.map(function (r) { return r[ix.major]; }))).sort();
    var byProv = {};
    for (var t2 = 0; t2 < rows.length; t2++) {
      var rr = rows[t2], pv = rr[ix.province];
      if (!byProv[pv]) byProv[pv] = {};
      byProv[pv][rr[ix.school]] = 1;
    }
    var schoolsByProvince = {};
    Object.keys(byProv).forEach(function (p) { schoolsByProvince[p] = Object.keys(byProv[p]).sort(); });

    return {
      ix: ix, rows: rows, hist: hist,
      schoolSet: new Set(schools), majorSet: new Set(majors),
      meta: {
        years: years, latestYear: years[0],
        provinces: countBy("province"), natures: countBy("school_nature"), batches: countBy("batch"),
        schools: schools, majors: majors, schoolsByProvince: schoolsByProvince,
        reselect_options: ["化学", "生物", "思想政治", "地理"],
        first_options: ["物理", "历史"]
      }
    };
  }

  function isEligible(r, ix, first, set) {
    var fc = r[ix.first_choice];
    if (fc !== "不限" && fc !== first) return false;
    var mode = r[ix.reselect_mode];
    if (mode === "none") return true;
    var subs = (r[ix.reselect_subjects] || "").split(",").filter(Boolean);
    if (subs.length === 0) return true;
    if (mode === "any") return subs.some(function (s) { return set.has(s); });
    if (mode === "all") return subs.every(function (s) { return set.has(s); });
    return true;
  }

  function query(ds, p) {
    var ix = ds.ix, rows = ds.rows, hist = ds.hist;
    var category = FIRST_TO_CATEGORY[p.first];
    if (!category) return { error: "首选科目必须是 物理 或 历史", items: [], total: 0 };

    var reselect = new Set(p.reselect || []);
    var noRange = (p.margin === -1);   // -1 = 不加减（不限分数区间）
    var margin = noRange ? 0 : Math.max(0, p.margin == null ? 15 : p.margin);
    var limit = Math.min(500, p.limit == null ? 100 : p.limit);   // 最多抽取 500 条
    var schoolToks = tokens(p.school_keyword);
    var majorInc = tokens(p.major_include != null ? p.major_include : p.major_keyword);
    var majorExc = tokens(p.major_exclude);
    var schoolSet = ds.schoolSet;
    var provinceSet = (p.province && p.province.length) ? new Set(p.province) : null;
    var natureSet = (p.nature && p.nature.length) ? new Set(p.nature) : null;
    var batchSet = (p.batch && p.batch.length) ? new Set(p.batch) : null;

    var scored = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r[ix.year] !== p.year) continue;
      if (r[ix.category] !== category) continue;
      if (provinceSet && !provinceSet.has(r[ix.province])) continue;
      if (natureSet && !natureSet.has(r[ix.school_nature])) continue;
      if (batchSet && !batchSet.has(r[ix.batch])) continue;
      if (p.coop_only && !r[ix.is_coop]) continue;
      if (p.exclude_coop && r[ix.is_coop]) continue;
      if (p.feat_985 && !r[ix.is_985]) continue;
      if (p.feat_211 && !r[ix.is_211]) continue;
      if (!matchTags(r[ix.school], schoolToks, schoolSet)) continue;
      if (majorInc.length && !matchSub(r[ix.major], majorInc)) continue;
      if (majorExc.length && matchSub(r[ix.major], majorExc)) continue;
      if (!isEligible(r, ix, p.first, reselect)) continue;

      var diff = p.score - r[ix.min_score];
      if (noRange) {
        if (diff < 0) continue;              // 不加减：只列"能上的"（最低分 ≤ 我的分数）
      } else if (Math.abs(diff) > margin) {
        continue;                            // ±N：最低分落在 [我的分-N, 我的分+N]
      }
      scored.push({ diff: diff, r: r });
    }

    var total = scored.length;
    scored.sort(function (x, y) {
      var d = y.r[ix.min_score] - x.r[ix.min_score];
      if (d) return d;
      var rx = x.r[ix.min_rank], ry = y.r[ix.min_rank];
      if (rx == null && ry == null) return 0;
      if (rx == null) return 1;
      if (ry == null) return -1;
      return rx - ry;
    });

    // 按最低分从高到低取前 limit 条（不做抽样，避免漏掉区间内的院校）
    var selected = scored.slice(0, limit);
    selected.sort(function (x, y) {
      var d = y.r[ix.min_score] - x.r[ix.min_score];
      if (d) return d;
      var rx = x.r[ix.min_rank], ry = y.r[ix.min_rank];
      if (rx == null && ry == null) return 0;
      if (rx == null) return 1;
      if (ry == null) return -1;
      return rx - ry;
    });

    var items = selected.map(function (it) {
      var r = it.r;
      var key = r[ix.category] + "|" + r[ix.school] + "|" + r[ix.major] + "|" + remarkKey(r[ix.remark]);
      var hm = hist.get(key) || {};
      var history = Object.keys(hm).map(function (y) { return hm[y]; })
        .sort(function (a, b) { return b.year - a.year; })
        .map(function (s) {
          return { year: s.year, score_min: s.s_min, score_max: s.s_max, rank_min: s.r_min, rank_max: s.r_max, count: s.count };
        });
      return {
        school: r[ix.school], major: r[ix.major], major_code: r[ix.major_code], remark: r[ix.remark],
        batch: r[ix.batch], subject_req: r[ix.subject_req],
        min_score: r[ix.min_score], min_rank: r[ix.min_rank], diff: it.diff,
        province: r[ix.province], school_nature: r[ix.school_nature],
        is_985: r[ix.is_985], is_211: r[ix.is_211], is_coop: r[ix.is_coop],
        history: history
      };
    });

    return { year: p.year, category: category, total: total, returned: items.length, items: items };
  }

  return { buildIndex: buildIndex, query: query, FIRST_TO_CATEGORY: FIRST_TO_CATEGORY };
});
