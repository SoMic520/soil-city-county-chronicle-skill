# 检查、状态与交付

技能/检查器修订标识：2026-09-07-r4；这是工具版本，不是土壤普查规范版本。JSON检查结果带tool_version，归档时连同输入台账和人工检查记录保留。

## 模板及单一记录源

复制assets/project或执行init；目录必须是新目录，以防覆盖用户记录。CSV用UTF-8，脚本兼容UTF-8 BOM；多个ID用`|`分隔。保留字符串型编号和原始小数，不让电子表格自动转为日期/科学计数。

| 文件 | 用途与填写规则 |
|---|---|
| project.json | 行政对象、市县级与确认依据、项目范围、规范锁定、专题四态、六章状态、人工终检；不是地方事实库 |
| sources.csv | 来源主表：source_id唯一；path为实际文件/URL或明确确认记录；version不可空；status为catalogued/extracted/verified/rejected；qc为confirmed/unknown/not_applicable及依据 |
| evidence.csv | 主张主表：evidence_id、section_id、原主张、kind、source_ids、locator、metric_ids、comparison_id、quantitative_comparison、status；status=draft/verified/withheld；可选depends_on记录上游E ID |
| metrics.csv | 指标主表：原值value、单位、scope、population、时期、土层、方法、统计量、有效n、分母说明、精度、source_id和locator；不适用字段写NA并在定义说明 |
| comparisons.csv | 八项历史可比性检查及依据，status=verified/incomparable/unknown；只有全部same/harmonized且有处理依据才能verified；basis定位基期、现期指标及比较关系 |
| conflicts.csv | 冲突范围与来源、状态open/resolved及裁决；解决不能只把状态改成resolved |
| figures.csv | 图表/照片来源、文件、位置、关联主张、清晰度、标注与公开权限；从正文题注映射，不能只存图片。可选kind：map/table/profile_photo/landscape_photo/other，三普土种照片必须填明确角色 |
| checks.json | 本次计算的结果、输入ID与复核记录；内置sum、ratio、weighted_mean及外部计算manual记录。已有报告统计量不强制重算，不为未发生的运算凑记录 |
| requirements.csv | 必需内容映射：requirement_id、章/专题、内容/图件/编辑类别、要求及依据、状态open/covered/not_applicable、E/F ID、成稿定位、例外处置依据；跨章复用主张填写reuse_basis说明实际支撑关系 |
| soil_types.csv | 按确认清单登记`record_level`；市级逐土属、县级逐土种记录分类、名称、来源、主张和正文位置，县级另核剖面/历史记述与照片；与soil_inventory核对 |
| gaps.csv | 具体缺口及影响章、对应要求、优先查哪份已有报告、最小补件、责任方、open/resolved、处理结果和依据 |
| length-plan.json | 项目与模板层级、模板身份/哈希/实测值、同口径结构清单、六章目标/上下限/实际值、正式例外和锁定状态；按length执行，不是法定全国字数表 |
| layout.json | schema版本3；level_profile记录市县级与适用导引，styles/execution记录三普基准，acceptance_requirements记录已采纳要求，逐字段例外、局部保护对象和12项实际格式检查分开登记 |
| section-contract.md / soil-type-card.md | 每个章节或土种复制后填；这是编辑工作文件，不能原样混进志稿 |
| review.md | 内容、数据、渲染页范围、问题及回归检查证据 |

sources的verified表示本次已读并核对可用范围，不自动等于原数据已经阶段验收；qc另记。全志正式交付需要根据采用规范检查相关三普源的阶段验收依据。历史文献/地方背景等无需三普验收可标not_applicable，不能给未核验三普检测源随意标NA。

metrics的value仅存可运算十进制数值，暂缺可空但不能被已核对主张使用；定性等级名放evidence或原始分类表。scope是预先确认的共同计算范围键（区域、时期、地类/土层等），population描述该行的具体组别；同scope不是自动可比证明。相同单位而方法/土层不同不得赋同一个计算范围键。核算前另查类互斥完整、权重意义和可比性。

checks.json示例（合成ID，需要在metrics登记对应量；容差由显示精度和算法确定，不照抄）：

```json
[
  {"type":"ratio", "numerator":"M_low", "denominator":"M_total", "result":"M_percent", "tolerance":"0.05"},
  {"type":"sum", "parts":["M_a","M_b"], "result":"M_sum", "tolerance":"0.5"},
  {"type":"weighted_mean", "pairs":[{"value":"M_mean_a","weight":"M_n_a"},{"value":"M_mean_b","weight":"M_n_b"}], "result":"M_mean", "tolerance":"0.05"}
]
```

ratio仅用于非负分子不大于正分母的组成占比，结果单位为%；不是相对增长率计算器。sum不检查类别互斥性；weighted_mean不检查权重是否正确代表样本/面积，因此都需要人工方法审查。

同一结果ID只允许一个计算定义；输入不能与结果相同、不得成环。sum不能重复同一输入，weighted_mean不能重复同一分组值。检查器沿“在用结果→中间结果→全部输入”追查来源状态及终稿质量状态，不能只给计算结果挂一个合格来源。

