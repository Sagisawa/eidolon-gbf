/**
 * 第 5 幕「记忆」的 3D 场景（.scratch/landing-memory-3d）：一张单独的 three.js 画布（WebGL 渲染器，ADR-0016 的修订），
 * 固定铺满视口、叠在光层上面，把落地页模型给的第 5 幕场景状态（model/memory.ts 的 MemoryScene）画出来。three.js
 * 和这个模块只在运动档、滚到第 5 幕前约一屏时才由 LightStage 动态 import（three.js 和第 4 幕的手机共用一个包，
 * 这里的场景代码单独一个包），不进首屏。
 *
 * - 相机照模型摆：正交相机，注视点、取景半高、方位角都是模型给的，和 DOM 上按 project 摆的东西同一个出处。
 * - 场景：夜空渐变和星星（铺在画面上，不随镜头转）；四座浮岛的柱子，顶面亮、两侧一明一暗、往下渐隐进夜色；
 *   演员脚下她印象色的地砖。
 * - 体素小人：从角色接口给的地址下载体素文件（scripts/glb-voxelize.mts 的格式，不等它：布景先画），每人露在外面的面合成一份网格，
 *   顶点色，顶面、底面压到 0.86、0.78 留住方块感；按 `front` 缩放到场景里的身高，默认朝着镜头，轻轻起伏。
 *   地址没有、下载或解析失败时，站着的是她印象色的小方块，上面写她的名字。下载、合成一次，记在模块里：
 *   手机上离开这一段释放了上下文，回来时重建渲染器，不重新下载。
 * - 档位：DPR 按档位封顶。
 */

import {
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  Color,
  DirectionalLight,
  Group,
  HemisphereLight,
  type Material,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  type MeshLambertMaterialParameters,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  type Texture,
  WebGLRenderer,
} from "three";

import type { CanvasLayer } from "./canvasStage";
import { idle } from "./idle";
import { cameraBasis, FIGURE_HEIGHT, ISLAND_SIZE, ISLANDS, STANDS, type Actor, type MemoryScene } from "./model/memory";
import type { Quality } from "./model/tier";

/** 体素文件（scripts/glb-voxelize.mts 的 Voxels）。 */
type Voxels = {
  size: [w: number, h: number, d: number];
  front: number;
  palette: string[];
  voxels: number[];
};

/** 一位小人露在外面的面合成的网格，脚底在原点、正面朝 +z。 */
type FigureMesh = { position: Float32Array; normal: Int8Array; color: Float32Array; index: Uint32Array };

/** 体素文件下载多久没回来就当加载失败。 */
const VOXELS_TIMEOUT_MS = 30000;
/** 顶面、底面的颜色压到这么多：表面是一级级台阶，压得太狠每一级都成了一道横纹，不压顶面又迎着光成了亮线。 */
const TOP_SHADE = 0.86;
const BOTTOM_SHADE = 0.78;
/** 小人自己亮一点：夜色的紫光下肤色发灰，在自发光里加上一份自己的底色。 */
const FIGURE_LIFT = 0.18;
/** 相机退到注视点后面多远：正交投影，远近只管裁切。 */
const CAMERA_DISTANCE = 50;
/** 柱子的侧面往下渐隐成这个颜色：夜空渐变中段的颜色，光照以后再混，柱脚才融进夜空、不发黑。 */
const NIGHT = "#151030";
/** 柱子往下伸到这么低：竖屏取景高，柱脚不能露在画面里。 */
const PILLAR_FOOT = -32;

const figures = new Map<string, Promise<FigureMesh>>();

/** 下载、合成一位小人的网格；同一页里同一个地址只做一次（失败了下次重试）。 */
function loadFigure(url: string): Promise<FigureMesh> {
  let mesh = figures.get(url);
  if (!mesh) {
    mesh = fetch(url, { signal: AbortSignal.timeout(VOXELS_TIMEOUT_MS) })
      .then((res) => {
        if (!res.ok) throw new Error(`体素文件 ${res.status}`);
        return res.json() as Promise<unknown>;
      })
      .then((data) => figureMesh(asVoxels(data)))
      .catch((e: unknown) => {
        figures.delete(url);
        throw e;
      });
    figures.set(url, mesh);
  }
  return mesh;
}

