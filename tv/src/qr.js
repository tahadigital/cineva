/* Mavie TV — Pure ES2018 / ES5-Safe Zero-Dependency QR Code SVG Generator
 * Implements ISO/IEC 18004 QR Code Versions 1..6 (Byte mode, ECC Level L).
 * Runs offline inside Samsung Tizen (.wgt), LG webOS (.ipk), and /tv browsers.
 */
(function (root) {
  'use strict';

  // GF(256) log/exp tables with primitive polynomial 0x11d
  var GF_EXP = new Array(512);
  var GF_LOG = new Array(256);
  (function initGalois() {
    var x = 1;
    var i;
    for (i = 0; i < 255; i++) {
      GF_EXP[i] = x;
      GF_LOG[x] = i;
      x = x << 1;
      if (x & 256) {
        x = x ^ 285;
      }
    }
    for (i = 255; i < 512; i++) {
      GF_EXP[i] = GF_EXP[i - 255];
    }
  })();

  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return GF_EXP[GF_LOG[a] + GF_LOG[b]];
  }

  function rsGeneratorPoly(ecLen) {
    var poly = [1];
    var i, j, next;
    for (i = 0; i < ecLen; i++) {
      next = new Array(poly.length + 1);
      for (j = 0; j < next.length; j++) next[j] = 0;
      for (j = 0; j < poly.length; j++) {
        next[j] ^= poly[j];
        next[j + 1] ^= gfMul(poly[j], GF_EXP[i]);
      }
      poly = next;
    }
    return poly;
  }

  function rsEncode(data, ecLen) {
    var gen = rsGeneratorPoly(ecLen);
    var res = new Array(ecLen);
    var i, j, factor;
    for (i = 0; i < ecLen; i++) res[i] = 0;
    for (i = 0; i < data.length; i++) {
      factor = data[i] ^ res[0];
      for (j = 0; j < ecLen - 1; j++) {
        res[j] = res[j + 1];
      }
      res[ecLen - 1] = 0;
      if (factor !== 0) {
        for (j = 0; j < ecLen; j++) {
          res[j] ^= gfMul(gen[j + 1], factor);
        }
      }
    }
    return res;
  }

  // QR Version specs for ECC Level L (versions 1..6, up to 134 bytes)
  // [version, size, totalDataBytes, ecPerBlock, blocks, alignPositions]
  var VERSIONS = [
    null,
    [1, 21, 19, 7, 1, []],
    [2, 25, 34, 10, 1, [6, 18]],
    [3, 29, 55, 15, 1, [6, 22]],
    [4, 33, 80, 20, 1, [6, 26]],
    [5, 37, 108, 26, 1, [6, 30]],
    [6, 41, 136, 18, 2, [6, 34]]
  ];

  // Format info strings for ECC L (01) and Mask 0..7 (precomputed BCH(15,5) ^ 0x5412)
  var FORMAT_INFO_L = [
    0x77c4, 0x72f3, 0x7daa, 0x789d, 0x662f, 0x6318, 0x6c41, 0x6976
  ];

  function toUtf8Bytes(text) {
    var str = String(text || '');
    var out = [];
    var i, code;
    for (i = 0; i < str.length; i++) {
      code = str.charCodeAt(i);
      if (code < 0x80) {
        out.push(code);
      } else if (code < 0x800) {
        out.push(0xc0 | (code >> 6));
        out.push(0x80 | (code & 0x3f));
      } else {
        out.push(0xe0 | (code >> 12));
        out.push(0x80 | ((code >> 6) & 0x3f));
        out.push(0x80 | (code & 0x3f));
      }
    }
    return out;
  }

  function pickVersion(byteLen) {
    var v;
    for (v = 1; v < VERSIONS.length; v++) {
      // Byte mode header: 4 bits mode + 8 bits length = 12 bits (+ 4 terminator = 2 bytes)
      if (byteLen <= VERSIONS[v][2] - 2) {
        return VERSIONS[v];
      }
    }
    return VERSIONS[VERSIONS.length - 1];
  }

  function buildCodewords(bytes, spec) {
    var totalData = spec[2];
    var ecPerBlock = spec[3];
    var numBlocks = spec[4];
    var maxPayload = totalData - 2;
    var trimmed = bytes.length > maxPayload ? bytes.slice(0, maxPayload) : bytes;
    var bits = [];
    var i, b;

    function pushBits(val, len) {
      for (var k = len - 1; k >= 0; k--) {
        bits.push((val >> k) & 1);
      }
    }

    // Mode 0100 (Byte), count (8 bits for v1..v6)
    pushBits(4, 4);
    pushBits(trimmed.length, 8);
    for (i = 0; i < trimmed.length; i++) {
      pushBits(trimmed[i], 8);
    }
    // Terminator up to 4 zeros
    var maxBits = totalData * 8;
    for (i = 0; i < 4 && bits.length < maxBits; i++) bits.push(0);
    while (bits.length % 8 !== 0) bits.push(0);

    var data = [];
    for (i = 0; i < bits.length; i += 8) {
      b = 0;
      for (var j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
      data.push(b);
    }
    var padIdx = 0;
    while (data.length < totalData) {
      data.push(padIdx % 2 === 0 ? 0xec : 0x11);
      padIdx++;
    }

    // Split into blocks, compute RS ECC, interleave
    var blockSize = Math.floor(totalData / numBlocks);
    var dataBlocks = [];
    var ecBlocks = [];
    for (i = 0; i < numBlocks; i++) {
      var chunk = data.slice(i * blockSize, (i + 1) * blockSize);
      dataBlocks.push(chunk);
      ecBlocks.push(rsEncode(chunk, ecPerBlock));
    }

    var codewords = [];
    for (i = 0; i < blockSize; i++) {
      for (b = 0; b < numBlocks; b++) codewords.push(dataBlocks[b][i]);
    }
    for (i = 0; i < ecPerBlock; i++) {
      for (b = 0; b < numBlocks; b++) codewords.push(ecBlocks[b][i]);
    }
    return codewords;
  }

  function createMatrix(size) {
    var m = new Array(size);
    var isFunc = new Array(size);
    var r, c;
    for (r = 0; r < size; r++) {
      m[r] = new Array(size);
      isFunc[r] = new Array(size);
      for (c = 0; c < size; c++) {
        m[r][c] = 0;
        isFunc[r][c] = false;
      }
    }
    return { m: m, isFunc: isFunc, size: size };
  }

  function setFunc(grid, r, c, val) {
    if (r >= 0 && r < grid.size && c >= 0 && c < grid.size) {
      grid.m[r][c] = val ? 1 : 0;
      grid.isFunc[r][c] = true;
    }
  }

  function drawFinder(grid, top, left) {
    var dr, dc, dist;
    for (dr = -1; dr <= 7; dr++) {
      for (dc = -1; dc <= 7; dc++) {
        dist = Math.max(Math.abs(dr - 3), Math.abs(dc - 3));
        setFunc(grid, top + dr, left + dc, dist !== 2 && dist !== 4);
      }
    }
  }

  function drawAlignment(grid, cx, cy) {
    var dr, dc, dist;
    for (dr = -2; dr <= 2; dr++) {
      for (dc = -2; dc <= 2; dc++) {
        dist = Math.max(Math.abs(dr), Math.abs(dc));
        setFunc(grid, cy + dr, cx + dc, dist !== 1);
      }
    }
  }

  function drawFormat(grid, maskIdx) {
    var bits = FORMAT_INFO_L[maskIdx];
    var size = grid.size;
    var i, bit;
    for (i = 0; i <= 5; i++) {
      bit = (bits >> i) & 1;
      setFunc(grid, 8, i, bit);
    }
    setFunc(grid, 8, 7, (bits >> 6) & 1);
    setFunc(grid, 8, 8, (bits >> 7) & 1);
    setFunc(grid, 7, 8, (bits >> 8) & 1);
    for (i = 9; i < 15; i++) {
      setFunc(grid, 14 - i, 8, (bits >> i) & 1);
    }
    for (i = 0; i < 8; i++) {
      setFunc(grid, size - 1 - i, 8, (bits >> i) & 1);
    }
    for (i = 8; i < 15; i++) {
      setFunc(grid, 8, size - 15 + i, (bits >> i) & 1);
    }
    setFunc(grid, size - 8, 8, 1);
  }

  function encodeMatrix(text) {
    var bytes = toUtf8Bytes(text);
    var spec = pickVersion(bytes.length);
    var size = spec[1];
    var align = spec[5];
    var codewords = buildCodewords(bytes, spec);
    var grid = createMatrix(size);
    var i, j, r, c;

    drawFinder(grid, 0, 0);
    drawFinder(grid, 0, size - 7);
    drawFinder(grid, size - 7, 0);

    for (i = 0; i < size; i++) {
      if (!grid.isFunc[6][i]) setFunc(grid, 6, i, i % 2 === 0);
      if (!grid.isFunc[i][6]) setFunc(grid, i, 6, i % 2 === 0);
    }

    for (i = 0; i < align.length; i++) {
      for (j = 0; j < align.length; j++) {
        if ((i === 0 && j === 0) || (i === 0 && j === align.length - 1) || (i === align.length - 1 && j === 0)) {
          continue;
        }
        drawAlignment(grid, align[i], align[j]);
      }
    }

    // Reserve format area before placing data bits
    var maskIdx = 0; // (r + c) % 2 === 0
    drawFormat(grid, maskIdx);

    // Place data bits in upward/downward zig-zag columns
    var bitIndex = 0;
    var totalBits = codewords.length * 8;
    var upward = true;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) {
        r = upward ? (size - 1 - vert) : vert;
        for (j = 0; j < 2; j++) {
          c = right - j;
          if (!grid.isFunc[r][c]) {
            var bit = 0;
            if (bitIndex < totalBits) {
              bit = (codewords[bitIndex >> 3] >> (7 - (bitIndex & 7))) & 1;
              bitIndex++;
            }
            if ((r + c) % 2 === 0) {
              bit = bit ^ 1;
            }
            grid.m[r][c] = bit;
          }
        }
      }
      upward = !upward;
    }

    return grid.m;
  }

  function toSvg(text, options) {
    var opts = options || {};
    var matrix = encodeMatrix(text);
    var size = matrix.length;
    var quiet = typeof opts.quiet === 'number' ? opts.quiet : 3;
    var total = size + quiet * 2;
    var fg = opts.fg || '#090D18';
    var bg = opts.bg || '#FFFFFF';
    var parts = [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + total + ' ' + total + '" shape-rendering="crispEdges" role="img" aria-label="QR kod">',
      '<rect width="' + total + '" height="' + total + '" fill="' + bg + '"/>',
      '<path fill="' + fg + '" d="'
    ];
    var r, c;
    for (r = 0; r < size; r++) {
      for (c = 0; c < size; c++) {
        if (matrix[r][c]) {
          parts.push('M' + (c + quiet) + ',' + (r + quiet) + 'h1v1h-1z');
        }
      }
    }
    parts.push('"/></svg>');
    return parts.join('');
  }

  var api = {
    encodeMatrix: encodeMatrix,
    toSvg: toSvg
  };

  root.MavieQR = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : this);
