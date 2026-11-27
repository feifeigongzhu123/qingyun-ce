const fs = require("fs");
const path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "frontend", "index.html"), "utf8");
// 提取所有内联 <script>（无 src）内容
const re = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m, n = 0, ok = true;
while ((m = re.exec(html))) {
  n++;
  const code = m[1];
  try {
    new Function(code); // 仅编译，不执行
    console.log(`内联脚本 #${n}: 语法 OK (${code.length} 字符)`);
  } catch (e) {
    ok = false;
    console.log(`内联脚本 #${n}: 语法错误 -> ${e.message}`);
  }
}
// 额外校验 query.js 能被解析
try { new Function(fs.readFileSync(path.join(__dirname, "..", "frontend", "query.js"), "utf8")); console.log("query.js: 语法 OK"); }
catch (e) { ok = false; console.log("query.js: 语法错误 ->", e.message); }
process.exit(ok ? 0 : 1);