function asVoxels(data: unknown): Voxels {
  const v = data as Partial<Voxels> | null;
  const ok =
    !!v &&
    Array.isArray(v.size) &&
    v.size.length === 3 &&
    v.size.every((n) => Number.isInteger(n) && n > 0) &&
    typeof v.front === "number" &&
    v.front > 0 &&
    Array.isArray(v.palette) &&
    Array.isArray(v.voxels) &&
    v.voxels.length % 4 === 0;
  if (!ok) throw new Error("体素文件的格式不对");
  return v as Voxels;
}

/** 每个方向的面：法线和逆时针（从外面看）的四个角。 */
const FACES: readonly { n: [number, number, number]; corners: [number, number, number][]; shade: number }[] = [
  { n: [1, 0, 0], corners: [[1, 0, 0], [1, 1, 0], [1, 1, 1], [1, 0, 1]], shade: 1 },
  { n: [-1, 0, 0], corners: [[0, 0, 0], [0, 0, 1], [0, 1, 1], [0, 1, 0]], shade: 1 },
  { n: [0, 1, 0], corners: [[0, 1, 0], [0, 1, 1], [1, 1, 1], [1, 1, 0]], shade: TOP_SHADE },
  { n: [0, -1, 0], corners: [[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]], shade: BOTTOM_SHADE },
  { n: [0, 0, 1], corners: [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], shade: 1 },
  { n: [0, 0, -1], corners: [[0, 0, 0], [0, 1, 0], [1, 1, 0], [1, 0, 0]], shade: 1 },
];

/** 体素合成一份网格：只要露在外面的面（旁边那一格是空的），一格一种颜色。按 `front` 缩放到场景里的身高。 */
function figureMesh(v: Voxels): FigureMesh {
  const [W, H, D] = v.size;
  const size = FIGURE_HEIGHT / v.front;
  const solid = new Uint8Array(W * H * D);
  const cells: number[] = [];
  const inside = (x: number, y: number, z: number) => x >= 0 && y >= 0 && z >= 0 && x < W && y < H && z < D;
  for (let i = 0; i < v.voxels.length; i += 4) {
    const [x, y, z, c] = [v.voxels[i], v.voxels[i + 1], v.voxels[i + 2], v.voxels[i + 3]];
    if (!inside(x, y, z) || !v.palette[c]) continue;
    solid[x + W * (y + H * z)] = 1;
    cells.push(x, y, z, c);
  }
  const filled = (x: number, y: number, z: number) => inside(x, y, z) && solid[x + W * (y + H * z)] === 1;
  // 调色板转成线性色（顶点色在线性空间里算光照）。
  const linear = v.palette.map((hex) => new Color(hex).toArray() as [number, number, number]);

  let faces = 0;
  for (let i = 0; i < cells.length; i += 4)
    for (const f of FACES) if (!filled(cells[i] + f.n[0], cells[i + 1] + f.n[1], cells[i + 2] + f.n[2])) faces++;
  const position = new Float32Array(faces * 12);
  const normal = new Int8Array(faces * 12);
  const color = new Float32Array(faces * 12);
  const index = new Uint32Array(faces * 6);
  let k = 0;
  for (let i = 0; i < cells.length; i += 4) {
    const [x, y, z, c] = [cells[i], cells[i + 1], cells[i + 2], cells[i + 3]];
    const rgb = linear[c];
    for (const f of FACES) {
      if (filled(x + f.n[0], y + f.n[1], z + f.n[2])) continue;
      f.corners.forEach(([cx, cy, cz], j) => {
        const o = (k * 4 + j) * 3;
        position[o] = (x + cx - W / 2) * size;
        position[o + 1] = (y + cy) * size;
        position[o + 2] = (z + cz - D / 2) * size;
        normal[o] = f.n[0] * 127;
        normal[o + 1] = f.n[1] * 127;
        normal[o + 2] = f.n[2] * 127;
        color[o] = rgb[0] * f.shade;
        color[o + 1] = rgb[1] * f.shade;
        color[o + 2] = rgb[2] * f.shade;
      });
      index.set([k * 4, k * 4 + 1, k * 4 + 2, k * 4, k * 4 + 2, k * 4 + 3], k * 6);
      k++;
    }
  }
  return { position, normal, color, index };
}