内置算式核对显式period、depth、method是否矛盾。确已统一口径的，先登记统一后的指标及依据；确需保留不同原始标签时，算式可填harmonized_dimensions列表和harmonization_basis，定位实际统一过程。这只是供复核的记录，不会自动转换单位/土层、证明方法等价或消除真实性问题。method记录测定/汇总口径，不把“sum公式”混填成另一种测定方法。

未内置的计算（例如按已确认方法求储量或变化率），可由适用工具完成并复核后登记manual，示例如下。脚本仅检查依赖、原值和复核记录存在，并在notes明确“不重算”；不能把其通过称为数值复算通过。未实际复核，不填review_locator，也不能改kind逃避检查。

```json
{"type":"manual", "inputs":["M_base","M_current"], "result":"M_change", "formula":"(M_current-M_base)/M_base*100", "method_basis":"填写适用方法、可比性ID及非零基期依据", "review_locator":"填写实际计算底稿/脚本版本与复核位置"}
```

## 覆盖、缺口和旧项目升级

requirements的基础映射项是本技能按市县级六章共有内容归纳的工作清单，不是官方发布的CSV或新的全国验收表。层级专属要求按levels和适用导引追加，不删除基本内容映射来制造完整。covered必须定位正文，并关联对应主张或图件；not_applicable必须有适用依据和处置依据，不能因材料缺失就勾选省略。

soil_inventory.expected_ids来自实际已核对的完整分类清单，不由已经写完的条目倒推。市级土壤志以土属ID核对正文覆盖，record_level=`soil_genus`、profile_kind=`not_required`，逐土种与剖面转入独立土种志核验；县级以土种ID核对，record_level=`soil_species`，profile_kind为third_survey、historical_profile、historical_description或missing。县级三普剖面需至少分别关联剖面照和景观照；figures.kind分别登记profile_photo、landscape_photo。脚本检查层级、照片ID数量、角色和关联；分类清单真实身份、全部上位单元记述和市级跨县一致性仍须人工核对。

gaps中的影响章用`|`分隔，全志问题用all；责任方尚未明确时如实写“待指定”，不能虚构负责人。open只限制受影响内容送审/定稿；resolved必须记录处理结果和依据。requirements覆盖定位、gaps缺口处置、section-contract写作策略各有职责，不把三份表抄成三份互相矛盾的数据源。

旧项目不重新init、不覆盖原台账。先备份，把缺少的requirements.csv、soil_types.csv、gaps.csv和length-plan.json从新模板补入；在project.json补建administrative_level与soil_inventory，并按已有材料逐项填实。旧evidence.csv暂缺depends_on、figures.csv暂缺kind、requirements.csv暂缺reuse_basis列仍可读取，在需要相应功能时追加该列。旧项目可继续局部起草，但正式终稿检查会要求补齐层级、覆盖台账和篇幅契约。任何升级都不自动把记录置为verified/covered/done/locked。

project.sections中status支持materials、drafting、review_ready、final，required_claim_ids记录该节必须支持的主张；section.topic_id仅用于条件专题节，不把六个基本章设成可随意取消的专题。topic的依据可为适用文件/任务、报告记录或明确用户确认；若存在正式要求冲突，必须登记conflicts。

脚本不会读取并理解报告、不会验证CSV中的主张真假，也不从一个来源合格推导整章资料完备。它检查登记是否有缺项、悬空引用或已知状态矛盾；“verified”“done”只能在实际人工检查后填写，不能为通过脚本批量置位。

## 篇幅契约与落实检查

具体计量、折算和阈值完整执行[length](length.md)。项目与模板必须同为市级或同为县级，且使用同一个measurement_version；模板各章值不能手填估计，须保存只读计量输出。第三至六章还须标出模板固定叙述范围和结构单元清单，登记模板结构数量、本项目同口径数量和定位。模板固定叙述字符数应由实际标注区间汇总，不使用无来源的经验占比。

普通项目控制线：第一、二章目标在模板±15%；第三至六章按结构密度折算且目标在模板±30%；六章目标合计在模板±20%；各章实际在目标±15%；全志实际在总目标±10%且在模板合计±25%。达到下限不代表内容充分，超过上限也不能机械删掉土种、必要事实或证据。正式/书面结构性例外必须换算为统一有效字符口径并登记来源、定位和确认人。

`check`在有length-plan时检查计划；旧项目缺该文件时只提示，不阻断局部资料工作。`check --final`强制检查模板身份、哈希、结构依据、六章目标和实际、总量、锁定状态及阈值。脚本不验证结构标注是否真实，也不把篇幅通过当作写作质量通过；review.md须记录计量输出、最终DOCX哈希和人工复核。

## 排版计划与落实检查

字体字号、章标题、缩进、粗体、页码、目录、题注、图表空行、表宽及分节逐项按[layout](layout.md)执行，创建/修改DOCX前必须完整读取。严格使用适用导引确认的“第一章—一、—（一）—1.—（1）”字体层级，不因引入章标题而把“一、”仍设Heading 1，也不把目录深度与正文可用标题层级混为一谈。

