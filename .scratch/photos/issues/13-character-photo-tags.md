# 13: 28 位偶像的照片 tag

**What to build:** 每位偶像都有角色 tag 和外貌 tag，发来的照片一眼认得出是她，冷门的也一样。代理先写好 28 位的初稿，用户校对定稿。规格见 `../spec.md`「角色配置」，依据是「原型：外貌一致性」（`05-appearance-prototype.md` 的 Answer）。

这张票只改角色配置的数据。`photo_tag`、`photo_appearance` 两个字段由 14 加进配置格式；14 还没合进来时，这张先把初稿写成一张对照表交给用户校对，14 合进来以后再写进 `characters.toml`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

- [x] 28 位都有角色 tag：Danbooru 写法，比如 `sakuragi mano`，在 V5 Curated 的官方 tag 建议接口里是已知的角色 tag
- [x] 28 位都有外貌 tag，只写发色、发型、瞳色，不写饰物和服装
  - [x] 初稿对着存储桶里默认衣装的缩略图写，参考 Danbooru 共现 tag，但不照搬（团体图里会混进别人的特征）
  - [x] 每个 tag 都用官方 tag 建议接口核对过是已知的（68 条在 V5 Curated 和 V4.5 Curated 上都命中）
- [x] 票 05 定稿的五位（真乃、あさひ、夏葉、智代子、はるき）照用那张票里的写法
- [ ] **人工**：初稿以对照表的形式（角色、缩略图、角色 tag、外貌 tag）交给用户校对，校对后的结果写进 `characters.toml`
- [ ] **可选，人工**：用户想看效果时，用 `.env.novelai` 里的中转按 14 的提示词结构出几张。出图花用户的额度，出之前先报张数、等用户点头
- [x] 后端测试通过（配置能读出全部 28 位的这两项）— 这张没动 `characters.toml`，缺 14 加的两个字段，所以"配置能读出这两项"由 14 的后端测试覆盖；现有 `uv run pytest` 照旧通过

## Comments

**初稿已就绪，等用户校对。** 28 位齐，机器可读的初稿是 `draft.json`，缩略图拼版是 `contact_sheet.png`（编号和下面的表一致）。脚本和说明在 `.scratch/photos/prototype/tags/`（见那里的 `README.md`）。每条 tag 都用官方 tag 建议接口核对过是 V5 Curated 的已知 tag：28 个角色 tag + 40 个外貌 tag，共 68 条。

初稿不是凭记忆写的：`face_sheet.py` 按 alpha 通道裁出每位默认衣装缩略图的头，逐位看发色和发型；只看眼睛的放大图逐位确认瞳色；`danbooru_related.py` 的共现 tag 做交叉参考（不能直接用，团体图会混进别人的特征）；`verify_draft.py` 最后统一核对写法、去重、正好一条瞳色、没混进饰物和服装。

