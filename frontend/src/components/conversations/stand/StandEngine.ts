import type { Outfit } from "@/lib/api";
import { FrameGate, pixelRatio } from "@/lib/standFrames";

import type {
  AnimationState,
  AssetManager,
  ClippingAttachment,
  SceneRenderer,
  Skeleton,
  SlotData,
  Slot,
  SpineRuntime,
  TextureAtlas,
} from "./spineRuntime";

/** 取景（spec「渲染」）：手机「大立绘」贴着头顶、到膝；电脑「半身 ADV」贴着头顶、到腰。 */
export type Framing = "knees" | "waist";

/** 取景的高度，占身体的比例。 */
const FRAMING_HEIGHT: Record<Framing, number> = { knees: 0.85, waist: 0.66 };
/** 取景的宽度不窄于身体的这个比例，免得竖屏上只剩一张脸。 */
const MIN_WIDTH = 0.7;
/** 头顶上方留的空，占身体高度的比例。 */
const HEADROOM = 0.03;

/** 轨道照原作 ADV：0 身体、1 表情；2 点头、3 视线、5 口型由「选动画」接上（ticket 15）。 */
const TRACK = { body: 0, face: 1 } as const;
/** 同一条轨道上换动画时的混合时间（秒）。 */
const MIX_SECONDS = 0.3;
/** 一帧最多推进这么久（秒）：卡了一下或者刚恢复时，动作不会一下子跳过去。 */
const MAX_STEP_SECONDS = 0.1;

const UNPACK_PREMULTIPLY_ALPHA_WEBGL = 0x9241;

/** 这台设备上画不了立绘：浏览器不支持 WebGL。 */
export class StandUnavailable extends Error {}

/** 载入好的一套衣装：骨架、它的动画状态和这套衣装有哪些动画。 */
type Pose = {
  skeleton: Skeleton;
  state: AnimationState;
  animations: ReadonlySet<string>;
  /** 初始姿势下整个人的范围，取景据此计算。 */
  bounds: { x: number; y: number; width: number; height: number };
  /** 见过的剪裁，按剪裁附件记下它原本的结束插槽（见 `keepClipsEnding`）。 */
  clips: Map<ClippingAttachment, Clip>;
};

type Clip = { slot: Slot; end: SlotData; detached: boolean };

/**
 * 通话层上的立绘（spec「渲染」）：在一块画布上载入一套衣装，每帧推进动画并绘制。不依赖 React。
 *
 * 现在只播待机（身体 `wait`、表情 `face_wait`）。runtime 的几个已知问题都在这里处理：剪裁不结束、
 * 预乘 alpha、上下文丢失后恢复、React 开发模式下同一块画布上重建引擎。像素比不超过 2、最多 60 帧，
 * 暂停时（通话层收起）不画。
 */
export class StandEngine {
  private readonly gl: WebGLRenderingContext;
  private readonly renderer: SceneRenderer;
  private readonly assets: AssetManager;
  private readonly listeners = new AbortController();
  private readonly gate = new FrameGate();
  private pose: Pose | null = null;
  private raf = 0;
  private last = 0;
  private paused = false;
  private lost = false;
  private disposed = false;

