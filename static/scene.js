// The scene strip: a picture of where the player stands, drawn from the snapshot alone.
// Every fact is a word the engine chose; this file turns words into shapes (docs/architecture/ui-layout.md).
"use strict";
const drawScene = (() => {
const NS = "http://www.w3.org/2000/svg";
const W = 1000, H = 200, HORIZON = 150;
const BLOOD = "#4d0b08", BLOOD_FRESH = "#6e1410", BONE = "#b9ae94", SCAB = "#1c1715";
const WARM_RIM = "#e3ad6c", LAMP = "#ffcf86", GRASS = "#4a5638", WOOD = "#5d4a38";
// Colour grade per stage: the world loses its colour as it falls apart.
const STAGE_GRADE = ["saturate(.95) contrast(1.02)", "saturate(.86) contrast(1.04)", "saturate(.76) contrast(1.06)", "saturate(.62) sepia(.18) contrast(1.0)"];

const PALETTES = {
    morning:   { sky0: "#68737c", sky1: "#b4a083", far: "#5b636a", mid: "#434950", near: "#2c3035", ground: "#26282a", wall: "#4b4842", floor: "#2a2622", fig: "#121212", rim: "#d6bf9b", fog: "#b3b0a6", cloud: "#97928a", star: "#fff" },
    afternoon: { sky0: "#758591", sky1: "#b1b7b0", far: "#666f75", mid: "#4b5359", near: "#353a40", ground: "#303337", wall: "#57544c", floor: "#332e29", fig: "#151617", rim: "#dfe2da", fog: "#c3c5be", cloud: "#b3b6b1", star: "#fff" },
    evening:   { sky0: "#27262f", sky1: "#9b5a3c", far: "#453a3a", mid: "#30272a", near: "#211c1d", ground: "#191516", wall: "#372d29", floor: "#1f1917", fig: "#0b0909", rim: "#d98a58", fog: "#86766f", cloud: "#674f4b", star: "#ffe" },
    night:     { sky0: "#05070a", sky1: "#1a1f25", far: "#13171b", mid: "#0d1013", near: "#090b0d", ground: "#08090a", wall: "#121212", floor: "#0a0a0a", fig: "#020202", rim: "#7c8894", fog: "#3a3f45", cloud: "#1e2328", star: "#d9e0ea" },
};
// Indoors at night is dim, never black, until a light mechanic says otherwise.
const DIM_ROOM = { wall: "#24252a", floor: "#141417", near: "#101114", mid: "#1b1c20", fig: "#050505" };

const DISTANCE = {
    "on you":  { scale: 1.95, base: 252, band: [400, 600] },
    "close":   { scale: 1.15, base: 205, band: [250, 750] },
    "nearby":  { scale: 0.72, base: 182, band: [230, 770] },
    "far off": { scale: 0.42, base: 166, band: [230, 770] },
};
const DISTANCE_ORDER = ["far off", "nearby", "close", "on you"];
// Threat state_word -> how the figure is drawn. "none" draws no figure (its barrier already thumps).
const POSTURE = {
    "hasn't noticed you": "idle",
    "turning toward the noise": "alerted",
    "coming at you": "chasing",
    "coming at you fast": "chasing-fast",
    "attacking you": "attacking",
    "right behind you": "behind",
    "down": "down",
    "pounding": "none",
    "crawling": "crawl",
    "crawling toward the noise": "crawl",
    "crawling toward you": "crawl-chase",
};
const BEHIND_BARRIER = /^behind the /;
const STAGE_LEVEL = { normal: 0, panic: 1, collapse: 2, abandoned: 3 };
const SETTING_NAMES = { apartment: "apartment", hallway: "hallway", street: "street", neighborhood: "neighborhood", store: "store", clinic: "clinic" };
const TIME_WORDS = { morning: "morning", afternoon: "afternoon", evening: "evening", night: "night" };
const SKY_WORDS = { clear: "clear", "some clouds": "some clouds", overcast: "overcast" };
const FOG_WORDS = { none: "none", light: "light", thick: "thick" };
const FALLING_WORDS = { none: "none", rain: "rain", snow: "snow" };
const STRENGTH_WORDS = { light: "light", steady: "steady", heavy: "heavy", storm: "storm" };
const INDOOR_SETTINGS = ["apartment", "hallway", "store", "clinic"];
const STORAGE_HIDDEN = "scene.hidden";
const STORAGE_BLOOD = "scene.blood";

const warned = new Set();
// A word missing from a table draws the table's default and says so once.
function lookup(table, word, fallback, what) {
    if (Object.hasOwn(table, word)) return table[word];
    const key = what + ":" + word;
    if (!warned.has(key)) {
        warned.add(key);
        console.warn(`scene: no drawing for ${what} "${word}"; drawing the default`);
    }
    return fallback;
}
// Disposition band -> how a person stands.
const STANCE = { loyal: "open", friendly: "open", neutral: "pockets", wary: "crossed", hostile: "squared", hated: "squared", terrified: "cower" };

function hash(text) {
    let h = 2166136261;
    for (const ch of String(text)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
    return h >>> 0;
}
function rng(seed) {
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function el(tag, attrs, parent) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null && v !== "") node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
}
const pick = (r, list) => list[Math.floor(r() * list.length)];
const f = (n) => n.toFixed(1);

let uidCounter = 0;
let blood = "full";

// ---------------------------------------------------------------- the scene

function paint(host, snap) {
    const uid = "s" + (++uidCounter);
    const falling = lookup(FALLING_WORDS, snap.scene.falling, "none", "falling");
    const scene = {
        ...snap.scene,
        setting: lookup(SETTING_NAMES, snap.scene.setting, "street", "setting"),
        sky: lookup(SKY_WORDS, snap.scene.sky, "clear", "sky"),
        fog: lookup(FOG_WORDS, snap.scene.fog, "none", "fog"),
        falling,
        falling_strength: falling === "none" ? "" : lookup(STRENGTH_WORDS, snap.scene.falling_strength, "steady", "falling strength"),
    };
    const timeOfDay = lookup(TIME_WORDS, snap.time_of_day, "afternoon", "time of day");
    const indoors = INDOOR_SETTINGS.includes(scene.setting);
    const L = lookup(STAGE_LEVEL, scene.stage, 0, "stage");
    const night = timeOfDay === "night";
    const base = PALETTES[timeOfDay];
    let P = base;
    if (indoors && night) P = { ...P, ...DIM_ROOM };
    const ctx = { P, uid, scene, snap, indoors, L, night, dusk: night || timeOfDay === "evening",
        gore: blood === "full", grime: L >= 1 ? `url(#${uid}grime)` : null };
    ctx.lampsOn = L === 0 && ctx.dusk;

    host.querySelector("svg")?.remove();
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid slice", style: `filter: ${STAGE_GRADE[L]}` });
    host.prepend(svg);
    ctx.defs = el("defs", {}, svg);
    buildDefs(ctx);

    const window_ = indoors ? WINDOWS[scene.setting] : null;
    let outsideClip = null;
    if (window_) {
        const clip = el("clipPath", { id: uid + "win" }, ctx.defs);
        el("rect", { x: window_.x, y: window_.y, width: window_.w, height: window_.h }, clip);
        outsideClip = `url(#${uid}win)`;
    }

    const outside = el("g", outsideClip ? { "clip-path": outsideClip } : {}, svg);
    drawSky(outside, ctx);
    if (indoors) {
        drawSkyline(outside, ctx, 128, hash(scene.setting), base.far);
        drawWeather(outside, ctx);
        drawFog(outside, ctx, 0, H);
        SETTINGS[scene.setting](svg, ctx, window_);
    } else {
        SETTINGS[scene.setting](svg, ctx);
        if (scene.falling === "rain") wetGround(svg, ctx);
        drawFog(svg, ctx, 60, 150);
    }

    drawBodies(svg, ctx, snap.corpses || []);
    drawActors(svg, ctx, snap.threats || [], snap.npcs || []);

    if (!indoors) drawWeather(svg, ctx);
    if (!indoors) drawFog(svg, ctx, 110, 90, true);

    if (scene.falling_strength === "storm") {
        el("rect", { class: "lightning", x: 0, y: 0, width: W, height: H, fill: "#fff", opacity: 0, style: indoors ? "fill-opacity: .35" : "" }, svg);
    }

    const heard = (snap.threats || []).some((t) => !t.id);
    el("rect", { x: 0, y: 0, width: W, height: H, fill: `url(#${uid}vig)`, opacity: heard ? 1 : (L === 0 ? .4 : .7) }, svg);
    if (heard) el("rect", { x: 0, y: 0, width: W, height: H, fill: `url(#${uid}edge)` }, svg);
    if (L >= 1) {
        const grain = el("g", { class: "grain" }, svg);
        el("rect", { x: -20, y: -20, width: W + 40, height: H + 40, filter: `url(#${uid}grain)`, opacity: .1 + L * .04, style: "mix-blend-mode: overlay" }, grain);
    }
}

function buildDefs({ P, uid, defs }) {
    const sky = el("linearGradient", { id: uid + "sky", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": P.sky0 }, sky);
    el("stop", { offset: "1", "stop-color": P.sky1 }, sky);

    const vig = el("radialGradient", { id: uid + "vig", cx: ".5", cy: ".5", r: ".72" }, defs);
    el("stop", { offset: ".45", "stop-color": "#000", "stop-opacity": "0" }, vig);
    el("stop", { offset: "1", "stop-color": "#000", "stop-opacity": ".85" }, vig);
    const edge = el("radialGradient", { id: uid + "edge", cx: ".5", cy: ".5", r: ".7" }, defs);
    el("stop", { offset: ".55", "stop-color": "#2a0302", "stop-opacity": "0" }, edge);
    el("stop", { offset: "1", "stop-color": "#2a0302", "stop-opacity": ".8" }, edge);

    const fog = el("linearGradient", { id: uid + "fog", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": P.fog, "stop-opacity": "0" }, fog);
    el("stop", { offset: ".6", "stop-color": P.fog, "stop-opacity": "1" }, fog);
    el("stop", { offset: "1", "stop-color": P.fog, "stop-opacity": ".6" }, fog);

    const wet = el("linearGradient", { id: uid + "wet", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": P.sky1, "stop-opacity": ".35" }, wet);
    el("stop", { offset: "1", "stop-color": P.sky1, "stop-opacity": "0" }, wet);

    const glow = el("radialGradient", { id: uid + "lamp", cx: ".5", cy: ".5", r: ".5" }, defs);
    el("stop", { offset: "0", "stop-color": LAMP, "stop-opacity": ".55" }, glow);
    el("stop", { offset: "1", "stop-color": LAMP, "stop-opacity": "0" }, glow);
    const cone = el("linearGradient", { id: uid + "cone", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": LAMP, "stop-opacity": ".45" }, cone);
    el("stop", { offset: "1", "stop-color": LAMP, "stop-opacity": ".05" }, cone);
    const fire = el("linearGradient", { id: uid + "fire", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": "#c4502a", "stop-opacity": "0" }, fire);
    el("stop", { offset: "1", "stop-color": "#c4502a", "stop-opacity": ".45" }, fire);
    const city = el("linearGradient", { id: uid + "city", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": LAMP, "stop-opacity": "0" }, city);
    el("stop", { offset: "1", "stop-color": LAMP, "stop-opacity": ".28" }, city);

    const grime = el("filter", { id: uid + "grime", x: "-5%", y: "-5%", width: "110%", height: "110%" }, defs);
    el("feTurbulence", { type: "fractalNoise", baseFrequency: "0.01 0.045", numOctaves: 4, seed: 4, result: "n" }, grime);
    el("feColorMatrix", { in: "n", type: "matrix", values: "0 0 0 0 0.025  0 0 0 0 0.018  0 0 0 0 0.01  1.3 0 0 0 -0.6", result: "stain" }, grime);
    el("feComposite", { in: "stain", in2: "SourceAlpha", operator: "in", result: "stainIn" }, grime);
    el("feTurbulence", { type: "fractalNoise", baseFrequency: "0.55", numOctaves: 1, seed: 9, result: "fine" }, grime);
    el("feColorMatrix", { in: "fine", type: "matrix", values: "0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.4 0 0 0 -1.62", result: "pits" }, grime);
    el("feComposite", { in: "pits", in2: "SourceAlpha", operator: "in", result: "pitsIn" }, grime);
    const merge = el("feMerge", {}, grime);
    el("feMergeNode", { in: "SourceGraphic" }, merge);
    el("feMergeNode", { in: "stainIn" }, merge);
    el("feMergeNode", { in: "pitsIn" }, merge);

    const grain = el("filter", { id: uid + "grain", x: 0, y: 0, width: "100%", height: "100%" }, defs);
    el("feTurbulence", { type: "fractalNoise", baseFrequency: "0.85", numOctaves: 2, stitchTiles: "stitch" }, grain);
    el("feColorMatrix", { type: "saturate", values: "0" }, grain);
}

function drawSky(g, ctx) {
    const { P, uid, scene, L, dusk } = ctx;
    el("rect", { x: 0, y: 0, width: W, height: H, fill: `url(#${uid}sky)` }, g);
    const dark = P.sky0 === PALETTES.night.sky0 || P.sky0 === PALETTES.evening.sky0;
    if (scene.sky === "clear" && dark && scene.falling === "none") {
        const r = rng(7);
        const nightSky = P.sky0 === PALETTES.night.sky0;
        // City lights wash out the stars until the power fails.
        const count = nightSky ? (L === 0 ? 12 : 60) : 14;
        for (let i = 0; i < count; i++) el("circle", { cx: r() * W, cy: r() * (nightSky ? 110 : 50), r: r() * 1 + .3, fill: P.star, opacity: .4 + r() * .5 }, g);
        if (nightSky) el("circle", { cx: 640, cy: 34, r: 11, fill: "#cfd3c8", opacity: .55 }, g);
    }
    if (scene.sky === "some clouds") {
        const r = rng(11);
        for (let i = 0; i < 6; i++) {
            const cx = 60 + i * 170 + r() * 80, cy = 22 + r() * 35, s = .7 + r() * .7;
            const cl = el("g", { opacity: .7, fill: P.cloud }, g);
            el("ellipse", { cx, cy, rx: 70 * s, ry: 10 * s }, cl);
            el("ellipse", { cx: cx - 20 * s, cy: cy - 7 * s, rx: 28 * s, ry: 12 * s }, cl);
            el("ellipse", { cx: cx + 18 * s, cy: cy - 9 * s, rx: 34 * s, ry: 14 * s }, cl);
        }
    }
    if (scene.sky === "overcast" || scene.falling !== "none") {
        const heavy = ["heavy", "storm"].includes(scene.falling_strength);
        el("rect", { x: 0, y: 0, width: W, height: H, fill: heavy ? "#22252a" : "#6c7076", opacity: heavy ? .66 : .45 }, g);
        const r = rng(13);
        const band = el("g", { fill: P.cloud, opacity: heavy ? .35 : .5 }, g);
        for (let i = 0; i < 16; i++) el("ellipse", { cx: i * 70 + r() * 40, cy: 6 + r() * 26, rx: 70 + r() * 40, ry: 16 + r() * 12 }, band);
    }
    // The horizon: a lit city before, fires during the panic, nothing after.
    if (dusk && L === 0) el("rect", { x: 0, y: 80, width: W, height: 80, fill: `url(#${uid}city)` }, g);
    if (dusk && L === 1) el("rect", { x: 0, y: 70, width: W, height: 90, fill: `url(#${uid}fire)` }, g);
}

function drawSkyline(g, ctx, horizon, seed, fill) {
    const { L, dusk } = ctx;
    const r = rng(seed);
    const far = el("g", { fill }, g);
    let x = -20;
    while (x < W + 20) {
        const w = 40 + r() * 70, h = 30 + r() * 70;
        const broken = r() < .25 && L >= 2;
        if (broken) el("path", { d: `M${f(x)} ${f(horizon - h + 10)} l${f(w * .3)} -12 l${f(w * .15)} 9 l${f(w * .25)} -16 l${f(w * .3)} 19 V${horizon + 80} H${f(x)} z` }, far);
        else el("rect", { x, y: horizon - h, width: w, height: h + 80 }, far);
        if (r() < .35) el("rect", { x: x + w * .3, y: horizon - h - 12, width: 2, height: 12 }, far);
        // Lit windows in the far towers while the power is on.
        if (L === 0 && dusk) {
            for (let i = 0; i < 6; i++) if (r() < .6) el("rect", { x: x + 4 + r() * (w - 8), y: horizon - h + 6 + r() * (h - 10), width: 2, height: 2, fill: LAMP, opacity: .7 }, g);
        }
        x += w + r() * 6;
    }
    if (L === 1) for (const sx of [180 + r() * 200, 560 + r() * 240]) smoke(g, sx, horizon - 30, 1.2, "#262626");
    if (L === 2) smoke(g, 180 + r() * 640, horizon - 40, .8, "#2b2b2b");
}

function smoke(g, x, y, s, fill) {
    const col = el("g", { class: "smoke" }, g);
    el("path", { d: `M${f(x)} ${f(y)} q${-14 * s} ${-30 * s} ${6 * s} ${-55 * s} q${22 * s} ${-26 * s} ${2 * s} ${-60 * s} q${40 * s} ${22 * s} ${18 * s} ${62 * s} q${-12 * s} ${24 * s} ${-4 * s} ${53 * s} z`, fill, opacity: .35 }, col);
}

function buildingWindows(g, ctx, x, y, w, h, r) {
    const { L, dusk } = ctx;
    for (let wy = y + 10; wy < y + h - 12; wy += 16) {
        for (let wx = x + 8; wx < x + w - 10; wx += 14) {
            const roll = r();
            if (L >= 2 && roll < .12) {
                el("rect", { x: wx - 1, y: wy + 1, width: 8, height: 2, fill: WOOD, opacity: .8 }, g);
                el("rect", { x: wx - 1, y: wy + 5, width: 8, height: 2, fill: WOOD, opacity: .8 }, g);
            } else if ((L === 1 && roll < .08) || (L >= 2 && roll < .3)) {
                el("path", { d: `M${wx} ${wy} h6 l-2 3 l2 2 l-3 3 h-3 z`, fill: "#000", opacity: .55 }, g);
            } else if (dusk && L <= 1 && roll > (L === 0 ? .62 : .9)) {
                el("rect", { x: wx, y: wy, width: 6, height: 8, fill: LAMP, opacity: .75 }, g);
            } else {
                el("rect", { x: wx, y: wy, width: 6, height: 8, fill: L === 0 ? "#8fa3b3" : "#000", opacity: L === 0 ? .18 : .3 }, g);
            }
            if (L >= 2 && r() < .08) el("rect", { x: wx + 2, y: wy + 8, width: 1.5, height: 10 + r() * 14, fill: "#000", opacity: .25 }, g);
        }
    }
}

function litter(g, ctx, y0, y1, count, seed) {
    const r = rng(seed);
    const { P } = ctx;
    for (let i = 0; i < count; i++) {
        const x = r() * W, y = y0 + r() * (y1 - y0), kind = r();
        if (kind < .45) el("path", { d: `M${f(x)} ${f(y)} l${f(4 + r() * 5)} ${f(-1 - r() * 2)} l${f(2 + r() * 3)} ${f(3)} l${f(-6 - r() * 4)} 1 z`, fill: "#a39c88", opacity: .22 + r() * .2 }, g);
        else if (kind < .75) el("rect", { x, y, width: 3 + r() * 5, height: 2 + r() * 2, fill: P.near, opacity: .9, transform: `rotate(${f(r() * 60 - 30)} ${f(x)} ${f(y)})` }, g);
        else el("circle", { cx: x, cy: y, r: 1 + r() * 1.6, fill: P.mid, opacity: .9 }, g);
    }
}

function grass(g, y0, y1, count, seed, tall) {
    const r = rng(seed);
    for (let i = 0; i < count; i++) {
        const x = r() * W, y = y0 + r() * (y1 - y0), h = (tall ? 8 : 4) + r() * (tall ? 10 : 5);
        el("path", { d: `M${f(x)} ${f(y)} l${f(-2 - r() * 2)} ${f(-h)} l${f(3)} ${f(h * .7)} l${f(1)} ${f(-h * 1.1)} l${f(2)} ${f(h * 1.1)} l${f(3)} ${f(-h * .8)} l${f(-1)} ${f(h * .8)} z`, fill: GRASS, opacity: .85 }, g);
    }
}

function vines(g, x, top, bottom, seed) {
    const r = rng(seed);
    let d = `M${f(x)} ${f(top)}`;
    for (let y = top; y < bottom; y += 8) d += ` q${f((r() - .5) * 10)} 4 ${f((r() - .5) * 4)} 8`;
    el("path", { d, stroke: GRASS, "stroke-width": 2, fill: "none", opacity: .8 }, g);
}

function trashBag(g, P, x, y, s) {
    el("path", { d: `M${x} ${y} q-2 -${12 * s} ${9 * s} -${15 * s} l2 -${4 * s} l3 ${4 * s} q${10 * s} ${3 * s} ${8 * s} ${15 * s} z`, fill: P.near }, g);
}

function bloodSmear(g, ctx, x, y, len, seed) {
    if (!ctx.gore || ctx.L < 2) return;
    const r = rng(seed);
    el("path", { d: `M${x} ${y} q${len * .3} -3 ${len * .6} -1 t${len * .4} 1 l0 3 q-${len * .5} 2 -${len} 0 z`, fill: BLOOD, opacity: .8 }, g);
    for (let i = 0; i < 6; i++) el("circle", { cx: x + r() * len, cy: y - 3 + r() * 7, r: .6 + r() * 1.4, fill: BLOOD, opacity: .8 }, g);
}

const WINDOWS = {
    apartment: { x: 420, y: 34, w: 150, h: 96 },
    hallway: { x: 460, y: 40, w: 70, h: 60 },
    store: { x: 228, y: 30, w: 236, h: 130 },
    clinic: { x: 430, y: 40, w: 120, h: 70 },
};

const SETTINGS = {
    street(svg, ctx) {
        const { P, L, dusk } = ctx;
        drawSkyline(svg, ctx, HORIZON - 10, 3, P.far);
        const r = rng(5);
        const mid = el("g", { filter: ctx.grime }, svg);
        let x = -30;
        const doors = [];
        const spots = [];
        while (x < W + 30) {
            const w = 110 + r() * 90, h = 60 + r() * 55;
            el("rect", { x, y: HORIZON - h, width: w, height: h + 20, fill: P.mid }, mid);
            buildingWindows(mid, ctx, x, HORIZON - h, w, h - 22, r);
            el("rect", { x: x + w * .4, y: HORIZON - 22, width: 18, height: 22, fill: P.near }, mid);
            doors.push([x, w]);
            spots.push({ x: x + w * .4 - 4, y: HORIZON - 30, w: 26, h: 30, kind: "door" });
            for (const at of [.12, .68]) spots.push({ x: x + w * at, y: HORIZON - 56, w: 30, h: 22, kind: "window" });
            const awning = r() < .55;
            if (awning && L >= 2) el("path", { d: `M${f(x + 6)} ${HORIZON - 30} h${f(w * .55)} l-6 7 l-4 -2 l-5 8 l-4 -3 h${f(-(w * .55 - 25))} z`, fill: P.near }, mid);
            else if (awning) el("path", { d: `M${f(x + 6)} ${HORIZON - 30} h${f(w * .55)} l6 8 h${f(-(w * .55 + 12))} z`, fill: L === 0 ? "#5a3a32" : P.near }, mid);
            if (L === 3 && r() < .5) vines(svg, x + 10 + r() * (w - 20), HORIZON - h + 10, HORIZON, hash(x));
            x += w + 4;
        }
        if (L >= 2) {
            const [dx, dw] = doors.find(([bx, bw]) => bx + bw * .4 > 300 && bx + bw * .4 < 700) ?? [400, 100];
            const d = dx + dw * .4;
            el("path", { d: `M${f(d + 2)} ${HORIZON - 19} l14 15 M${f(d + 16)} ${HORIZON - 19} l-14 15`, stroke: "#7a2a1c", "stroke-width": 1.8, opacity: L === 3 ? .45 : .8 }, svg);
        }

        drawBarriersOutside(svg, ctx, spots);

        const ground = el("g", { filter: ctx.grime }, svg);
        el("rect", { x: 0, y: HORIZON, width: W, height: H - HORIZON, fill: P.ground }, ground);
        el("rect", { x: 0, y: HORIZON, width: W, height: 4, fill: P.near }, ground);
        for (let dx = 20; dx < W; dx += 90) el("rect", { x: dx, y: 178, width: 40, height: 3, fill: L === 0 ? "#b9b29a" : P.mid, opacity: L === 0 ? .35 : .5 }, ground);
        if (L >= 2) el("path", { d: "M560 172 l12 6 l9 -3 l14 9 M590 184 l6 10 M120 168 l18 8 l10 -4 M820 186 l14 -6 l20 4", stroke: "#000", "stroke-width": 1, fill: "none", opacity: .5 }, svg);

        // The streetlight: lit while the power is on, snapped once things collapse.
        const near = el("g", { fill: P.near }, svg);
        el("rect", { x: 712, y: 58, width: 5, height: 98 }, near);
        if (L >= 2) {
            el("path", { d: "M714 60 q2 -12 18 -12 h6 v4 h-6 q-10 0 -12 6 z" }, near);
            el("path", { d: "M736 52 l3 1 l2 16 l-6 4 l-4 -4 z" }, near);
        } else {
            el("path", { d: "M714 60 q2 -12 18 -12 h14 v4 h-14 q-10 0 -12 6 z" }, near);
            el("rect", { x: 738, y: 50, width: 14, height: 5, rx: 2 }, near);
            if (dusk) {
                el("path", { d: "M738 55 h14 l40 101 h-94 z", fill: `url(#${ctx.uid}cone)` }, svg);
                el("ellipse", { cx: 745, cy: 160, rx: 60, ry: 6, fill: LAMP, opacity: .18 }, svg);
                el("rect", { x: 739, y: 54, width: 12, height: 2, fill: LAMP }, svg);
            }
        }

        drawCar(svg, ctx);

        const junk = el("g", {}, svg);
        if (L === 0) el("path", { d: "M600 152 l2 -18 h14 l2 18 z", fill: P.near }, junk);
        if (L === 1) { el("path", { d: "M600 152 l2 -18 h14 l2 18 z", fill: P.near }, junk); litter(junk, ctx, HORIZON + 4, H, 12, 17); trashBag(junk, P, 455, 152, 1); }
        if (L >= 2) {
            trashBag(junk, P, 455, 152, 1.1); trashBag(junk, P, 470, 153, .8); trashBag(junk, P, 640, 152, 1);
            el("path", { d: "M600 152 l4 -16 h14 l4 16 z", fill: P.near, transform: "rotate(76 610 150)" }, junk);
            litter(junk, ctx, HORIZON + 4, H, L === 3 ? 22 : 40, 17);
        }
        if (L === 3) grass(svg, HORIZON + 2, H, 40, 61, false);
        bloodSmear(svg, ctx, 520, 188, 70, 3);
    },

    neighborhood(svg, ctx) {
        const { P, L, dusk } = ctx;
        const r = rng(9);
        const trees = el("g", { fill: P.far }, svg);
        for (let x = -20; x < W + 40; x += 34 + r() * 30) {
            const bare = r() < .25, cy = HORIZON - 30 - r() * 25;
            if (bare) el("path", { d: `M${f(x)} ${HORIZON - 10} V${f(cy - 6)} M${f(x)} ${f(cy + 8)} l-12 -14 M${f(x)} ${f(cy)} l10 -16 M${f(x)} ${f(cy - 4)} l-6 -14`, stroke: P.far, "stroke-width": 3, fill: "none" }, trees);
            else el("circle", { cx: x, cy, r: 18 + r() * 16 }, trees);
        }
        el("rect", { x: 0, y: HORIZON - 40, width: W, height: 50, fill: P.far }, svg);
        if (L === 1) smoke(svg, 300 + r() * 400, HORIZON - 50, 1, "#262626");
        const houses = el("g", { filter: ctx.grime }, svg);
        const spots = [];
        for (const [x, w, h, i] of [[150, 150, 50, 0], [370, 120, 44, 1], [560, 170, 56, 2], [790, 130, 46, 3]]) {
            const burnt = L >= 2 && i === 1;
            el("rect", { x, y: HORIZON - h, width: w, height: h + 10, fill: P.mid }, houses);
            if (burnt) el("path", { d: `M${x - 10} ${HORIZON - h} L${x + w * .3} ${HORIZON - h - 22} l8 10 l6 -14 l10 18 L${x + w + 10} ${HORIZON - h} z`, fill: P.mid }, houses);
            else el("path", { d: `M${x - 10} ${HORIZON - h} L${x + w / 2} ${HORIZON - h - 34} L${x + w + 10} ${HORIZON - h} z`, fill: P.mid }, houses);
            spots.push({ x: x + w * .45, y: HORIZON - 26, w: 16, h: 26, kind: "door" });
            for (const [k, wx] of [[0, x + w * .2], [1, x + w * .65]]) {
                spots.push({ x: wx - 2, y: HORIZON - h + 10, w: 18, h: 16, kind: "window" });
                const lit = L === 0 && dusk && (i + k) % 2 === 0;
                const broken = (L === 1 && i === 2 && k === 0) || (L >= 2 && k === 0);
                el("rect", { x: wx, y: HORIZON - h + 12, width: 14, height: 12, fill: lit ? LAMP : "#000", opacity: lit ? .75 : broken ? .55 : .3 }, houses);
                if (L >= 2 && k === 1) {
                    el("rect", { x: wx - 2, y: HORIZON - h + 14, width: 18, height: 2.5, fill: WOOD }, houses);
                    el("rect", { x: wx - 2, y: HORIZON - h + 19, width: 18, height: 2.5, fill: WOOD }, houses);
                }
            }
            if (burnt) el("path", { d: `M${x + w * .2} ${HORIZON - h + 12} q4 -20 -4 -40 q16 14 14 40 z`, fill: "#000", opacity: .45 }, houses);
            if (L === 3) vines(svg, x + 6, HORIZON - h, HORIZON, hash(x) + 1);
        }
        drawBarriersOutside(svg, ctx, spots);
        el("rect", { x: 0, y: HORIZON, width: W, height: H - HORIZON, fill: L === 3 ? "#2e3427" : P.ground, filter: ctx.grime }, svg);
        const fence = el("g", { fill: P.near }, svg);
        el("rect", { x: 0, y: 166, width: W, height: 3 }, fence);
        for (let x = 4; x < W; x += 14) {
            if (L >= 2 && x > 500 && x < 560) continue;
            const lean = L >= 2 && r() < .15 ? (r() - .5) * (L === 3 ? 50 : 30) : 0;
            el("path", { d: `M${x} 186 v-28 l3 -4 l3 4 v28 z`, transform: `rotate(${f(lean)} ${x + 3} 186)` }, fence);
        }
        if (L >= 2) el("path", { d: "M502 186 l4 -26 l6 3 l-2 23 z M548 186 l-2 -18 l6 -2 l2 20 z", fill: P.near }, svg);
        const tilt = L >= 2 ? 9 : 0;
        el("rect", { x: 846, y: 150, width: 4, height: 30, fill: P.near, transform: `rotate(${tilt} 848 180)` }, svg);
        el("rect", { x: 838, y: 140, width: 20, height: 12, rx: 4, fill: P.near, transform: `rotate(${tilt} 848 180)` }, svg);
        const junk = el("g", {}, svg);
        if (L >= 1) trashBag(junk, P, 300, 168, 1);
        if (L >= 2) { trashBag(junk, P, 680, 170, .9); litter(junk, ctx, 160, H, 30, 23); }
        if (L === 3) grass(svg, 150, H, 70, 67, true);
    },

    apartment(svg, ctx, win) {
        const { P, L } = ctx;
        frameWindow(svg, ctx, wallAndFloor(svg, ctx, 172), win, true);
        if (ctx.gore && L >= 2) el("path", { d: "M340 92 l3 -12 l2 11 l2 -14 l2 14 l2 -12 l1 13 l3 -7 l-1 12 q0 6 -8 7 l-2 30 l-3 0 l-1 -30 q-4 -2 -3 -12 z", fill: BLOOD, opacity: .75 }, svg);
        drawBarrier(svg, ctx, findBarrier(ctx.snap, "door"), { x: 262, y: 46, w: 62, h: 126, kind: "door" });
        const furniture = el("g", { fill: P.near, filter: ctx.grime }, svg);
        el("path", { d: "M610 172 v-36 q0 -10 10 -10 h150 q10 0 10 10 v36 z" }, furniture);
        el("path", { d: "M600 172 v-46 q0 -8 10 -8 q10 0 10 8 v46 z M770 172 v-46 q0 -8 10 -8 q10 0 10 8 v46 z" }, furniture);
        if (L >= 2) {
            el("path", { d: "M625 130 v-22 q0 -6 8 -6 h50 l6 6 l-8 4 l4 6 l-6 12 z M700 130 v-24 q0 -6 8 -6 h50 q8 0 8 6 v24 z" }, furniture);
            el("path", { d: "M690 112 l6 -4 l-2 8 z", fill: "#a39c88", opacity: .5 }, svg);
            el("path", { d: "M800 170 l60 -6 l2 4 l-60 6 z M856 160 l18 -6 l6 12 l-20 4 z", fill: P.near }, svg);
            el("path", { d: "M390 172 l6 -22 h30 l-2 6 h-24 l-4 16 z M400 156 l-10 -20 h4 l10 20 z", fill: P.near }, svg);
            litter(svg, ctx, 174, H, 24, 29);
        } else {
            el("rect", { x: 625, y: 104, width: 140, height: 26, rx: 6 }, furniture);
            // The floor lamp, lit before the outbreak at dusk.
            el("rect", { x: 838, y: 70, width: 4, height: 102, fill: P.near }, svg);
            el("path", { d: "M824 72 l8 -24 h16 l8 24 z", fill: ctx.lampsOn ? LAMP : P.near, opacity: ctx.lampsOn ? .9 : 1 }, svg);
            el("path", { d: "M396 172 v-34 h26 v-30 h4 v64 h-4 v-20 h-22 v20 z", fill: P.near }, svg);
            if (L === 1) litter(svg, ctx, 174, H, 6, 29);
        }
        if (ctx.lampsOn) {
            el("ellipse", { cx: 840, cy: 70, rx: 260, ry: 140, fill: `url(#${ctx.uid}lamp)` }, svg);
        }
        bloodSmear(svg, ctx, 300, 186, 110, 8);
    },

    hallway(svg, ctx, win) {
        const { P, L } = ctx;
        frameWindow(svg, ctx, wallAndFloor(svg, ctx, 172), win, false);
        const doors = barriersOf(ctx.snap, "door");
        [262, 352, 562, 172].forEach((x, i) => {
            if (doors[i] || i < 2) drawBarrier(svg, ctx, doors[i], { x, y: 52, w: 64, h: 120, kind: "door" });
        });
        el("path", { d: "M640 172 l150 -110 h30 v110 z", fill: P.near, filter: ctx.grime }, svg);
        el("rect", { x: 560, y: 4, width: 40, height: 6, fill: ctx.lampsOn ? LAMP : P.near }, svg);
        if (ctx.lampsOn) el("ellipse", { cx: 580, cy: 20, rx: 300, ry: 140, fill: `url(#${ctx.uid}lamp)` }, svg);
        if (L >= 1) litter(svg, ctx, 174, H, L >= 2 ? 20 : 5, 31);
    },

    clinic(svg, ctx, win) {
        const { P, L } = ctx;
        frameWindow(svg, ctx, wallAndFloor(svg, ctx, 172), win, false);
        drawBarrier(svg, ctx, findBarrier(ctx.snap, "door"), { x: 262, y: 52, w: 64, h: 120, kind: "door" });
        const gear = el("g", { fill: P.near, filter: ctx.grime }, svg);
        // The curtain rail, and the curtain hung from it (torn once things collapse).
        el("rect", { x: 560, y: 22, width: 330, height: 3 }, gear);
        if (L >= 2) el("path", { d: "M568 25 h120 l-6 40 l8 20 l-10 30 l6 30 h-118 z M760 25 h120 v70 l-14 -10 l-8 40 l-18 -10 l-6 50 h-74 z" }, gear);
        else el("path", { d: "M568 25 h74 q-10 70 6 135 h-80 z M808 25 h80 v135 h-86 q10 -70 6 -135 z", opacity: .8 }, gear);
        // The bed: frame, mattress, a pillow and the head rail.
        el("rect", { x: 600, y: 118, width: 230, height: 6 }, gear);
        el("rect", { x: 604, y: 124, width: 5, height: 48 }, gear);
        el("rect", { x: 820, y: 124, width: 5, height: 48 }, gear);
        if (L >= 2) {
            el("path", { d: "M612 118 q40 -16 100 -10 l30 10 z M780 118 l30 -16 l24 18 z" }, gear);
            el("path", { d: "M700 124 q30 20 60 40 l-10 8 q-30 -14 -52 -34 z", opacity: .8 }, gear);
        } else {
            el("rect", { x: 604, y: 104, width: 218, height: 14, rx: 6 }, gear);
            el("rect", { x: 610, y: 96, width: 44, height: 10, rx: 5 }, gear);
        }
        el("rect", { x: 596, y: 82, width: 5, height: 90 }, gear);
        // The cabinet, glass front, and the shelves inside it.
        el("rect", { x: 380, y: 70, width: 56, height: 102 }, gear);
        for (const sy of [86, 112, 138]) el("rect", { x: 386, y: sy, width: 44, height: 3, fill: P.mid }, gear);
        if (L >= 2) el("path", { d: "M380 70 l18 8 l-6 60 l-12 -4 z", fill: P.wall }, gear);
        else el("rect", { x: 386, y: 76, width: 44, height: 90, fill: "#9fb0bd", opacity: .12 }, gear);
        if (ctx.lampsOn) {
            el("rect", { x: 520, y: 0, width: 60, height: 4, fill: LAMP, opacity: .9 }, svg);
            el("ellipse", { cx: 550, cy: 20, rx: 300, ry: 140, fill: `url(#${ctx.uid}lamp)` }, svg);
        }
        const spill = el("g", {}, svg);
        for (let i = 0, r = rng(43); i < [0, 3, 14, 12][L]; i++) {
            const x = 340 + r() * 360, y = 176 + r() * 18;
            el("rect", { x, y, width: 4 + r() * 6, height: 3 + r() * 4, fill: P.mid, transform: `rotate(${f(r() * 80 - 40)} ${f(x)} ${f(y)})` }, spill);
        }
        if (L >= 2) litter(spill, ctx, 174, H, 16, 47);
        bloodSmear(svg, ctx, 330, 188, 120, 14);
    },

    store(svg, ctx, win) {
        const { P, L } = ctx;
        frameWindow(svg, ctx, wallAndFloor(svg, ctx, 172), win, false);
        const [first] = barriersOf(ctx.snap);
        if (first && !/window/.test(first.name)) drawBarrier(svg, ctx, first, { x: 314, y: 52, w: 64, h: 120, kind: "door" });
        else drawBarrier(svg, ctx, first, { x: win.x, y: win.y, w: win.w, h: win.h, kind: "window" });
        const r = rng(21);
        const stock = [.92, .6, .35, .15][L];
        const shelf = el("g", { filter: ctx.grime }, svg);
        for (const [sx, tilt] of [[500, 0], [640, L >= 2 ? -7 : 0]]) {
            const s = el("g", { transform: `rotate(${tilt} ${sx + 120} 172)` }, shelf);
            el("rect", { x: sx, y: 64, width: 120, height: 108, fill: P.near }, s);
            for (let sy = 74; sy < 168; sy += 24) {
                el("rect", { x: sx + 4, y: sy + 18, width: 112, height: 4, fill: P.mid }, s);
                let px = sx + 8;
                while (px < sx + 110) {
                    const pw = 6 + r() * 10, ph = 6 + r() * 12;
                    const colour = L === 0 ? pick(r, ["#6b5a48", "#4d5a62", "#6a4a44", "#56604a", P.mid]) : P.mid;
                    if (r() < stock) el("rect", { x: px, y: sy + 18 - ph, width: pw, height: ph, fill: colour, opacity: .9 }, s);
                    px += pw + 2;
                }
            }
        }
        const counter = el("g", { fill: P.near, filter: ctx.grime }, svg);
        el("rect", { x: 790, y: 120, width: 160, height: 52 }, counter);
        if (L >= 2) el("path", { d: "M820 120 l4 -16 l30 -4 l2 20 z" }, counter);
        else { el("rect", { x: 820, y: 100, width: 34, height: 20 }, counter); el("rect", { x: 826, y: 94, width: 22, height: 8 }, counter); }
        if (ctx.lampsOn) {
            for (const lx of [380, 640, 880]) el("rect", { x: lx - 30, y: 0, width: 60, height: 4, fill: LAMP, opacity: .9 }, svg);
            el("rect", { x: 0, y: 0, width: W, height: H, fill: LAMP, opacity: .1 }, svg);
        }
        const spill = el("g", {}, svg);
        const spilled = [0, 6, 26, 18][L];
        for (let i = 0; i < spilled; i++) {
            const x = 470 + r() * 330, y = 174 + r() * 22;
            el("rect", { x, y, width: 4 + r() * 6, height: 3 + r() * 5, fill: P.mid, transform: `rotate(${f(r() * 80 - 40)} ${f(x)} ${f(y)})` }, spill);
        }
        if (L >= 2) litter(spill, ctx, 174, H, 18, 37);
        bloodSmear(svg, ctx, 360, 190, 160, 12);
    },
};

function drawCar(svg, ctx) {
    const { P, L } = ctx;
    const car = el("g", { filter: ctx.grime }, svg);
    const body = L >= 2 ? (L === 3 ? "#3d2c22" : P.near) : (L === 0 ? "#3a4652" : P.near);
    const tilt = L >= 2 ? -2 : 0;
    el("path", { d: "M250 162 l10 -18 q6 -8 20 -8 h60 q12 0 20 10 l12 14 h22 q8 0 8 8 v8 h-158 v-8 q0 -6 6 -6 z", fill: body, transform: `rotate(${tilt} 330 160)` }, car);
    if (L >= 2) {
        el("path", { d: "M268 145 l8 -7 h24 v9 z M305 138 h30 q6 0 10 5 l3 4 h-43 z", fill: "#000", opacity: .55 }, car);
        el("path", { d: "M312 140 l8 4 l-4 3 M326 139 l-3 6", stroke: "#8b9196", "stroke-width": .8, opacity: .5 }, car);
        el("ellipse", { cx: 275, cy: 170, rx: 10, ry: 7, fill: P.ground }, car);
        el("ellipse", { cx: 372, cy: 172, rx: 11, ry: 4, fill: P.ground }, car);
    } else {
        el("path", { d: "M268 145 l8 -7 h24 v9 z M305 138 h30 q6 0 10 5 l3 4 h-43 z", fill: "#9fb0bd", opacity: .3 }, car);
        el("circle", { cx: 275, cy: 170, r: 9, fill: P.ground }, car);
        el("circle", { cx: 372, cy: 170, r: 9, fill: P.ground }, car);
        // Abandoned with the door open once the panic starts.
        if (L === 1) {
            el("path", { d: "M300 139 v24 h-4 v-22 z", fill: "#000", opacity: .6 }, car);
            el("path", { d: "M300 139 l-22 -10 v28 l22 6 z", fill: "#2b3036" }, car);
            el("path", { d: "M297 138 l-16 -7 v9 l16 5 z", fill: "#9fb0bd", opacity: .25 }, car);
        }
    }
    if (L === 3) grass(svg, 166, 176, 8, 71, true);
}

function wallAndFloor(svg, ctx, floorY) {
    const { P, L } = ctx;
    const room = el("g", { filter: ctx.grime }, svg);
    const wall = el("path", { d: `M0 0 H${W} V${floorY} H0 Z`, fill: P.wall, "fill-rule": "evenodd" }, room);
    el("rect", { x: 0, y: floorY, width: W, height: H - floorY, fill: P.floor }, room);
    el("rect", { x: 0, y: floorY - 5, width: W, height: 5, fill: P.near }, room);
    if (L >= 2) el("path", { d: "M120 0 l6 30 l-8 22 l10 30 M880 0 l-10 26 l6 18 l-12 28", stroke: "#000", "stroke-width": 1, fill: "none", opacity: .35 }, svg);
    if (L === 3) el("path", { d: "M0 0 q30 10 40 40 M0 0 q16 22 10 50 M0 0 q40 4 70 20", stroke: "#cfcfc4", "stroke-width": .5, fill: "none", opacity: .25 }, svg);
    return wall;
}

function frameWindow(svg, ctx, wall, win, curtains) {
    const { P, L } = ctx;
    wall.setAttribute("d", `${wall.getAttribute("d")} M${win.x} ${win.y} h${win.w} v${win.h} h${-win.w} z`);
    const fr = el("g", { fill: P.near }, svg);
    el("rect", { x: win.x - 6, y: win.y - 6, width: win.w + 12, height: 6 }, fr);
    el("rect", { x: win.x - 6, y: win.y + win.h, width: win.w + 12, height: 8 }, fr);
    el("rect", { x: win.x - 6, y: win.y, width: 6, height: win.h }, fr);
    el("rect", { x: win.x + win.w, y: win.y, width: 6, height: win.h }, fr);
    el("rect", { x: win.x, y: win.y, width: win.w, height: win.h, fill: "#3a3a30", opacity: L >= 2 ? .25 : .1 }, svg);
    if (curtains) {
        el("rect", { x: win.x + win.w / 2 - 2, y: win.y, width: 4, height: win.h }, fr);
        el("rect", { x: win.x, y: win.y + win.h / 2 - 2, width: win.w, height: 4 }, fr);
        if (L >= 2) {
            el("path", { d: `M${win.x - 16} ${win.y - 10} h34 q-10 40 6 60 l-6 6 l4 10 q-4 10 0 ${win.h - 54} h-38 z` }, fr);
            el("path", { d: `M${win.x + win.w + 16} ${win.y - 10} h-24 l-6 30 l10 -4 q-4 40 6 ${win.h - 4} h14 z` }, fr);
        } else {
            el("path", { d: `M${win.x - 16} ${win.y - 10} h34 q-10 50 4 ${win.h + 22} h-38 z` }, fr);
            el("path", { d: `M${win.x + win.w + 16} ${win.y - 10} h-34 q10 50 -4 ${win.h + 22} h38 z` }, fr);
        }
    }
}

// A setting has few spots for barriers: a thumping one is drawn first, then a broken, smashed or planked one.
function barrierRank(b) {
    if (b.thumping) return 0;
    return b.state_word === "broken" || b.state_word === "smashed" || b.planks_here > 0 ? 1 : 2;
}
function barriersOf(snap, kind) {
    return (snap.barriers || [])
        .filter((b) => !kind || (kind === "window") === /window/.test(b.name))
        .sort((a, b) => barrierRank(a) - barrierRank(b) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}
function findBarrier(snap, kind) {
    return barriersOf(snap, kind)[0];
}
const BARRIER_SIZE = { door: { w: 64, h: 120 }, window: { w: 100, h: 70 } };
// Outdoors a barrier is drawn at full size and shrunk onto the building's own door or window.
function drawBarrierSmall(svg, ctx, barrier, spot) {
    const full = BARRIER_SIZE[spot.kind];
    const g = el("g", { transform: `translate(${f(spot.x)} ${f(spot.y)}) scale(${f(spot.w / full.w)} ${f(spot.h / full.h)})` }, svg);
    drawBarrier(g, ctx, barrier, { x: 0, y: 0, ...full, kind: spot.kind });
}
// Spots inside the narrow crop, middle first; the worst-off barriers take them in order.
function drawBarriersOutside(svg, ctx, spots) {
    const centre = (s) => Math.abs(s.x + s.w / 2 - 500);
    const inside = spots.filter((s) => s.x >= 200 && s.x + s.w <= 800).sort((a, b) => centre(a) - centre(b));
    for (const kind of ["door", "window"]) {
        const ranked = barriersOf(ctx.snap, kind);
        inside.filter((s) => s.kind === kind).slice(0, ranked.length).forEach((s, i) => drawBarrierSmall(svg, ctx, ranked[i], s));
    }
}

function drawBarrier(svg, ctx, barrier, spot) {
    const { P } = ctx;
    if (!barrier) {
        if (spot.kind === "door") el("rect", { x: spot.x, y: spot.y, width: spot.w, height: spot.h, fill: P.near, filter: ctx.grime }, svg);
        return;
    }
    const g = el("g", { class: barrier.thumping ? "thump" : "" }, svg);
    const { x, y, w, h } = spot;
    const state = barrier.state_word;
    if (spot.kind === "door") {
        if (state === "open" || state === "broken") {
            el("rect", { x, y, width: w, height: h, fill: "#000", opacity: .9 }, g);
            if (state === "open") el("path", { d: `M${x} ${y} l-18 8 v${h - 14} l18 6 z`, fill: P.near, filter: ctx.grime }, g);
            else {
                el("path", { d: `M${x} ${y + 30} l14 -6 l6 40 l-4 4 l2 6 l-12 10 z`, fill: P.near }, g);
                el("path", { d: `M${x + w} ${y + 70} l-10 4 l-6 12 l-8 38 h24 z`, fill: P.near }, g);
                el("path", { d: `M${x + 10} ${y + h} l12 -8 l20 3 l6 5 z M${x - 20} ${y + h} l8 -4 l14 2 z`, fill: P.near }, g);
            }
        } else {
            el("rect", { x, y, width: w, height: h, fill: P.near, filter: ctx.grime }, g);
            el("rect", { x: x + 8, y: y + 10, width: w - 16, height: h * .4, fill: "#000", opacity: .2 }, g);
            el("circle", { cx: x + w - 10, cy: y + h * .55, r: 3, fill: P.mid }, g);
            if (barrier.thumping) {
                el("path", { d: `M${x + 18} ${y + 30} l4 10 l-3 8 l5 9 M${x + 40} ${y + 60} l-5 9 l4 7`, stroke: "#000", "stroke-width": 1.2, fill: "none", opacity: .7 }, g);
                if (ctx.gore) el("path", { d: `M${x + 6} ${y + h} q10 -3 18 -1 q-2 3 -18 3 z`, fill: BLOOD, opacity: .9 }, g);
            }
        }
    } else if (state === "smashed") {
        const shards = el("g", { fill: "#c8d0d2", opacity: .2 }, g);
        el("path", { d: `M${x} ${y} h${w * .35} l-${w * .12} ${h * .3} l-${w * .18} ${h * .1} z` }, shards);
        el("path", { d: `M${x + w} ${y + h} h-${w * .3} l${w * .1} -${h * .35} l${w * .2} -${h * .05} z` }, shards);
        el("path", { d: `M${x} ${y + h} v-${h * .4} l${w * .14} ${h * .22} z` }, shards);
        const cracks = el("g", { stroke: "#e6eef0", "stroke-width": 1, opacity: .45, fill: "none" }, g);
        el("path", { d: `M${x + w * .23} ${y + h * .3} l-30 22 M${x + w * .23} ${y + h * .3} l12 34 M${x + w * .8} ${y + h * .6} l40 -10 M${x + w * .8} ${y + h * .6} l-10 40` }, cracks);
        el("path", { d: `M${x + 6} ${y + h + 4} l10 -3 l4 4 z M${x + 40} ${y + h + 6} l8 -2 l2 3 z`, fill: "#c8d0d2", opacity: .3 }, g);
    } else if (state === "open") {
        el("rect", { x: x + w * .55, y, width: w * .45, height: h, fill: "#c8d0d2", opacity: .1 }, g);
    } else {
        el("rect", { x, y, width: w, height: h, fill: "#c8d0d2", opacity: .08 }, g);
        el("path", { d: `M${x + 20} ${y + 10} l40 40 M${x + 40} ${y + 8} l30 30`, stroke: "#fff", "stroke-width": 2, opacity: .12 }, g);
    }
    const r = rng(hash(barrier.id));
    for (let i = 0; i < (barrier.planks_here || 0); i++) {
        const py = y + h * (0.2 + i * 0.25);
        const tilt = (i % 2 ? -1 : 1) * (4 + r() * 5);
        const plank = el("g", {}, g);
        el("path", { d: `M${x - 10} ${f(py + tilt)} L${x + w + 10} ${f(py - tilt)} l0 12 L${x - 10} ${f(py + tilt + 12)} z`, fill: WOOD, filter: ctx.grime }, plank);
        el("path", { d: `M${x} ${f(py + tilt + 4)} l${w * .6} ${f(-tilt * 1.1)}`, stroke: "#3b2e22", "stroke-width": .8 }, plank);
        el("circle", { cx: x - 3, cy: py + tilt + 6, r: 1.6, fill: "#1a1410" }, plank);
        el("circle", { cx: x + w + 3, cy: py - tilt + 6, r: 1.6, fill: "#1a1410" }, plank);
    }
}

function wetGround(svg, { uid, P }) {
    el("rect", { x: 0, y: HORIZON + 4, width: W, height: H - HORIZON, fill: `url(#${uid}wet)` }, svg);
    const r = rng(51);
    for (let i = 0; i < 9; i++) el("ellipse", { cx: r() * W, cy: 168 + r() * 28, rx: 20 + r() * 40, ry: 2 + r() * 2.5, fill: P.sky1, opacity: .18 }, svg);
}

function drawWeather(parent, { uid, scene, defs }) {
    if (scene.falling === "none") return;
    const strength = scene.falling_strength;
    if (scene.falling === "rain") {
        const per = { light: 1, steady: 3, heavy: 6, storm: 8 }[strength];
        const slant = strength === "storm" ? -14 : -5;
        const pat = el("pattern", { id: uid + "rain", width: 60, height: 60, patternUnits: "userSpaceOnUse" }, defs);
        const r = rng(31);
        for (let i = 0; i < per; i++) {
            const x = r() * 60, y = r() * 60, len = 14 + r() * 8;
            for (const oy of [0, -60, 60]) el("line", { x1: x, y1: y + oy, x2: x + slant, y2: y + oy + len, stroke: "#c4ccd0", "stroke-width": 1, opacity: .5 }, pat);
        }
        const g = el("g", { class: "rain", style: `--rain-speed:${strength === "storm" ? .32 : strength === "light" ? .8 : .5}s` }, parent);
        el("rect", { x: -40, y: -120, width: W + 80, height: H + 140, fill: `url(#${uid}rain)` }, g);
    } else {
        for (const [layer, size, speed, count, op] of [[0, 1.4, 9, { light: 2, steady: 4, heavy: 8, storm: 12 }[strength], .55], [1, 2.4, 5.5, { light: 1, steady: 2, heavy: 5, storm: 8 }[strength], .8]]) {
            const pat = el("pattern", { id: `${uid}snow${layer}`, width: 60, height: 60, patternUnits: "userSpaceOnUse" }, defs);
            const r = rng(41 + layer);
            for (let i = 0; i < count; i++) el("circle", { cx: r() * 60, cy: r() * 60, r: size * (.6 + r() * .5), fill: "#e8ebee", opacity: op }, pat);
            const g = el("g", { class: "snow", style: `--snow-speed:${strength === "storm" ? speed / 3 : speed}s` }, parent);
            el("rect", { x: -40, y: -120, width: W + 80, height: H + 140, fill: `url(#${uid}snow${layer})` }, g);
        }
    }
}

function drawFog(parent, { uid, P, scene }, y, h, front) {
    if (scene.fog !== "light" && scene.fog !== "thick") return;
    const thick = scene.fog === "thick";
    const base = front ? (thick ? .38 : .14) : (thick ? .72 : .35);
    const g = el("g", { class: "fog" }, parent);
    el("rect", { x: -80, y, width: W + 160, height: h, fill: `url(#${uid}fog)`, opacity: base }, g);
    if (!front && thick) el("rect", { x: 0, y: 0, width: W, height: H, fill: P.fog, opacity: .25 }, parent);
}

// ---------------------------------------------------------------- bodies, zombies, people

function drawBodies(svg, ctx, corpses) {
    corpses.slice(0, 3).forEach((c, i) => {
        const seed = hash(c.id);
        const y = ctx.indoors ? 186 : 178 + (i % 2) * 8;
        bodyOnGround(svg, ctx, 300 + (seed % 380), y, seed, { pool: true });
    });
}

// A figure lying on the ground; a corpse has a blood pool, a zombie that is down does not.
function bodyOnGround(svg, { P, gore }, x, y, seed, { pool, scale = 1, twitch = false }) {
    const r = rng(seed);
    const flip = r() < .5 ? -1 : 1;
    const mirror = `translate(${flip < 0 ? 2 * x + 100 : 0} 0) scale(${flip} 1)`;
    const outer = el("g", { transform: `translate(${x} ${y}) scale(${scale}) translate(${-x} ${-y})` }, svg);
    if (pool) el("path", { d: `M${x - 10} ${y + 4} q20 -6 60 -4 q40 1 56 5 q-6 6 -40 6 q-14 4 -40 1 q-30 0 -36 -8 z`, fill: gore ? BLOOD : "#000", opacity: gore ? .85 : .3, transform: mirror }, outer);
    const g = el("g", { fill: P.fig, stroke: P.fig, "stroke-linecap": "round", transform: mirror, class: twitch ? "twitch" : "" }, outer);
    el("path", { d: `M${x} ${y} q6 -9 30 -9 l38 1 q10 1 10 7 q0 6 -12 6 h-48 q-16 0 -18 -5 z`, stroke: "none" }, g);
    el("ellipse", { cx: x + 92, cy: y - 2, rx: 8, ry: 7, stroke: "none" }, g);
    el("path", { d: `M${x + 60} ${y - 6} q8 -14 22 -18 M${x + 40} ${y - 6} l-4 -10 l-10 -2`, "stroke-width": 4.5, fill: "none" }, g);
    el("path", { d: `M${x + 2} ${y - 2} l-26 -6 M${x + 4} ${y + 3} l-22 6 l-4 -6`, "stroke-width": 5.5, fill: "none" }, g);
    if (gore) {
        el("path", { d: `M${x + 38} ${y - 7} q4 -3 10 0`, stroke: BLOOD_FRESH, "stroke-width": 2, fill: "none" }, g);
        el("path", { d: `M${x + 30} ${y - 8} l3 -3 l2 3 l3 -3 l2 3`, stroke: BONE, "stroke-width": .8, opacity: .55, fill: "none" }, g);
    }
}

// Everyone in one depth order: far zombies first, the one on you last.
function drawActors(svg, ctx, threats, npcs) {
    const actors = [];
    for (const t of threats) {
        if (!t.id || BEHIND_BARRIER.test(t.distance_word || "")) continue;
        const pose = lookup(POSTURE, t.state_word, "idle", "threat state");
        if (pose === "none") continue;
        const depth = pose === "behind" ? DISTANCE_ORDER.length : DISTANCE_ORDER.indexOf(t.distance_word);
        actors.push({ kind: "zombie", depth: depth < 0 ? 0 : depth, t, pose });
    }
    npcs.forEach((n) => actors.push({ kind: "person", depth: n.following ? 2.5 : 1.5, n }));
    actors.sort((a, b) => a.depth - b.depth);
    const zombies = actors.filter((a) => a.kind === "zombie");
    const kept = new Set(zombies.slice(-8));
    let followers = 0;
    for (const a of actors) {
        if (a.kind === "zombie") {
            if (kept.has(a)) drawThreat(svg, ctx, a.t, a.pose);
        } else {
            const n = a.n;
            const seed = hash(n.id || n.name);
            if (n.following) {
                const x = followers++ % 2 === 0 ? 236 : 764;
                person(svg, ctx, x, 236, 1.55, n.disposition, seed);
            } else {
                const x = 300 + (seed % 400);
                person(svg, ctx, x, ctx.indoors ? 190 : 188, .92, n.disposition, seed);
            }
        }
    }
}

function drawThreat(svg, ctx, t, pose) {
    const seed = hash(t.id);
    const spot = { ...(pose === "behind" ? DISTANCE["on you"] : lookup(DISTANCE, t.distance_word, DISTANCE["far off"], "distance")) };
    if (ctx.indoors && t.distance_word === "far off") { spot.scale = .5; spot.base = 172; }
    const [lo, hi] = spot.band;
    let x = lo + (seed % (hi - lo));
    if (pose === "behind") x = seed % 2 === 0 ? 270 : 730;
    if (pose === "down") {
        const size = spot.scale * .8;
        bodyOnGround(svg, ctx, x - 55 * size, Math.min(spot.base - 2, 194), seed, { pool: false, scale: size, twitch: true });
        return;
    }
    const drawn = { chasing: "chasing", "chasing-fast": "chasing", behind: "attacking" }[pose] || pose;
    const quick = pose === "chasing-fast" || pose === "attacking" || pose === "behind";
    zombie(svg, ctx, x, spot.base, spot.scale, drawn, seed, quick);
}

function zombieLook(seed) {
    const r = rng(seed);
    return {
        build: r(),
        garment: pick(r, ["shirt", "shirt", "coat", "dress", "bare"]),
        hair: pick(r, ["none", "short", "long", "matted"]),
        missingArm: r() < .2 ? (r() < .5 ? -1 : 1) : 0,
        limp: r() < .4 ? (r() < .5 ? -1 : 1) : 0,
        dropShoulder: (r() - .5) * 8,
        headTilt: (r() - .5) * 26,
        jawOpen: r() < .5,
        wounds: 1 + Math.floor(r() * 3),
        r,
    };
}

function zombie(svg, ctx, x, base, scale, posture, seed, quick) {
    const { P } = ctx;
    const look = zombieLook(seed);
    const crawling = posture.startsWith("crawl");
    const outer = el("g", { transform: `translate(${x} ${base}) scale(${scale})` }, svg);
    const g = el("g", { class: "fig" + (quick ? " fast" : posture === "chasing" ? " hurry" : "") + (crawling ? " crawl" : ""), style: `animation-delay:-${(look.r() * 3).toFixed(2)}s` }, outer);
    const rim = el("g", { transform: "translate(1.4 -0.8)", opacity: P.sky0 === PALETTES.night.sky0 ? .5 : .32 }, g);
    const body = el("g", {}, g);
    if (crawling) {
        crawlerShape(rim, P.rim, posture);
        crawlerShape(body, P.fig, posture);
        crawlerDetail(g, ctx, posture);
        return;
    }
    const shape = standingShape(look, posture);
    drawStanding(rim, shape, P.rim);
    drawStanding(body, shape, P.fig);
    standingDetail(g, ctx, look, shape, posture);
}

function standingShape(look, posture) {
    const sw = 12 + look.build * 6, hw = 7 + look.build * 5;
    const drop = look.dropShoulder;
    const shoulderL = [-sw, -82 + Math.max(0, drop)], shoulderR = [sw, -82 + Math.max(0, -drop)];
    const hunch = posture === "idle" ? 4 : posture === "alerted" ? 2 : 6;
    const head = [posture === "idle" ? 5 : posture === "alerted" ? 3 : 0, -99 + hunch];
    const reach = {
        idle:      [[-(sw + 5), -62, -(sw + 3), -43], [sw + 5, -63, sw + 4, -44]],
        alerted:   [[-(sw + 6), -63, -(sw + 9), -47], [sw + 9, -66, sw + 15, -56]],
        chasing:   [[-(sw + 14), -78, -(sw + 26), -86], [sw + 15, -76, sw + 27, -84]],
        attacking: [[-(sw + 20), -80, -(sw + 34), -72], [sw + 22, -82, sw + 36, -76]],
    }[posture];
    return { sw, hw, shoulderL, shoulderR, head, reach, look, seed: Math.floor(look.build * 1e9) ^ look.wounds };
}

function jagged(r, x0, x1, y, depth, teeth) {
    let d = "";
    const step = (x1 - x0) / teeth;
    for (let i = 1; i <= teeth; i++) {
        const xm = x0 + step * (i - .5), xe = x0 + step * i;
        d += ` L${f(xm)} ${f(y + depth * (.4 + r() * .8))} L${f(xe)} ${f(y + r() * depth * .3)}`;
    }
    return d;
}

function drawStanding(g, s, color) {
    const { sw, hw, shoulderL, shoulderR, head, reach, look } = s;
    const r = rng(s.seed);
    const strokes = { stroke: color, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round" };

    const legW = 6.5 + look.build * 3;
    for (const side of [-1, 1]) {
        const limping = look.limp === side;
        const knee = [side * (hw * .7 + (limping ? 5 : 0)), limping ? -20 : -23];
        const foot = [side * (hw + (limping ? 9 : 2)), limping ? -3 : 0];
        el("path", { d: `M${f(side * hw * .55)} -44 L${f(knee[0])} ${knee[1]} L${f(foot[0])} ${foot[1]}`, "stroke-width": legW, ...strokes }, g);
        el("ellipse", { cx: foot[0] + side * 2, cy: foot[1], rx: 5.5, ry: 2.6, fill: color, transform: limping ? `rotate(${side * 30} ${foot[0]} ${foot[1]})` : "" }, g);
        el("path", { d: `M${f(knee[0] - 4)} ${knee[1] - 2} l2 6 l2 -4 l2 5 l2 -6`, fill: color }, g);
    }

    let torso = `M-4 -90 L${f(shoulderL[0])} ${f(shoulderL[1])} L${f(-hw)} -44`;
    if (look.garment === "coat") torso += ` L${f(-hw - 8)} -16` + jagged(r, -hw - 8, hw + 8, -16, 8, 7) + ` L${f(hw)} -44`;
    else if (look.garment === "dress") torso += ` L${f(-hw - 11)} -26` + jagged(r, -hw - 11, hw + 11, -26, 7, 6) + ` L${f(hw)} -46`;
    else if (look.garment === "bare") torso += ` L${f(hw)} -44`;
    else torso += jagged(r, -hw - 2, hw + 2, -42, 6, 5);
    torso += ` L${f(shoulderR[0])} ${f(shoulderR[1])} L4 -90 Z`;
    el("path", { d: torso, fill: color }, g);
    el("rect", { x: -3.5, y: -94, width: 7, height: 8, fill: color }, g);

    for (const [i, side] of [[0, -1], [1, 1]]) {
        const sh = side < 0 ? shoulderL : shoulderR;
        const [ex, ey, hx, hy] = reach[i];
        if (look.missingArm === side) {
            const sx = sh[0] + (ex - sh[0]) * .55, sy = sh[1] + (ey - sh[1]) * .55;
            el("path", { d: `M${f(sh[0])} ${f(sh[1])} L${f(sx)} ${f(sy)}`, "stroke-width": 6 + look.build * 2, ...strokes }, g);
            el("path", { d: `M${f(sx - 3)} ${f(sy)} l2 4 l2 -3 l2 4 l2 -5`, fill: color }, g);
            continue;
        }
        el("path", { d: `M${f(sh[0])} ${f(sh[1])} L${f(ex)} ${ey} L${f(hx)} ${hy}`, "stroke-width": 5.5 + look.build * 2, ...strokes }, g);
        const ang = Math.atan2(hy - ey, hx - ex);
        for (const spread of [-.6, -.2, .2, .6]) {
            const a = ang + spread;
            el("path", { d: `M${f(hx)} ${hy} q${f(Math.cos(a) * 5)} ${f(Math.sin(a) * 5)} ${f(Math.cos(a + .5) * 7)} ${f(Math.sin(a + .5) * 7)}`, "stroke-width": 1.8, ...strokes }, g);
        }
        if (look.garment !== "bare") {
            const mx = (sh[0] + ex) / 2, my = (sh[1] + ey) / 2;
            el("path", { d: `M${f(mx - 3)} ${f(my)} l1 7 l2 -4 l2 6 l2 -8 z`, fill: color }, g);
        }
    }

    const [hx, hy] = head;
    const hg = el("g", { transform: `rotate(${f(look.headTilt)} 0 -90)` }, g);
    el("path", { d: `M${hx - 8} ${hy + 2} q-1 -12 8 -13 q10 0 9 12 q0 5 -3 7 h-11 q-3 -2 -3 -6 z`, fill: color }, hg);
    const jawDrop = look.jawOpen ? 4 : 1;
    el("path", { d: `M${hx - 5.5} ${hy + 8 + jawDrop} h11 l-1.5 5 q-4 2.5 -8 0 z`, fill: color }, hg);
    if (look.jawOpen) el("rect", { x: hx - 4.5, y: hy + 8.5, width: 9, height: jawDrop + .5, fill: color, opacity: .4 }, hg);
    if (look.hair === "long" || look.hair === "matted") {
        const n = look.hair === "long" ? 7 : 4;
        for (let i = 0; i < n; i++) {
            const sx = hx - 7 + i * (14 / (n - 1));
            const len = look.hair === "long" ? 14 + r() * 10 : 6 + r() * 6;
            el("path", { d: `M${f(sx)} ${hy - 9} q${f((sx - hx) * .6)} ${f(len * .4)} ${f((sx - hx) * .4 + (r() - .5) * 4)} ${f(len)}`, "stroke-width": look.hair === "long" ? 1.5 : 2.6, ...strokes }, hg);
        }
    } else if (look.hair === "short") {
        el("path", { d: `M${hx - 8} ${hy - 4} l2 -6 l3 2 l2 -4 l3 3 l3 -4 l2 4 l3 -1 l0 6 z`, fill: color }, hg);
    }
}

function standingDetail(g, ctx, look, shape, posture) {
    const gore = ctx.gore;
    const r = rng(hash("detail") ^ look.wounds ^ Math.floor(look.build * 1e6));
    const [hx, hy] = shape.head;
    const spots = [[shape.sw * .35, -86, 3.5, 2.8], [(r() - .5) * shape.hw, -68 + r() * 10, 5, 2], [-shape.sw * .6, -60 + r() * 8, 3, 3.5]];
    for (const [wx, wy, rx, ry] of spots.slice(0, look.wounds)) {
        el("ellipse", { cx: wx, cy: wy, rx, ry, fill: gore ? BLOOD_FRESH : SCAB, opacity: .95 }, g);
        if (gore) for (let i = 0; i < 2; i++) el("path", { d: `M${f(wx - 1.5 + i * 2.5)} ${f(wy + ry)} v${f(5 + r() * 12)}`, stroke: BLOOD, "stroke-width": 1.1, "stroke-linecap": "round" }, g);
    }
    if (gore && (look.garment === "bare" || look.wounds === 3)) {
        for (let i = 0; i < 4; i++) el("path", { d: `M-8 ${-77 + i * 4.5} q8 3 16 0`, stroke: BONE, "stroke-width": .9, fill: "none", opacity: .35 }, g);
    }
    const hg = el("g", { transform: `rotate(${f(look.headTilt)} 0 -90)` }, g);
    if (look.jawOpen) {
        el("rect", { x: hx - 4.5, y: hy + 8.5, width: 9, height: 4, fill: "#1a0202" }, hg);
        if (gore) {
            for (let i = 0; i < 4; i++) el("rect", { x: hx - 4 + i * 2.2, y: hy + 8.5, width: 1.3, height: 1.6 + (i % 2), fill: BONE, opacity: .8 }, hg);
            el("path", { d: `M${hx - 2} ${hy + 13} v6 M${hx + 2} ${hy + 13} v4`, stroke: BLOOD_FRESH, "stroke-width": 1, "stroke-linecap": "round" }, hg);
        }
    }
    if (posture === "chasing" || posture === "attacking") {
        for (const dx of [-3.3, 3.3]) el("circle", { cx: hx + dx, cy: hy, r: 1.5, fill: "#d2453d" }, hg);
    } else if (posture === "alerted") {
        el("circle", { cx: hx + 3, cy: hy, r: 1.1, fill: "#d2453d", opacity: .6 }, hg);
    } else {
        for (const dx of [-3.3, 3.3]) el("circle", { cx: hx + dx, cy: hy, r: 1.3, fill: "#000", opacity: .8 }, hg);
    }
    if (look.missingArm && gore) {
        const sh = look.missingArm < 0 ? shape.shoulderL : shape.shoulderR;
        const [ex, ey] = shape.reach[look.missingArm < 0 ? 0 : 1];
        const sx = sh[0] + (ex - sh[0]) * .55, sy = sh[1] + (ey - sh[1]) * .55;
        el("path", { d: `M${f(sx)} ${f(sy)} l${look.missingArm * 3} 2`, stroke: BONE, "stroke-width": 1.6, "stroke-linecap": "round", opacity: .85 }, g);
        el("path", { d: `M${f(sx)} ${f(sy + 2)} v${f(6 + r() * 8)}`, stroke: BLOOD, "stroke-width": 1.4, "stroke-linecap": "round" }, g);
    }
}

function crawlerShape(g, color, posture) {
    const strokes = { stroke: color, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round" };
    el("path", { d: "M-28 -8 q4 -12 26 -14 q20 -2 32 4 q4 6 -4 10 q-22 6 -54 0 z", fill: color }, g);
    el("path", { d: "M-28 -9 l-6 3 l-2 -4 l-5 4 l-2 -5 l-4 6 l14 4 z", fill: color }, g);
    el("path", { d: "M26 -24 q2 -9 11 -9 q9 1 8 10 q0 4 -3 6 h-12 q-4 -2 -4 -7 z", fill: color }, g);
    el("path", { d: "M29 -16 h10 l-1 5 q-4 2 -8 0 z", fill: color }, g);
    el("path", { d: "M22 -14 L40 -4 L48 0", "stroke-width": 6, ...strokes }, g);
    const reach = posture === "crawl-chase" ? "M14 -16 L36 -20 L56 -14" : "M14 -16 L30 -12 L44 -2";
    el("path", { d: reach, "stroke-width": 5.5, ...strokes }, g);
    const end = posture === "crawl-chase" ? [56, -14] : [44, -2];
    for (const a of [-.5, 0, .5]) el("path", { d: `M${end[0]} ${end[1]} l${f(Math.cos(a) * 6)} ${f(Math.sin(a) * 6 + 2)}`, "stroke-width": 1.8, ...strokes }, g);
}

function crawlerDetail(g, ctx, posture) {
    if (ctx.gore) {
        el("path", { d: "M-36 -4 q-10 4 -18 0 q-8 -4 -16 2 q-6 4 -14 2", stroke: BLOOD_FRESH, "stroke-width": 2.6, fill: "none", "stroke-linecap": "round" }, g);
        el("path", { d: "M-34 1 q-30 4 -70 1", stroke: BLOOD, "stroke-width": 4, opacity: .6, fill: "none", "stroke-linecap": "round" }, g);
        el("path", { d: "M-30 -6 l-3 2", stroke: BONE, "stroke-width": 1.6, "stroke-linecap": "round" }, g);
    } else {
        el("path", { d: "M-34 1 q-30 4 -70 1", stroke: "#000", "stroke-width": 3, opacity: .3, fill: "none", "stroke-linecap": "round" }, g);
    }
    if (posture === "crawl-chase") for (const dx of [-2.6, 2.6]) el("circle", { cx: 36 + dx, cy: -24, r: 1.3, fill: "#d2453d" }, g);
}

// A living person: upright, clean-edged, lit warm, no wounds and no red. Stance from the disposition band.
function person(svg, ctx, x, base, scale, disposition, seed) {
    const { P } = ctx;
    const r = rng(seed);
    const look = { build: r(), hair: pick(r, ["short", "long", "ponytail", "cap", "hood"]), top: pick(r, ["jacket", "coat", "hoodie"]), bag: r() < .5 };
    const stance = lookup(STANCE, disposition, "pockets", "disposition");
    const outer = el("g", { transform: `translate(${x} ${base}) scale(${scale})` }, svg);
    const g = el("g", { class: "person" + (stance === "cower" ? " scared" : ""), style: `animation-delay:-${(r() * 3).toFixed(2)}s` }, outer);
    const rim = el("g", { transform: "translate(-1.4 -0.8)", opacity: .45 }, g);
    drawPerson(rim, look, stance, WARM_RIM);
    drawPerson(el("g", {}, g), look, stance, P.fig);
}

function drawPerson(g, look, stance, color) {
    const strokes = { stroke: color, fill: "none", "stroke-linecap": "round", "stroke-linejoin": "round" };
    const sw = 12 + look.build * 4, hw = 8 + look.build * 3;
    const cower = stance === "cower", squared = stance === "squared";
    const drop = cower ? 22 : 0;
    const lean = squared ? "rotate(3 0 0)" : cower ? "rotate(-4 0 0)" : "";
    const body = el("g", { transform: lean }, g);

    // Legs: apart when squared up, folded when cowering.
    const spread = squared ? 6 : 0;
    for (const side of [-1, 1]) {
        const knee = cower ? [side * (hw + 6), -22] : [side * (hw * .6 + spread * .6), -23];
        const foot = cower ? [side * (hw + 2), 0] : [side * (hw * .6 + spread), 0];
        const hip = cower ? -24 : -44;
        el("path", { d: `M${f(side * hw * .5)} ${hip} L${f(knee[0])} ${knee[1]} L${f(foot[0])} ${foot[1]}`, "stroke-width": 7 + look.build * 2, ...strokes }, body);
        el("ellipse", { cx: foot[0] + side * 2, cy: 0, rx: 5.5, ry: 2.5, fill: color }, body);
    }

    const top = -84 + drop, hip = -44 + (cower ? 20 : 0);
    let hem = hip + 2;
    if (look.top === "coat") hem = cower ? -6 : -20;
    const flare = look.top === "coat" ? 4 : 1;
    el("path", { d: `M${-sw} ${top} Q0 ${top - 5} ${sw} ${top} L${hw + flare} ${hem} L${-hw - flare} ${hem} Z`, fill: color }, body);
    el("rect", { x: -3.5, y: top - 7, width: 7, height: 8, fill: color }, body);
    if (look.bag) el("path", { d: `M${-sw + 3} ${top} L${hw} ${hip - 4}`, stroke: color, "stroke-width": 2.4 }, body);

    const head = [0, top - 15];
    el("ellipse", { cx: head[0], cy: head[1], rx: 8, ry: 9.5, fill: color }, body);
    if (look.hair === "long") el("path", { d: `M-8.5 ${head[1] - 2} q-1 14 -3 20 h5 l2 -14 z M8.5 ${head[1] - 2} q1 14 3 20 h-5 l-2 -14 z`, fill: color }, body);
    if (look.hair === "ponytail") el("path", { d: `M6 ${head[1] - 6} q10 2 9 16 q-4 -6 -8 -10 z`, fill: color }, body);
    if (look.hair === "cap") el("path", { d: `M-9 ${head[1] - 4} q0 -9 9 -9 q9 0 9 9 h7 v2 h-25 z`, fill: color }, body);
    if (look.hair === "hood" || look.top === "hoodie") el("path", { d: `M-11 ${head[1] + 6} q-2 -18 11 -19 q13 1 11 19 l-3 4 h-16 z`, fill: color }, body);

    const sh = [[-sw, top + 2], [sw, top + 2]];
    const arms = {
        open:    [[-sw - 4, top + 22, -sw - 2, top + 40], [sw + 4, top + 22, sw + 2, top + 40]],
        pockets: [[-sw - 4, top + 20, -hw - 1, top + 34], [sw + 4, top + 20, hw + 1, top + 34]],
        crossed: [[-sw - 7, top + 22, sw - 2, top + 20], [sw + 7, top + 22, -sw + 2, top + 24]],
        squared: [[-sw - 6, top + 18, -sw - 4, top + 34], [sw + 6, top + 18, sw + 4, top + 34]],
        cower:   [[-sw + 2, top - 6, sw - 2, top - 22], [sw - 2, top - 6, -sw + 2, top - 22]],
    }[stance];
    arms.forEach(([ex, ey, hx, hy], i) => {
        el("path", { d: `M${f(sh[i][0])} ${f(sh[i][1])} L${f(ex)} ${f(ey)} L${f(hx)} ${f(hy)}`, "stroke-width": 6 + look.build * 1.5, ...strokes }, body);
        if (stance === "squared") el("circle", { cx: hx, cy: hy, r: 3.6, fill: color }, body);
    });
}

// ---------------------------------------------------------------- the strip's controls

function stored(key, fallback) {
    try {
        return localStorage.getItem(key) ?? fallback;
    } catch {
        return fallback;
    }
}

function keep(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch {
        // A browser that refuses storage just forgets the choice.
    }
}

let latest = null;

function redraw(strip) {
    const hidden = strip.classList.contains("collapsed");
    strip.classList.toggle("dead", !!(latest && latest.game_over));
    if (latest && !hidden) paint(strip.querySelector(".scene-art"), latest);
}

function wireControls(strip) {
    const hide = strip.querySelector(".scene-hide");
    const bloodButton = strip.querySelector(".scene-blood");
    const showHidden = (hidden) => {
        strip.classList.toggle("collapsed", hidden);
        hide.textContent = hidden ? "+" : "–";
        hide.setAttribute("aria-label", hidden ? "Show the scene" : "Hide the scene");
    };
    const showBlood = () => {
        bloodButton.textContent = blood === "full" ? "Blood: full" : "Blood: reduced";
        bloodButton.setAttribute("aria-label", `Blood in the scene: ${blood}. Press to change.`);
    };
    blood = stored(STORAGE_BLOOD, "full") === "reduced" ? "reduced" : "full";
    showBlood();
    showHidden(stored(STORAGE_HIDDEN, "no") === "yes");
    hide.addEventListener("click", () => {
        const hidden = !strip.classList.contains("collapsed");
        keep(STORAGE_HIDDEN, hidden ? "yes" : "no");
        showHidden(hidden);
        redraw(strip);
    });
    bloodButton.addEventListener("click", () => {
        blood = blood === "full" ? "reduced" : "full";
        keep(STORAGE_BLOOD, blood);
        showBlood();
        redraw(strip);
    });
}

// Draws the strip from one snapshot; the page calls it on every render.
function drawScene(snapshot) {
    const strip = document.getElementById("scene-strip");
    if (!strip || !snapshot.scene) return;
    if (latest === null) wireControls(strip);
    latest = snapshot;
    redraw(strip);
}

return drawScene;
})();
