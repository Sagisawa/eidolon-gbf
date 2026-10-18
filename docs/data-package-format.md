# 数据包的格式

数据包（`GLOSSARY.md`「数据包」）是用户在设置的「数据包」里导出的一个 zip：他自己的数据，带到这个部署或别的部署导入，接着用。它不是备份，也没有加密，是用户自己保管的明文。这份说明给别的部署者和以后的版本看：每个键的意思和版本规则。为什么好感度和礼物不在里面，见 ADR-0025。

现在的格式是**第 1 版**。

## zip 里有什么

固定这几样，别的条目一律当坏包：

| 条目 | 说明 |
| --- | --- |
| `manifest.json` | zip 里的**第一个**条目，不压缩（stored），页面只读文件开头就能拿到它。 |
| `data.json` | 缩进排版、UTF-8、英文键名的数据。 |

## `manifest.json`

```json
{
  "format": 1,
  "exported_at": "2026-10-19T08:00:00.000000+00:00",
  "categories": ["profile"],
  "counts": { "profile": 1 }
}
```

- `format`：整数，这个包的格式版本。
- `exported_at`：导出的时间。
- `categories`：这个包里有哪几类，按 `conversations`、`photos`、`memories`、`profile` 的顺序。导出时没勾的类别不在这里。
- `counts`：每类的条数，键同 `categories`。`profile` 是 1。

## `data.json`

`categories` 里的每一类在这里有一个键，没有的类别就没有这个键。

### `profile`：制作人档案

```json
{
  "profile": {
    "form_of_address": "小林",
    "gender": "female",
    "timezone": "Asia/Tokyo",
    "birthday_month": 2,
    "birthday_day": 29
  }
}
```

- `form_of_address`：她怎么称呼制作人，最多 20 个字；`null` 是按她自己的习惯。
- `gender`：`"male"`、`"female"` 或 `null`（和原作一致，男性）。
- `timezone`：IANA 时区名；`null` 是跟着设备。
- `birthday_month`、`birthday_day`：生日的月和日，没有年；要么都有、要么都是 `null`。2 月 29 日可以。

导入时勾了「制作人档案」就整份覆盖：包里是 `null` 的项，这里也清空、沿用默认。

## 时间

所有时间都是带时区的 ISO 8601。导出成库里的写法：UTC、带微秒，比如 `2026-10-19T08:00:00.000000+00:00`。导入时先解析，再按同一种写法写回；不带时区或解析不了的，整包当坏包。

## 版本规则

- 导入时先看 `manifest.json` 的 `format`：比这个部署支持的新，就拒绝（错误码 `too_new`），请部署者升级；等于或更老的，按那一版的规则读。
- 改格式时 `format` 加一，旧版本的读法保留：新版本能导入所有老格式。
- 坏包一律拒绝（错误码 `broken`）：zip 打不开，条目多了或少了，JSON 不合这份说明，时间解析不了，`categories` 和 `data.json` 里的键对不上。
- 导入要么全部写进去，要么什么也不写。
