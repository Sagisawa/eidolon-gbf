"use client";

// 临时示例路由（shadcn-redesign 共用件波，清理波删掉）：用户侧的新版共用件和 shadcn 组件都在这里摆一遍，
// 没有任何页面在用它们（验收清单第 4 行）。浅色、深色跟随系统，页首的「强制深色」把整页切成深色。
// 只有后台用的通用件（StatusDot、Timestamp、MetadataList、NumberInput）在 /preview/admin。
// 文案只给开发者看，不进 i18n。
import { DarkToggle } from "@/app/preview/DarkToggle";
import { AppLink } from "@/components/app/AppLink";
import { FailureNotice } from "@/components/app/FailureNotice";
import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { PageShell } from "@/components/app/PageShell";
import { SettingsSection } from "@/components/app/SettingsSection";
import { SubpageHeader } from "@/components/app/SubpageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Message, MessageContent } from "@/components/ui/message";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { herVars } from "@/theme/herVars";
import { MoreIcon, TrashIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

export default function SharedPreviewPage() {
  return (
    <PageShell
      header={
        <SubpageHeader
          title="示例：新版共用件"
          backHref="/preview"
          end={
            <>
              <DarkToggle />
              <Button variant="ghost" size="icon-lg" aria-label="末端操作">
                <MoreIcon />
              </Button>
            </>
          }
        />
      }
      footer={
        <p className="text-meta text-muted-foreground">
          页脚：PageShell 的 footer，固定在底部。<AppLink href="/preview/admin">后台共用件的示例</AppLink>
        </p>
      }
    >
      <SettingsSection title="SettingsSection" description="设置页的一节：标题、说明、内容，下沿一条细分隔线，不套卡片。">
        <p className="text-body">这一节的内容。</p>
      </SettingsSection>

      <SettingsSection title="FailureNotice" description="失败提示；没登录时右边有「去登录」。">
        <FailureNotice failure={{ message: "保存失败：网络连不上。", signedOut: false }} />
        <FailureNotice failure={{ message: "登录已经过期，请重新登录。", signedOut: true }} />
      </SettingsSection>

      <SettingsSection title="AppLink">
        <p className="text-body">
          句中的链接画下划线，例如<AppLink href="/privacy">隐私政策</AppLink>和<AppLink href="/terms">使用条款</AppLink>。
        </p>
        <AppLink href="/preview" isStandalone>
          独立成行的链接（悬停才有下划线）
        </AppLink>
      </SettingsSection>

      <SettingsSection
        title="MarkedAvatar"
        description="sm 24px、bubble 36px、lg 48px、list 56px；没有图时显示第一个字。无描边。"
      >
        <div className="flex items-end gap-4">
          <MarkedAvatar name="櫻木真乃" size="sm" />
          <MarkedAvatar name="八宮めぐる" size="bubble" />
          <MarkedAvatar name="風野灯織" size="lg" />
          <MarkedAvatar name="月岡恋鐘" size="list" />
        </div>
      </SettingsSection>

      <SettingsSection title="Field">
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="sample-name">称呼</FieldLabel>
            <Input id="sample-name" placeholder="制作人" />
            <FieldDescription>她会这样叫你。</FieldDescription>
          </Field>
        </FieldGroup>
      </SettingsSection>

      <SettingsSection title="useMediaQuery">
        <MediaSample />
      </SettingsSection>

      <SettingsSection title="Button" description="destructive 是挂断红实底、白字。">
        <div className="flex flex-wrap gap-2">
          <Button>default</Button>
          <Button variant="outline">outline</Button>
          <Button variant="secondary">secondary</Button>
          <Button variant="ghost">ghost</Button>
          <Button variant="destructive">destructive</Button>
          <Button variant="link">link</Button>
        </div>
      </SettingsSection>

      <SettingsSection title="Badge">
        <div className="flex flex-wrap gap-2">
          <Badge variant="destructive">已封禁</Badge>
          <Badge variant="secondary">管理者</Badge>
          <Badge variant="outline">自带密钥：语音识别</Badge>
          <Badge variant="outline">单独限额：每天 30 分钟</Badge>
        </div>
      </SettingsSection>

      <SettingsSection title="Alert、Empty">
        <Alert>
          <AlertTitle>已保存</AlertTitle>
          <AlertDescription>下一通电话起生效。</AlertDescription>
        </Alert>
        <Empty>
          <EmptyHeader>
            <EmptyTitle>她还没有记住什么</EmptyTitle>
            <EmptyDescription>聊得多了，她会记住你告诉她的事。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </SettingsSection>

      <SettingsSection title="浮层" description="AlertDialog 的执行键是挂断红；深色模式下浮层比页面高一层、带边线。">
        <div className="flex flex-wrap gap-2">
          <AlertDialog>
            <AlertDialogTrigger render={<Button variant="outline" />}>
              <TrashIcon />
              删除账号
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>删除这个账号？</AlertDialogTitle>
                <AlertDialogDescription>对话、记忆和设置都会删掉，不能恢复。</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction variant="destructive">删除</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Sheet>
            <SheetTrigger render={<Button variant="outline" />}>底部 Sheet</SheetTrigger>
            <SheetContent side="bottom">
              <SheetHeader>
                <SheetTitle>切换麦克风</SheetTitle>
                <SheetDescription>当前的一项铺中性的 bg-muted。</SheetDescription>
              </SheetHeader>
              <div className="flex flex-col px-4 pb-4">
                <div className="flex items-center justify-between rounded-lg bg-muted px-3 py-2.5 text-body">
                  内置麦克风<span className="text-meta text-muted-foreground">正在使用</span>
                </div>
                <div className="px-3 py-2.5 text-body">耳机麦克风</div>
              </div>
            </SheetContent>
          </Sheet>
          <Popover>
            <PopoverTrigger render={<Button variant="outline" />}>Popover</PopoverTrigger>
            <PopoverContent>
              <PopoverHeader>
                <PopoverTitle>Popover</PopoverTitle>
                <PopoverDescription>更多菜单也可以用它。</PopoverDescription>
              </PopoverHeader>
            </PopoverContent>
          </Popover>
        </div>
      </SettingsSection>

      <SettingsSection title="Tabs、ToggleGroup">
        <Tabs defaultValue="24h">
          <TabsList>
            <TabsTrigger value="24h">24 小时</TabsTrigger>
            <TabsTrigger value="7d">7 天</TabsTrigger>
            <TabsTrigger value="30d">30 天</TabsTrigger>
            <TabsTrigger value="90d">90 天</TabsTrigger>
          </TabsList>
          <TabsContent value="24h" className="text-body text-muted-foreground">
            24 小时内的数字。
          </TabsContent>
          <TabsContent value="7d" className="text-body text-muted-foreground">
            7 天内的数字。
          </TabsContent>
        </Tabs>
        <ToggleGroup defaultValue={["casual"]} variant="outline">
          <ToggleGroupItem value="casual">私服</ToggleGroupItem>
          <ToggleGroupItem value="stage">演出</ToggleGroupItem>
        </ToggleGroup>
      </SettingsSection>

      <SettingsSection
        title="Resizable"
        description="按像素调宽：默认 160px，120–240px（对话列表在第 3 波用 320、240–480px）。"
      >
        <ResizablePanelGroup orientation="horizontal" className="min-h-32 rounded-lg border">
          <ResizablePanel defaultSize="160px" minSize="120px" maxSize="240px">
            <div className="p-3 text-body">列表</div>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel>
            <div className="p-3 text-body">对话</div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </SettingsSection>

      <SettingsSection
        title="Message、Bubble（未改样式）"
        description="官方聊天组件原样摆在她的子树里；气泡的形状和颜色在第 3 波按 DESIGN.md 改。"
      >
        <div style={herVars("#ffbad6")} className="flex flex-col gap-2 rounded-lg bg-her-wall p-4">
          <Message>
            <MessageContent>
              <Bubble variant="outline">
                <BubbleContent>
                  <Ja>ほわっ……そうだったんですか。</Ja>
                </BubbleContent>
              </Bubble>
            </MessageContent>
          </Message>
          <Message align="end">
            <MessageContent>
              <Bubble>
                <BubbleContent>是啊。</BubbleContent>
              </Bubble>
            </MessageContent>
          </Message>
        </div>
      </SettingsSection>
    </PageShell>
  );
}

function MediaSample() {
  const wide = useMediaQuery("(min-width: 768px)", true);
  return (
    <p className="text-body">
      <span className="text-muted-foreground">(min-width: 768px)：</span>
      {wide ? "成立：电脑宽度" : "不成立：手机宽度"}
    </p>
  );
}
