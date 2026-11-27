const fs = require("fs");
const path = require("path");
const QYCE = require(path.join(__dirname, "..", "frontend", "query.js"));
const json = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "frontend", "data.json"), "utf8"));
const ds = QYCE.buildIndex(json);

const MED = ["临床医学","口腔","护理","药学","医学","中医","麻醉","预防","康复","影像","检验"];
const CS = ["计算机","软件","数据科学","人工智能","物联网","信息安全","网络工程","数字媒体"];

const base = { year: ds.meta.latestYear, score: 560, first: "物理", reselect: ["化学","生物"], limit: 100, margin: 15, band: "all",
  batch: ["本科批","本科批一段","本科第一阶段"] };

function run(name, ov){
  const r = QYCE.query(ds, Object.assign({}, base, ov));
  console.log(`\n--- ${name} ---\n total=${r.total} returned=${r.returned} band=${JSON.stringify(r.band_count)}`);
  r.items.slice(0,3).forEach(i=>console.log(`  [${i.band}] ${i.school} - ${i.major} ${i.min_score}分`));
  return r;
}
run("默认本科批");
const rInc = run("包含计算机", { major_include: CS });
const rExc = run("排除医学", { major_exclude: MED });
// 校验：排除医学后，前100里不应出现含“医学/临床/护理”的
const bad = rExc.items.filter(i => MED.some(k => i.major.indexOf(k) !== -1));
console.log("  排除医学校验：仍含医学类 =", bad.length);
// 校验包含计算机：前100应都含计算机相关关键词
const bad2 = rInc.items.filter(i => !CS.some(k => i.major.indexOf(k) !== -1));
console.log("  包含计算机校验：非计算机 =", bad2.length);
run("包含计算机 + 排除医学", { major_include: CS, major_exclude: MED });