export type MemoryLayer = CanvasLayer & {
  /** 画这一刻的场景；`time` 是秒，给小人的起伏用。 */
  render(memory: MemoryScene, time: number): void;
};

/**
 * 在 `canvas` 上建第 5 幕的场景，分几批建：建上下文、搭布景、编译着色器各占一批，每批之间让出主线程。建不起来时
 * reject，调用方收起画布。演员的体素文件同时开始下载，不等它们：布景先画出来，她站的地方先空着，网格合成好了再站上去，
 * 加载不到就换成她印象色的方块和名字（`font` 是写名字的字体）。
 */
export async function createMemoryLayer(canvas: HTMLCanvasElement, quality: Quality, actors: readonly Actor[], font: string): Promise<MemoryLayer> {
  const loading = actors.map((a) => (a.voxels ? loadFigure(a.voxels) : Promise.reject(new Error("没有体素文件"))));
  // 还没下载完就放掉了上下文：之后到的不再往场景里放。
  let destroyed = false;
  const dprOf = (q: Quality) => Math.min(window.devicePixelRatio || 1, q.dprCap);
  const renderer = new WebGLRenderer({ canvas, antialias: true });
  renderer.outputColorSpace = SRGBColorSpace;
  await idle();

  const owned: { dispose(): void }[] = [];
  const own = <T extends { dispose(): void }>(x: T) => (owned.push(x), x);
  const lambert = (params: MeshLambertMaterialParameters) => own(new MeshLambertMaterial(params));
  const scene = new Scene();

  // —— 光：天光从上往下、偏紫；一盏暖色的主光从右前上方打来，柱子两侧一明一暗；一盏紫色的补光从背面。
  scene.add(new HemisphereLight(0xc9c2ff, 0x2a1f3d, 1.5));
  const sun = new DirectionalLight(0xffe2cc, 2.2);
  sun.position.set(2, 10, 7);
  sun.target.position.set(5, 0, 1);
  scene.add(sun, sun.target);
  const fill = new DirectionalLight(0x8a7cff, 0.6);
  fill.position.set(8, 2, -2);
  scene.add(fill);

  // —— 夜空：渐变和星星，按画面的宽高比画，星星不被拉成椭圆。
  let skyAspect = 0;
  let sky: Texture | null = null;
  const paintSky = (aspect: number) => {
    sky?.dispose();
    sky = skyTexture(aspect);
    scene.background = sky;
    skyAspect = aspect;
  };

  // —— 四座浮岛：柱子和一圈沿，往下渐隐进夜色。
  const pillarMat = fadeIntoNight(lambert({ vertexColors: true }));
  ISLANDS.forEach(([x, y, z]) => {
    scene.add(new Mesh(own(pillarGeometry(ISLAND_SIZE, y, y - PILLAR_FOOT, 10 + y, x, z, "#8d79b3", "#e6dbf2")), pillarMat));
    scene.add(new Mesh(own(pillarGeometry(ISLAND_SIZE + 0.12, y - 0.12, 0.35, 0.35, x, z, "#a893c9", "#cdbde6")), pillarMat));
  });

  // —— 演员：脚下她印象色的地砖，站着她的体素小人（加载不到时是她印象色的方块和名字）。
  const tileGeo = own(new BoxGeometry(0.9, 0.04, 0.9));
  const blob = own(shadowTexture());
  const blobGeo = own(new PlaneGeometry(0.84, 0.84));
  const blobMat = own(new MeshBasicMaterial({ map: blob, transparent: true, depthWrite: false }));
  const figureMat = lift(lambert({ vertexColors: true }));
  const cubeGeo = own(new BoxGeometry(0.55, 0.55, 0.55));
  const bodies: Group[] = [];
  const stand = (body: Group) => (mesh: FigureMesh) => {
    if (!destroyed) body.add(new Mesh(own(figureGeometry(mesh)), figureMat));
  };
  const standIn = (actor: Actor, body: Group, group: Group) => () => {
    if (destroyed) return;
    const cube = new Mesh(cubeGeo, lambert({ color: actor.color, emissive: actor.color, emissiveIntensity: 0.25 }));
    cube.position.y = 0.275;
    body.add(cube);
    const label = nameSprite(actor.name, font, own);
    label.position.y = 0.95;
    group.add(label);
  };
  actors.forEach((actor, k) => {
    const [x, y, z] = STANDS[actor.island];
    const tile = new Mesh(tileGeo, lambert({ color: actor.color, emissive: actor.color, emissiveIntensity: 0.3 }));
    tile.position.set(x, y + 0.02, z);
    scene.add(tile);
    const group = new Group();
    group.position.set(x, y + 0.04, z);
    scene.add(group);
    const body = new Group();
    group.add(body);
    bodies.push(body);
    const shadow = new Mesh(blobGeo, blobMat);
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.005;
    group.add(shadow);
    loading[k].then(stand(body), standIn(actor, body, group));
  });
  await idle();

  const camera = new OrthographicCamera(-1, 1, 1, -1, 1, CAMERA_DISTANCE * 3);
  let q = quality;
  let size = { w: 1, h: 1 };
  const applyQuality = () => renderer.setPixelRatio(dprOf(q));
  applyQuality();

  // 先编一遍着色器，第一次显出来时不顿：支持 KHR_parallel_shader_compile 的浏览器异步编，不卡主线程。
  paintSky(1);
  if (renderer.extensions.has("KHR_parallel_shader_compile")) await renderer.compileAsync(scene, camera);
  else renderer.compile(scene, camera);
  await idle();

  return {
    resize(w, h) {
      size = { w, h };
      renderer.setSize(w, h, false);
      // 宽高比变得多了才重画夜空：手机上地址栏收起放下只差一点，不重画。
      if (Math.abs(Math.log(w / h / skyAspect)) > 0.15) paintSky(w / h);
    },
    setQuality(next) {
      q = next;
      applyQuality();
    },
    render(memory, time) {
      const cam = memory.camera;
      const aspect = size.w / size.h;
      camera.left = -cam.half * aspect;
      camera.right = cam.half * aspect;
      camera.top = cam.half;
      camera.bottom = -cam.half;
      const [tx, ty, tz] = cam.target;
      const { back } = cameraBasis(cam);
      camera.position.set(tx + back[0] * CAMERA_DISTANCE, ty + back[1] * CAMERA_DISTANCE, tz + back[2] * CAMERA_DISTANCE);
      camera.lookAt(tx, ty, tz);
      camera.updateProjectionMatrix();
      // 默认朝着镜头，轻轻起伏（各人错开）。
      bodies.forEach((body, k) => {
        body.rotation.y = cam.azimuth;
        body.scale.y = 1 + Math.sin(time * 1.8 + k * 1.3) * 0.006;
      });
      renderer.render(scene, camera);
    },
    destroy() {
      destroyed = true;
      owned.forEach((x) => x.dispose());
      sky?.dispose();
      renderer.dispose();
      // 上下文已经丢了的时候（收到 webglcontextlost 才来收起）不用、也放不了。
      if (!renderer.getContext().isContextLost()) renderer.forceContextLoss();
    },
  };
}