| # | 角色 | 缩略图 | 角色 tag | 外貌 tag | 来历 |
|---|---|---|---|---|---|
| 01 | 櫻木真乃 | `stand/1030010010.png` | `sakuragi mano` | `brown hair, medium hair, brown eyes` | 票 05 定稿 |
| 02 | 風野灯織 | `stand/1030020010.png` | `kazano hiori` | `black hair, long hair, ponytail, blue eyes` | 本次初稿 |
| 03 | 八宮めぐる | `stand/1030030010.png` | `hachimiya meguru` | `blonde hair, long hair, ahoge, low twintails, blue eyes` | 本次初稿 |
| 04 | 月岡恋鐘 | `stand/1030040010.png` | `tsukioka kogane` | `grey hair, long hair, wavy hair, pink eyes` | 本次初稿 |
| 05 | 田中摩美々 | `stand/1030050010.png` | `tanaka mamimi` | `purple hair, long hair, twintails, drill hair, diagonal bangs, purple eyes` | 本次初稿 |
| 06 | 白瀬咲耶 | `stand/1030060010.png` | `shirase sakuya` | `black hair, long hair, high ponytail, yellow eyes` | 本次初稿 |
| 07 | 三峰結華 | `stand/1030070010.png` | `mitsumine yuika` | `black hair, long hair, twintails, blue eyes` | 本次初稿 |
| 08 | 幽谷霧子 | `stand/1030080010.png` | `yukoku kiriko` | `grey hair, long hair, twintails, purple eyes` | 本次初稿 |
| 09 | 浅倉透 | `stand/1030200010.png` | `asakura toru` | `purple hair, short hair, gradient hair, green eyes` | 本次初稿 |
| 10 | 樋口円香 | `stand/1030210010.png` | `higuchi madoka` | `brown hair, short hair, purple eyes` | 本次初稿 |
| 11 | 福丸小糸 | `stand/1030220010.png` | `fukumaru koito` | `dark blue hair, long hair, twintails, purple eyes` | 本次初稿 |
| 12 | 市川雛菜 | `stand/1030230010.png` | `ichikawa hinana` | `light brown hair, long hair, wavy hair, drill hair, brown eyes` | 本次初稿 |
| 13 | 七草にちか | `stand/1030240010.png` | `nanakusa nichika` | `green hair, short hair, green eyes` | 本次初稿 |
| 14 | 緋田美琴 | `stand/1030250010.png` | `aketa mikoto` | `brown hair, short hair, multicolored hair, aqua eyes` | 本次初稿 |
| 15 | 芹沢あさひ | `stand/1030170010.png` | `serizawa asahi` | `grey hair, short hair, blue eyes` | 票 05 定稿 |
| 16 | 黛冬優子 | `stand/1030180010.png` | `mayuzumi fuyuko` | `black hair, long hair, twintails, blunt bangs, red eyes` | 本次初稿 |
| 17 | 和泉愛依 | `stand/1030190010.png` | `izumi mei` | `blonde hair, long hair, gradient hair, brown eyes` | 本次初稿 |
| 18 | 小宮果穂 | `stand/1030090010.png` | `komiya kaho` | `red hair, long hair, ahoge, red eyes` | 本次初稿 |
| 19 | 園田智代子 | `stand/1030100010.png` | `sonoda chiyoko` | `brown hair, double bun, twintails, red eyes` | 票 05 定稿 |
| 20 | 西城樹里 | `stand/1030110010.png` | `saijo juri` | `blonde hair, short hair, purple eyes` | 本次初稿 |
| 21 | 杜野凛世 | `stand/1030120010.png` | `morino rinze` | `blue hair, short hair, hair bun, red eyes` | 本次初稿 |
| 22 | 有栖川夏葉 | `stand/1030130010.png` | `arisugawa natsuha` | `orange hair, long hair, wavy hair, swept bangs, grey eyes` | 票 05 定稿 |
| 23 | 大崎甘奈 | `stand/1030140010.png` | `osaki amana` | `brown hair, long hair, swept bangs, brown eyes` | 本次初稿 |
| 24 | 大崎甜花 | `stand/1030150010.png` | `osaki tenka` | `brown hair, long hair, brown eyes` | 本次初稿 |
| 25 | 桑山千雪 | `stand/1030160010.png` | `kuwayama chiyuki` | `brown hair, long hair, braided ponytail, ahoge, brown eyes` | 本次初稿 |
| 26 | 斑鳩ルカ | `stand/1030260010.png` | `ikaruga luca` | `black hair, medium hair, two-tone hair, yellow eyes` | 本次初稿 |
| 27 | 鈴木羽那 | `stand/1030270010.png` | `suzuki hana` | `light blue hair, long hair, purple eyes` | 本次初稿 |
| 28 | 郁田はるき | `stand/1030280010.png` | `ikuta haruki` | `brown hair, short hair, yellow eyes` | 票 05 定稿 |

**要用户做的**：对着 `contact_sheet.png` 逐行看，重点确认两类：

- **瞳色**：缩略图里眼睛只有十几个像素，高光容易带偏。拿不准的主要是恋鐘（`pink eyes`，看着偏洋红）、甘奈和甜花（`brown eyes`，偏琥珀）、樹里、凛世。
- **发色偏哪一档**：恋鐘现在是 `grey hair`（灰棕），円香、千雪、美琴是 `brown hair`（美琴带 `multicolored hair`）。觉得该往深或往浅挪一档就直接说改成哪个。

其余按 Danbooru 共现和缩略图都对得上，包括最冷门的はるき（票 05 定稿）。改 `draft.json` 的 `photo_appearance` 后重跑 `python verify_draft.py` 就能确认新写的 tag 还是已知 tag。

角色 tag 一律是 `name_romaji` 转小写，28 位都在 V5 Curated 和 V4.5 Curated 的 tag 建议接口里是已知角色 tag。规格要求另存一项而不是从 `name_romaji` 推，因为新角色不一定对得上 Danbooru 的写法；这一版恰好都能对上。

出图可选，等 14 合进来以后再说；出之前先报张数、等用户点头。
