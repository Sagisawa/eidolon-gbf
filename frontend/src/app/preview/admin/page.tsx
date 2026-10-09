"use client";

// 临时示例路由（shadcn-redesign 共用件波，清理波删掉）：后台的新版外壳（Sidebar）、AdminPage、统计卡，
// 以及装在 Card 里的表格、定义列表、表单（验收清单第 4 行）。后台的真实页面在第 4 波才换上这套外壳。
// 文案只给开发者看，不进 i18n。
import { useState } from "react";

import { DarkToggle } from "@/app/preview/DarkToggle";
import { AppLink } from "@/components/app/AppLink";
import { AdminPage } from "@/components/app/admin/AdminPage";
import { AdminShell } from "@/components/app/admin/AdminShell";
import { StatTile } from "@/components/app/admin/StatTile";
import { MetadataList, MetadataListItem } from "@/components/app/admin/MetadataList";
import { NumberInput } from "@/components/app/admin/NumberInput";
import { StatusDot } from "@/components/app/admin/StatusDot";
import { Timestamp } from "@/components/app/admin/Timestamp";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const HOUR = 60 * 60 * 1000;

const SERVICES = [
  { name: "语音识别", calls: "1,204", errors: "38", status: "warning" as const, label: "出错偏多" },
  { name: "语音合成", calls: "1,198", errors: "402", status: "error" as const, label: "大量出错" },
  { name: "对话模型", calls: "2,310", errors: "0", status: null, label: "正常" },
];

export default function AdminPreviewPage() {
  const [range, setRange] = useState("24h");
  return (
    <AdminShell name="Sallyn" trail="示例">
      <AdminPage
        width="wide"
        title="示例：后台共用件"
        intro="AdminShell（Sidebar 外壳、48px 页首、面包屑）、AdminPage（限宽内容列、页首）、统计卡，以及装在 Card 里的表格、定义列表和表单。"
        above={
          <AppLink href="/preview/shared" isStandalone>
            用户侧共用件的示例
          </AppLink>
        }
        end={
          <div className="flex items-center gap-2">
            <DarkToggle />
            <Tabs value={range} onValueChange={(value) => setRange(String(value))}>
            <TabsList>
              <TabsTrigger value="24h">24 小时</TabsTrigger>
              <TabsTrigger value="7d">7 天</TabsTrigger>
              <TabsTrigger value="30d">30 天</TabsTrigger>
              <TabsTrigger value="90d">90 天</TabsTrigger>
            </TabsList>
            </Tabs>
          </div>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[1fr_5fr]">
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">此刻</p>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <StatTile label="正在通话" value="3" />
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{range} 内</p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <StatTile label="活跃用户" value="128" />
              <StatTile label="通话" value="1,042" note="平均 6 分钟" />
              <StatTile label="消息" value="8,377" />
              <StatTile label="新用户" value="12" />
              <StatTile label="花费" value="$41.20" note="按单价估算" />
            </div>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>服务健康</CardTitle>
              <CardDescription>只给出问题的项加点。</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>服务</TableHead>
                    <TableHead className="text-right">调用</TableHead>
                    <TableHead className="text-right">出错</TableHead>
                    <TableHead>状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {SERVICES.map((service) => (
                    <TableRow key={service.name}>
                      <TableCell>{service.name}</TableCell>
                      <TableCell className="text-right tabular-nums">{service.calls}</TableCell>
                      <TableCell className="text-right tabular-nums">{service.errors}</TableCell>
                      <TableCell>
                        {service.status ? (
                          <span className="inline-flex items-center gap-2 font-medium">
                            <StatusDot variant={service.status} />
                            {service.label}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{service.label}</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>资料</CardTitle>
              <CardDescription>两列定义列表；单独限额的按钮在 CardFooter。</CardDescription>
              <CardAction>
                <Button variant="outline" size="sm">
                  封禁
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <MetadataList>
                <MetadataListItem label="状态">
                  <span className="flex flex-wrap gap-1.5">
                    <Badge variant="destructive">已封禁</Badge>
                    <Badge variant="secondary">管理者</Badge>
                    <Badge variant="outline">自带密钥：语音识别</Badge>
                  </span>
                </MetadataListItem>
                <MetadataListItem label="注册于">
                  <Timestamp value="2026-03-05T09:07:00+08:00" />
                </MetadataListItem>
                <MetadataListItem label="最近活动">
                  <Timestamp value={new Date(Date.now() - 3 * HOUR)} format="auto" />
                </MetadataListItem>
                <MetadataListItem label="用户 ID">
                  <span className="font-mono">8f2c1e9a-41d7-4c4b-9a55-0b8e2d7f6c13</span>
                </MetadataListItem>
              </MetadataList>
            </CardContent>
            <CardFooter>
              <Button variant="outline" size="sm">
                设置单独限额
              </Button>
            </CardFooter>
          </Card>
        </div>

        <LimitCard />
      </AdminPage>
    </AdminShell>
  );
}

function LimitCard() {
  const [value, setValue] = useState<number | null>(30);
  return (
    <Card className="max-w-240">
      <CardHeader>
        <CardTitle>每天的通话时长</CardTitle>
        <Badge variant="secondary" className="w-fit">
          已被后台覆盖
        </Badge>
        <CardAction>
          <Button variant="outline" size="sm">
            修改
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          <Field>
            <FieldLabel>每位用户每天（分钟）</FieldLabel>
            <NumberInput label="每位用户每天（分钟）" value={value} onChange={setValue} min={1} isIntegerOnly />
            <FieldDescription>.env 里是 60。</FieldDescription>
          </Field>
          <div className="flex gap-2">
            <Button>试调并保存</Button>
            <Button variant="ghost">取消</Button>
          </div>
        </FieldGroup>
      </CardContent>
      <CardFooter>
        <Button variant="ghost" size="sm">
          恢复成 .env 的值
        </Button>
      </CardFooter>
    </Card>
  );
}