/**
 * 一根柱子：边长 `w`，顶面在 `top`，往下 `depth` 深。顶面是 `topColor`，侧面是 `color`；`fade` 属性是侧面融进夜色的
 * 程度（fadeIntoNight），往下 `fade` 深的地方完全融进去。侧面竖着切成一段段，渐隐才照着曲线走，不是首尾之间的直线。
 */
function pillarGeometry(w: number, top: number, depth: number, fade: number, x: number, z: number, color: string, topColor: string): BufferGeometry {
  const g = new BoxGeometry(w, depth, w, 1, Math.max(1, Math.ceil(depth / 2))).toNonIndexed();
  g.translate(x, top - depth / 2, z);
  const pos = g.getAttribute("position");
  const nor = g.getAttribute("normal");
  const colors = new Float32Array(pos.count * 3);
  const fades = new Float32Array(pos.count);
  const side = new Color(color);
  const lit = new Color(topColor);
  for (let i = 0; i < pos.count; i++) {
    const c = nor.getY(i) > 0.5 ? lit : side;
    colors.set([c.r, c.g, c.b], i * 3);
    fades[i] = nor.getY(i) > 0.5 ? 0 : Math.min(1, Math.max(0, (top - pos.getY(i)) / fade)) ** 0.8;
  }
  g.setAttribute("color", new BufferAttribute(colors, 3));
  g.setAttribute("fade", new BufferAttribute(fades, 1));
  return g;
}

