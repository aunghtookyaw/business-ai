#!/usr/bin/env node

const fs = require('fs');
const QRCode = require('/opt/homebrew/lib/node_modules/npm/node_modules/qrcode-terminal/vendor/QRCode');
const QRErrorCorrectLevel = require('/opt/homebrew/lib/node_modules/npm/node_modules/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel');

const url = process.argv[2];
const destination = process.argv[3];
if (!url || !destination) {
  console.error('Usage: generate_business_os_qr.js URL OUTPUT.svg');
  process.exit(2);
}

const qr = new QRCode(-1, QRErrorCorrectLevel.M);
qr.addData(url);
qr.make();

const quietZone = 4;
const scale = 12;
const moduleCount = qr.getModuleCount();
const size = (moduleCount + quietZone * 2) * scale;
const cells = [];

for (let row = 0; row < moduleCount; row += 1) {
  for (let column = 0; column < moduleCount; column += 1) {
    if (qr.isDark(row, column)) {
      cells.push(`<rect x="${(column + quietZone) * scale}" y="${(row + quietZone) * scale}" width="${scale}" height="${scale}"/>`);
    }
  }
}

const svg = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="QR code for ${url}">`,
  `<rect width="${size}" height="${size}" fill="#fff"/>`,
  '<g fill="#000" shape-rendering="crispEdges">',
  ...cells,
  '</g>',
  '</svg>',
  '',
].join('\n');

fs.writeFileSync(destination, svg, { encoding: 'utf8', mode: 0o644 });
