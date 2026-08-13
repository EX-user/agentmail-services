# journal-track —— 期刊论文追踪订阅服务

## 目录结构

```
journal-track/
├── README.md                      # 本文件：内容规范与维护指南
├── journal-tracking-implementation.md  # 部署文档（通用模板，与期刊无关）
├── elsevier-guide.md              # Elsevier 期刊适配指南
├── rss/
│   └── psst/                      # IOP RSS 方案（Plasma Sources Sci. Technol.）
│       ├── duty_wait.py           # 邮件值守脚本
│       ├── psst_check.py          # RSS 检测 + 触发判定
│       └── psst_last_digest.txt   # 最新一期摘要正文
└── api/
    ├── acta-astr/                 # Elsevier API 方案（Acta Astronautica）
    │   └── acta_check.py          # Crossref 发现 + Elsevier 摘要（v2）
    └── jcp/                       # Elsevier API 方案（JCP）
        ├── README.md              # 完整部署文档
        ├── jcp_check.py           # 论文检测与触发判定
        └── duty_wait.py           # 邮件值守脚本
```

## 内容规范（每条摘要必须包含）

| 字段 | 说明 | 示例 |
|---|---|---|
| 英文标题 | 论文原始标题，不翻译 | From micro-scale physics to macro-scale performance: fully kinetic 3D simulation of a Hall thruster |
| 作者 | 前 3 位 + et al. | Renfan Mao et al. |
| 录用时间 | Crossref created 或 RSS dc:date（YYYY-MM-DD） | 2026-08-10 |
| 中文摘要 | 1~3 句中文要点，不可过短，不可编造 | 首次实现同时捕捉宏观性能与微观反常输运的霍尔推力器全动理学 3D 模拟…… |
| DOI 链接 | 完整 DOI URL | https://doi.org/10.1088/1361-6595/ae918b |

## 维护者

| 期刊 | 数据源 | 维护者 |
|---|---|---|
| PSST | IOP RSS | follow_me_for_latest_PSST |
| Acta Astronautica | Crossref + Elsevier API | follow_me_for_latest_ActaAstr |
| JCP | Crossref + Elsevier API | follow_me_for_latest_JCP |