function figureGeometry(mesh: FigureMesh): BufferGeometry {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(mesh.position, 3));
  g.setAttribute("normal", new BufferAttribute(mesh.normal, 3, true));
  g.setAttribute("color", new BufferAttribute(mesh.color, 3));
  g.setIndex(new BufferAttribute(mesh.index, 1));
  return g;
}

/** 光照算完以后，按顶点的 `fade` 属性把颜色混向夜空的颜色。 */
function fadeIntoNight<M extends Material>(m: M): M {
  const night = new Color(NIGHT);
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uNight = { value: night };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", `#include <common>
attribute float fade;
varying float vFade;`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>
  vFade = fade;`);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
uniform vec3 uNight;
varying float vFade;`)
      .replace("#include <opaque_fragment>", `outgoingLight = mix(outgoingLight, uNight, vFade);
#include <opaque_fragment>`);
  };
  return m;
}

/** 在自发光里加上一份自己的底色。 */
function lift<M extends Material>(m: M): M {
  m.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      `#include <emissivemap_fragment>
  totalEmissiveRadiance += diffuseColor.rgb * ${FIGURE_LIFT.toFixed(2)};`,
    );
  };
  return m;
}

/** 一块画布当贴图。 */
function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  draw(c.getContext("2d")!);
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace;
  return t;
}

/** 夜空：上方偏紫的径向渐变，撒一层星星（固定的种子，每次一样）。长边 1024 像素。 */
function skyTexture(aspect: number): CanvasTexture {
  const w = Math.round(aspect >= 1 ? 1024 : 1024 * aspect);
  const h = Math.round(aspect >= 1 ? 1024 / aspect : 1024);
  return canvasTexture(w, h, (g) => {
    const grad = g.createRadialGradient(w / 2, h * 0.3, 50, w / 2, h * 0.42, Math.max(w, h) * 0.9);
    grad.addColorStop(0, "#2d2152");
    grad.addColorStop(0.55, NIGHT);
    grad.addColorStop(1, "#090716");
    g.fillStyle = grad;
    g.fillRect(0, 0, w, h);
    const rnd = seeded(11);
    const count = Math.round((380 * w * h) / (1024 * 1024));
    for (let i = 0; i < count; i++) {
      g.fillStyle = `rgba(230,225,255,${0.12 + rnd() * 0.5})`;
      g.beginPath();
      g.arc(rnd() * w, rnd() * h, rnd() * 1.4, 0, Math.PI * 2);
      g.fill();
    }
  });
}

/** 脚下一团淡淡的影子。 */
function shadowTexture(): CanvasTexture {
  return canvasTexture(64, 64, (g) => {
    const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, "rgba(10,6,24,0.55)");
    grad.addColorStop(1, "rgba(10,6,24,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
  });
}

/** 方块上她的名字：半透明深色胶囊里的白字，总是朝着镜头。 */
function nameSprite(name: string, font: string, own: <T extends { dispose(): void }>(x: T) => T): Sprite {
  const css = `600 44px ${font}`;
  const probe = document.createElement("canvas").getContext("2d")!;
  probe.font = css;
  const w = Math.ceil(probe.measureText(name).width) + 48;
  const map = own(
    canvasTexture(w, 72, (g) => {
      g.fillStyle = "rgba(20,16,40,0.78)";
      g.beginPath();
      g.roundRect(0, 0, w, 72, 36);
      g.fill();
      g.font = css;
      g.fillStyle = "#f3eeff";
      g.textBaseline = "middle";
      g.fillText(name, 24, 38);
    }),
  );
  const sprite = new Sprite(own(new SpriteMaterial({ map, transparent: true, depthWrite: false })));
  sprite.scale.set((0.22 * w) / 72, 0.22, 1);
  return sprite;
}

/** 固定种子的伪随机数（0 到 1）。 */
function seeded(seed: number) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}
