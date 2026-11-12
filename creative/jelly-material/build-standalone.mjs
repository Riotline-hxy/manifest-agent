// 把设计稿打包成一个单独的 html：引擎直接塞进页面里，双击就能打开，也能直接发给别人。
//   node creative/jelly-material/build-standalone.mjs
// 页面平时引用的是 demo/public/js/jelly.js；浏览器不允许双击打开的网页再去读别的 js 文件，所以要这一步。
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const page = readFileSync(join(here, 'index.html'), 'utf8');
const engine = readFileSync(join(here, '../../demo/public/js/jelly.js'), 'utf8')
  .replace(/^export \{[^}]*\};?\s*$/gm, '')
  .replace(/^export (const|let|function|class) /gm, '$1 ');

const re = /^import \{([^}]+)\} from '\.\.\/\.\.\/demo\/public\/js\/jelly\.js';$/m;
const m = page.match(re);
if (!m) throw new Error('index.html 里没找到 jelly.js 的 import');
const names = m[1].trim();
const inlined = `const { ${names} } = (() => {\n${engine}\nreturn { ${names} };\n})();`;
const out = join(here, '小光果冻-质感和形状.html');
writeFileSync(out, page.replace(re, () => inlined));
console.log('wrote', out);
