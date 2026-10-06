// Optional developer utility; the extension ships PNGs and needs no renderer.
// Install: npm install --prefix work/icon-tools --ignore-scripts --save-exact @resvg/resvg-js@2.6.2
// Run: node scripts/render_icons.cjs
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const { Resvg } = require(path.join(root, "work/icon-tools/node_modules/@resvg/resvg-js"));
const svg = fs.readFileSync(path.join(root, "site/icon.svg"));
fs.mkdirSync(path.join(root, "extension/icons"), { recursive: true });
for (const size of [16, 32, 48, 128, 256]) {
  const target = size === 256 ? "site/icon.png" : `extension/icons/${size}.png`;
  const png = new Resvg(svg, {
    fitTo: { mode: "width", value: size },
    font: { loadSystemFonts: false },
  }).render().asPng();
  fs.writeFileSync(path.join(root, target), png);
  console.log(`${target}: ${png.length} bytes`);
}