`layout-check <layout.json>`检查配置值是否偏离已采纳基准、有无缺字段/未知字段/无效例外；`--final`另要求12项格式检查有实际证据，目标软件、目录语义范围、表内中文字体和独立页眉/页脚距离已记录。全志`check --final`复用同一检查。只读计划检查不检查DOCX字体继承、实际空行或页面；需把结果与review.md中的真实样式/对象/页面证据对应。

不能只为通过检查修改基准模板。全局例外必须同时填写实际值及path/value/scope=global/basis/confirmed_by/confirmed=true；横向页、附图或用户保护对象用局部保护清单，不将其边距回写整个正文。各字段说明和支持范围见layout第8节。

toc_semantic_levels用有序角色数组，不再收自由说明文字；默认只可["chapter"]或["chapter","level_1"]，空数组仅用于未完成计划。实际目录收录必须与选择一致，不能一边记录二级一边实际生成五级。任何正式地方深度例外按layout登记并审查，检查器不判断该依据真实性。

旧排版配置没有layout_schema_version=3时，资料整理可继续，但排版终稿检查要求先备份并升级。不得直接覆盖已有真实项目设置；逐项迁入新版，并核对差异。新模板的所有format_checks保持pending，不生成未经实际打开/渲染的passed记录。

## 人工验收门槛

| 门槛 | 必须看到的证据 | 失败处理 |
|---|---|---|
| 来源与范围 | 规范采纳、实际读取位置、使用限制和专题状态；无未经许可外传 | 补具体定位/确认；限制受影响结论 |
| 覆盖 | 六章契约、分类清单对逐种记述、应有历史内容、适用评价和附图 | 指明缺哪项，不用空话填章节 |
| 数量与篇幅 | 关键值回查、单位/分母/有效n、合计及舍入、正文表图一致；篇幅模板/结构清单/六章实测同口径 | 原因定位；有依据才更正；不靠空话扩写或删必需内容 |
| 历史与解释 | 八项H检查、因果用语符合证据、建议回扣问题 | 改为分期记载或受限解释，不报确定变化 |
| 内容 | 分类/剖面/照片一致，术语稳定，引用真实，段落无操作提示 | 专业修订并回归相关条目 |
| 文件与版面 | 源文件保护、实际更新字段、目标软件重开、同版本逐页渲染记录 | 未完成则仅交工作稿/结构检查稿 |
| 交付一致性 | 正文、数据、表图、原图、版本清单对应，已知重大问题关闭 | 不称定稿；交影响及最小下一步 |

## 静态检查能力边界

`check`：校验基本表结构/ID、在用主张来源、计算指标及依赖、定量历史比较的两期指标和八项状态、冲突对象与裁决、专题/章节状态、必需内容、土种覆盖、具体缺口和已有篇幅计划；检查已声明的内置算式或manual复核记录。上游E撤回后，仍标verified的下游E会报告状态矛盾；不自动改写正文或重新核实事实。阶段状态不足时输出“记录未具备相应门槛”，允许其他章节推进。`--final`要求六章final、基础映射与完整土种清单覆盖、条件专题有明确处置、没有未决冲突/在用待核主张、篇幅契约锁定且实测合格、规范和人工检查记录完成。0只代表这些登记未发现阻断问题；无法自动识别所有正文中未登记的数值或遗漏事实。

`docx-check`：只读ZIP/XML，检查Content Types与officeDocument包入口、内部关系目标存在性及常见r:id/embed/link引用、书签ID/名称冲突及起止顺序、REF/PAGEREF常见目标、复杂域配对/重复分隔符和常见错误文字；允许合法重叠书签和嵌套域，列外部关系但不联网/执行。当前面向常见Transitional DOCX、主部件word/document.xml；加密、Strict OOXML、宏格式、其他主部件布局或解析失败可能返回2，表示输入/支持范围问题，不能据此宣告文件必然损坏。不自动修复。对跨部件复杂域、内容控件、旧式域、修订语义、完整OOXMLschema、图片视觉和字体继承不作完备保证。无报错仍需实际打开与渲染。

## 回归和停止条件

新写：证据→正文/表图；修订：原稿→授权改动→接受后逻辑文本→最终渲染。每轮修正记录错误原因、修复位置和验证动作。不要靠增加“检查一遍”字样替代证据。

若关键源缺失、责任方裁决未到或用户必须决定冲突：完成不依赖它的工作，准确报告具体影响和请求；不无限润色已通过内容。正式完成是已满足声明的交付范围且无已知重大缺陷，不是保证所有未来规范和软件均无问题。

最小交付包：可编辑志稿、按需求的PDF/附图册、资料及引用索引、数据/图表锁定记录、审查与版面记录、未解决事项和限制。源原图留存；是否交出原始敏感数据依权限。通用技能包交付不包含真实市县级资料或超大样稿。
