"use client";

// 临时示例路由（shadcn-redesign 底座波，清理波删掉）：在两位印象色差别大的角色的子树里，
// 单独检查她的颜色注入 shadcn 变量的效果（验收清单第 2、3 行）。文案只给开发者看，不进 i18n。
import { useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { herVars } from "@/theme/herVars";
import { MoreIcon, PhoneIcon, SendIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

/** 两位印象色差别大的角色：真乃的浅粉、めぐる的黄（characters.toml）。 */
const SAMPLES = [
  { name: "櫻木真乃", color: "#ffbad6", line: "ほわっ……そうだったんですか。", subtitle: "呼哇……原来是这样啊。" },
  { name: "八宮めぐる", color: "#ffe012", line: "ねえねえ、一緒に行こうよ！", subtitle: "呐呐，一起去吧！" },
];

export default function PreviewPage() {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 bg-background p-6 text-foreground">
      <header className="flex flex-col gap-1">
        <h1 className="text-list-title">示例：她的颜色注入 shadcn</h1>
        <p className="text-body text-muted-foreground">
          每一栏是一位角色的对话子树（herVars）。primary 按钮、焦点环、壁纸、发送键、未读数应是她的颜色； 浮层通过
          container 渲染在子树里，也带她的颜色。按 Tab 看焦点环。最后一栏是强制深色（.dark）的子树。
        </p>
      </header>
      <div className="grid gap-6 md:grid-cols-3">
        {SAMPLES.map((sample) => (
          <Subtree key={sample.name} {...sample} />
        ))}
        <Subtree {...SAMPLES[0]} forcedDark />
      </div>
    </main>
  );
}

function Subtree({
  name,
  color,
  line,
  subtitle,
  forcedDark = false,
}: (typeof SAMPLES)[number] & { forcedDark?: boolean }) {
  const subtree = useRef<HTMLElement>(null);
  return (
    <section
      ref={subtree}
      style={herVars(color)}
      className={cn("flex flex-col overflow-hidden rounded-xl bg-background text-foreground", forcedDark && "dark")}
    >
      {/* 页首和消息区铺同一张壁纸（DESIGN.md「The Wallpaper Rule」）。 */}
      <div className="bg-her-wall">
        <div className="flex items-center gap-2 px-4 py-3">
          <h2 className="flex-1 text-header">
            {name}
            {forcedDark && <span className="ml-2 text-meta text-muted-foreground">强制深色</span>}
          </h2>
          <Button variant="ghost" size="icon" aria-label="打电话">
            <PhoneIcon className="text-her-mark" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="更多" />}>
              <MoreIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent container={subtree} align="end">
              <DropdownMenuItem>开始新对话</DropdownMenuItem>
              <DropdownMenuItem>换衣装</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive">挂断并离开</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex flex-col gap-3 px-4 py-4">
          <p className="self-center rounded-full bg-foreground/10 px-3 py-0.5 text-meta text-muted-foreground">今天</p>
          <div className="max-w-[80%] self-start rounded-bubble bg-bubble-her px-4 py-2.5">
            <p className="text-japanese-line">
              <Ja>{line}</Ja>
            </p>
            <p className="text-subtitle text-muted-foreground">{subtitle}</p>
          </div>
          <p className="max-w-[80%] self-end rounded-bubble bg-producer-ink px-4 py-2.5 text-body text-on-producer-ink">
            制作人的话用事务所深蓝墨水。
          </p>
          <span className="self-start text-meta text-muted-foreground">12:48</span>
        </div>
      </div>

      <div className="flex items-center gap-2 px-4 py-3">
        <Input placeholder="用中文或日语说点什么" className="flex-1" />
        <Button variant="her" size="icon-lg" aria-label="发送">
          <SendIcon />
        </Button>
      </div>

      <Specimen label="未读数">
        {/* 未读数还没有组件，第 2、3 波做成项目组件后这里改用它。 */}
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-her-button px-1.5 text-meta text-her-button-fg tabular-nums">
          3
        </span>
      </Specimen>
      <Specimen label="primary 按钮">
        <Button>继续</Button>
        <Button variant="outline">取消</Button>
        <Button variant="destructive">挂断</Button>
      </Specimen>
      <Specimen label="浮层">
        <Dialog>
          <DialogTrigger render={<Button variant="outline" />}>对话框</DialogTrigger>
          <DialogContent container={subtree}>
            <DialogHeader>
              <DialogTitle>会挂断和她的通话</DialogTitle>
              <DialogDescription>离开这段对话会挂断正在进行的通话。</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
              <Button variant="destructive">挂断并离开</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Drawer>
          <DrawerTrigger render={<Button variant="outline" />}>底部面板</DrawerTrigger>
          <DrawerContent container={subtree}>
            <DrawerHeader>
              <DrawerTitle>切换麦克风</DrawerTitle>
              <DrawerDescription>面板也渲染在她的子树里。</DrawerDescription>
            </DrawerHeader>
            <div className="flex flex-col gap-2 p-4">
              <Button>正在使用：内置麦克风</Button>
              <Button variant="outline">耳机麦克风</Button>
            </div>
          </DrawerContent>
        </Drawer>
      </Specimen>
    </section>
  );
}

/** 示例里的一行：左边写这一行展示的是什么。只在这个临时路由里用。 */
function Specimen({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t px-4 py-3">
      <span className="w-24 text-preview text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}
