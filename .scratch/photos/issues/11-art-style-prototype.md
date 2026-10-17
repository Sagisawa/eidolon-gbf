# 11: 原型：画风

Type: prototype
Status: open
Blocked by: 05

## Question

照片用什么画风。画风由服务器写死，她写的标签里不能出现画风或画师 tag（见「拍板：怎么触发、谁来写提示词」）。在「原型：外貌一致性」选定的外貌做法和模型上，对比几种画风：

- 不加任何画风 tag 的默认画风，作为对照；
- 画师 tag：重点比这一项，看选哪几位、单个还是几个组合、各自配多大权重；
- 往原作卡面的感觉靠（例如 `official art` 这类 tag）；
- 往手机照片的真实感靠（半写实、手机照片的质感）。

每种画风都要看换了以后还像不像她（画师 tag 会改变脸型），以及自拍、别人帮她拍、室内、外景各是什么样。还要回答：用真人画师的名字作画风，和 ADR-0003 对粉丝衍生图的立场有没有冲突，要不要修订那条 ADR。结论决定服务器拼进提示词的画风部分写什么，以及同一部署里所有角色是不是共用一种画风。

生成的图不进仓库，也不进存储桶；对比页放在 `prototype/photos-art-style` 分支，图片放在仓库外的目录。只出全年龄的图。

## Comments

- 「调研：NovelAI 提示词写法」（`research/novelai-prompting` 分支的 `.scratch/photos/research/novelai-prompting.md`）建议不用 `photo (medium)`、`photo background`，因为它们会把画风拉向实拍或拼贴；对比真实感时注意这一点。
- 「原型：外貌一致性」已定：模型用 V5 Curated，前缀是角色 tag 加外貌 tag（发色、发型、瞳色），五位的外貌 tag 写在那张票的 Answer 里。生成脚本可以照着改：`prototype/photos-appearance` 分支的 `.scratch/photos/prototype/appearance/gen.py`，同一个种子能和那次的图对照。**每张都扣用户中转的额度，开跑前先跟用户说要出几张、等他点头**；那次计划 100 张，用户嫌多，叫停在第 34 张。