  /**
   * 在 `canvas` 上准备好绘制；浏览器不支持 WebGL 时抛出 `StandUnavailable`。
   * `framing` 可以随时改，下一帧起按新的取景画。
   */
  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly spine: SpineRuntime,
    public framing: Framing,
  ) {
    const signal = this.listeners.signal;
    // 要注册在创建 ManagedWebGLRenderingContext 之前：恢复时浏览器按注册顺序调用监听，
    // 先重新开启「上传时预乘 alpha」，runtime 自己的监听再重新上传贴图，否则恢复后会出白边。
    // 恢复不了时画布一直是空的，通话层上就只剩背景图和纱，这次通话不再重试。
    canvas.addEventListener("webglcontextlost", () => (this.lost = true), { signal });
    canvas.addEventListener(
      "webglcontextrestored",
      () => {
        this.gl.pixelStorei(UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
        this.lost = false;
      },
      { signal },
    );
    const context = new spine.webgl.ManagedWebGLRenderingContext(canvas, { alpha: true, premultipliedAlpha: true });
    if (!context.gl) {
      this.listeners.abort();
      throw new StandUnavailable("浏览器不支持 WebGL");
    }
    this.gl = context.gl;
    this.lost = this.gl.isContextLost();
    // 贴图上传时预乘 alpha，绘制时也按预乘处理，否则部分衣装脸上有白边、关节处有细线。
    this.gl.pixelStorei(UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    this.renderer = new spine.webgl.SceneRenderer(canvas, context, true);
    this.assets = new spine.webgl.AssetManager(context);
  }

  /**
   * 载入一套衣装，摆好待机姿势后开始绘制。素材加载不到、数据读不了时 reject。
   * 现在一个引擎只载入一套；换衣装（ticket 19）时要在这里释放上一套的素材。
   */
  async load(outfit: Outfit): Promise<void> {
    const json = `${outfit.url}data.json`;
    const atlas = `${outfit.url}data.atlas`;
    // 等两份都有了结果再往下走：先失败的那份不能让另一份在引擎销毁之后才把贴图传上去。
    const results = await Promise.allSettled([
      new Promise<void>((resolve, reject) =>
        this.assets.loadText(json, () => resolve(), (_, message) => reject(new Error(message))),
      ),
      new Promise<void>((resolve, reject) =>
        this.assets.loadTextureAtlas(atlas, () => resolve(), (_, message) => reject(new Error(message))),
      ),
    ]);
    if (this.disposed) {
      this.assets.dispose();
      return;
    }
    for (const result of results) if (result.status === "rejected") throw result.reason;

    const spine = this.spine;
    const loader = new spine.AtlasAttachmentLoader(this.assets.get(atlas) as TextureAtlas);
    const data = new spine.SkeletonJson(loader).readSkeletonData(this.assets.get(json) as string);
    const skeleton = new spine.Skeleton(data);
    if (data.findSkin("normal")) skeleton.setSkinByName("normal");
    skeleton.setToSetupPose();
    skeleton.updateWorldTransform();
    const offset = new spine.Vector2();
    const size = new spine.Vector2();
    skeleton.getBounds(offset, size, []);
    const stateData = new spine.AnimationStateData(data);
    stateData.defaultMix = MIX_SECONDS;

    this.pose = {
      skeleton,
      state: new spine.AnimationState(stateData),
      animations: new Set(data.animations.map((a) => a.name)),
      bounds: { x: offset.x, y: offset.y, width: size.x, height: size.y },
      clips: new Map(),
    };
    this.idle();
    this.start();
  }

  /** 暂停（通话层收起时）不画，也不推进动画；恢复后从当前姿势接着画。 */
  setPaused(paused: boolean): void {
    this.paused = paused;
    if (paused) this.stop();
    else this.start();
  }

  /**
   * 停止绘制并释放素材。不调用 `loseContext()`：React 开发模式下 effect 会执行两次，
   * 在同一块画布上重建引擎时拿到的还是同一个上下文，丢掉它新引擎就画不出来了。
   */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.stop();
    this.listeners.abort();
    this.pose = null;
    this.assets.dispose();
    this.renderer.dispose();
  }

  /** 待机：身体 `wait`、表情 `face_wait`，都循环。缺了哪个就不放，交给另一条轨道和初始姿势。 */
  private idle(): void {
    this.play(TRACK.body, "wait", true);
    this.play(TRACK.face, "face_wait", true);
  }

  private play(track: number, name: string, loop: boolean): void {
    if (this.pose?.animations.has(name)) this.pose.state.setAnimation(track, name, loop);
  }

  private start(): void {
    if (this.raf || !this.pose || this.paused || this.disposed) return;
    this.last = 0;
    this.raf = requestAnimationFrame(this.frame);
  }

  private stop(): void {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private readonly frame = (now: number): void => {
    this.raf = requestAnimationFrame(this.frame);
    if (!this.gate.shouldDraw(now)) return;
    const step = this.last ? Math.min((now - this.last) / 1000, MAX_STEP_SECONDS) : 0;
    this.last = now;
    if (this.pose && !this.lost) this.draw(this.pose, step);
  };

  private draw(pose: Pose, step: number): void {
    const { canvas, gl, renderer } = this;
    const ratio = pixelRatio(window.devicePixelRatio);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    pose.state.update(step);
    pose.state.apply(pose.skeleton);
    pose.skeleton.updateWorldTransform();
    this.keepClipsEnding(pose);
    this.aim(pose, width / height);
    renderer.begin();
    renderer.drawSkeleton(pose.skeleton, true);
    renderer.end();
  }

  /** 按取景对准镜头：贴着头顶，高度是身体的一段，宽度不窄于身体的约 70%，左右居中。 */
  private aim({ bounds }: Pose, aspect: number): void {
    const viewHeight = Math.max(bounds.height * FRAMING_HEIGHT[this.framing], (bounds.width * MIN_WIDTH) / aspect);
    const top = bounds.y + bounds.height * (1 + HEADROOM);
    const camera = this.renderer.camera;
    camera.position.x = bounds.x + bounds.width / 2;
    camera.position.y = top - viewHeight / 2;
    camera.setViewport(viewHeight * aspect, viewHeight);
  }

  /**
   * 绕开 spine-ts 3.6 的剪裁 bug（不改 runtime）：渲染器遇到没有附件的插槽直接跳过，也就跳过了
   * 「剪裁到此结束」的判断，结束插槽当下没有附件时剪裁永远不结束，后面画的东西全被裁掉
   * （2215 套里有 304 套在初始姿势下就会触发，例如「花風Smiley」的眼睛、睫毛、眉毛）。
   * 每帧把结束插槽改成「剪裁开始之后、原结束插槽为止，最后一个真的会画出来的插槽」；
   * 范围里这一帧什么都不画时，这一帧摘掉剪裁附件，下一帧有东西画了再挂回去。
   */
  private keepClipsEnding({ skeleton, clips }: Pose): void {
    const { ClippingAttachment, RegionAttachment, MeshAttachment } = this.spine;
    for (const slot of skeleton.slots) {
      const attachment = slot.getAttachment();
      if (attachment instanceof ClippingAttachment && attachment.endSlot && !clips.has(attachment)) {
        clips.set(attachment, { slot, end: attachment.endSlot, detached: false });
      }
    }
    const order = skeleton.drawOrder;
    for (const [clip, c] of clips) {
      const current = c.slot.getAttachment();
      if (current !== clip && !(c.detached && current === null)) {
        c.detached = false; // 动画给这个插槽换上了别的附件，不再归这里管
        continue;
      }
      const from = order.indexOf(c.slot);
      const to = order.findIndex((slot) => slot.data === c.end);
      if (from < 0 || to < 0) continue;
      let last: SlotData | null = null;
      for (let i = to; i > from; i--) {
        const drawn = order[i].getAttachment();
        if (drawn instanceof RegionAttachment || drawn instanceof MeshAttachment) {
          last = order[i].data;
          break;
        }
      }
      if (last) {
        clip.endSlot = last;
        if (c.detached) c.slot.setAttachment(clip);
        c.detached = false;
      } else if (!c.detached) {
        c.slot.setAttachment(null);
        c.detached = true;
      }
    }
  }
}
